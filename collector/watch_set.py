"""LIVE WATCH SET: poll candidates. Never sets canonical LIVE from kickoff."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from sqlalchemy import or_, and_

from collector.live_state import CONFIRMED_LIVE, is_live
from collector.models import SportsEvent, SportsLiveWatch
from collector.util import load_json
from collector.watch_windows import pre_start_window, watch_duration

REASON_EXPLICIT = "EXPLICIT_LIVE"
REASON_WINDOW = "KICKOFF_WINDOW"


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _precision(row: SportsEvent) -> str:
    extra = load_json(row.extra_json, {}) or {}
    return str(extra.get("start_precision") or "")


def in_kickoff_watch_window(row: SportsEvent, *, now: Optional[datetime] = None) -> bool:
    now = _aware(now) or datetime.utcnow()
    if _precision(row) != "EXACT_TIME" or row.start_time is None:
        return False
    start = _aware(row.start_time)
    if start is None:
        return False
    if start.hour == 0 and start.minute == 0 and start.second == 0 and _precision(row) != "EXACT_TIME":
        return False
    pre = pre_start_window(row.sport_id)
    extra = load_json(row.extra_json, {}) or {}
    duration = watch_duration(row.sport_id, extra)
    return (start - pre) <= now <= (start + duration)


def rebuild_watch_set(db: Session, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = _aware(now) or datetime.utcnow()
    keep: Dict[str, SportsLiveWatch] = {}
    existing = {row.event_id: row for row in db.query(SportsLiveWatch).all()}
    entered = 0
    horizon_past = now - timedelta(days=6)
    horizon_future = now + timedelta(minutes=20)
    events = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(
            or_(
                SportsEvent.display_eligible.is_(True),
                SportsEvent.display_eligible.is_(None),
            )
        )
        .filter(
            or_(
                SportsEvent.status.in_(("live", "halftime", "break", "stale")),
                and_(SportsEvent.start_time >= horizon_past, SportsEvent.start_time <= horizon_future),
            )
        )
        .all()
    )
    for row in events:
        extra = load_json(row.extra_json, {}) or {}
        reason = None
        expires = now + timedelta(hours=4)
        if is_live(row.status) and extra.get("live_class") == CONFIRMED_LIVE:
            reason = REASON_EXPLICIT
            expires = now + watch_duration(row.sport_id, extra)
        elif (row.status or "") in {"scheduled", "delayed"} and in_kickoff_watch_window(row, now=now):
            reason = REASON_WINDOW
            start = _aware(row.start_time)
            expires = (start or now) + watch_duration(row.sport_id, extra)
        if not reason:
            continue
        watch = existing.get(row.event_id)
        if watch is None:
            watch = SportsLiveWatch(event_id=row.event_id)
            db.add(watch)
            entered += 1
        watch.competition_id = row.competition_id
        watch.sport_id = row.sport_id
        watch.reason = reason
        watch.expires_at = expires
        if watch.entered_at is None:
            watch.entered_at = now
        keep[row.event_id] = watch
    removed = 0
    for event_id, watch in existing.items():
        if event_id in keep:
            continue
        if watch.expires_at and watch.expires_at < now:
            db.delete(watch)
            removed += 1
        elif event_id not in keep:
            db.delete(watch)
            removed += 1
    db.flush()
    return {"watched": len(keep), "entered": entered, "removed": removed}


def watched_rows(db: Session) -> List[SportsLiveWatch]:
    return db.query(SportsLiveWatch).all()
