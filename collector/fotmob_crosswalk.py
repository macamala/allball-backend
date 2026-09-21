"""Attach FotMob match IDs onto existing canonical football events.

Uses competition + kickoff + participants. Does not create duplicate fixtures.
Does not match on title text alone.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_fotmob import FOTMOB_LEAGUES, _BOARD, _load_boards, match_to_event
from collector.identity_events import identity_confidence
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.source_ids import families_with_ids, merge_family_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

_YOUTH = ("u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior")
_WOMEN = ("women", "womens", "woms")
_RESERVE = ("reserve", " ii", "2nd", "b team")


def _tokens(name: str) -> set:
    folded = " ".join(str(name or "").lower().replace("-", " ").split())
    marks = set()
    for item in _YOUTH:
        if item in folded:
            marks.add("youth")
    for item in _WOMEN:
        if item in folded:
            marks.add("women")
    for item in _RESERVE:
        if item in folded:
            marks.add("reserve")
    return marks


def _protected_conflict(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    l_home = ((left.get("home") or {}).get("name") or "") + " " + ((left.get("away") or {}).get("name") or "")
    r_home = ((right.get("home") or {}).get("name") or "") + " " + ((right.get("away") or {}).get("name") or "")
    return bool(_tokens(l_home) ^ _tokens(r_home))


def _league_to_competition() -> Dict[str, str]:
    return {str(spec["id"]): competition_id for competition_id, spec in FOTMOB_LEAGUES.items() if spec.get("id")}


def _event_view(row: SportsEvent) -> Dict[str, Any]:
    parts = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}
    return {
        "sport": row.sport_id,
        "competition": row.competition_id,
        "competition_key": row.competition_id,
        "home": parts.get("home") or {},
        "away": parts.get("away") or {},
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "source_event_ids": families_with_ids(extra),
    }


def _attach(row: SportsEvent, fotmob_id: str) -> bool:
    extra = load_json(row.extra_json, {}) or {}
    before = dict(families_with_ids(extra))
    extra["source_event_ids"] = merge_family_ids(extra.get("source_event_ids"), family="fotmob", source_event_id=fotmob_id)
    if families_with_ids(extra) == before:
        return False
    row.extra_json = dump_json(extra)
    store_list_extra(row, extra)
    return True


def crosswalk_fotmob_ids(db: Session, *, hours: int = 120, getter=None) -> Dict[str, int]:
    from collector.http import fetch_url

    _BOARD.clear()
    try:
        matches = _load_boards(getter or fetch_url)
    except Exception:
        matches = []
    league_map = _league_to_competition()
    bound = datetime.utcnow() - timedelta(hours=hours)
    keepers = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .all()
    )
    by_comp: Dict[str, List[SportsEvent]] = {}
    for row in keepers:
        by_comp.setdefault(row.competition_id, []).append(row)
    upstream = attached = skipped_conflict = unmatched = 0
    eligible_ids: List[str] = []
    for match in matches:
        league_id = str((match.get("_league") or {}).get("id") or "")
        competition_id = league_map.get(league_id)
        if not competition_id:
            continue
        parsed = match_to_event(match, competition_id)
        if not parsed or not parsed.get("source_event_id"):
            continue
        upstream += 1
        eligible_ids.append(str(parsed["source_event_id"]))
        incoming = {
            "sport": "football",
            "competition": competition_id,
            "competition_key": competition_id,
            "home": parsed.get("home") or {},
            "away": parsed.get("away") or {},
            "start_time": parsed.get("start_time"),
            "source_event_ids": {"fotmob": str(parsed["source_event_id"])},
        }
        incoming_day = str(incoming.get("start_time") or "")[:10]
        best: Optional[Tuple[int, SportsEvent]] = None
        for row in by_comp.get(competition_id) or []:
            view = _event_view(row)
            if incoming_day and str(view.get("start_time") or "")[:10] != incoming_day:
                continue
            if _protected_conflict(view, incoming):
                skipped_conflict += 1
                continue
            score = identity_confidence(view, incoming)
            if score < 90:
                continue
            if best is None or score > best[0]:
                best = (score, row)
        if best is None:
            unmatched += 1
            continue
        if _attach(best[1], str(parsed["source_event_id"])):
            attached += 1
    db.flush()
    logger.info(
        "fotmob_crosswalk upstream=%s attached=%s unmatched=%s protected=%s",
        upstream,
        attached,
        unmatched,
        skipped_conflict,
    )
    return {
        "upstream_eligible": upstream,
        "attached": attached,
        "unmatched": unmatched,
        "protected_conflicts": skipped_conflict,
    }


def eligible_coverage(db: Session, *, hours: int = 168, getter=None) -> Dict[str, Any]:
    from collector.http import fetch_url

    _BOARD.clear()
    try:
        matches = _load_boards(getter or fetch_url)
    except Exception:
        matches = []
    league_map = _league_to_competition()
    bound = datetime.utcnow() - timedelta(hours=hours)
    eligible = 0
    for match in matches:
        league_id = str((match.get("_league") or {}).get("id") or "")
        if league_id not in league_map:
            continue
        if match.get("id"):
            eligible += 1
    comps = set(FOTMOB_LEAGUES)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .filter(SportsEvent.competition_id.in_(comps))
        .all()
    )
    with_id = 0
    for row in rows:
        if families_with_ids(load_json(row.extra_json, {}) or {}).get("fotmob"):
            with_id += 1
    pct = round((with_id / eligible) * 100, 1) if eligible else 0.0
    payload = {
        "recent_football_total": db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .count(),
        "fotmob_competitions": len(comps),
        "canonical_in_fotmob_comps": len(rows),
        "upstream_eligible": eligible,
        "canonical_with_fotmob_id": with_id,
        "coverage_pct": pct,
    }
    logger.info("fotmob_eligible_coverage %s", payload)
    return payload
