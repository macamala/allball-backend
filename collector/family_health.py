"""In-process provider-family health. One upstream incident is one family state."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

_STATE: Dict[str, Dict[str, Any]] = {}

HOST_FAMILY = {
    "www.thesportsdb.com": "thesportsdb",
    "thesportsdb.com": "thesportsdb",
    "www.espn.com": "espn-html",
    "espn.com": "espn-html",
    "site.api.espn.com": "espn-html",
    "api.wtatennis.com": "wta-json",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def family_state(family: str) -> Dict[str, Any]:
    row = _STATE.setdefault(
        family,
        {
            "family": family,
            "status": "unknown",
            "last_success": None,
            "last_event_seen": None,
            "consecutive_failures": 0,
            "rate_limit_until": None,
            "last_http_status": None,
            "last_parser_success": None,
            "blocked_until_mono": 0.0,
        },
    )
    return row


def note_family_success(family: str, *, http_status: Optional[int] = None, events: int = 0, parse_ok: bool = True) -> None:
    if not family:
        return
    row = family_state(family)
    row["status"] = "healthy" if events else "empty"
    row["last_success"] = _now().isoformat()
    row["consecutive_failures"] = 0
    row["last_http_status"] = http_status
    row["blocked_until_mono"] = 0.0
    row["rate_limit_until"] = None
    if events:
        row["last_event_seen"] = _now().isoformat()
    if parse_ok:
        row["last_parser_success"] = _now().isoformat()


def note_family_failure(
    family: str,
    *,
    http_status: Optional[int] = None,
    error_type: str = "error",
    retry_after_s: float = 0,
) -> None:
    if not family:
        return
    row = family_state(family)
    row["consecutive_failures"] = int(row.get("consecutive_failures") or 0) + 1
    row["last_http_status"] = http_status
    if http_status == 429 or error_type == "RATE_LIMITED":
        row["status"] = "RATE_LIMITED"
        wait = max(30.0, retry_after_s or 120.0)
        until = time.monotonic() + wait
        row["blocked_until_mono"] = max(float(row.get("blocked_until_mono") or 0), until)
        row["rate_limit_until"] = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
    elif http_status in {401, 403, 404, 410}:
        row["status"] = "ACCESS_BLOCKED"
        wait = max(300.0, retry_after_s or 900.0)
        until = time.monotonic() + wait
        row["blocked_until_mono"] = max(float(row.get("blocked_until_mono") or 0), until)
        row["rate_limit_until"] = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat()
    else:
        row["status"] = "degraded"
        wait = min(300.0, max(15.0, 8.0 * (2 ** min(int(row["consecutive_failures"]), 5))))
        until = time.monotonic() + wait
        row["blocked_until_mono"] = max(float(row.get("blocked_until_mono") or 0), until)


def family_rate_limited(family: str) -> bool:
    if not family:
        return False
    row = _STATE.get(family)
    if not row:
        return False
    return time.monotonic() < float(row.get("blocked_until_mono") or 0)


def family_access_blocked(family: str) -> bool:
    if not family:
        return False
    row = _STATE.get(family)
    if not row:
        return False
    if row.get("status") != "ACCESS_BLOCKED":
        return False
    return time.monotonic() < float(row.get("blocked_until_mono") or 0)


def family_from_host(host: str) -> Optional[str]:
    return HOST_FAMILY.get((host or "").lower())


def snapshot() -> Dict[str, Any]:
    return {key: dict(val) for key, val in _STATE.items()}


def reset_family_health() -> None:
    _STATE.clear()
