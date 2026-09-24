"""Bounded exact-ID artwork backfill for visible OpenLigaDB events.

This job is asset-only. It reuses OpenLigaDB's own team IDs and teamIconUrl
from the current match feed, so no club-name guessing is needed and score
authority is unchanged.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_openligadb import API
from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.models import SportsEvent
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 180
FETCH_TTL_S = 6 * 3600
MAX_SHORTCUTS_PER_RUN = 4

_next_run_at = 0.0
_last_fetch: Dict[str, float] = {}


def _logo(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    return str(
        node.get("teamIconUrl")
        or node.get("teamIconURL")
        or node.get("logo")
        or ""
    ).strip()


def _catalog(payload: Any) -> Dict[str, Dict[str, str]]:
    rows = payload if isinstance(payload, list) else []
    out: Dict[str, Dict[str, str]] = {}
    for match in rows:
        if not isinstance(match, dict):
            continue
        for key in ("team1", "team2"):
            node = match.get(key)
            if not isinstance(node, dict):
                continue
            team_id = str(node.get("teamId") or "").strip()
            logo = _logo(node)
            if not team_id or not logo:
                continue
            out[team_id] = {
                "id": team_id,
                "name": str(node.get("teamName") or node.get("shortName") or "").strip(),
                "logo": logo,
            }
    return out


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


def _candidate_shortcuts(db: Session, now: float) -> List[str]:
    lower = datetime.utcnow() - timedelta(days=1)
    upper = datetime.utcnow() + timedelta(days=3)
    counts: Dict[str, int] = defaultdict(int)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= lower,
            SportsEvent.start_time <= upper,
        )
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "openligadb":
            continue
        shortcut = str(extra.get("source_competition_id") or "").strip()
        if not shortcut:
            continue
        missing = 0
        participants = load_json(row.participants_json, {}) or {}
        for side_name in ("home", "away"):
            side = participants.get(side_name)
            if isinstance(side, dict) and str(side.get("id") or "").strip() and _missing_logo(side):
                missing += 1
        if missing:
            counts[shortcut] += missing

    candidates = [
        shortcut
        for shortcut, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        if now - float(_last_fetch.get(shortcut) or 0.0) >= FETCH_TTL_S
    ]
    return candidates[:MAX_SHORTCUTS_PER_RUN]


def _apply_catalog(db: Session, shortcut: str, catalog: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    rows_updated = 0
    participants_filled = 0
    rows = db.query(SportsEvent).filter(SportsEvent.display_eligible.is_(True)).all()
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "openligadb":
            continue
        if str(extra.get("source_competition_id") or "").strip() != shortcut:
            continue
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            team_id = str(side.get("id") or "").strip()
            asset = catalog.get(team_id)
            if not asset:
                continue
            merged = dict(side)
            merged["logo"] = asset["logo"]
            participants[side_name] = merged

            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and _missing_logo(mirror):
                mirror_id = str(mirror.get("id") or "").strip()
                if not mirror_id or mirror_id == team_id:
                    mirror_merged = dict(mirror)
                    mirror_merged["logo"] = asset["logo"]
                    if not mirror_id:
                        mirror_merged["id"] = team_id
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
    global _next_run_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S
    getter = getter or fetch_url
    shortcuts = _candidate_shortcuts(db, now)
    stats: Dict[str, Any] = {
        "status": "ok" if shortcuts else "idle",
        "shortcuts": 0,
        "requests": 0,
        "rows_updated": 0,
        "participants_filled": 0,
        "http_errors": 0,
        "by_shortcut": {},
    }

    for shortcut in shortcuts:
        result = getter(f"{API}/getmatchdata/{shortcut}")
        stats["requests"] += 1
        if heartbeat:
            heartbeat()
        _last_fetch[shortcut] = now
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue
        catalog = _catalog(result.payload)
        applied = _apply_catalog(db, shortcut, catalog)
        if applied["rows_updated"]:
            db.commit()
        stats["shortcuts"] += 1
        stats["rows_updated"] += applied["rows_updated"]
        stats["participants_filled"] += applied["participants_filled"]
        stats["by_shortcut"][shortcut] = {
            "catalog": len(catalog),
            **applied,
        }

    return stats
