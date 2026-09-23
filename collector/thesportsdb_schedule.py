"""Registry-driven future fixture backfill for known TheSportsDB leagues."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from collector.adapters import FetchRequest
from collector.adapters_thesportsdb import TheSportsDbAdapter
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.util import dump_json, load_json

JOB_KEY = "thesportsdb-known-league-fixtures-v1"
TARGET_SPORTS = ("handball", "volleyball", "ice-hockey", "baseball")


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _mappings(db: Session):
    return (
        db.query(SportsSourceCompetition, SportsCompetition, SportsSource)
        .join(
            SportsCompetition,
            SportsCompetition.competition_id == SportsSourceCompetition.competition_id,
        )
        .join(
            SportsSource,
            SportsSource.source_id == SportsSourceCompetition.source_id,
        )
        .filter(
            SportsSourceCompetition.enabled.is_(True),
            SportsSource.enabled.is_(True),
            SportsSource.adapter_key == "thesportsdb",
            SportsCompetition.active.is_(True),
            SportsCompetition.sport_id.in_(TARGET_SPORTS),
        )
        .order_by(
            SportsCompetition.sport_id.asc(),
            SportsSourceCompetition.priority.asc(),
            SportsCompetition.competition_id.asc(),
        )
        .all()
    )


def run_backfill(
    db: Session,
    *,
    heartbeat: Optional[Callable[[], None]] = None,
    max_requests: int = 40,
) -> Dict[str, Any]:
    from collector.provider_crosswalk import _ingest

    rows = _mappings(db)
    stats: Dict[str, Any] = {
        "status": "ok",
        "mappings": len(rows),
        "requests": 0,
        "upstream_total": 0,
        "ingested": 0,
        "sports": {},
    }

    seen = set()
    for mapping, competition, source in rows:
        league_identity = str(mapping.source_competition_id or "").strip()
        dedupe_key = (source.source_id, competition.competition_id, league_identity)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if stats["requests"] >= max_requests:
            stats["status"] = "bounded"
            break

        sport_stats = stats["sports"].setdefault(
            competition.sport_id,
            {"mappings": 0, "requests": 0, "upstream": 0, "ingested": 0, "http": {}},
        )
        sport_stats["mappings"] += 1

        adapter = TheSportsDbAdapter(source_id=source.source_id)
        request = FetchRequest(
            capability="fixtures",
            sport_id=competition.sport_id,
            competition_id=competition.competition_id,
            source_competition_id=mapping.source_competition_id,
            source_config=load_json(mapping.source_config_json, {}) or {},
            coverage_scope=mapping.coverage_scope or "full",
            upstream_family=mapping.upstream_family or source.upstream_family or "thesportsdb",
        )
        result = adapter.fetch(request)
        stats["requests"] += 1
        sport_stats["requests"] += 1
        status_key = str(int(getattr(result, "http_status", 0) or 0))
        sport_stats["http"][status_key] = int(sport_stats["http"].get(status_key) or 0) + 1

        if int(getattr(result, "http_status", 0) or 0) == 429:
            stats["status"] = "rate_limited"
            break
        if not getattr(result, "ok", False):
            continue

        events = list(getattr(result, "events", None) or [])
        stats["upstream_total"] += len(events)
        sport_stats["upstream"] += len(events)
        for event in events:
            incoming = dict(event)
            incoming["sport"] = competition.sport_id
            incoming["sport_id"] = competition.sport_id
            incoming["competition"] = incoming.get("competition") or competition.name
            incoming["competition_key"] = competition.competition_id
            incoming["source_family"] = "thesportsdb"
            incoming["source_competition_id"] = (
                incoming.get("source_competition_id")
                or mapping.source_competition_id
            )
            extra = incoming.get("extra") if isinstance(incoming.get("extra"), dict) else {}
            extra.update(
                {
                    "source_family": "thesportsdb",
                    "source_competition_id": incoming.get("source_competition_id"),
                    "source_competition_name": incoming.get("source_competition_name")
                    or incoming.get("competition"),
                    "known_league_schedule": True,
                }
            )
            incoming["extra"] = extra
            if _ingest(db, incoming, mapping.source_id):
                stats["ingested"] += 1
                sport_stats["ingested"] += 1

        db.commit()
        if heartbeat and stats["requests"] % 6 == 0:
            heartbeat()

    job = _job(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = stats["status"]
    job.items_written = int(stats["ingested"])
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats


def run_if_due(
    db: Session,
    *,
    min_interval_hours: int = 2,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None

    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if (
        payload.get("state") == "done"
        and job.last_run_at
        and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours)
    ):
        return None

    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_backfill(db, heartbeat=heartbeat)
