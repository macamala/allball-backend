"""Provider-family collection capabilities. Family minimums always beat urgency."""

from __future__ import annotations

from typing import Any, Dict

from collector.family_plan import family_refresh_class

_DEFAULT = {
    "supports_live": True,
    "supports_schedule": True,
    "supports_results": True,
    "is_static": False,
    "minimum_safe_interval": 60,
    "rate_limit_profile": "standard",
    "shared_request_scope": "competition",
    "explicit_live_status": True,
    "exact_scheduled_time": True,
    "live_clock": False,
    "partial_periods": False,
    "score": True,
    "terminal_status": True,
    "stale_after_seconds": 1800,
}

_BY_FAMILY: Dict[str, Dict[str, Any]] = {
    "thesportsdb": {
        "supports_live": True,
        "supports_schedule": True,
        "supports_results": True,
        "is_static": False,
        "minimum_safe_interval": 90,
        "rate_limit_profile": "shared_api",
        "shared_request_scope": "url",
        "explicit_live_status": True,
        "exact_scheduled_time": True,
        "live_clock": False,
        "partial_periods": False,
        "score": True,
        "terminal_status": True,
        "stale_after_seconds": 3600,
    },
    "openligadb": {
        "supports_live": True,
        "minimum_safe_interval": 60,
        "rate_limit_profile": "standard",
        "shared_request_scope": "competition",
        "explicit_live_status": False,
        "exact_scheduled_time": True,
        "live_clock": False,
        "partial_periods": True,
        "score": True,
        "terminal_status": True,
        "stale_after_seconds": 900,
    },
    "espn-html": {
        "supports_live": True,
        "minimum_safe_interval": 21600,
        "rate_limit_profile": "restricted_html",
        "shared_request_scope": "url",
        "production_status": "ACCESS_BLOCKED",
        "explicit_live_status": True,
        "exact_scheduled_time": True,
        "live_clock": True,
        "partial_periods": True,
        "score": True,
        "terminal_status": True,
        "stale_after_seconds": 21600,
    },
    "wta-json": {
        "supports_live": True,
        "minimum_safe_interval": 120,
        "rate_limit_profile": "standard",
        "shared_request_scope": "family",
    },
    "pulselive": {
        "supports_live": True,
        "minimum_safe_interval": 90,
        "rate_limit_profile": "shared_api",
        "shared_request_scope": "family",
        "live_clock": True,
        "partial_periods": True,
        "stale_after_seconds": 900,
    },
    "sportscore": {
        "supports_live": True,
        "minimum_safe_interval": 60,
        "rate_limit_profile": "shared_api",
        "shared_request_scope": "url",
        "explicit_live_status": True,
        "live_clock": False,
        "partial_periods": True,
        "stale_after_seconds": 1800,
    },
    "nhl-web": {
        "supports_live": True,
        "minimum_safe_interval": 30,
        "shared_request_scope": "family",
        "live_clock": True,
        "partial_periods": True,
        "stale_after_seconds": 120,
    },
    "mlb-statsapi": {
        "supports_live": True,
        "minimum_safe_interval": 30,
        "shared_request_scope": "family",
        "live_clock": False,
        "partial_periods": True,
        "stale_after_seconds": 120,
    },
    "khl-mobile": {
        "supports_live": True,
        "minimum_safe_interval": 45,
        "live_clock": True,
        "partial_periods": True,
    },
    "liiga-web": {
        "supports_live": True,
        "minimum_safe_interval": 45,
        "live_clock": True,
        "partial_periods": True,
    },
    "euroleague-live": {
        "supports_live": True,
        "minimum_safe_interval": 30,
        "live_clock": True,
        "partial_periods": True,
    },
    "wikipedia": {
        "supports_live": False,
        "is_static": True,
        "minimum_safe_interval": 86400,
        "rate_limit_profile": "archive",
        "shared_request_scope": "url",
    },
    "cricsheet": {
        "supports_live": False,
        "is_static": True,
        "minimum_safe_interval": 86400,
        "rate_limit_profile": "archive",
    },
    "sackmann-tennis": {
        "supports_live": False,
        "is_static": True,
        "minimum_safe_interval": 86400,
        "rate_limit_profile": "archive",
    },
}


def family_caps(family: str) -> Dict[str, Any]:
    name = (family or "").strip()
    row = dict(_DEFAULT)
    kind = family_refresh_class(name)
    if kind == "archive":
        row.update(
            supports_live=False,
            is_static=True,
            minimum_safe_interval=86400,
            rate_limit_profile="archive",
        )
    elif kind == "shared_api":
        row.update(minimum_safe_interval=90, rate_limit_profile="shared_api", shared_request_scope="url")
    if name in _BY_FAMILY:
        row.update(_BY_FAMILY[name])
    if name.startswith("wikipedia") or "wikipedia" in name or name.startswith("wiki"):
        row.update(supports_live=False, is_static=True, minimum_safe_interval=max(int(row["minimum_safe_interval"]), 86400))
    return row


def supports_live(family: str) -> bool:
    return bool(family_caps(family).get("supports_live"))


def is_static_family(family: str) -> bool:
    return bool(family_caps(family).get("is_static"))


def min_safe_interval(family: str) -> int:
    return int(family_caps(family).get("minimum_safe_interval") or 60)
