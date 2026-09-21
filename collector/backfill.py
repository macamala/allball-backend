"""Bounded production backfill. Uses normal collect/normalize/merge.

Safe to rerun: force=True collection is idempotent via fingerprints/merge.
Does not mutate source_matrix_final. Does not invent scores.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_sofascore import SOFA_COMPETITIONS
from collector.collect import run_cycle
from collector.detail_enrich import enrich_event_row
from collector.models import SportsCollectorJob, SportsEvent
from collector.production import register_production_adapters
from collector.source_ids import families_with_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

JOB_KEY = "bounded-rich-backfill-v4"

CORE_COMPETITIONS: List[str] = [
    "wta-tour",
    "gbgb-meetings",
    "bha-meetings",
    "nsw-hrnsw-meetings",
    "mlb",
    "nhl",
    "italy-serie-a",
    "france-ligue-1",
    "netherlands-eredivisie",
    "portugal-primeira-liga",
    "croatia-hnl",
    "norway-eliteserien",
    "poland-ekstraklasa",
    "romania-superliga",
    "korea-k-league-1",
    "china-super-league",
    "czech-first-league",
    "hungary-nb-i",
]
CORE_COMPETITIONS.extend(sorted(SOFA_COMPETITIONS)[:8])

ENRICH_FAMILIES = {"fotmob", "sofascore-web", "mlb-statsapi", "nhl-web", "wta-json"}


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY)
        db.add(row)
        db.flush()
    return row


def run_bounded_backfill(db: Session, *, competitions: Optional[List[str]] = None) -> Dict[str, Any]:
    register_production_adapters()
    from collector.id_backfill import attach_observation_ids, copy_complementary_ids, coverage_counts
    from collector.list_extra import store_list_extra

    before = coverage_counts(db)
    attach_observation_ids(db)
    copy_complementary_ids(db)
    db.commit()
    comps = list(dict.fromkeys(competitions or CORE_COMPETITIONS))
    summaries: Dict[str, Any] = {}
    for competition_id in comps:
        try:
            summaries[competition_id] = run_cycle(
                db,
                capabilities=["fixtures", "results", "snapshot"],
                competition_id=competition_id,
                sleeper=lambda _d: None,
                force=True,
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed competition=%s", competition_id)
            summaries[competition_id] = {"error": str(exc)[:240]}
            db.rollback()
    attach_observation_ids(db)
    copy_complementary_ids(db)
    db.commit()
    enrich = enrich_recent_detail(db)
    after = coverage_counts(db)
    bound = datetime.utcnow() - timedelta(hours=192)
    racing = {"greyhound-racing", "horse-racing", "harness-racing"}
    for row in (
        db.query(SportsEvent)
        .filter(SportsEvent.start_time >= bound)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .all()
    ):
        extra = load_json(row.extra_json, {}) or {}
        if row.sport_id in racing and (row.status or "").lower() == "finished":
            if not extra.get("winner") and not extra.get("runners"):
                row.status = "scheduled"
                row.live = False
        store_list_extra(row, extra)
    db.commit()
    return {"competitions": summaries, "enrich": enrich, "count": len(comps), "coverage_before": before, "coverage_after": after}


def enrich_recent_detail(db: Session, *, hours: int = 96, limit: int = 80) -> Dict[str, int]:
    bound = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.start_time >= bound)
        .order_by(SportsEvent.start_time.desc())
        .limit(400)
        .all()
    )
    attempted = filled = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        ids = families_with_ids(extra)
        if not any(fam in ENRICH_FAMILIES for fam in ids):
            continue
        if attempted >= limit:
            break
        attempted += 1
        try:
            enrich_event_row(db, row)
        except Exception:
            continue
        extra = load_json(row.extra_json, {}) or {}
        if extra.get("incidents") or extra.get("statistics") or extra.get("lineups") or extra.get("periods"):
            filled += 1
    return {"attempted": attempted, "filled": filled}


def run_if_due(db: Session, *, min_interval_hours: int = 6) -> Optional[Dict[str, Any]]:
    job = _job(db)
    if job.last_run_at and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours):
        return None
    result = run_bounded_backfill(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int((result.get("enrich") or {}).get("filled") or 0)
    job.last_error = dump_json({"competitions": len(result.get("competitions") or {}), "enrich": result.get("enrich")})[:2000]
    db.commit()
    return result


if __name__ == "__main__":
    from database import SessionLocal

    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        print(run_bounded_backfill(db))
    finally:
        db.close()
