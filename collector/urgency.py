"""Event urgency classes for incremental results scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# Seconds. Provider-family minimums still win in cadence_for().
URGENCY_SECONDS = {
    "LIVE": 45,
    "LIVE_CANDIDATE": 90,
    "IMMINENT": 120,
    "RECENTLY_FINISHED": 180,
    "RESULT_CATCHUP": 180,
    "TODAY": 600,
    "NEAR_FUTURE": 3600,
    "FUTURE": 21600,
    "LONG_FUTURE": 86400,
    "HISTORICAL": 86400,
    "DISCOVERY_ACTIVE": 2700,
    "DISCOVERY_QUIET": 43200,
}

URGENCY_PRIORITY = {
    "LIVE": 1,
    "LIVE_CANDIDATE": 2,
    "IMMINENT": 3,
    "RECENTLY_FINISHED": 4,
    "RESULT_CATCHUP": 4,
    "TODAY": 5,
    "NEAR_FUTURE": 6,
    "FUTURE": 7,
    "LONG_FUTURE": 8,
    "HISTORICAL": 9,
    "DISCOVERY_ACTIVE": 10,
    "DISCOVERY_QUIET": 11,
}


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def classify_event(status: Optional[str], start_time: Optional[datetime], *, now: Optional[datetime] = None) -> str:
    now = _aware(now) or datetime.utcnow()
    start = _aware(start_time)
    st = (status or "").lower()
    if st in {"live", "halftime", "break", "ht", "inplay", "in_play"}:
        return "LIVE"
    if st == "stale":
        return "TODAY"
    if st == "finished":
        if start and now - start <= timedelta(hours=2):
            return "RECENTLY_FINISHED"
        if start and now - start <= timedelta(hours=4):
            return "HISTORICAL"
        return "HISTORICAL"
    if start is None:
        return "TODAY"
    delta = start - now
    if timedelta(minutes=-30) <= delta <= timedelta(minutes=30):
        return "IMMINENT"
    if delta <= timedelta(hours=24):
        return "TODAY"
    if delta <= timedelta(days=7):
        return "NEAR_FUTURE"
    if delta <= timedelta(days=30):
        return "FUTURE"
    return "LONG_FUTURE"


WORKLOAD_CONFIRMED_LIVE = "CONFIRMED_LIVE"
WORKLOAD_LIVE_CANDIDATE = "LIVE_CANDIDATE"
WORKLOAD_RECENTLY_FINISHED = "RECENTLY_FINISHED"
WORKLOAD_FIXTURE = "FIXTURE_REFRESH"
WORKLOAD_DISCOVERY = "DISCOVERY"
WORKLOAD_ENRICHMENT = "ENRICHMENT"


def workload_for_urgency(urgency: str) -> str:
    if urgency == "LIVE":
        return WORKLOAD_CONFIRMED_LIVE
    if urgency in {"LIVE_CANDIDATE", "IMMINENT"}:
        return WORKLOAD_LIVE_CANDIDATE
    if urgency in {"RECENTLY_FINISHED", "RESULT_CATCHUP"}:
        return WORKLOAD_RECENTLY_FINISHED
    if urgency.startswith("DISCOVERY"):
        return WORKLOAD_DISCOVERY
    if urgency == "ENRICHMENT":
        return WORKLOAD_ENRICHMENT
    return WORKLOAD_FIXTURE


def capability_for_urgency(urgency: str) -> str:
    if urgency in {"LIVE", "LIVE_CANDIDATE"}:
        return "live_scores"
    if urgency in {"RECENTLY_FINISHED", "RESULT_CATCHUP"}:
        return "results"
    if urgency == "HISTORICAL":
        return "results"
    return "fixtures"


def job_dict(*, competition_id: str, family: str, urgency: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {
        "competition_id": competition_id,
        "family": family,
        "urgency": urgency,
        "reason": reason,
        "priority": URGENCY_PRIORITY.get(urgency, 50),
        "capability": capability_for_urgency(urgency),
        "workload": extra.get("workload") or workload_for_urgency(urgency),
        **extra,
    }
