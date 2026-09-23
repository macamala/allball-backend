"""Persistent SportScore breadth discovery for basketball, tennis and cricket.

The public /matches board is production-proven for these three sports. It is
used as a live/current-day breadth source. Dynamic competition IDs are derived
from sport + full upstream label + competition-logo fingerprint. Ambiguous
generic labels are deliberately excluded rather than merged incorrectly.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from collector.adapters_sportscore import MATCHES_URL, TEAM_URL, _payload_matches, match_to_event
from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.util import dump_json, load_json, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "sportscore-multisport-breadth-v1"
SCHEDULE_JOB_KEY = "sportscore-team-schedule-v2"
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


def _schedule_job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, SCHEDULE_JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=SCHEDULE_JOB_KEY, last_status="pending")
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

    # A provider board can reuse very generic labels across countries.
    # Specific full competition names are stable enough on their own and must
    # remain identical between /matches and /team responses (the latter often
    # omits competition_logo). Generic names require logo evidence.
    generic = name.lower().strip() in GENERIC_LABELS
    if generic and not logo:
        return None, name, ""

    material = f"{sport_id}|{name.casefold()}"
    if generic:
        material += f"|{logo}"
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


def repair_missing_sport_ids(db: Session) -> Dict[str, int]:
    """Repair only SportScore source-native rows whose ID encodes an allowed sport."""
    from collector.models import SportsEvent

    repaired: Dict[str, int] = {}
    for sport_id in SPORTS:
        prefix = f"{sport_id}-ss-%"
        rows = (
            db.query(SportsEvent)
            .filter(
                SportsEvent.competition_id.like(prefix),
                SportsEvent.sport_id.in_(["", "unknown"]),
            )
            .all()
        )
        for row in rows:
            extra = load_json(row.extra_json, {}) or {}
            if str(extra.get("source_family") or "") != "sportscore":
                continue
            row.sport_id = sport_id
            repaired[sport_id] = repaired.get(sport_id, 0) + 1
    if repaired:
        db.commit()
    return repaired


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

    repaired = repair_missing_sport_ids(db)
    fetch = getter or fetch_url
    stats: Dict[str, Any] = {
        "status": "ok",
        "upstream_total": 0,
        "eligible": 0,
        "ingested": 0,
        "skipped_ambiguous": 0,
        "sports": {},
        "repaired_missing_sport": repaired,
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

            event["sport"] = sport_id
            event["sport_id"] = sport_id
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


def _match_team_slugs(row: Dict[str, Any]) -> List[str]:
    from urllib.parse import urlparse

    raw = str(row.get("url") or "").strip()
    path = urlparse(raw).path.rstrip("/") if raw else ""
    slug = path.rsplit("/", 1)[-1] if path else ""
    if "-vs-" not in slug:
        return []
    left, right = slug.split("-vs-", 1)
    return [part for part in (left.strip(), right.strip()) if part]


def _parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _schedule_window(row: Dict[str, Any], *, now: datetime) -> bool:
    stamp = _parse_iso(row.get("time"))
    if stamp is None:
        return False
    return now - timedelta(hours=18) <= stamp <= now + timedelta(days=21)


def run_team_schedule_backfill(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_team_requests: int = 220,
) -> Dict[str, Any]:
    """Slow recent+upcoming backfill using team/player slugs discovered on active boards."""
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "ingested": 0, "sports": {}}

    repaired = repair_missing_sport_ids(db)
    fetch = getter or fetch_url
    now = datetime.now(timezone.utc)
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "upstream_total": 0,
        "eligible": 0,
        "ingested": 0,
        "sports": {},
        "repaired_missing_sport": repaired,
    }

    for sport_id in SPORTS:
        board = fetch(MATCHES_URL.format(sport=sport_id, limit=50))
        board_rows = _payload_matches(board.payload) if getattr(board, "ok", False) else []
        team_slugs: List[str] = []
        seen_slugs: Set[str] = set()
        for row in board_rows:
            for slug in _match_team_slugs(row):
                if slug in seen_slugs:
                    continue
                seen_slugs.add(slug)
                team_slugs.append(slug)

        sport_stats: Dict[str, Any] = {
            "board_status": int(getattr(board, "http_status", 0) or 0),
            "discovered_slugs": len(team_slugs),
            "requests": 0,
            "upstream": 0,
            "eligible": 0,
            "ingested": 0,
            "future": 0,
            "competitions": 0,
        }
        seen_competitions: Set[str] = set()
        seen_matches: Set[str] = set()

        for idx, team_slug in enumerate(team_slugs):
            if stats["requests"] >= max_team_requests:
                stats["status"] = "bounded"
                break
            result = fetch(TEAM_URL.format(sport=sport_id, slug=team_slug))
            stats["requests"] += 1
            sport_stats["requests"] += 1
            if not getattr(result, "ok", False):
                continue
            rows = _payload_matches(result.payload)
            stats["upstream_total"] += len(rows)
            sport_stats["upstream"] += len(rows)

            for row in rows:
                if not _schedule_window(row, now=now):
                    continue
                row_key = str(row.get("url") or "") + "|" + str(row.get("time") or "")
                if row_key in seen_matches:
                    continue
                seen_matches.add(row_key)

                competition_id, competition_name, source_identity = source_native_identity(sport_id, row)
                if not competition_id:
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
                event["sport"] = sport_id
                event["sport_id"] = sport_id
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
                        "sportscore_team_schedule": True,
                        "sportscore_team_slug": team_slug,
                    }
                )
                event["extra"] = extra
                seen_competitions.add(competition_id)
                stats["eligible"] += 1
                sport_stats["eligible"] += 1
                stamp = _parse_iso(row.get("time"))
                if stamp and stamp > now:
                    sport_stats["future"] += 1
                if _ingest(db, event, mapping.source_id):
                    stats["ingested"] += 1
                    sport_stats["ingested"] += 1

            if heartbeat and (idx + 1) % 12 == 0:
                db.commit()
                heartbeat()

        sport_stats["competitions"] = len(seen_competitions)
        stats["sports"][sport_id] = sport_stats
        db.commit()
        if heartbeat:
            heartbeat()
        if stats["status"] == "bounded":
            break

    job = _schedule_job(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = stats["status"]
    job.items_written = int(stats["ingested"])
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats


def run_team_schedule_if_due(
    db: Session,
    *,
    min_interval_hours: int = 4,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    getter=None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None
    job = _schedule_job(db)
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
    return run_team_schedule_backfill(db, getter=getter, heartbeat=heartbeat)


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
