"""Source health and raw ingest persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from collector.models import (
    SportsCompetitionHealth,
    SportsIngestionError,
    SportsRawIngest,
    SportsSourceHealth,
)
from collector.util import payload_hash


def record_ingest(
    db: Session,
    *,
    source_id: str,
    entity_kind: str,
    payload: Any,
    capability: Optional[str] = None,
    source_entity_id: Optional[str] = None,
    competition_id: Optional[str] = None,
    http_status: Optional[int] = None,
    restricted: bool = False,
    error: Optional[str] = None,
) -> SportsRawIngest:
    row = SportsRawIngest(
        source_id=source_id,
        entity_kind=entity_kind,
        source_entity_id=source_entity_id,
        competition_id=competition_id,
        capability=capability,
        fetched_at=datetime.utcnow(),
        http_status=http_status,
        payload_hash=payload_hash(payload) if payload is not None else None,
        payload=None,
        restricted=restricted,
        error=error,
    )
    db.add(row)
    return row


def _health(db: Session, source_id: str) -> SportsSourceHealth:
    cache = db.info.setdefault("source_health", {})
    row = cache.get(source_id)
    if row is None:
        row = db.get(SportsSourceHealth, source_id)
    if row is None:
        for pending in db.new:
            if isinstance(pending, SportsSourceHealth) and pending.source_id == source_id:
                row = pending
                break
    if row is None:
        row = db.query(SportsSourceHealth).filter_by(source_id=source_id).first()
    if row is None:
        row = SportsSourceHealth(source_id=source_id, status="unknown")
        db.add(row)
    cache[source_id] = row
    return row


def mark_attempt(
    db: Session,
    source_id: str,
    *,
    latency_ms: Optional[int] = None,
    parse_status: Optional[str] = None,
    events_returned: Optional[int] = None,
    http_status: Optional[int] = None,
    error_type: Optional[str] = None,
) -> None:
    row = _health(db, source_id)
    row.last_attempt_at = datetime.utcnow()
    row.last_latency_ms = latency_ms
    row.last_parse_status = parse_status
    row.last_events_returned = events_returned
    if http_status is not None:
        row.last_http_status = http_status
    row.last_error_type = error_type
    row.updated_at = datetime.utcnow()


def mark_success(db: Session, source_id: str, http_status: Optional[int] = None, events_returned: Optional[int] = None) -> None:
    row = _health(db, source_id)
    row.status = "empty" if events_returned == 0 else "healthy"
    row.last_success_at = datetime.utcnow()
    if events_returned:
        row.last_success_event_at = datetime.utcnow()
        row.consecutive_failures = 0
    else:
        row.consecutive_failures = 0
    row.last_http_status = http_status
    row.last_error = None
    row.last_error_type = None
    if events_returned == 0:
        row.last_error_type = "empty"
    row.updated_at = datetime.utcnow()


def mark_failure(
    db: Session,
    source_id: str,
    error: str,
    *,
    http_status: Optional[int] = None,
    restricted: bool = False,
    error_type: Optional[str] = None,
) -> None:
    row = _health(db, source_id)
    row.consecutive_failures = int(row.consecutive_failures or 0) + 1
    row.last_failure_at = datetime.utcnow()
    row.last_error = error
    row.last_http_status = http_status
    row.last_error_type = error_type or ("restricted" if restricted else "error")
    row.status = "failed" if restricted or row.consecutive_failures >= 5 else "degraded"
    row.updated_at = datetime.utcnow()


def record_competition_health(
    db: Session,
    competition_id: str,
    *,
    primary_status: str,
    fallback_status: str = "unused",
    active_source_id: Optional[str] = None,
    events_ingested: int = 0,
    duplicates_merged: int = 0,
    error: Optional[str] = None,
    classification: Optional[str] = None,
    success: bool = False,
) -> None:
    cache = db.info.setdefault("competition_health", {})
    row = cache.get(competition_id)
    if row is None:
        row = db.get(SportsCompetitionHealth, competition_id)
    if row is None:
        for pending in db.new:
            if isinstance(pending, SportsCompetitionHealth) and pending.competition_id == competition_id:
                row = pending
                break
    if row is None:
        row = db.query(SportsCompetitionHealth).filter_by(competition_id=competition_id).first()
    if row is None:
        row = SportsCompetitionHealth(competition_id=competition_id)
        db.add(row)
    cache[competition_id] = row
    row.primary_status = primary_status
    row.fallback_status = fallback_status
    row.active_source_id = active_source_id
    row.last_attempt_at = datetime.utcnow()
    row.events_ingested = int(row.events_ingested or 0) + events_ingested
    row.duplicates_merged = int(row.duplicates_merged or 0) + duplicates_merged
    row.last_error = error
    row.last_classification = classification
    if success:
        row.last_success_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()


def record_ingestion_error(
    db: Session,
    *,
    competition_id: Optional[str],
    source_id: Optional[str],
    error_type: str,
    message: str,
    run_id: Optional[int] = None,
) -> None:
    db.add(
        SportsIngestionError(
            run_id=run_id,
            competition_id=competition_id,
            source_id=source_id,
            error_type=error_type,
            message=message,
        )
    )
