"""Bounded multi-sport breadth ingest from SofaScore dated sport boards."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_sofascore import SCHED_URL, sofa_event
from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.util import dump_json, load_json, slugify

logger = logging.getLogger(__name__)

JOB_ID = "sofascore-multisport-breadth-v1"

SOFA_BREADTH_SPORTS: Dict[str, str] = {
    "basketball": "basketball",
    "tennis": "tennis",
    "ice-hockey": "ice-hockey",
    "baseball": "baseball",
    "handball": "handball",
    "volleyball": "volleyball",
    "american-football": "american-football",
    "futsal": "futsal",
    "badminton": "badminton",
    "table-tennis": "table-tennis",
    "cricket": "cricket",
    "waterpolo": "water-polo",
    "netball": "netball",
    "field-hockey": "field-hockey",
    "darts": "darts",
    "snooker": "snooker",
}


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_ID)
    if row is None:
        row = SportsCollectorJob(job_id=JOB_ID, last_error=dump_json({"state": "pending"}))
        db.add(row)
        db.flush()
    return row


def board_dates(*, past_days: int = 1, future_days: int = 2) -> List[str]:
    today = datetime.now(timezone.utc).date()
    return [
        (today + timedelta(days=delta)).strftime("%Y-%m-%d")
        for delta in range(-past_days, future_days + 1)
    ]


def _tournament_parts(row: Dict[str, Any]) -> Tuple[str, str, str]:
    tour = row.get("tournament") if isinstance(row.get("tournament"), dict) else {}
    unique = tour.get("uniqueTournament") if isinstance(tour.get("uniqueTournament"), dict) else {}
    source = unique or tour
    tournament_id = str(source.get("id") or "").strip()
    name = str(source.get("name") or "").strip()
    category = tour.get("category") if isinstance(tour.get("category"), dict) else {}
    country = category.get("country") if isinstance(category.get("country"), dict) else {}
    country_id = str(
        country.get("alpha2")
        or country.get("alpha3")
        or country.get("name")
        or category.get("countryCode")
        or ""
    ).strip()
    return tournament_id, name, country_id


def source_native_identity(row: Dict[str, Any], sport_id: str) -> Tuple[Optional[str], str, str, str]:
    tournament_id, name, country_id = _tournament_parts(row)
    if not tournament_id or not name:
        return None, tournament_id, name, country_id
    geo = slugify(country_id)[:16] if country_id else "int"
    label = slugify(name)
    if not label:
        return None, tournament_id, name, country_id
    competition_id = f"{sport_id}-{geo}-{label}-t{slugify(tournament_id)}"
    return competition_id[:120], tournament_id, name, country_id


def _source(db: Session) -> Optional[SportsSource]:
    return (
        db.query(SportsSource)
        .filter(SportsSource.adapter_key == "sofascore-web", SportsSource.enabled.is_(True))
        .first()
    )


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    sport_id: str,
    sofa_sport: str,
    tournament_id: str,
    tournament_name: str,
    country_id: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id=sport_id,
            name=tournament_name,
            official_name=tournament_name,
            slug=competition_id,
            country_id=country_id.lower() if len(country_id) == 2 else (country_id or None),
            event_model="team_match",
            country_based=bool(country_id),
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()

    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=source.source_id,
            priority=950,
            source_competition_id=tournament_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="SofaScore source-native dated-board breadth",
            verification="provider tournament id + sport dated board",
            polling_class="NORMAL",
            source_config_json=dump_json(
                {
                    "sofascore_tournament_id": tournament_id,
                    "sofascore_tournament_name": tournament_name,
                    "sofascore_sport": sofa_sport,
                    "sport_id": sport_id,
                }
            ),
            independence_status="single-source-breadth",
            upstream_family="sofascore-web",
        )
        db.add(mapping)
        db.flush()
    return mapping


def run_breadth_ingest(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_ingest: int = 1600,
) -> Dict[str, Any]:
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "ingested": 0, "upstream_total": 0}

    fetch = getter or fetch_url
    dates = board_dates()
    stats: Dict[str, Any] = {
        "status": "ok",
        "dates": dates,
        "upstream_total": 0,
        "eligible": 0,
        "ingested": 0,
        "sports": {},
    }

    for sofa_sport, sport_id in SOFA_BREADTH_SPORTS.items():
        sport_stats = {"upstream": 0, "eligible": 0, "ingested": 0}
        for day in dates:
            result = fetch(SCHED_URL.format(sport=sofa_sport, date=day))
            payload = result.payload if getattr(result, "ok", False) and isinstance(result.payload, dict) else {}
            rows = [
                row
                for row in (payload.get("events") or [])
                if isinstance(row, dict) and row.get("id") is not None
            ]
            sport_stats["upstream"] += len(rows)
            stats["upstream_total"] += len(rows)
            for row in rows:
                if stats["ingested"] >= max_ingest:
                    break
                competition_id, tournament_id, tournament_name, country_id = source_native_identity(row, sport_id)
                if not competition_id:
                    continue
                event = sofa_event(row, competition_id, sport_id)
                if not event or not event.get("start_time"):
                    continue
                sport_stats["eligible"] += 1
                stats["eligible"] += 1
                mapping = _ensure_mapping(
                    db,
                    source=source,
                    competition_id=competition_id,
                    sport_id=sport_id,
                    sofa_sport=sofa_sport,
                    tournament_id=tournament_id,
                    tournament_name=tournament_name,
                    country_id=country_id,
                )
                event["competition"] = tournament_name
                event["competition_key"] = competition_id
                event["source_family"] = "sofascore-web"
                event["source_competition_id"] = tournament_id
                event["source_competition_name"] = tournament_name
                event["country_id"] = country_id or None
                extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
                extra.update(
                    {
                        "source_family": "sofascore-web",
                        "source_competition_id": tournament_id,
                        "source_competition_name": tournament_name,
                        "public_competition_key": competition_id,
                    }
                )
                event["extra"] = extra
                if _ingest(db, event, mapping.source_id):
                    sport_stats["ingested"] += 1
                    stats["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                break
        stats["sports"][sport_id] = sport_stats
        db.commit()
        if heartbeat:
            heartbeat()
        if stats["ingested"] >= max_ingest:
            stats["status"] = "bounded"
            break

    job = _job(db)
    job.last_run_at = datetime.utcnow()
    job.last_error = dump_json({"state": "done", "stats": stats})
    db.commit()
    return stats


def run_if_due(
    db: Session,
    *,
    min_interval_hours: int = 2,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    getter=None,
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
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(db, getter=getter, heartbeat=heartbeat)
