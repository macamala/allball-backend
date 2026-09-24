"""SofaScore identity-only artwork repair for visible Dota 2 events.

OpenDota remains the score/fixture authority. This job only fills blank team
and competition artwork when a visible canonical Dota event matches one
SofaScore Dota event by both participants and a bounded start-time window.
It never creates events and never changes scores, statuses or fixture times.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.adapters_sofascore import (
    LIVE_URL,
    SCHED_URL,
    _blob as sofa_blob,
    _competition_logo_url,
    _source_tournament_name,
    sofa_fetch_url,
)
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 300
MAX_START_DELTA_S = 8 * 3600

_next_run_at = 0.0

_GENERIC_TOURNAMENT_TOKENS = {
    "dota",
    "2",
    "professional",
    "season",
    "group",
    "stage",
    "playoffs",
    "playoff",
    "qualifier",
    "qualifiers",
    "2025",
    "2026",
}


def _dota_name(value: Any) -> str:
    tokens = [
        token
        for token in fold_for_identity(str(value or "")).split()
        if token not in {"team", "dota", "2"}
    ]
    return " ".join(tokens)


def _pair_key(home: Any, away: Any) -> Tuple[str, str]:
    values = sorted((_dota_name(home), _dota_name(away)))
    if len(values) != 2 or not all(values):
        return ("", "")
    return values[0], values[1]


def _source_start(row: Dict[str, Any]) -> Optional[datetime]:
    raw = row.get("startTimestamp")
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _is_dota(row: Dict[str, Any]) -> bool:
    return "dota" in sofa_blob(row)


def _tournament_tokens(value: Any) -> set[str]:
    folded = fold_for_identity(str(value or ""))
    return {
        token
        for token in re.findall(r"[a-z0-9]+", folded)
        if len(token) >= 3 and token not in _GENERIC_TOURNAMENT_TOKENS
    }


def _competition_names_compatible(left: Any, right: Any) -> bool:
    a = _tournament_tokens(left)
    b = _tournament_tokens(right)
    if not a or not b:
        return False
    shared = a & b
    if len(shared) >= 2:
        return True
    # A distinctive long token is enough when one side is a concise provider
    # label (for example "Wallachia" vs "PGL Wallachia 2026 Season 9").
    return len(shared) == 1 and len(next(iter(shared))) >= 9


def _side_logo(side: Dict[str, Any]) -> str:
    return str(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or ""
    ).strip()


def _fetch_board(getter=None) -> Tuple[List[Dict[str, Any]], int, int]:
    fetch = getter or sofa_fetch_url
    seen: Dict[str, Dict[str, Any]] = {}
    requests = 0
    errors = 0

    live = fetch(LIVE_URL.format(sport="esports"))
    requests += 1
    if getattr(live, "ok", False) and isinstance(getattr(live, "payload", None), dict):
        for item in live.payload.get("events") or []:
            if isinstance(item, dict) and item.get("id") is not None and _is_dota(item):
                seen[str(item["id"])] = item
    else:
        errors += 1

    now = datetime.now(timezone.utc)
    for delta in (-1, 0, 1):
        day = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
        result = fetch(SCHED_URL.format(sport="esports", date=day))
        requests += 1
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), dict):
            errors += 1
            continue
        for item in result.payload.get("events") or []:
            if isinstance(item, dict) and item.get("id") is not None and _is_dota(item):
                seen[str(item["id"])] = item

    return list(seen.values()), requests, errors


def _best_match(row: SportsEvent, board: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    participants = load_json(row.participants_json, {}) or {}
    home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
    away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
    pair = _pair_key(home.get("name"), away.get("name"))
    if not all(pair) or not row.start_time:
        return None

    candidates: List[Tuple[float, str, Dict[str, Any]]] = []
    for source in board:
        source_home = source.get("homeTeam") if isinstance(source.get("homeTeam"), dict) else {}
        source_away = source.get("awayTeam") if isinstance(source.get("awayTeam"), dict) else {}
        if _pair_key(source_home.get("name"), source_away.get("name")) != pair:
            continue
        source_start = _source_start(source)
        if source_start is None:
            continue
        delta = abs((source_start - row.start_time).total_seconds())
        if delta > MAX_START_DELTA_S:
            continue
        candidates.append((delta, str(source.get("id") or ""), source))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now_mono = time.monotonic()
    if now_mono < _next_run_at:
        return None
    _next_run_at = now_mono + RUN_INTERVAL_S

    board, requests, errors = _fetch_board(getter=getter)
    if heartbeat:
        heartbeat()

    stats: Dict[str, Any] = {
        "status": "ok" if board else ("fetch_error" if errors else "empty"),
        "requests": requests,
        "http_errors": errors,
        "dota_board_events": len(board),
        "candidate_rows": 0,
        "matched_rows": 0,
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "competition_logos_filled": 0,
        "matches": {},
    }
    if not board:
        return stats

    start = datetime.utcnow() - timedelta(days=2)
    end = datetime.utcnow() + timedelta(days=2)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "dota-2",
            or_(SportsEvent.display_eligible.is_(True), SportsEvent.display_eligible.is_(None)),
            SportsEvent.start_time >= start,
            SportsEvent.start_time <= end,
        )
        .all()
    )

    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        missing_side = any(
            isinstance(participants.get(key), dict)
            and str((participants.get(key) or {}).get("name") or "").strip()
            and not _side_logo(participants.get(key) or {})
            for key in ("home", "away")
        )
        missing_comp = not bool(str(extra.get("competition_logo") or "").strip())
        if not (missing_side or missing_comp):
            continue
        stats["candidate_rows"] += 1

        source = _best_match(row, board)
        if source is None:
            continue
        stats["matched_rows"] += 1

        source_home = source.get("homeTeam") if isinstance(source.get("homeTeam"), dict) else {}
        source_away = source.get("awayTeam") if isinstance(source.get("awayTeam"), dict) else {}
        source_by_name = {
            _dota_name(source_home.get("name")): source_home,
            _dota_name(source_away.get("name")): source_away,
        }

        changed = False
        extra_changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _side_logo(side):
                continue
            source_side = source_by_name.get(_dota_name(side.get("name")))
            sofa_id = str((source_side or {}).get("id") or "").strip()
            if not sofa_id:
                continue
            merged = dict(side)
            merged["logo"] = f"https://img.sofascore.com/api/v1/team/{sofa_id}/image"
            participants[side_name] = merged
            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and not _side_logo(mirror):
                mirror_merged = dict(mirror)
                mirror_merged["logo"] = merged["logo"]
                participants[mirror_name] = mirror_merged
            stats["participant_logos_filled"] += 1
            changed = True

        source_tournament = _source_tournament_name(source)
        canonical_tournament = (
            extra.get("source_competition_name")
            or extra.get("league_name")
            or ""
        )
        competition_logo = _competition_logo_url(source)
        if (
            missing_comp
            and competition_logo
            and _competition_names_compatible(canonical_tournament, source_tournament)
        ):
            extra["competition_logo"] = competition_logo
            extra_changed = True
            changed = True
            stats["competition_logos_filled"] += 1

        if not changed:
            continue

        row.participants_json = dump_json(participants)
        if extra_changed:
            extra.setdefault("identity_asset_sources", {})
            if isinstance(extra["identity_asset_sources"], dict):
                extra["identity_asset_sources"]["competition_logo"] = "sofascore-web"
            row.extra_json = dump_json(extra)
            store_list_extra(row, extra)
        note_list_invalidation(
            db,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
        )
        stats["rows_updated"] += 1
        stats["matches"][str(row.event_id or "")] = {
            "sofascore_event_id": str(source.get("id") or ""),
            "source_tournament": source_tournament,
        }

    if stats["rows_updated"]:
        db.commit()
    return stats
