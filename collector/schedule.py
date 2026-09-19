"""Collector cadence derived from the existing cache policy. Not started by the API process."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.models import SportsCollectorJob
from sports_registry.cache_policy import policy_for

CAPABILITY_POLICIES = {
    "live_scores": "live_events",
    "fixtures": "upcoming_fixtures",
    "results": "finished_events",
    "standings": "standings",
    "rankings": "standings",
}


def cadence_seconds(capability: str) -> int:
    policy_key = CAPABILITY_POLICIES.get(capability, "upcoming_fixtures")
    ttl = int(policy_for(policy_key).get("ttl_seconds") or 300)
    if capability == "results":
        return min(ttl, 300)
    return ttl


def due_capabilities(db: Session, now: Optional[datetime] = None) -> List[str]:
    now = now or datetime.utcnow()
    due: List[str] = []
    for capability in CAPABILITY_POLICIES:
        job = db.query(SportsCollectorJob).filter_by(job_key=capability).first()
        interval = timedelta(seconds=cadence_seconds(capability))
        if job is None or job.last_run_at is None or job.last_run_at + interval <= now:
            due.append(capability)
    return due


def mark_job(db: Session, capability: str, status: str, items_written: int, error: Optional[str] = None) -> None:
    row = db.query(SportsCollectorJob).filter_by(job_key=capability).first()
    if row is None:
        row = SportsCollectorJob(job_key=capability)
        db.add(row)
    row.last_run_at = datetime.utcnow()
    row.last_status = status
    row.last_error = error
    row.items_written = items_written
