"""In-process results scheduler metrics. No secrets."""

from __future__ import annotations

from typing import Any, Dict

_METRICS: Dict[str, Any] = {
    "cycles": 0,
    "logical_jobs": 0,
    "physical_requests": 0,
    "coalesced": 0,
    "cache_hits": 0,
    "unchanged_skipped": 0,
    "score_changes": 0,
    "status_changes": 0,
    "clock_changes": 0,
    "live_updates_changed": 0,
    "due_jobs": 0,
    "selected_jobs": 0,
    "live_jobs": 0,
    "a_failures": 0,
    "b_activations": 0,
    "periods_persisted": 0,
    "incidents_persisted": 0,
    "runners_persisted": 0,
    "best_of_persisted": 0,
    "enrichment_promoted": 0,
    "jobs_starved": 0,
    "oldest_due_age_s": 0,
    "last_cycle_s": None,
    "last_cycle_at": None,
}


def incr(name: str, amount: int = 1) -> None:
    _METRICS[name] = int(_METRICS.get(name) or 0) + amount


def set_metric(name: str, value: Any) -> None:
    _METRICS[name] = value


def snapshot() -> Dict[str, Any]:
    return dict(_METRICS)


def reset_metrics() -> None:
    for key in list(_METRICS):
        if isinstance(_METRICS[key], int):
            _METRICS[key] = 0
        else:
            _METRICS[key] = None
