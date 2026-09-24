"""Official ACB Liga Endesa season breadth.

Fetches the public full-season calendar once per refresh window and persists
every published fixture/result. When ACB exposes only the date (XX:XX), the
event is explicitly DATE_ONLY so the public UI renders TBD instead of a fake
kickoff time.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_official import parse_acb
from collector.http import fetch_text
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime

JOB_KEY = "acb-season-breadth-v1"
COMPETITION_ID = "spain-acb"
CALENDAR_URL = "https://www.acb.com/es/liga/calendario"


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    rows = (
        db.query(SportsSource)
        .filter(SportsSource.adapter_key == "acb-html", SportsSource.enabled.is_(True))
        .all()
    )
    return next((row for row in rows if source_collectable(row)), None)


def _ensure_mapping(db: Session, source: SportsSource) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, COMPETITION_ID)
    if competition is None:
        competition = SportsCompetition(
            competition_id=COMPETITION_ID,
            sport_id="basketball",
            name="Liga Endesa",
            official_name="Liga Endesa",
            slug=COMPETITION_ID,
            country_id="ESP",
            region_id="europe",
            event_model="team_match",
            competition_type="league",
            country_based=True,
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()

    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=COMPETITION_ID, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=COMPETITION_ID,
            source_id=source.source_id,
            priority=12,
            source_competition_id=COMPETITION_ID,
            enabled=True,
            coverage_scope="full",
            coverage_notes="Official ACB full-season public calendar",
            verification="acb.com Liga Endesa calendar",
            polling_class="SLOW",
            source_config_json=dump_json({"url": CALENDAR_URL}),
            independence_status="established",
            upstream_family="acb-web",
        )
        db.add(mapping)
        db.flush()
    return mapping


def _date_only_midday(raw: Any) -> Optional[str]:
    stamp = parse_datetime(raw)
    if stamp is None:
        return None
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    # Midday UTC is a neutral storage anchor for a date-only Spanish fixture.
    # The public payload carries DATE_ONLY and therefore renders TBD, not 12:00.
    return stamp.replace(hour=12, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_acb_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    home = raw.get("home") if isinstance(raw.get("home"), dict) else {}
    away = raw.get("away") if isinstance(raw.get("away"), dict) else {}
    home_name = str(home.get("name") or "").strip()
    away_name = str(away.get("name") or "").strip()
    start_time = _date_only_midday(raw.get("start_time"))
    if not home_name or not away_name or not start_time:
        return None

    day = start_time[:10]
    source_event_id = hashlib.sha1(
        f"{day}|{home_name.lower()}|{away_name.lower()}".encode("utf-8")
    ).hexdigest()[:24]

    extra = dict(raw.get("extra") or {})
    extra.update(
        {
            "source_family": "acb-web",
            "source_event_id": source_event_id,
            "source_event_ids": {"acb-web": source_event_id},
            "source_competition_id": COMPETITION_ID,
            "source_competition_name": "Liga Endesa",
            "public_competition_key": COMPETITION_ID,
            "start_date": day,
            "start_precision": "DATE_ONLY",
        }
    )
    return {
        **raw,
        "id": f"acb:{source_event_id}",
        "source_event_id": source_event_id,
        "source_event_ids": {"acb-web": source_event_id},
        "sport": "basketball",
        "event_family": "team_match",
        "competition": "Liga Endesa",
        "competition_key": COMPETITION_ID,
        "source_family": "acb-web",
        "source_competition_id": COMPETITION_ID,
        "source_competition_name": "Liga Endesa",
        "start_time": start_time,
        "start_date": day,
        "start_precision": "DATE_ONLY",
        "extra": extra,
    }


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_ingest: int = 500,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    result = getter(CALENDAR_URL)
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 1,
        "http_status": int(getattr(result, "http_status", 0) or 0),
        "events": 0,
        "eligible": 0,
        "ingested": 0,
    }
    if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), str):
        stats["status"] = "unavailable"
        return stats

    mapping = _ensure_mapping(db, source)
    parsed = parse_acb(result.payload)
    stats["events"] = len(parsed)

    for raw in parsed:
        event = normalize_acb_event(raw)
        if event is None:
            continue
        stats["eligible"] += 1
        if _ingest(db, event, mapping.source_id):
            stats["ingested"] += 1
        if stats["ingested"] >= max_ingest:
            stats["status"] = "bounded"
            break

    db.commit()
    if heartbeat:
        heartbeat()
    cache_clear(db, prefix="events:")

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
    min_interval_hours: int = 6,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    text_getter=None,
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
    return run_breadth_ingest(
        db,
        text_getter=text_getter,
        heartbeat=heartbeat,
    )
