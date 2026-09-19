"""Compact timestamped write-path stages. No event dumps."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_t0 = time.perf_counter()
_last = _t0
_stages: list[Dict[str, Any]] = []


def _rss_mb() -> Optional[float]:
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)
    except Exception:
        pass
    try:
        import psutil  # type: ignore

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return None


def reset_progress() -> None:
    global _t0, _last, _stages
    _t0 = time.perf_counter()
    _last = _t0
    _stages = []


def stage(name: str, **extra: Any) -> Dict[str, Any]:
    global _last
    now = time.perf_counter()
    row = {
        "stage": name,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "since_start_s": round(now - _t0, 3),
        "since_prev_s": round(now - _last, 3),
        "rss_mb": _rss_mb(),
        **extra,
    }
    _last = now
    _stages.append(row)
    bits = " ".join(f"{k}={v}" for k, v in extra.items() if v is not None)
    print(f"STAGE {name} t={row['since_start_s']}s d={row['since_prev_s']}s rss={row['rss_mb']} {bits}", flush=True)
    if row["since_prev_s"] >= 60:
        print(f"WATCHDOG slow_stage={name} seconds={row['since_prev_s']}", flush=True)
    return row


def persist_progress(done: int, total: int) -> None:
    if total <= 0:
        return
    step = 500
    if done % step == 0 or done == total:
        print(f"PERSIST {done} / {total}", flush=True)


def stages() -> list[Dict[str, Any]]:
    return list(_stages)


def peak_rss_mb() -> Optional[float]:
    values = [row.get("rss_mb") for row in _stages if row.get("rss_mb") is not None]
    return max(values) if values else _rss_mb()
