"""OpenDota team-logo backfill for the public Dota scoreboard.

This job is identity-only. It performs one bounded OpenDota team-catalogue
request, matches by the exact numeric Dota team id already stored on canonical
participants, and fills only blank logo fields. It never creates, removes,
rekeys, or changes match rows.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.models import SportsEvent
from collector.util import dump_json, load_json

TEAMS_URL = "https://api.opendota.com/api/teams"
RUN_INTERVAL_S = 300
CATALOG_TTL_S = 6 * 3600

_next_run_at = 0.0
_catalog: Dict[str, Dict[str, str]] = {}
_catalog_at = 0.0


def _missing_logo(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return not bool(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or side.get("logo_url")
        or side.get("logoUrl")
    )


def _parse_catalog(payload: Any) -> Dict[str, Dict[str, str]]:
    rows = payload if isinstance(payload, list) else []
    out: Dict[str, Dict[str, str]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        team_id = str(item.get("team_id") or "").strip()
        logo = str(item.get("logo_url") or "").strip()
        if not team_id.isdigit() or not logo:
            continue
        out[team_id] = {
            "id": team_id,
            "name": str(item.get("name") or "").strip(),
            "tag": str(item.get("tag") or "").strip(),
            "logo": logo,
        }
    return out


def _candidate_ids(db: Session) -> Set[str]:
    start = datetime.utcnow() - timedelta(days=1)
    end = datetime.utcnow() + timedelta(days=3)
    ids: Set[str] = set()
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "dota-2",
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= start,
            SportsEvent.start_time <= end,
        )
        .all()
    )
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        for key in ("home", "away"):
            side = participants.get(key)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            team_id = str(side.get("id") or "").strip()
            if team_id.isdigit():
                ids.add(team_id)
    return ids


def _fill_side(side: Any, asset: Dict[str, str]) -> tuple[Any, bool]:
    if not isinstance(side, dict) or not asset.get("logo") or not _missing_logo(side):
        return side, False
    if str(side.get("id") or "").strip() != str(asset.get("id") or "").strip():
        return side, False
    merged = dict(side)
    merged["logo"] = asset["logo"]
    return merged, True


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at, _catalog, _catalog_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S

    candidate_ids = _candidate_ids(db)
    stats: Dict[str, Any] = {
        "status": "idle" if not candidate_ids else "ok",
        "candidate_ids": len(candidate_ids),
        "requests": 0,
        "catalog_teams": len(_catalog),
        "matched_ids": 0,
        "rows_updated": 0,
        "participants_filled": 0,
        "http_errors": 0,
    }
    if not candidate_ids:
        return stats

    if not _catalog or now - _catalog_at >= CATALOG_TTL_S:
        getter = getter or fetch_url
        result = getter(TEAMS_URL)
        stats["requests"] += 1
        if heartbeat:
            heartbeat()
        if not getattr(result, "ok", False):
            stats["status"] = "fetch_error"
            stats["http_errors"] += 1
            return stats
        parsed = _parse_catalog(result.payload)
        if not parsed:
            stats["status"] = "empty_catalog"
            return stats
        _catalog = parsed
        _catalog_at = now

    stats["catalog_teams"] = len(_catalog)
    matched = candidate_ids & set(_catalog)
    stats["matched_ids"] = len(matched)
    if not matched:
        return stats

    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "dota-2",
            SportsEvent.display_eligible.is_(True),
        )
        .all()
    )
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        filled = 0
        for key, mirror_key in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(key)
            team_id = str((side or {}).get("id") or "").strip() if isinstance(side, dict) else ""
            asset = _catalog.get(team_id)
            if not asset:
                continue
            next_side, side_changed = _fill_side(side, asset)
            if not side_changed:
                continue
            participants[key] = next_side
            mirror = participants.get(mirror_key)
            if isinstance(mirror, dict):
                next_mirror, mirror_changed = _fill_side(mirror, asset)
                if mirror_changed:
                    participants[mirror_key] = next_mirror
            changed = True
            filled += 1
        if not changed:
            continue
        row.participants_json = dump_json(participants)
        note_list_invalidation(
            db,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
        )
        stats["rows_updated"] += 1
        stats["participants_filled"] += filled

    if stats["rows_updated"]:
        db.commit()
    return stats
