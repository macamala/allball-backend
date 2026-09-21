"""Bounded production backfill. Uses normal collect/normalize/merge.

Safe to rerun: force=True collection is idempotent via fingerprints/merge.
Does not mutate source_matrix_final. Does not invent scores.
Completion is durable on SportsCollectorJob so a restart resumes pending work.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_fotmob import FOTMOB_LEAGUES
from collector.collect import run_cycle
from collector.detail_enrich import enrich_event_row
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsEvent
from collector.production import register_production_adapters
from collector.source_ids import families_with_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

JOB_KEY = "bounded-rich-backfill-v6"

CORE_COMPETITIONS: List[str] = [
    "wta-tour",
    "gbgb-meetings",
    "bha-meetings",
    "nsw-hrnsw-meetings",
    "mlb",
    "nhl",
]
CORE_COMPETITIONS.extend(sorted(FOTMOB_LEAGUES))

ENRICH_FAMILIES = {"fotmob", "sofascore-web", "mlb-statsapi", "nhl-web", "wta-json"}


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY)
        db.add(row)
        db.flush()
    return row


def _checkpoint(job: SportsCollectorJob, **fields: Any) -> None:
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(fields)
    job.last_error = dump_json(payload)[:4000]
    job.last_status = str(payload.get("state") or job.last_status or "")


def run_bounded_backfill(
    db: Session,
    *,
    competitions: Optional[List[str]] = None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    register_production_adapters()
    from collector.fotmob_crosswalk import crosswalk_fotmob_ids, eligible_coverage
    from collector.id_backfill import attach_observation_ids, copy_complementary_ids, coverage_counts
    from collector.list_extra import store_list_extra
    from collector.wta_rewrite import rewrite_wta_result_types

    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    comps = list(dict.fromkeys(competitions or payload.get("comp_list") or CORE_COMPETITIONS))
    next_index = 0 if competitions is not None else int(payload.get("next_index") or 0)
    before = coverage_counts(db)
    eligible_before = eligible_coverage(db)
    attach_observation_ids(db)
    copy_complementary_ids(db)
    cross_before = crosswalk_fotmob_ids(db)
    db.commit()
    _checkpoint(
        job,
        state="running",
        next_index=next_index,
        comp_list=comps,
        coverage_before=before,
        fotmob_eligible_before=eligible_before,
        fotmob_crosswalk=cross_before,
    )
    db.commit()
    summaries: Dict[str, Any] = dict(payload.get("competitions") or {})
    for index, competition_id in enumerate(comps):
        if index < next_index:
            continue
        if heartbeat:
            heartbeat()
        try:
            summary = run_cycle(
                db,
                capabilities=["fixtures", "results", "snapshot"],
                competition_id=competition_id,
                sleeper=lambda _d: None,
                force=True,
            )
            if summary.get("write_lock") == 0:
                logger.info("backfill pausing; write lock not owned competition=%s", competition_id)
                _checkpoint(job, state="running", next_index=index, competitions=summaries)
                db.commit()
                return {
                    "paused": True,
                    "next_index": index,
                    "competitions": summaries,
                    "count": len(comps),
                }
            summaries[competition_id] = summary
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed competition=%s", competition_id)
            summaries[competition_id] = {"error": str(exc)[:240]}
            db.rollback()
        if competition_id == "wta-tour":
            try:
                summaries["wta_rewrite"] = rewrite_wta_result_types(db)
                db.commit()
            except Exception:
                logger.exception("WTA result rewrite failed")
                db.rollback()
        _checkpoint(job, state="running", next_index=index + 1, competitions=summaries)
        db.commit()
    attach_observation_ids(db)
    copy_complementary_ids(db)
    cross_after = crosswalk_fotmob_ids(db)
    db.commit()
    enrich = enrich_recent_detail(db)
    after = coverage_counts(db)
    eligible_after = eligible_coverage(db)
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
    _checkpoint(
        job,
        state="done",
        next_index=len(comps),
        competitions=summaries,
        enrich=enrich,
        coverage_after=after,
        fotmob_eligible_after=eligible_after,
        fotmob_crosswalk_after=cross_after,
    )
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int((enrich or {}).get("filled") or 0)
    db.commit()
    logger.info(
        "bounded_backfill_complete coverage_before=%s coverage_after=%s eligible_before=%s eligible_after=%s",
        before,
        after,
        eligible_before,
        eligible_after,
    )
    return {
        "competitions": summaries,
        "enrich": enrich,
        "count": len(comps),
        "coverage_before": before,
        "coverage_after": after,
        "fotmob_eligible_before": eligible_before,
        "fotmob_eligible_after": eligible_after,
    }


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


def run_if_due(
    db: Session,
    *,
    min_interval_hours: int = 6,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        logger.info("skip backfill; scheduler lease is not held")
        return None
    if owner and status.get("owner_id") != owner:
        logger.info("skip backfill; process is not the scheduler owner")
        return None
    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    state = payload.get("state")
    if state == "done" and job.last_run_at and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours):
        return None
    return run_bounded_backfill(db, heartbeat=heartbeat)


if __name__ == "__main__":
    from database import SessionLocal

    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        print(run_bounded_backfill(db))
    finally:
        db.close()
