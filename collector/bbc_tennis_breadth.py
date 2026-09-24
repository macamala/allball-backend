"""Global BBC tennis dated-board breadth.

BBC's public tennis Scores & Schedule page groups the day's matches by real
tournament name. The normal per-competition adapter historically filtered
those groups through the umbrella atp-tour/wta-tour IDs, which loses breadth.
This collector keeps each tournament as source-native NinkoSports identity.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_bbc import extract_bbc_events
from collector.competition_identity import unique_label_competition
from collector.html_parse import _quoted_window_json
from collector.http import fetch_text
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "bbc-tennis-breadth-v3"
BASE = "https://www.bbc.com/sport/tennis/scores-and-schedule"


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    row = db.get(SportsSource, "bbc-tennis-global")
    return row if row is not None and row.enabled and source_collectable(row) else None


def _competition_id(name: str) -> str:
    canonical = unique_label_competition(name, sport_id="tennis")
    if canonical:
        return canonical
    suffix = slugify(name)
    digest = hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"tennis-bbc-{digest}-{suffix}"[:120].rstrip("-")


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="tennis",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            region_id="world",
            event_model="individual_match",
            competition_type="tournament",
            country_based=False,
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
            priority=12,
            source_competition_id=slugify(competition_name),
            enabled=True,
            coverage_scope="full",
            coverage_notes="BBC Tennis Scores & Schedule public dated board",
            verification="BBC public Scores & Schedule grouped tournament",
            polling_class="MEDIUM",
            source_config_json=dump_json({
                "url": BASE,
                "source_competition_name": competition_name,
            }),
            independence_status="established",
            upstream_family="bbc-sport",
        )
        db.add(mapping)
        db.flush()
    return mapping


def parse_bbc_tennis_html(html: str) -> List[Dict[str, Any]]:
    data = _quoted_window_json(html or "", "__INITIAL_DATA__")
    if data is None:
        return []
    rows = extract_bbc_events(data, "")
    events: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("source_competition_name") or row.get("competition") or "").strip()
        home = row.get("home") or {}
        away = row.get("away") or {}
        home_name = home.get("name") if isinstance(home, dict) else str(home or "")
        away_name = away.get("name") if isinstance(away, dict) else str(away or "")
        if not name or not home_name or not away_name:
            continue
        competition_id = _competition_id(name)
        source_event_id = str(row.get("id") or "").strip()
        if not source_event_id:
            material = f"{competition_id}|{row.get('start_time')}|{home_name}|{away_name}"
            source_event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]
        event = dict(row)
        event.update({
            "id": f"bbc-tennis:{source_event_id}",
            "source_event_id": source_event_id,
            "source_event_ids": {"bbc-sport": source_event_id},
            "sport": "tennis",
            "event_family": "individual_match",
            "competition": name,
            "competition_key": competition_id,
            "source_family": "bbc-sport",
            "source_competition_id": slugify(name),
            "source_competition_name": name,
        })
        extra = dict(event.get("extra") or {})
        extra.update({
            "source_family": "bbc-sport",
            "source_event_id": source_event_id,
            "source_event_ids": {"bbc-sport": source_event_id},
            "source_competition_id": slugify(name),
            "source_competition_name": name,
            "public_competition_key": competition_id,
        })
        event["extra"] = extra
        events.append(event)
    return events


def _in_window(event: Dict[str, Any], *, now: datetime, back: int = 1, forward: int = 4) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return True
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.replace(tzinfo=None)
    return now - timedelta(days=back) <= stamp <= now + timedelta(days=forward)


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    days_back: int = 1,
    days_forward: int = 4,
    max_ingest: int = 1600,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    now = datetime.utcnow()
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "http_errors": 0,
        "by_date": {},
    }
    competitions = set()

    for offset in range(-days_back, days_forward + 1):
        day = now.date() + timedelta(days=offset)
        url = f"{BASE}/{day.isoformat()}"
        result = getter(url)
        stats["requests"] += 1
        day_stats = {
            "http": int(getattr(result, "http_status", 0) or 0),
            "events": 0,
            "eligible": 0,
            "ingested": 0,
        }
        stats["by_date"][day.isoformat()] = day_stats
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), str):
            stats["http_errors"] += 1
            continue
        events = parse_bbc_tennis_html(result.payload)
        day_stats["events"] = len(events)
        stats["events"] += len(events)
        for event in events:
            if not _in_window(event, now=now, back=days_back + 1, forward=days_forward + 1):
                continue
            competition_id = str(event.get("competition_key") or "")
            competition_name = str(event.get("competition") or competition_id)
            if not competition_id:
                continue
            _ensure_mapping(
                db,
                source=source,
                competition_id=competition_id,
                competition_name=competition_name,
            )
            competitions.add(competition_id)
            stats["eligible"] += 1
            day_stats["eligible"] += 1
            if _ingest(db, event, source.source_id):
                stats["ingested"] += 1
                day_stats["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                stats["status"] = "bounded"
                break
        db.commit()
        if heartbeat:
            heartbeat()
        if stats["ingested"] >= max_ingest:
            break

    stats["competitions"] = len(competitions)
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
    min_interval_minutes: int = 60,
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
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
    ):
        return None
    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(
        db,
        heartbeat=heartbeat,
        text_getter=text_getter,
    )
