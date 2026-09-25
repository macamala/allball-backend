"""Bounded live-score cycles with a small discovery share; no history-wide repair."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from collector.incremental import run_incremental_tick
from collector.lock import heartbeat_scheduler_lock
from collector.models import SportsEvent

logger = logging.getLogger(__name__)
_last_discovery = 0.0


def has_priority_events(db, *, now=None) -> bool:
    """A polling candidate is not a declaration that a match is LIVE."""
    now = now or datetime.utcnow()
    return db.query(SportsEvent.event_id).filter(
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.isnot(False),
        or_(
            and_(SportsEvent.sport_id == "football",
                 SportsEvent.status.in_(("scheduled", "delayed", "unknown")),
                 SportsEvent.start_time >= now - timedelta(hours=48),
                 SportsEvent.start_time <= now),
            and_(SportsEvent.status.in_(("live", "halftime", "break", "stale")),
                 SportsEvent.start_time >= now - timedelta(days=6)),
            and_(SportsEvent.status.in_(("scheduled", "delayed")),
                 SportsEvent.start_time >= now - timedelta(hours=5),
                 SportsEvent.start_time <= now + timedelta(minutes=20)),
        ),
    ).first() is not None


def run_priority_cycle(db, *, owner: str) -> bool:
    """Return true while bulk maintenance must yield to active score polling."""
    global _last_discovery
    # Source-native leagues must not wait behind slower all-sport/detail work.
    # Same scheduler lease, cooldowns, cursor and observation acceptance gate.
    from collector.football_board_refresh import run_football_board_refresh
    try:
        urgent = run_football_board_refresh(db, owner=owner, hot_only=True)
        db.commit()
        logger.info("FOOTBALL_HOT_FIRST %s", urgent)
    except Exception:
        db.rollback()
        logger.exception("Hot football refresh failed; prior observations retained")
    if not heartbeat_scheduler_lock(db, owner=owner):
        db.rollback()
        raise RuntimeError("Results scheduler lease lost")
    db.commit()
    for label, filters in (
        ("FOOTBALL_SCORE_LANE", {"sport_id": "football", "source_family": "fotmob", "max_physical": 2}),
        ("ALLSPORT_LIVE_LANE", {"max_physical": 6}),
    ):
        logger.info("%s start", label)
        result = run_incremental_tick(db, liveish_only=True, run_maintenance=False, **filters)
        db.commit()
        if not heartbeat_scheduler_lock(db, owner=owner):
            db.rollback()
            raise RuntimeError("Results scheduler lease lost")
        db.commit()
        logger.info("%s %s", label, {key: result.get(key) for key in (
            "due_jobs", "selected_jobs", "jobs_processed", "events_changed", "duration_s", "stopped", "reason",
        )})
    from collector.football_board_refresh import run_football_board_refresh

    try:
        board = run_football_board_refresh(db, owner=owner)
        db.commit()
        if board.get("pages"):
            logger.info("FOOTBALL_BOARD_REFRESH %s", board)
    except Exception:
        db.rollback()
        logger.exception("Bounded football board refresh failed; retaining prior results")
    if not heartbeat_scheduler_lock(db, owner=owner):
        db.rollback()
        raise RuntimeError("Results scheduler lease lost")
    db.commit()
    active = has_priority_events(db)
    if active and time.monotonic() - _last_discovery >= 60:
        # Do not starve tomorrow's fixtures while international matches are live
        # around the clock. A single fair discovery group gets a bounded share.
        result = run_incremental_tick(db, discovery_only=True, max_physical=1, run_maintenance=False)
        db.commit()
        if not heartbeat_scheduler_lock(db, owner=owner):
            db.rollback()
            raise RuntimeError("Results scheduler lease lost")
        db.commit()
        _last_discovery = time.monotonic()
        logger.info("BOUNDED_DISCOVERY %s", {key: result.get(key) for key in (
            "jobs_processed", "events_changed", "duration_s", "stopped", "reason",
        )})
    # Enrichment gets a bounded share only AFTER score lanes. Uses this owner's
    # existing lease; it cannot create an independent collector or alter scores.
    try:
        from collector.football_enrichment_cycle import warm_current_football
        enrichment = warm_current_football(db, owner=owner)
        db.commit()
        if not enrichment.get("skipped"):
            logger.info("FOOTBALL_CURRENT_ENRICHMENT %s", enrichment)
    except Exception:
        db.rollback()
        logger.exception("Current football detail/table warming failed; prior data retained")
    return active
