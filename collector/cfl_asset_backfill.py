"""Asset-only repair for current official CFL scoreboard rows.

Uses the CFL scoreboard squads JSON as the identity authority and only attaches
logos when the stored side ID matches an official squad ID. It does not change
fixtures, scores, statuses, or provider priority.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from collector.adapters_ro56 import CFL_SQUADS, _cfl_squad_assets
from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.models import SportsEvent
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 180
FETCH_TTL_S = 6 * 3600

_next_run_at = 0.0
_last_fetch_at = 0.0


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


def _has_current_gap(db: Session) -> bool:
    lower = datetime.utcnow() - timedelta(days=1)
    upper = datetime.utcnow() + timedelta(days=3)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.competition_id == "cfl",
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= lower,
            SportsEvent.start_time <= upper,
        )
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "cfl-scoreboard-json":
            continue
        participants = load_json(row.participants_json, {}) or {}
        for key in ("home", "away"):
            side = participants.get(key)
            if isinstance(side, dict) and str(side.get("id") or "").strip() and _missing_logo(side):
                return True
    return False


def _apply(db: Session, assets: Dict[str, str]) -> Dict[str, int]:
    rows_updated = 0
    participants_filled = 0
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.competition_id == "cfl",
            SportsEvent.display_eligible.is_(True),
        )
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "cfl-scoreboard-json":
            continue
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            team_id = str(side.get("id") or "").strip().lower()
            logo = assets.get(team_id)
            if not team_id or not logo:
                continue
            merged = dict(side)
            merged["logo"] = logo
            participants[side_name] = merged

            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and _missing_logo(mirror):
                mirror_id = str(mirror.get("id") or "").strip().lower()
                if not mirror_id or mirror_id == team_id:
                    mirror_merged = dict(mirror)
                    mirror_merged["logo"] = logo
                    if not mirror_id:
                        mirror_merged["id"] = str(side.get("id") or "").strip()
                    participants[mirror_name] = mirror_merged

            changed = True
            participants_filled += 1

        if changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
            rows_updated += 1

    return {
        "rows_updated": rows_updated,
        "participants_filled": participants_filled,
    }


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at, _last_fetch_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S

    if not _has_current_gap(db):
        return {
            "status": "idle",
            "requests": 0,
            "rows_updated": 0,
            "participants_filled": 0,
            "catalog": 0,
        }
    if now - _last_fetch_at < FETCH_TTL_S:
        return None

    getter = getter or fetch_url
    result = getter(CFL_SQUADS)
    _last_fetch_at = now
    if heartbeat:
        heartbeat()
    if not getattr(result, "ok", False):
        return {
            "status": "unavailable",
            "requests": 1,
            "http_status": getattr(result, "http_status", None),
            "rows_updated": 0,
            "participants_filled": 0,
            "catalog": 0,
        }

    assets = _cfl_squad_assets(result.payload)
    applied = _apply(db, assets)
    if applied["rows_updated"]:
        db.commit()
    return {
        "status": "ok",
        "requests": 1,
        "catalog": len(assets),
        **applied,
    }
