"""Internal collector diagnostics. No secrets."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from collector.models import (
    SportsCompetition,
    SportsCompetitionHealth,
    SportsEvent,
    SportsIngestionRun,
    SportsSource,
    SportsSourceCompetition,
    SportsSourceHealth,
)
from collector.registry import build_runtime_registry
from collector.util import isoformat, load_json


def source_health_payload(db: Session) -> Dict[str, Any]:
    rows = []
    for source in db.query(SportsSource).all():
        health = db.query(SportsSourceHealth).filter_by(source_id=source.source_id).first()
        rows.append(
            {
                "source_id": source.source_id,
                "family": source.upstream_family,
                "adapter": source.adapter_key,
                "enabled": source.enabled,
                "status": health.status if health else "unknown",
                "last_attempt_at": isoformat(health.last_attempt_at) if health else None,
                "last_success_at": isoformat(health.last_success_at) if health else None,
                "last_failure_at": isoformat(health.last_failure_at) if health else None,
                "last_http_status": health.last_http_status if health else None,
                "last_latency_ms": health.last_latency_ms if health else None,
                "last_parse_status": health.last_parse_status if health else None,
                "last_events_returned": health.last_events_returned if health else None,
                "last_error_type": health.last_error_type if health else None,
                "consecutive_failures": health.consecutive_failures if health else 0,
                "requires_credentials": bool(source.requires_credentials),
            }
        )
    return {"items": rows, "count": len(rows)}


def competition_health_payload(db: Session) -> Dict[str, Any]:
    items = []
    for row in db.query(SportsCompetitionHealth).all():
        competition = db.query(SportsCompetition).filter_by(competition_id=row.competition_id).first()
        event_count = db.query(SportsEvent).filter_by(competition_id=row.competition_id).count()
        items.append(
            {
                "competition_id": row.competition_id,
                "sport": competition.sport_id if competition else None,
                "primary_status": row.primary_status,
                "fallback_status": row.fallback_status,
                "active_source": row.active_source_id,
                "last_attempt_at": isoformat(row.last_attempt_at),
                "last_success_at": isoformat(row.last_success_at),
                "events_ingested": row.events_ingested,
                "events_stored": event_count,
                "duplicates_merged": row.duplicates_merged,
                "classification": row.last_classification,
                "error": row.last_error,
            }
        )
    return {"items": items, "count": len(items)}


def coverage_payload() -> Dict[str, Any]:
    runtime = build_runtime_registry()
    competitions = []
    for item in runtime["competitions"].values():
        competitions.append(
            {
                "competition_id": item["competition_id"],
                "sport": item["sport"],
                "primary_source": item.get("primary_source"),
                "fallback_sources": item.get("fallback_sources") or [],
                "sources": [
                    {
                        "source_id": row["source_id"],
                        "family": row["source_family"],
                        "coverage": row["coverage"],
                        "priority": row["priority"],
                        "independent": row.get("independent"),
                        "enabled": row.get("enabled"),
                        "adapter": row.get("adapter_key"),
                        "notes": row.get("coverage_notes"),
                    }
                    for row in item["sources"]
                ],
            }
        )
    return {"counts": runtime["counts"], "competitions": competitions}


def freshness_payload(db: Session) -> Dict[str, Any]:
    now = datetime.utcnow()
    live = db.query(SportsEvent).filter_by(status="live").count()
    upcoming = (
        db.query(SportsEvent)
        .filter(SportsEvent.status == "scheduled", SportsEvent.start_time >= now)
        .count()
    )
    recent = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.status == "finished",
            SportsEvent.start_time >= now - timedelta(days=7),
        )
        .count()
    )
    return {"live": live, "upcoming": upcoming, "recent": recent, "total": db.query(SportsEvent).count()}


def _family_status_label(classification: str, http_status: Optional[int] = None) -> str:
    text = (classification or "").upper()
    if "RATE_LIMIT" in text:
        return "RATE_LIMITED"
    if text in {"ACCESS_BLOCKED"} or http_status in {401, 403}:
        return "ACCESS_BLOCKED"
    if text in {"SOURCE_CHANGED"}:
        return "BLOCKED"
    if "NETWORK" in text:
        return "NETWORK_ERROR"
    if "PARSE" in text:
        return "PARSER_ERROR"
    if text in {"NO_CURRENT_EVENTS", "WORKING_EMPTY"}:
        return "EMPTY"
    if text in {"WORKING_PARTIAL", "DEGRADED"} or "FAIL" in text:
        return "DEGRADED"
    if text in {"WORKING_WITH_EVENTS", "WORKING_FULL", "ok", "OK"} or "WORKING" in text:
        return "HEALTHY"
    return text or "UNKNOWN"


def results_health_payload(db: Session) -> Dict[str, Any]:
    from collector.family_health import snapshot as family_snapshot
    from collector.flags import flags_payload
    from collector.lock import lock_status
    from collector.matrix_guard import matrix_status
    from collector.models import SportsIngestionRun, SportsSchedulerLease  # noqa: F401

    last = (
        db.query(SportsIngestionRun)
        .order_by(SportsIngestionRun.started_at.desc())
        .first()
    )
    families: Dict[str, Dict[str, Any]] = {}
    for mapping in db.query(SportsSourceCompetition).filter_by(enabled=True).all():
        family = mapping.upstream_family or "unknown"
        health = db.query(SportsCompetitionHealth).filter_by(competition_id=mapping.competition_id).first()
        bucket = _family_status_label(health.last_classification if health else "", None)
        row = families.setdefault(
            family,
            {
                "family": family,
                "status": bucket,
                "competitions": 0,
                "classifications": {},
            },
        )
        row["competitions"] += 1
        row["classifications"][bucket] = int(row["classifications"].get(bucket) or 0) + 1
        if bucket == "RATE_LIMITED":
            row["status"] = "RATE_LIMITED"
        elif row["status"] not in {"RATE_LIMITED", "BLOCKED"} and bucket in {"BLOCKED", "NETWORK_ERROR", "PARSER_ERROR", "DEGRADED"}:
            row["status"] = bucket
    duration = None
    if last and last.started_at and last.finished_at:
        duration = (last.finished_at - last.started_at).total_seconds()
    latest_event = db.query(SportsEvent).order_by(SportsEvent.retrieved_at.desc()).first()
    return {
        "flags": flags_payload(),
        "matrix": matrix_status(),
        "scheduler": lock_status(db),
        "last_run": {
            "id": last.id if last else None,
            "status": last.status if last else None,
            "started_at": isoformat(last.started_at) if last else None,
            "finished_at": isoformat(last.finished_at) if last else None,
            "duration_s": duration,
            "events_written": last.events_written if last else 0,
            "errors": last.errors if last else 0,
        },
        "last_event_received": isoformat(latest_event.retrieved_at) if latest_event and latest_event.retrieved_at else None,
        "families": list(families.values()),
        "in_process_family_health": family_snapshot(),
        "freshness": freshness_payload(db),
        "incremental": __import__("collector.incremental", fromlist=["scheduler_snapshot"]).scheduler_snapshot(db),
    }
