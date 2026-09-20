"""Cross-provider event identity. Name similarity alone is never enough."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from collector.participant_alias import expand_abbreviations, participants_equivalent
from collector.participant_text import fold_for_identity

IDENTITY_MERGE_THRESHOLD = 90
_WEAK = {"united", "city", "racing", "sporting", "athletic", "rovers", "town", "county", "stars"}


def _ids(event: Dict[str, Any]) -> set:
    raw = event.get("source_event_ids") or {}
    if isinstance(raw, dict):
        return {str(value) for value in raw.values() if value}
    if isinstance(raw, list):
        return {str(value) for value in raw if value}
    sid = event.get("source_event_id")
    return {str(sid)} if sid else set()


def _fold_side(side: Any) -> str:
    if isinstance(side, dict):
        return expand_abbreviations(fold_for_identity(str(side.get("name") or "")))
    return expand_abbreviations(fold_for_identity(str(side or "")))


def _side_name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "")
    return str(side or "")


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _weak_pair(a: str, b: str) -> bool:
    parts_a = set(a.split())
    parts_b = set(b.split())
    if not parts_a or not parts_b:
        return True
    if parts_a <= _WEAK or parts_b <= _WEAK:
        return True
    return False


def identity_confidence(canonical: Dict[str, Any], candidate: Dict[str, Any]) -> int:
    if not canonical or not candidate:
        return 0
    if _ids(canonical) & _ids(candidate):
        return 100
    if (canonical.get("sport") or "") != (candidate.get("sport") or ""):
        return 0
    home = _fold_side(canonical.get("home") or canonical.get("participant_a"))
    away = _fold_side(canonical.get("away") or canonical.get("participant_b"))
    ch = _fold_side(candidate.get("home") or candidate.get("participant_a"))
    ca = _fold_side(candidate.get("away") or candidate.get("participant_b"))
    home_name = _side_name(canonical.get("home") or canonical.get("participant_a"))
    away_name = _side_name(canonical.get("away") or canonical.get("participant_b"))
    ch_name = _side_name(candidate.get("home") or candidate.get("participant_a"))
    ca_name = _side_name(candidate.get("away") or candidate.get("participant_b"))
    if not home or not away:
        return 0
    if {home, away} != {ch, ca} and not participants_equivalent(home_name, away_name, ch_name, ca_name):
        return 0
    if _weak_pair(home, away):
        return 0
    t0 = _ts(canonical.get("start_time"))
    t1 = _ts(candidate.get("start_time"))
    same_comp = (canonical.get("competition_key") or canonical.get("competition")) == (
        candidate.get("competition_key") or candidate.get("competition")
    )
    if t0 and t1:
        delta = abs((t0 - t1).total_seconds())
        if delta > 12 * 3600:
            return 0
        if same_comp and delta <= 15 * 60:
            return 95
        if same_comp and delta <= 3 * 3600:
            return 90
        if not same_comp and delta <= 3 * 3600:
            return 88
        return 0
    same_date = str(canonical.get("start_time") or "")[:10] == str(candidate.get("start_time") or "")[:10]
    if same_date and same_comp:
        return 70
    if same_date:
        return 65
    return 0


def should_merge_enrichment(canonical: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    score = identity_confidence(canonical, candidate)
    if score < IDENTITY_MERGE_THRESHOLD:
        return False
    same_comp = (canonical.get("competition_key") or canonical.get("competition")) == (
        candidate.get("competition_key") or candidate.get("competition")
    )
    return same_comp or score == 100
