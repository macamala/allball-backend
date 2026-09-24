"""Safely revalidate current source-native football rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from collector.competition_identity import correct_public_competition_id, unique_label_competition
from collector.competition_presentation import SOURCE_ALPHA3_TO_GEO, metadata_for
from collector.event_quality import reject_reason
from collector.list_extra import extra_for_list, store_list_extra
from collector.models import SportsCollectorJob, SportsEvent
from collector.util import dump_json, isoformat, load_json, slugify

JOB_KEY = "source-native-football-revalidate-v2"
SAFE_FAMILIES = {"fotmob", "fifa", "fifa-digital", "fifa-json"}
NON_BLOCKING_FLAGS = {
    "competition_attribution_mismatch",
    "participant_a:empty_name",
    "participant_b:empty_name",
}


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _country_geo(country_id: Any) -> str:
    raw = str(country_id or "").strip()
    if not raw or raw.upper() in {"INT", "WORLD", "GLOBAL"}:
        return ""
    return str(SOURCE_ALPHA3_TO_GEO.get(raw.upper(), raw.lower()) or "").strip()


def _country_token(country_id: Any) -> str:
    raw = str(country_id or "").strip()
    if not raw or raw.upper() in {"INT", "WORLD", "GLOBAL"}:
        return ""
    if len(raw) in {2, 3} and raw.isalpha():
        return raw.lower()
    return slugify(raw)


def _canonical_known_for_country(name: str, country_id: Any) -> Optional[str]:
    candidate = unique_label_competition(name, sport_id="football")
    if not candidate:
        return None
    source_geo = _country_geo(country_id)
    if not source_geo:
        return candidate
    meta = metadata_for(candidate, "football")
    candidate_geo = str(meta.get("country_code") or "").strip()
    return candidate if candidate_geo and candidate_geo == source_geo else None


def _merged_source_extra(row: SportsEvent) -> Dict[str, Any]:
    """Merge rich event metadata with the slim list metadata.

    Some migrations/backfills update list_extra_json without rewriting the
    larger extra_json blob. Source identity fields from list-extra are
    therefore authoritative when present.
    """
    extra = load_json(row.extra_json, {}) or {}
    slim = extra_for_list(row) or {}
    for key, value in slim.items():
        if value not in (None, "", [], {}):
            extra[key] = value
    return extra


def _safe_public_key(row: SportsEvent, extra: Dict[str, Any]) -> Optional[str]:
    family = str(extra.get("source_family") or "").strip()
    name = str(extra.get("source_competition_name") or "").strip()
    stored = str(extra.get("public_competition_key") or row.competition_id or "").strip()
    if family not in SAFE_FAMILIES or not name:
        return None

    if family == "fotmob":
        return correct_public_competition_id(
            stored_competition_id=stored,
            source_competition_name=name,
            sport_id="football",
            source_family=family,
        )

    known = _canonical_known_for_country(name, row.country_id)
    if known:
        return known
    suffix = slugify(name)
    if not suffix:
        return None
    geo = _country_token(row.country_id)
    return (f"football-{geo}-{suffix}" if geo else f"football-{suffix}")[:120].rstrip("-")


def _event_view(row: SportsEvent) -> Dict[str, Any]:
    participants = load_json(row.participants_json, {}) or {}
    return {
        "sport": "football",
        "competition": row.competition_id,
        "home": participants.get("home") or {},
        "away": participants.get("away") or {},
        "score": load_json(row.score_json, {}) or {},
        "start_time": isoformat(row.start_time),
    }


def revalidate_current_source_native(
    db: Session,
    *,
    days_back: int = 2,
    days_forward: int = 10,
) -> Dict[str, int]:
    now = datetime.utcnow()
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.canonical_event_id.is_(None),
            SportsEvent.display_eligible.is_(False),
            SportsEvent.start_time >= now - timedelta(days=days_back),
            SportsEvent.start_time <= now + timedelta(days=days_forward),
        )
        .all()
    )
    scanned = promoted = blocked = 0
    for row in rows:
        extra = _merged_source_extra(row)
        family = str(extra.get("source_family") or "").strip()
        if family not in SAFE_FAMILIES:
            continue
        scanned += 1
        flags = set(str(flag) for flag in (extra.get("quality_flags") or []))
        remaining = flags - NON_BLOCKING_FLAGS
        if "duplicate_or_contaminated" in remaining:
            blocked += 1
            continue
        if reject_reason(_event_view(row), sport_id="football", competition_id=row.competition_id):
            blocked += 1
            continue
        public_key = _safe_public_key(row, extra)
        if not public_key:
            blocked += 1
            continue

        extra["public_competition_key"] = public_key
        extra["quality_flags"] = sorted(flag for flag in flags if flag not in NON_BLOCKING_FLAGS)
        extra["display_eligible"] = True
        extra["resolution_method"] = "source_native_revalidated"
        extra["resolution_confidence"] = 95
        extra["source_native_revalidated_at"] = isoformat(datetime.utcnow())
        row.extra_json = dump_json(extra)
        row.display_eligible = True
        store_list_extra(row, extra)
        promoted += 1

    db.flush()
    if promoted:
        from collector.cache import cache_clear

        cache_clear(db, prefix="events:")
    return {"scanned": scanned, "promoted": promoted, "blocked": blocked}


def run_if_due(db: Session, *, min_interval_minutes: int = 30) -> Optional[Dict[str, int]]:
    job = _job(db)
    if (
        job.last_run_at
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
        and job.last_status == "ok"
    ):
        return None
    stats = revalidate_current_source_native(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int(stats["promoted"])
    job.last_error = dump_json(stats)
    db.commit()
    return stats
