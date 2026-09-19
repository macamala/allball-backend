"""Fail-closed production controls for results collection.

Missing env vars never silently enable scheduler or canonical writes.
"""

from __future__ import annotations

import os
from typing import Any, Dict


def _truthy(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def collection_enabled() -> bool:
    return _truthy("RESULTS_COLLECTION_ENABLED")


def writes_enabled() -> bool:
    return _truthy("RESULTS_WRITE_ENABLED")


def scheduler_enabled() -> bool:
    """Kill switch. False stops new scheduled collection; in-flight tick may finish."""
    return _truthy("RESULTS_SCHEDULER_ENABLED")


def run_once_requested() -> bool:
    return _truthy("RESULTS_RUN_ONCE")


def keepalive_enabled() -> bool:
    if os.getenv("RESULTS_KEEPALIVE") is not None:
        return _truthy("RESULTS_KEEPALIVE")
    return not _truthy("COLLECTOR_ONCE")


def flags_payload() -> Dict[str, Any]:
    return {
        "RESULTS_COLLECTION_ENABLED": collection_enabled(),
        "RESULTS_WRITE_ENABLED": writes_enabled(),
        "RESULTS_SCHEDULER_ENABLED": scheduler_enabled(),
        "RESULTS_KEEPALIVE": keepalive_enabled(),
        "fail_closed": True,
    }
