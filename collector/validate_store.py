"""Read-only production results validation. No writes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import func
from sqlalchemy.orm import Session

from collector.live_state import public_live_visible
from collector.models import (
    SportsCompetition,
    SportsEntity,
    SportsEvent,
    SportsEventDetail,
    SportsIdMap,
)
from collector.util import load_json, parse_datetime


def validate_store(db: Session) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    events = db.query(SportsEvent).all()
    comps = {row.competition_id: row for row in db.query(SportsCompetition).all()}
    ents = {row.entity_id for row in db.query(SportsEntity.entity_id).all()}
    details = {row.event_id for row in db.query(SportsEventDetail.event_id).all()}
    ids = [row.event_id for row in events]
    fps = [row.fingerprint for row in events if row.fingerprint]
    dup_ids = len(ids) - len(set(ids))
    dup_fp = len(fps) - len(set(fps))
    src = (
        db.query(SportsIdMap.entity_kind, SportsIdMap.source_id, SportsIdMap.source_entity_id, func.count())
        .group_by(SportsIdMap.entity_kind, SportsIdMap.source_id, SportsIdMap.source_entity_id)
        .having(func.count() > 1)
        .all()
    )
    orphan_details = db.query(SportsEventDetail).filter(~SportsEventDetail.event_id.in_(ids or [""])).count() if events else db.query(SportsEventDetail).count()
    orphan_comp = sum(1 for row in events if row.competition_id not in comps)
    orphan_ent = 0
    for row in events:
        if row.home_entity_id and row.home_entity_id not in ents:
            orphan_ent += 1
        if row.away_entity_id and row.away_entity_id not in ents:
            orphan_ent += 1
    future_finished = 0
    stale_live = 0
    cross_sport = 0
    comp_mismatch = 0
    invalid_status = 0
    allowed = {
        "scheduled",
        "pre_match",
        "delayed",
        "postponed",
        "suspended",
        "live",
        "halftime",
        "break",
        "finished",
        "cancelled",
        "abandoned",
        "walkover",
        "stale",
        "status_unknown",
        "unknown",
    }
    for row in events:
        if row.status not in allowed:
            invalid_status += 1
        start = row.start_time
        if start and start.tzinfo is None:
            start_aware = start.replace(tzinfo=timezone.utc)
        else:
            start_aware = start
        if row.status == "finished" and start_aware and start_aware > now + timedelta(hours=2):
            future_finished += 1
        payload = {
            "sport": row.sport_id,
            "competition": row.competition_id,
            "competition_key": row.competition_id,
            "status": row.status,
            "start_time": start.isoformat() + "Z" if start else None,
            "source_family": (load_json(row.extra_json, {}) or {}).get("source_family"),
            "source_event_updated_at": (load_json(row.extra_json, {}) or {}).get("source_event_updated_at"),
        }
        if row.status == "live" and not public_live_visible(payload, now=now):
            stale_live += 1
        spec = comps.get(row.competition_id)
        if spec and spec.sport_id and spec.sport_id != row.sport_id:
            cross_sport += 1
        if spec is None:
            comp_mismatch += 1
    return {
        "canonical_events": len(events),
        "duplicate_canonical_identities": dup_ids + dup_fp,
        "duplicate_source_identities": len(src),
        "orphan_details": orphan_details,
        "orphan_entities": orphan_ent,
        "orphan_competitions": orphan_comp,
        "invalid_statuses": invalid_status,
        "future_finished": future_finished,
        "stale_live_exposed": stale_live,
        "cross_sport_mismatch": cross_sport,
        "competition_mismatch": comp_mismatch,
        "read_only": True,
    }
