"""Internal live freshness diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from collector.cadence import interval_for
from collector.family_caps import family_caps, min_safe_interval
from collector.family_health import snapshot as family_snapshot
from collector.http import STATS
from collector.incremental import live_registry_snapshot
from collector.latency import snapshot as latency_snapshot
from collector.live_state import CONFIRMED_LIVE, STALE_LIVE
from collector.metrics import snapshot as metrics_snapshot
from collector.models import SportsEvent, SportsLiveWatch
from collector.util import isoformat, load_json


def _parse(value: Any) -> Optional[datetime]:
    from collector.live_state import parse_ts

    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return parse_ts(value)


def observation_age_class(updated_at: datetime | None, *, now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    if updated_at is None:
        return "unknown"
    age = (now - updated_at.replace(tzinfo=None)).total_seconds()
    if age <= 90:
        return "fresh"
    if age <= 300:
        return "aging"
    if age <= 900:
        return "stale"
    return "blocked"


def live_health_payload(db: Session) -> Dict[str, Any]:
    now = datetime.utcnow()
    watches = db.query(SportsLiveWatch).all()
    live_rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.status.in_(("live", "halftime", "break")))
        .all()
    )
    confirmed = 0
    stale = 0
    oldest_semantic = None
    oldest_contact = None
    family_live: Dict[str, Dict[str, Any]] = {}
    for row in live_rows:
        extra = load_json(row.extra_json, {}) or {}
        family = str(extra.get("source_family") or row.primary_source_id or "")
        live_class = extra.get("live_class")
        if live_class == CONFIRMED_LIVE:
            confirmed += 1
        if live_class == STALE_LIVE or row.status == "stale":
            stale += 1
        if row.updated_at and (oldest_semantic is None or row.updated_at < oldest_semantic):
            oldest_semantic = row.updated_at
        contact = _parse(extra.get("last_contact_at") or extra.get("source_fetch_time")) or row.retrieved_at
        if contact and (oldest_contact is None or contact < oldest_contact):
            oldest_contact = contact
        if family:
            bucket = family_live.setdefault(
                family,
                {"family": family, "live_event_count": 0, "oldest_live_canonical_age": 0, "oldest_contact_age": 0},
            )
            bucket["live_event_count"] += 1
            if row.updated_at:
                bucket["oldest_live_canonical_age"] = max(
                    int(bucket["oldest_live_canonical_age"] or 0),
                    int((now - row.updated_at.replace(tzinfo=None)).total_seconds()),
                )
            if contact:
                bucket["oldest_contact_age"] = max(
                    int(bucket["oldest_contact_age"] or 0),
                    int((now - contact.replace(tzinfo=None)).total_seconds()),
                )
    registry = live_registry_snapshot()
    health = family_snapshot()
    families = []
    names = sorted(set(family_live) | set(registry) | {key for key, val in health.items() if val.get("status")})
    for family in names:
        caps = family_caps(family)
        live_row = family_live.get(family) or {}
        reg = registry.get(family) or {}
        fam = health.get(family) or {}
        last_success = reg.get("last_success_at") or fam.get("last_success")
        last_dt = _parse(last_success)
        families.append(
            {
                "family": family,
                "live_event_count": int(live_row.get("live_event_count") or reg.get("live_event_count") or 0),
                "last_fetch_started_at": reg.get("last_fetch_started_at"),
                "last_fetch_completed_at": reg.get("last_fetch_completed_at"),
                "last_success_at": last_success,
                "last_success_age": int((now - last_dt).total_seconds()) if last_dt else None,
                "next_eligible_at": isoformat(reg["next_eligible_at"])
                if isinstance(reg.get("next_eligible_at"), datetime)
                else reg.get("next_eligible_at"),
                "failure_count": int(reg.get("failure_count") or fam.get("consecutive_failures") or 0),
                "backoff_until": reg.get("backoff_until") or fam.get("rate_limit_until"),
                "oldest_live_canonical_age": live_row.get("oldest_live_canonical_age")
                or reg.get("oldest_live_canonical_age"),
                "target_cadence_s": int(reg.get("target_cadence_s") or interval_for(family, "LIVE")),
                "minimum_safe_s": int(reg.get("minimum_safe_s") or min_safe_interval(family)),
                "effective_cadence_s": int(reg.get("target_cadence_s") or interval_for(family, "LIVE")),
                "production_status": caps.get("production_status"),
                "health_status": fam.get("status"),
            }
        )
    metrics = metrics_snapshot()
    http = STATS if isinstance(STATS, dict) else {}
    live_starved = int(metrics.get("live_families_starved") or 0)
    return {
        "confirmed_live_events": confirmed,
        "watched_events": len(watches),
        "stale_events": stale,
        "live_coverage_healthy": live_starved == 0 and (oldest_contact is None or (now - oldest_contact).total_seconds() <= 120),
        "oldest_live_observation_age": int((now - oldest_semantic).total_seconds()) if oldest_semantic else None,
        "oldest_live_contact_age": int((now - oldest_contact).total_seconds()) if oldest_contact else None,
        "background_jobs_waiting": metrics.get("background_jobs_waiting"),
        "background_jobs_starved": metrics.get("background_jobs_starved"),
        "live_families_waiting": metrics.get("live_families_waiting"),
        "live_families_starved": live_starved,
        "oldest_live_fetch_age_seconds": metrics.get("oldest_live_fetch_age_seconds"),
        "oldest_background_fetch_age_seconds": metrics.get("oldest_background_fetch_age_seconds"),
        "live_provider_requests": http.get("requests"),
        "provider_403": http.get("http_403") or http.get("status_403"),
        "provider_429": http.get("http_429") or http.get("status_429"),
        "timeouts": http.get("timeouts"),
        "metrics": metrics,
        "latency": latency_snapshot(),
        "families": families,
        "watch_reasons": {
            "EXPLICIT_LIVE": sum(1 for row in watches if row.reason == "EXPLICIT_LIVE"),
            "KICKOFF_WINDOW": sum(1 for row in watches if row.reason == "KICKOFF_WINDOW"),
        },
    }
