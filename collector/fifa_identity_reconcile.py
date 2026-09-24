"""Reconcile public identity for current FIFA global football rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from collector.adapters import FetchRequest
from collector.adapters_feeds import FifaFootballAdapter
from collector.adapters_fotmob import _load_boards, board_dates, match_to_event as fotmob_match_to_event
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.participant_alias import names_equivalent
from collector.util import dump_json, isoformat, load_json, parse_datetime


def _has_logo(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return any(
        side.get(key)
        for key in ("logo", "image", "crest", "badge", "team_logo", "teamLogo", "logo_url", "logoUrl")
    )


def _naive_stamp(value: Any) -> datetime | None:
    stamp = parse_datetime(value)
    if stamp is None:
        return None
    return stamp.replace(tzinfo=None) if getattr(stamp, "tzinfo", None) else stamp


def _fotmob_asset_match(row: SportsEvent, participants: Dict[str, Any], events: list[Dict[str, Any]]) -> Dict[str, Any] | None:
    row_time = row.start_time
    if row_time is None:
        return None
    row_time = row_time.replace(tzinfo=None) if getattr(row_time, "tzinfo", None) else row_time
    home_name = str((participants.get("home") or {}).get("name") or "").strip()
    away_name = str((participants.get("away") or {}).get("name") or "").strip()
    if not home_name or not away_name:
        return None

    candidates = []
    for event in events:
        event_time = _naive_stamp(event.get("start_time"))
        if event_time is None or abs((event_time - row_time).total_seconds()) > 12 * 3600:
            continue
        fh = str((event.get("home") or {}).get("name") or "").strip()
        fa = str((event.get("away") or {}).get("name") or "").strip()
        same = names_equivalent(home_name, fh) and names_equivalent(away_name, fa)
        swapped = names_equivalent(home_name, fa) and names_equivalent(away_name, fh)
        if same or swapped:
            candidates.append((event, swapped))
    if len(candidates) != 1:
        return None
    event, swapped = candidates[0]
    return {
        "home": event.get("away") if swapped else event.get("home"),
        "away": event.get("home") if swapped else event.get("away"),
        "competition_logo": event.get("competition_logo"),
    }


def _source_id(extra: Dict[str, Any]) -> str:
    ids = extra.get("source_event_ids") if isinstance(extra.get("source_event_ids"), dict) else {}
    return str(
        extra.get("source_event_id")
        or ids.get("fifa-digital")
        or ids.get("fifa")
        or ""
    ).strip()


def reconcile_current_fifa_identity(db, *, days_back: int = 2, days_forward: int = 7) -> Dict[str, int]:
    result = FifaFootballAdapter().fetch(
        FetchRequest(
            capability="snapshot",
            sport_id="football",
            competition_id="fifa-connected-competitions",
        )
    )
    if not result.ok:
        return {"fetched": 0, "matched": 0, "changed": 0}

    by_id = {
        str(event.get("source_event_id") or ""): event
        for event in (result.events or [])
        if isinstance(event, dict) and event.get("source_event_id")
    }
    if not by_id:
        return {"fetched": 0, "matched": 0, "changed": 0}

    now = datetime.utcnow()
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.primary_source_id == "fifa")
        .filter(SportsEvent.start_time >= now - timedelta(days=days_back))
        .filter(SportsEvent.start_time <= now + timedelta(days=days_forward))
        .all()
    )

    need_fallback = any(
        not _has_logo((load_json(row.participants_json, {}) or {}).get(side))
        for row in rows
        for side in ("home", "away")
    )
    fotmob_events: list[Dict[str, Any]] = []
    if need_fallback:
        boards = _load_boards(
            None,
            dates=board_dates(past_days=max(days_back + 1, 3), future_days=min(days_forward, 2)),
        )
        for match in boards:
            event = fotmob_match_to_event(match, "")
            if event:
                fotmob_events.append(event)

    matched = 0
    changed = 0
    participant_logos_filled = 0
    fotmob_matches = 0
    fotmob_participant_logos_filled = 0
    fotmob_competition_logos_filled = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        source = by_id.get(_source_id(extra))
        if source is None:
            continue
        matched += 1
        participants = load_json(row.participants_json, {}) or {}
        participant_changed = False

        # FIFA match rows expose club/national-team artwork as Team.PictureUrl.
        # Fill blanks only, preserving any better artwork already supplied by
        # another trusted source.
        for source_key, target_keys in (
            ("home", ("home", "participant_a")),
            ("away", ("away", "participant_b")),
        ):
            source_side = source.get(source_key) if isinstance(source.get(source_key), dict) else {}
            source_logo = str(source_side.get("logo") or "").strip()
            source_id = str(source_side.get("id") or "").strip()
            source_country = str(source_side.get("country_id") or "").strip()
            for target_key in target_keys:
                side = participants.get(target_key)
                if not isinstance(side, dict):
                    continue
                merged = dict(side)
                if source_logo and not any(
                    merged.get(key)
                    for key in ("logo", "image", "crest", "badge", "team_logo", "teamLogo", "logo_url", "logoUrl")
                ):
                    merged["logo"] = source_logo
                    participant_logos_filled += 1
                    participant_changed = True
                if source_id and not merged.get("id"):
                    merged["id"] = source_id
                    participant_changed = True
                if source_country and not (
                    merged.get("country_id") or merged.get("country") or merged.get("nationality")
                ):
                    merged["country_id"] = source_country
                    participant_changed = True
                participants[target_key] = merged

        fallback = _fotmob_asset_match(row, participants, fotmob_events) if fotmob_events else None
        if fallback:
            fotmob_matches += 1
            for source_key, target_keys in (
                ("home", ("home", "participant_a")),
                ("away", ("away", "participant_b")),
            ):
                fallback_side = fallback.get(source_key) if isinstance(fallback.get(source_key), dict) else {}
                fallback_logo = str(fallback_side.get("logo") or "").strip()
                if not fallback_logo:
                    continue
                for target_key in target_keys:
                    side = participants.get(target_key)
                    if not isinstance(side, dict) or _has_logo(side):
                        continue
                    merged = dict(side)
                    merged["logo"] = fallback_logo
                    participants[target_key] = merged
                    participant_changed = True
                    participant_logos_filled += 1
                    fotmob_participant_logos_filled += 1
            fallback_comp_logo = str(fallback.get("competition_logo") or "").strip()
            if fallback_comp_logo and not extra.get("competition_logo"):
                extra["competition_logo"] = fallback_comp_logo
                fotmob_competition_logos_filled += 1

        before = (
            extra.get("public_competition_key"),
            extra.get("source_competition_id"),
            extra.get("source_competition_name"),
            row.country_id,
        )
        public_key = str(source.get("competition_key") or "").strip()
        if public_key.startswith("football-"):
            extra["public_competition_key"] = public_key
        if source.get("source_competition_id"):
            extra["source_competition_id"] = str(source.get("source_competition_id"))
        if source.get("source_competition_name") or source.get("competition"):
            extra["source_competition_name"] = source.get("source_competition_name") or source.get("competition")
        if source.get("country_id"):
            row.country_id = str(source.get("country_id"))
        flags = list(extra.get("quality_flags") or [])
        flags = [flag for flag in flags if flag != "competition_attribution_mismatch"]
        extra["quality_flags"] = flags
        extra["fifa_identity_reconciled_at"] = isoformat(datetime.utcnow())
        after = (
            extra.get("public_competition_key"),
            extra.get("source_competition_id"),
            extra.get("source_competition_name"),
            row.country_id,
        )
        if participant_changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
        if after != before or participant_changed:
            changed += 1
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)

    return {
        "fetched": len(by_id),
        "matched": matched,
        "changed": changed,
        "participant_logos_filled": participant_logos_filled,
        "fotmob_matches": fotmob_matches,
        "fotmob_participant_logos_filled": fotmob_participant_logos_filled,
        "fotmob_competition_logos_filled": fotmob_competition_logos_filled,
    }
