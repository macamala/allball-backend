"""Attach FotMob match IDs onto existing canonical football events.

Uses competition + kickoff + participants. Does not create duplicate fixtures.
Does not match on title text alone. Date-board backfill is bounded and checkpointed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_fotmob import (
    FOTMOB_LEAGUES,
    _BOARD,
    _load_boards,
    board_dates,
    match_to_event,
)
from collector.identity_events import identity_confidence
from collector.list_extra import store_list_extra
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsEvent
from collector.source_ids import families_with_ids, merge_family_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

DATE_BOARD_JOB = "fotmob-date-boards-v1"
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


def _unique_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for match in matches:
        mid = str(match.get("id") or match.get("matchId") or "")
        if not mid:
            continue
        seen.setdefault(mid, match)
    return list(seen.values())


def _match_keepers(
    incoming: Dict[str, Any],
    rows: List[SportsEvent],
) -> Tuple[Optional[SportsEvent], int, int]:
    incoming_day = str(incoming.get("start_time") or "")[:10]
    scored: List[Tuple[int, SportsEvent]] = []
    protected = 0
    for row in rows:
        view = _event_view(row)
        if incoming_day and str(view.get("start_time") or "")[:10] != incoming_day:
            continue
        if _protected_conflict(view, incoming):
            protected += 1
            continue
        score = identity_confidence(view, incoming)
        if score < 90:
            continue
        scored.append((score, row))
    if not scored:
        return None, 0, protected
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[1][0] >= 90:
        return None, 2, protected
    return scored[0][1], 1, protected


def crosswalk_fotmob_ids(
    db: Session,
    *,
    hours: int = 192,
    getter=None,
    dates: Optional[List[str]] = None,
    past_days: Optional[int] = None,
    future_days: Optional[int] = None,
) -> Dict[str, int]:
    from collector.http import fetch_url

    _BOARD.clear()
    if dates is None and (past_days is not None or future_days is not None):
        dates = board_dates(past_days=past_days if past_days is not None else 3, future_days=future_days if future_days is not None else 1)
    try:
        matches = _load_boards(getter or fetch_url, dates=dates)
    except Exception:
        matches = []
    matches = _unique_matches(matches)
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
    upstream_total = len(matches)
    eligible = attached = skipped_conflict = unmatched = ambiguous = 0
    eligible_ids: List[str] = []
    for match in matches:
        league_id = str((match.get("_league") or {}).get("id") or "")
        competition_id = league_map.get(league_id)
        if not competition_id:
            continue
        parsed = match_to_event(match, competition_id)
        if not parsed or not parsed.get("source_event_id"):
            continue
        eligible += 1
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
        best, n_ok, protected = _match_keepers(incoming, by_comp.get(competition_id) or [])
        skipped_conflict += protected
        if n_ok >= 2:
            ambiguous += 1
            continue
        if best is None:
            unmatched += 1
            continue
        if _attach(best, str(parsed["source_event_id"])):
            attached += 1
    db.flush()
    logger.info(
        "fotmob_crosswalk upstream_total=%s eligible=%s attached=%s unmatched=%s ambiguous=%s protected=%s",
        upstream_total,
        eligible,
        attached,
        unmatched,
        ambiguous,
        skipped_conflict,
    )
    return {
        "upstream_total": upstream_total,
        "upstream_eligible": eligible,
        "attached": attached,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "protected_conflicts": skipped_conflict,
    }


def eligible_coverage(
    db: Session,
    *,
    hours: int = 192,
    getter=None,
    dates: Optional[List[str]] = None,
    past_days: int = 7,
    future_days: int = 1,
) -> Dict[str, Any]:
    from collector.http import fetch_url

    _BOARD.clear()
    board = dates or board_dates(past_days=past_days, future_days=future_days)
    try:
        matches = _unique_matches(_load_boards(getter or fetch_url, dates=board))
    except Exception:
        matches = []
    league_map = _league_to_competition()
    bound = datetime.utcnow() - timedelta(hours=hours)
    eligible_ids: set[str] = set()
    upstream_total = 0
    for match in matches:
        mid = str(match.get("id") or match.get("matchId") or "")
        if not mid:
            continue
        upstream_total += 1
        league_id = str((match.get("_league") or {}).get("id") or "")
        if league_id in league_map:
            eligible_ids.add(mid)
    comps = set(FOTMOB_LEAGUES)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .filter(SportsEvent.competition_id.in_(comps))
        .all()
    )
    canonical_ids: set[str] = set()
    with_id = 0
    for row in rows:
        fid = families_with_ids(load_json(row.extra_json, {}) or {}).get("fotmob")
        if fid:
            with_id += 1
            canonical_ids.add(str(fid))
    matched_ids = eligible_ids & canonical_ids
    eligible = len(eligible_ids)
    pct = round((len(matched_ids) / eligible) * 100, 1) if eligible else 0.0
    payload = {
        "recent_football_total": db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .count(),
        "fotmob_competitions": len(comps),
        "canonical_in_fotmob_comps": len(rows),
        "canonical_with_fotmob_id": with_id,
        "upstream_total": upstream_total,
        "upstream_eligible": eligible,
        "ids_attached_intersection": len(matched_ids),
        "unmatched_eligible": eligible - len(matched_ids),
        "coverage_pct": pct,
        "board_days": board,
    }
    logger.info("fotmob_eligible_coverage %s", payload)
    return payload


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, DATE_BOARD_JOB)
    if row is None:
        row = SportsCollectorJob(job_key=DATE_BOARD_JOB)
        db.add(row)
        db.flush()
    return row


def _checkpoint(job: SportsCollectorJob, **fields: Any) -> None:
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(fields)
    job.last_error = dump_json(payload)[:4000]
    job.last_status = str(payload.get("state") or job.last_status or "")


def run_date_board_backfill(
    db: Session,
    *,
    getter=None,
    past_days: int = 7,
    future_days: int = 1,
    heartbeat: Optional[Callable[[], None]] = None,
    owner: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Owner-only bounded FotMob date boards. Attaches IDs only; no matchDetails crawl."""
    status = lock_status(db)
    if not status.get("held"):
        logger.info("skip fotmob date boards; scheduler lease is not held")
        return None
    if owner and status.get("owner_id") != owner:
        logger.info("skip fotmob date boards; process is not the scheduler owner")
        return None
    from collector.http import fetch_url

    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    dates = list(payload.get("dates") or board_dates(past_days=past_days, future_days=future_days))
    next_index = int(payload.get("next_index") or 0)
    totals = {
        "upstream_total": int(payload.get("upstream_total") or 0),
        "upstream_eligible": int(payload.get("upstream_eligible") or 0),
        "attached": int(payload.get("attached") or 0),
        "unmatched": int(payload.get("unmatched") or 0),
        "ambiguous": int(payload.get("ambiguous") or 0),
        "days_processed": list(payload.get("days_processed") or []),
    }
    fetch = getter or fetch_url
    for index, day in enumerate(dates):
        if index < next_index:
            continue
        if heartbeat:
            heartbeat()
        _BOARD.clear()
        day_result = crosswalk_fotmob_ids(db, getter=fetch, dates=[day])
        for key in ("upstream_total", "upstream_eligible", "attached", "unmatched", "ambiguous"):
            totals[key] = int(totals.get(key) or 0) + int(day_result.get(key) or 0)
        totals["days_processed"].append(day)
        _checkpoint(
            job,
            state="running",
            dates=dates,
            next_index=index + 1,
            **totals,
        )
        db.commit()
    coverage = eligible_coverage(db, getter=fetch, dates=dates)
    _checkpoint(job, state="done", dates=dates, next_index=len(dates), coverage=coverage, **totals)
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int(totals.get("attached") or 0)
    db.commit()
    logger.info("fotmob_date_boards_complete %s coverage=%s", totals, coverage)
    return {**totals, "coverage": coverage, "dates": dates}


def run_date_boards_if_due(
    db: Session,
    *,
    min_interval_hours: int = 6,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    getter=None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None
    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    state = payload.get("state")
    if state == "done" and job.last_run_at and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours):
        return None
    if state == "done":
        job.last_error = dump_json({"state": "pending"})
        db.flush()
    return run_date_board_backfill(db, getter=getter, heartbeat=heartbeat, owner=owner)
