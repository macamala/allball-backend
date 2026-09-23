"""Persistent SportScore breadth discovery for basketball, tennis and cricket.

The public /matches board is production-proven for these three sports. It is
used as a live/current-day breadth source. Dynamic competition IDs are derived
from sport + full upstream label + competition-logo fingerprint. Ambiguous
generic labels are deliberately excluded rather than merged incorrectly.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_sportscore import MATCHES_URL, _payload_matches, match_to_event
from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.util import dump_json, load_json, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "sportscore-multisport-breadth-v1"
SPORTS = ("basketball", "tennis", "cricket")
GENERIC_LABELS = {
    "club friendship",
    "friendship",
    "friendly",
    "friendlies",
    "international friendly",
    "national basketball league",
    "premier league",
    "cup",
    "league",
}


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    return (
        db.query(SportsSource)
        .filter(SportsSource.adapter_key == "sportscore", SportsSource.enabled.is_(True))
        .first()
    )


def _identity_material(row: Dict[str, Any]) -> Tuple[str, str]:
    name = str(row.get("competition") or "").strip()
    logo = str(row.get("competition_logo") or "").strip()
    return name, logo


def source_native_identity(
    sport_id: str,
    row: Dict[str, Any],
) -> Tuple[Optional[str], str, str]:
    name, logo = _identity_material(row)
    label = slugify(name)
    if not name or not label:
        return None, name, ""

    # A provider board can reuse very generic labels across countries. Without
    # provider country/id metadata it is safer to skip those than to merge them.
    if name.lower().strip() in GENERIC_LABELS and not logo:
        return None, name, ""

    # Logo is provider-owned identity evidence when available. For specific
    # labels, the full label itself is already a stable upstream identity.
    material = f"{sport_id}|{name.casefold()}|{logo}"
    digest = hashlib.sha1(material.encode("utf-8")).hexdigest()[:10]
    max_label = max(12, 118 - len(sport_id) - len(digest) - 5)
    competition_id = f"{sport_id}-ss-{digest}-{label[:max_label]}".rstrip("-")
    return competition_id[:120], name, digest


def _event_model(sport_id: str) -> str:
    if sport_id == "tennis":
        return "head_to_head"
    return "team_match"


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    sport_id: str,
    competition_name: str,
    source_identity: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id=sport_id,
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            country_id=None,
            region_id="world",
            event_model=_event_model(sport_id),
            competition_type="tournament" if sport_id == "tennis" else "league",
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
            priority=950,
            source_competition_id=source_identity,
            enabled=True,
            coverage_scope="partial",
            coverage_notes="SportScore live/current-day source-native breadth",
            verification="production /matches board + stable competition label/logo identity",
            polling_class="FAST",
            source_config_json=dump_json(
                {
                    "sportscore_sport": sport_id,
                    "source_competition_name": competition_name,
                    "source_identity": source_identity,
                }
            ),
            independence_status="single-source-breadth",
            upstream_family="sportscore",
        )
        db.add(mapping)
        db.flush()
    return mapping


def run_breadth_ingest(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "ingested": 0, "sports": {}}

    fetch = getter or fetch_url
    stats: Dict[str, Any] = {
        "status": "ok",
        "upstream_total": 0,
        "eligible": 0,
        "ingested": 0,
        "skipped_ambiguous": 0,
        "sports": {},
    }

    for sport_id in SPORTS:
        result = fetch(MATCHES_URL.format(sport=sport_id, limit=50))
        rows = _payload_matches(result.payload) if getattr(result, "ok", False) else []
        sport_stats: Dict[str, Any] = {
            "http_status": int(getattr(result, "http_status", 0) or 0),
            "upstream": len(rows),
            "eligible": 0,
            "ingested": 0,
            "competitions": 0,
            "skipped_ambiguous": 0,
        }
        stats["upstream_total"] += len(rows)
        seen_competitions = set()

        for row in rows:
            competition_id, competition_name, source_identity = source_native_identity(sport_id, row)
            if not competition_id:
                sport_stats["skipped_ambiguous"] += 1
                stats["skipped_ambiguous"] += 1
                continue

            mapping = _ensure_mapping(
                db,
                source=source,
                competition_id=competition_id,
                sport_id=sport_id,
                competition_name=competition_name,
                source_identity=source_identity,
            )
            event = match_to_event(row, competition_id)
            if not event or not event.get("start_time"):
                continue

            event["competition"] = competition_name
            event["competition_key"] = competition_id
            event["source_family"] = "sportscore"
            event["source_competition_id"] = source_identity
            extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
            extra.update(
                {
                    "source_family": "sportscore",
                    "upstream_family": "thesports",
                    "source_competition_id": source_identity,
                    "source_competition_name": competition_name,
                    "public_competition_key": competition_id,
                    "sportscore_competition_logo": row.get("competition_logo"),
                }
            )
            event["extra"] = extra
            sport_stats["eligible"] += 1
            stats["eligible"] += 1
            seen_competitions.add(competition_id)
            if _ingest(db, event, mapping.source_id):
                sport_stats["ingested"] += 1
                stats["ingested"] += 1

        sport_stats["competitions"] = len(seen_competitions)
        stats["sports"][sport_id] = sport_stats
        db.commit()
        if heartbeat:
            heartbeat()

    job = _job(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int(stats["ingested"])
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats


def run_if_due(
    db: Session,
    *,
    min_interval_minutes: int = 5,
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
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
    ):
        return None

    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(db, getter=getter, heartbeat=heartbeat)
