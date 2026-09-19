"""Provider-family operational cadence. Urgency intervals lose to family minimums."""

from __future__ import annotations

from collector.family_caps import is_static_family, min_safe_interval, supports_live
from collector.family_plan import family_refresh_class
from collector.urgency import URGENCY_SECONDS

# Seconds. Provider observed 429/cooldown always wins over these.
CADENCE_SECONDS = {
    "LIVE": 45,
    "LIVE_CANDIDATE": 90,
    "TODAY": 600,
    "FUTURE": 3600,
    "HISTORICAL": 21600,
    "ARCHIVE": 43200,
    "SHARED_API": 900,
}


def operational_class(family: str, polling_class: str | None = None) -> str:
    refresh = family_refresh_class(family or "")
    if refresh == "archive":
        return "ARCHIVE"
    if refresh == "shared_api":
        return "SHARED_API"
    poll = (polling_class or "").upper()
    if poll == "LIVE":
        return "LIVE"
    if poll == "LIVE_CANDIDATE":
        return "LIVE_CANDIDATE"
    if poll in {"NEAR_LIVE", "NORMAL"}:
        return "TODAY"
    if poll == "SLOW":
        return "FUTURE"
    if refresh == "live":
        return "TODAY"
    return "FUTURE"


def cadence_seconds_for(family: str, polling_class: str | None = None) -> int:
    return CADENCE_SECONDS[operational_class(family, polling_class)]


def interval_for(family: str, urgency: str) -> int:
    base = int(URGENCY_SECONDS.get(urgency) or URGENCY_SECONDS["TODAY"])
    floor = min_safe_interval(family)
    if is_static_family(family) and urgency in {"LIVE", "LIVE_CANDIDATE", "IMMINENT", "RECENTLY_FINISHED", "TODAY"}:
        return max(floor, URGENCY_SECONDS["HISTORICAL"])
    if urgency in {"LIVE", "LIVE_CANDIDATE"} and not supports_live(family):
        return max(floor, URGENCY_SECONDS["TODAY"])
    return max(base, floor)
