"""Internal live freshness diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from collector.family_health import snapshot as family_snapshot
from collector.http import STATS
from collector.latency import snapshot as latency_snapshot
from collector.live_state import CONFIRMED_LIVE, STALE_LIVE
from collector.metrics import snapshot as metrics_snapshot
from collector.models import SportsEvent, SportsLiveWatch
from collector.util import load_json


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
    oldest = None
    for row in live_rows:
        extra = load_json(row.extra_json, {}) or {}
        if extra.get("live_class") == CONFIRMED_LIVE:
            confirmed += 1
        if extra.get("live_class") == STALE_LIVE or row.status == "stale":
            stale += 1
        if row.updated_at and (oldest is None or row.updated_at < oldest):
            oldest = row.updated_at
    http = STATS if isinstance(STATS, dict) else {}
    return {
        "confirmed_live_events": confirmed,
        "watched_events": len(watches),
        "stale_events": stale,
        "oldest_live_observation_age": int((now - oldest).total_seconds()) if oldest else None,
        "live_provider_requests": http.get("requests"),
        "provider_403": http.get("http_403") or http.get("status_403"),
        "provider_429": http.get("http_429") or http.get("status_429"),
        "timeouts": http.get("timeouts"),
        "metrics": metrics_snapshot(),
        "latency": latency_snapshot(),
        "families": family_snapshot(),
        "watch_reasons": {
            "EXPLICIT_LIVE": sum(1 for row in watches if row.reason == "EXPLICIT_LIVE"),
            "KICKOFF_WINDOW": sum(1 for row in watches if row.reason == "KICKOFF_WINDOW"),
        },
    }
