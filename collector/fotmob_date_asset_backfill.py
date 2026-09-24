"""Asset-only FotMob date-board reconciliation for public football events.

This job never creates fixtures and never changes scores, statuses, names, or
kickoff times. It fills only blank participant/competition artwork when one
unique FotMob match agrees on both participants and kickoff.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_fotmob import _load_boards, board_dates, match_to_event
from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.list_extra import extra_for_list, store_list_extra
from collector.models import SportsEvent
from collector.participant_alias import resolve_folded
from collector.util import dump_json, load_json, parse_datetime

RUN_INTERVAL_S = 6 * 3600
PAST_DAYS = 7
FUTURE_DAYS = 14
KICKOFF_TOLERANCE_SECONDS = 3 * 3600

_next_run_at = 0.0


def _has_logo(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return bool(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or side.get("logo_url")
        or side.get("logoUrl")
    )


def _stamp(value: Any) -> Optional[datetime]:
    stamp = parse_datetime(value)
    if stamp is None:
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp


def _name(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    return str(side.get("display_name") or side.get("name") or "").strip()


def _pair_key(db: Session, home: Any, away: Any) -> Optional[Tuple[str, str]]:
    left = resolve_folded(db, "football", _name(home))
    right = resolve_folded(db, "football", _name(away))
    if not left or not right or left == right:
        return None
    return tuple(sorted((left, right)))


def _merge_side(target: Any, source: Any) -> Tuple[Any, bool]:
    if not isinstance(target, dict) or not isinstance(source, dict):
        return target, False
    logo = str(source.get("logo") or "").strip()
    if not logo or _has_logo(target):
        return target, False
    merged = dict(target)
    merged["logo"] = logo
    merged.setdefault("logo_source", "fotmob-date-board")
    return merged, True


def run_if_due(
    db: Session,
    *,
    getter=None,
    past_days: int = PAST_DAYS,
    future_days: int = FUTURE_DAYS,
) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now_mono = time.monotonic()
    if now_mono < _next_run_at:
        return None
    _next_run_at = now_mono + RUN_INTERVAL_S

    getter = getter or fetch_url
    dates = board_dates(past_days=past_days, future_days=future_days)
    try:
        matches = _load_boards(getter, dates=dates)
    except Exception:
        matches = []

    indexed: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    parsed_matches = 0
    for match in matches:
        parsed = match_to_event(match, "")
        if not parsed:
            continue
        key = _pair_key(db, parsed.get("home"), parsed.get("away"))
        stamp = _stamp(parsed.get("start_time"))
        if not key or stamp is None:
            continue
        parsed["_asset_stamp"] = stamp
        parsed["_asset_home_key"] = resolve_folded(db, "football", _name(parsed.get("home")))
        parsed["_asset_away_key"] = resolve_folded(db, "football", _name(parsed.get("away")))
        indexed[key].append(parsed)
        parsed_matches += 1

    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=past_days + 1)
    last_day = today + timedelta(days=future_days + 1)
    start = datetime.combine(first_day, datetime.min.time())
    end = datetime.combine(last_day, datetime.min.time())

    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.canonical_event_id.is_(None),
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= start,
            SportsEvent.start_time < end,
        )
        .all()
    )

    candidate_rows = rows_updated = participant_logos_filled = 0
    competition_logos_filled = ambiguous = unmatched = 0

    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        slim = extra_for_list(row) or {}
        for key, value in slim.items():
            if value not in (None, "", [], {}):
                extra[key] = value

        missing_participants = any(
            isinstance(participants.get(side), dict) and not _has_logo(participants.get(side))
            for side in ("home", "away")
        )
        missing_competition = not bool(extra.get("competition_logo"))
        if not missing_participants and not missing_competition:
            continue
        candidate_rows += 1

        pair = _pair_key(db, participants.get("home"), participants.get("away"))
        if not pair or row.start_time is None:
            unmatched += 1
            continue
        row_stamp = row.start_time
        if row_stamp.tzinfo is not None:
            row_stamp = row_stamp.astimezone(timezone.utc).replace(tzinfo=None)

        possible = [
            item
            for item in indexed.get(pair, [])
            if abs((item["_asset_stamp"] - row_stamp).total_seconds()) <= KICKOFF_TOLERANCE_SECONDS
        ]
        if len(possible) != 1:
            if len(possible) > 1:
                ambiguous += 1
            else:
                unmatched += 1
            continue

        source = possible[0]
        row_home_key = resolve_folded(db, "football", _name(participants.get("home")))
        row_away_key = resolve_folded(db, "football", _name(participants.get("away")))
        same = (
            row_home_key == source.get("_asset_home_key")
            and row_away_key == source.get("_asset_away_key")
        )
        swapped = (
            row_home_key == source.get("_asset_away_key")
            and row_away_key == source.get("_asset_home_key")
        )
        if not same and not swapped:
            unmatched += 1
            continue

        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            source_name = side_name if same else ("away" if side_name == "home" else "home")
            filled, side_changed = _merge_side(participants.get(side_name), source.get(source_name))
            if not side_changed:
                continue
            participants[side_name] = filled
            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and not _has_logo(mirror):
                mirror_filled, mirror_changed = _merge_side(mirror, source.get(source_name))
                if mirror_changed:
                    participants[mirror_name] = mirror_filled
            participant_logos_filled += 1
            changed = True

        source_comp_logo = str(source.get("competition_logo") or "").strip()
        if missing_competition and source_comp_logo:
            extra["competition_logo"] = source_comp_logo
            extra.setdefault("competition_logo_source", "fotmob-date-board")
            competition_logos_filled += 1
            changed = True

        if not changed:
            continue
        row.participants_json = dump_json(participants)
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)
        note_list_invalidation(
            db,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
        )
        rows_updated += 1

    if rows_updated:
        db.commit()

    return {
        "status": "ok",
        "dates": len(dates),
        "upstream_matches": len(matches),
        "parsed_matches": parsed_matches,
        "candidate_rows": candidate_rows,
        "rows_updated": rows_updated,
        "participant_logos_filled": participant_logos_filled,
        "competition_logos_filled": competition_logos_filled,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
    }
