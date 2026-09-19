"""Measured pipeline latency. No claimed source-to-world latency without provider timestamps."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from collector.metrics import incr, set_metric

_SAMPLES: Dict[str, List[float]] = {
    "fetch_ms": [],
    "persist_ms": [],
    "canonical_ms": [],
}


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).replace("Z", "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _delta_ms(start: Any, end: Any) -> Optional[float]:
    a = _parse(start)
    b = _parse(end)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds() * 1000.0)


def _push(name: str, value: Optional[float]) -> None:
    if value is None:
        return
    bucket = _SAMPLES.setdefault(name, [])
    bucket.append(value)
    if len(bucket) > 400:
        del bucket[:200]


def percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(ordered[index], 1)


def record_observation_latency(event: Dict[str, Any]) -> None:
    fetch = _delta_ms(event.get("fetch_started_at"), event.get("fetch_completed_at"))
    persist = _delta_ms(event.get("fetch_completed_at") or event.get("parsed_at"), event.get("persisted_at"))
    canonical = _delta_ms(event.get("persisted_at"), event.get("canonical_updated_at"))
    _push("fetch_ms", fetch)
    _push("persist_ms", persist)
    _push("canonical_ms", canonical)
    if event.get("status") in {"live", "break", "halftime"}:
        incr("live_updates_changed")
    set_metric("latency", snapshot())


def snapshot() -> Dict[str, Any]:
    out = {}
    for name, values in _SAMPLES.items():
        out[name] = {
            "n": len(values),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
        }
    return out


def reset_latency() -> None:
    for key in _SAMPLES:
        _SAMPLES[key] = []
