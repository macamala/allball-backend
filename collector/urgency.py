"""Event urgency classes for incremental results scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# Seconds. Provider-family minimums still win in cadence_for().
URGENCY_SECONDS = {
    "LIVE": 45,
    "IMMINENT": 120,
    "RECENTLY_FINISHED": 300,
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
    "IMMINENT": 2,
    "RECENTLY_FINISHED": 3,
    "TODAY": 4,
    "NEAR_FUTURE": 5,
    "FUTURE": 6,
    "LONG_FUTURE": 7,
    "HISTORICAL": 8,
    "DISCOVERY_ACTIVE": 9,
    "DISCOVERY_QUIET": 10,
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
    if st == "live":
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


def capability_for_urgency(urgency: str) -> str:
    if urgency == "LIVE":
        return "live_scores"
    if urgency == "RECENTLY_FINISHED":
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
        **extra,
    }
