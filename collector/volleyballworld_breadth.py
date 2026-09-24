"""Global Volleyball World breadth from the official competition sitemap."""

from __future__ import annotations

import hashlib
import html as html_lib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from collector.adapters import FetchRequest
from collector.adapters_volleyballworld import BASE, VolleyballWorldAdapter
from collector.http import fetch_text
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "volleyballworld-global-breadth-v1"
SOURCE_ID = "volleyballworld-global"
SITEMAP_URL = f"{BASE}/sitemap.xml"
COMP_RE = re.compile(
    r"https://en\.volleyballworld\.com/volleyball/competitions/(?P<slug>[a-z0-9-]+)/",
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

PRIORITY_SLUGS = (
    "volleyball-nations-league",
    "avc-men-nations-cup",
    "avc-women-nations-cup",
)


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    row = db.get(SportsSource, SOURCE_ID)
    if row is not None and source_collectable(row):
        return row
    return None


def discover_competition_slugs(sitemap: str, *, max_slugs: int = 32) -> List[str]:
    counts: Dict[str, int] = {}
    for match in COMP_RE.finditer(sitemap or ""):
        slug = match.group("slug").lower()
        counts[slug] = counts.get(slug, 0) + 1
    ordered: List[str] = []
    for slug in PRIORITY_SLUGS:
        if slug in counts:
            ordered.append(slug)
    remaining = sorted(
        (slug for slug in counts if slug not in ordered),
        key=lambda slug: (-counts[slug], slug),
    )
    ordered.extend(remaining)
    return ordered[:max_slugs]


def _title(html: str, slug: str) -> str:
    match = TITLE_RE.search(html or "")
    if match:
        raw = re.sub(r"<[^>]+>", " ", match.group(1))
        title = re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()
        title = re.sub(r"\s*[|\-–]\s*Volleyball World.*$", "", title, flags=re.I).strip()
        title = re.sub(r"\s*Schedule(?:\s*&\s*Results)?\s*$", "", title, flags=re.I).strip()
        if title:
            return title
    return slug.replace("-", " ").title()


def _competition_id(slug: str) -> str:
    return f"volleyball-vw-{slugify(slug)}"[:120].rstrip("-")


def _stable_event(
    row: Dict[str, Any],
    *,
    competition_id: str,
    competition_name: str,
    slug: str,
) -> Optional[Dict[str, Any]]:
    home = row.get("home") if isinstance(row.get("home"), dict) else {}
    away = row.get("away") if isinstance(row.get("away"), dict) else {}
    home_name = str(home.get("name") or "").strip()
    away_name = str(away.get("name") or "").strip()
    start = str(row.get("start_time") or "").strip()
    if not home_name or not away_name:
        return None

    existing = str(row.get("source_event_id") or row.get("id") or "").strip()
    if existing:
        source_event_id = existing
    else:
        material = f"{competition_id}|{start}|{home_name.casefold()}|{away_name.casefold()}"
        source_event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]

    extra = dict(row.get("extra") or {})
    extra.update(
        {
            "source_family": "volleyballworld",
            "source_event_id": source_event_id,
            "source_event_ids": {"volleyballworld": source_event_id},
            "source_competition_id": slug,
            "source_competition_name": competition_name,
            "public_competition_key": competition_id,
            "volleyballworld_slug": slug,
        }
    )
    out = dict(row)
    out.update(
        {
            "id": f"volleyballworld:{source_event_id}",
            "source_event_id": source_event_id,
            "source_event_ids": {"volleyballworld": source_event_id},
            "sport": "volleyball",
            "event_family": "team_match",
            "competition": competition_name,
            "competition_key": competition_id,
            "source_family": "volleyballworld",
            "source_competition_id": slug,
            "source_competition_name": competition_name,
            "extra": extra,
        }
    )
    return out


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
    slug: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="volleyball",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            region_id="world",
            event_model="team_match",
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
            source_competition_id=slug,
            enabled=True,
            coverage_scope="full",
            coverage_notes="Volleyball World official current competition schedule/results",
            verification="Volleyball World sitemap + competition schedule",
            polling_class="MEDIUM",
            source_config_json=dump_json(
                {
                    "slug": slug,
                    "url": f"{BASE}/volleyball/competitions/{slug}/schedule/",
                    "source_competition_name": competition_name,
                }
            ),
            independence_status="established",
            upstream_family="volleyballworld",
        )
        db.add(mapping)
        db.flush()
    return mapping


def _in_window(event: Dict[str, Any], *, now: datetime) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return False
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.replace(tzinfo=None)
    return now - timedelta(days=45) <= stamp <= now + timedelta(days=220)


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_slugs: int = 24,
    max_ingest: int = 1800,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "slugs": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    adapter = VolleyballWorldAdapter(source_id=source.source_id, text_getter=getter)
    now = datetime.utcnow()
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "slugs": 0,
        "active_slugs": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "http_errors": 0,
        "by_competition": {},
    }
    seen_competitions: Set[str] = set()

    sitemap = getter(SITEMAP_URL)
    stats["requests"] += 1
    sitemap_text = (
        sitemap.payload
        if getattr(sitemap, "ok", False) and isinstance(getattr(sitemap, "payload", None), str)
        else ""
    )
    if not sitemap_text:
        stats["http_errors"] += 1
    slugs = discover_competition_slugs(sitemap_text, max_slugs=max_slugs)
    stats["slugs"] = len(slugs)

    for slug in slugs:
        if stats["ingested"] >= max_ingest:
            stats["status"] = "bounded"
            break

        landing_url = f"{BASE}/volleyball/competitions/{slug}/"
        landing = adapter._get(landing_url)
        stats["requests"] += 1
        if not landing.ok or not isinstance(landing.payload, str):
            stats["http_errors"] += 1
            continue
        # Ignore stale archive-only competition pages. Current official pages
        # normally expose the season year in title/body/schedule metadata.
        if "2026" not in landing.payload:
            continue

        competition_name = _title(landing.payload, slug)
        competition_id = _competition_id(slug)
        result = adapter.fetch(
            FetchRequest(
                capability="snapshot",
                sport_id="volleyball",
                competition_id=competition_id,
                source_config={
                    "slug": slug,
                    "url": f"{BASE}/volleyball/competitions/{slug}/schedule/",
                    "tokens": (competition_name, slug),
                },
            )
        )
        stats["requests"] += int(result.request_count or 1)
        rows: List[Dict[str, Any]] = []
        for raw in result.events or []:
            event = _stable_event(
                raw,
                competition_id=competition_id,
                competition_name=competition_name,
                slug=slug,
            )
            if event:
                rows.append(event)
        if not rows:
            continue

        stats["active_slugs"] += 1
        stats["events"] += len(rows)
        _ensure_mapping(
            db,
            source=source,
            competition_id=competition_id,
            competition_name=competition_name,
            slug=slug,
        )
        seen_competitions.add(competition_id)
        bucket = stats["by_competition"].setdefault(
            competition_id,
            {"events": 0, "eligible": 0, "ingested": 0},
        )
        bucket["events"] += len(rows)

        for event in rows:
            if not _in_window(event, now=now):
                continue
            stats["eligible"] += 1
            bucket["eligible"] += 1
            if _ingest(db, event, source.source_id):
                stats["ingested"] += 1
                bucket["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                break

        db.commit()
        if heartbeat:
            heartbeat()

    stats["competitions"] = len(seen_competitions)
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
    min_interval_minutes: int = 120,
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
    return run_breadth_ingest(db, text_getter=text_getter, heartbeat=heartbeat)
