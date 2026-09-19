"""Canonical status transition validation. Old LIVE is not evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from collector.live_state import AUTHORITATIVE_END, canonical_status, is_live, observation_time

TERMINAL = AUTHORITATIVE_END | {"postponed"}

_REJECTED: list[Dict[str, Any]] = []


def _ts(event: Dict[str, Any]) -> datetime:
    observed = observation_time(event)
    return observed.replace(tzinfo=None) if observed and observed.tzinfo else (observed or datetime.min)


def allowed_status_transition(current: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    cur = canonical_status(current.get("status") or "")
    inc = canonical_status(incoming.get("status") or "")
    if cur == inc:
        return True
    cur_ts = _ts(current)
    inc_ts = _ts(incoming)
    if cur in TERMINAL and is_live(inc):
        if inc_ts <= cur_ts:
            return False
        return True
    if is_live(cur) and inc in TERMINAL:
        if inc_ts < cur_ts and inc_ts != datetime.min:
            return False
        return True
    if cur in TERMINAL and inc in TERMINAL and inc_ts < cur_ts:
        return False
    return True


def apply_or_reject(current: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if allowed_status_transition(current, incoming):
        return incoming
    note = {
        "from": current.get("status"),
        "to": incoming.get("status"),
        "event_id": current.get("id") or incoming.get("id"),
        "reason": "rejected_weaker_or_stale_status",
    }
    _REJECTED.append(note)
    incoming = dict(incoming)
    incoming["status"] = current.get("status")
    incoming["status_transition_rejected"] = note["reason"]
    return incoming


def rejected_transitions() -> list[Dict[str, Any]]:
    return list(_REJECTED)


def reset_rejected_transitions() -> None:
    _REJECTED.clear()
