"""Attach stored provider event IDs onto canonical rows and copy complementary IDs.

Uses observations and already-collected canonical extra, not title-only matching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from collector.identity_events import identity_confidence
from collector.models import SportsEvent, SportsEventObservation
from collector.source_ids import families_with_ids, merge_family_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

ENRICH_FAMILIES = ("fotmob", "sofascore-web", "mlb-statsapi", "nhl-web", "wta-json")


def _write_ids(row: SportsEvent, extra: Dict[str, Any], ids: Dict[str, str]) -> bool:
    merged = merge_family_ids(extra.get("source_event_ids"), ids)
    if merged == families_with_ids(extra) and extra.get("source_event_ids") == merged:
        return False
    extra["source_event_ids"] = merged
    if not extra.get("source_event_id") and merged:
        extra["source_event_id"] = next(iter(merged.values()))
    row.extra_json = dump_json(extra)
    if hasattr(row, "list_extra_json"):
        from collector.list_extra import store_list_extra

        store_list_extra(row, extra)
    return True


def attach_observation_ids(db: Session, *, hours: int = 120) -> Dict[str, int]:
    bound = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(SportsEventObservation)
        .filter(SportsEventObservation.retrieved_at >= bound)
        .filter(SportsEventObservation.source_event_id.isnot(None))
        .all()
    )
    updated = scanned = 0
    cache: Dict[str, SportsEvent] = {}
    for obs in rows:
        scanned += 1
        family = str(obs.source_family or "")
        if family not in ENRICH_FAMILIES:
            continue
        row = cache.get(obs.event_id)
        if row is None:
            row = db.get(SportsEvent, obs.event_id)
            if row:
                cache[obs.event_id] = row
        if row is None or row.canonical_event_id:
            continue
        extra = load_json(row.extra_json, {}) or {}
        before = dict(families_with_ids(extra))
        extra["source_event_ids"] = merge_family_ids(
            extra.get("source_event_ids"),
            family=family,
            source_event_id=obs.source_event_id,
        )
        if families_with_ids(extra) != before:
            row.extra_json = dump_json(extra)
            updated += 1
    db.flush()
    return {"observations": scanned, "rows_updated": updated}


def copy_complementary_ids(db: Session, *, hours: int = 120, sport_id: str = "football") -> int:
    bound = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == sport_id)
        .filter(SportsEvent.start_time >= bound)
        .all()
    )
    packed: List[Tuple[SportsEvent, Dict[str, Any], Dict[str, str]]] = []
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        packed.append((row, extra, families_with_ids(extra)))
    copied = 0
    for left, l_extra, l_ids in packed:
        if not any(fam in l_ids for fam in ("fotmob", "sofascore-web")):
            continue
        left_view = {
            "sport": left.sport_id,
            "home": (load_json(left.participants_json, {}) or {}).get("home") or {},
            "away": (load_json(left.participants_json, {}) or {}).get("away") or {},
            "start_time": left.start_time.isoformat() + "Z" if left.start_time else None,
            "source_event_ids": l_ids,
        }
        for right, r_extra, r_ids in packed:
            if left.event_id == right.event_id:
                continue
            if left.competition_id != right.competition_id:
                continue
            if identity_confidence(left_view, {
                "sport": right.sport_id,
                "home": (load_json(right.participants_json, {}) or {}).get("home") or {},
                "away": (load_json(right.participants_json, {}) or {}).get("away") or {},
                "start_time": right.start_time.isoformat() + "Z" if right.start_time else None,
                "source_event_ids": r_ids,
            }) < 90:
                continue
            merged = merge_family_ids(r_ids, l_ids)
            if merged != r_ids:
                r_extra["source_event_ids"] = merged
                right.extra_json = dump_json(r_extra)
                copied += 1
    db.flush()
    return copied


def coverage_counts(db: Session, *, hours: int = 168) -> Dict[str, Any]:
    bound = datetime.utcnow() - timedelta(hours=hours)
    specs = (
        ("football", None),
        ("baseball", "mlb"),
        ("ice-hockey", "nhl"),
        ("tennis", "wta-tour"),
    )
    out: Dict[str, Any] = {}
    for sport, competition in specs:
        query = (
            db.query(SportsEvent)
            .filter(SportsEvent.canonical_event_id.is_(None))
            .filter(SportsEvent.sport_id == sport)
            .filter(SportsEvent.start_time >= bound)
        )
        if competition:
            query = query.filter(SportsEvent.competition_id == competition)
        rows = query.all()
        fotmob = sofa = both = neither = 0
        mlb = nhl = wta = 0
        for row in rows:
            ids = families_with_ids(load_json(row.extra_json, {}) or {})
            has_f = bool(ids.get("fotmob"))
            has_s = bool(ids.get("sofascore-web"))
            if has_f:
                fotmob += 1
            if has_s:
                sofa += 1
            if has_f and has_s:
                both += 1
            if not has_f and not has_s:
                neither += 1
            if ids.get("mlb-statsapi"):
                mlb += 1
            if ids.get("nhl-web"):
                nhl += 1
            if ids.get("wta-json"):
                wta += 1
        key = competition or sport
        payload = {"total": len(rows), "fotmob": fotmob, "sofascore": sofa, "both": both, "neither": neither}
        if sport == "baseball":
            payload["mlb"] = mlb
        if sport == "ice-hockey":
            payload["nhl"] = nhl
        if sport == "tennis":
            payload["wta"] = wta
        out[key] = payload
    logger.info("source_id_coverage %s", out)
    return out
