"""Read-only public status changes with retirements and an exact paging cursor.

A status delta must never bypass list visibility or revive a retired alias. The
cursor uses both microsecond timestamp and ID, not the client's response time.
"""
from __future__ import annotations
import base64
import json
from datetime import datetime, timedelta
from sqlalchemy import and_, or_
from collector.models import SportsEvent
from collector.maintenance_policy import automatic_promotion_blocked
from collector.util import load_json, parse_datetime

PAGE_SIZE = 400


def _cursor(row):
    text = json.dumps([row.updated_at.isoformat(timespec='microseconds'), row.event_id], separators=(',', ':'))
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def _bound(cursor):
    if not cursor or not isinstance(cursor, str) or len(cursor) > 512:
        return None
    try:
        ts, eid = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
        at = parse_datetime(ts)
        if at and isinstance(eid, str) and 0 < len(eid) <= 200:
            return at, eid
    except (ValueError, TypeError, UnicodeError):
        pass
    return None


def status_delta_page(db, provider, *, since=None, sport=None, cursor=None):
    from collector.provider import _blocked_public_sources, _row_public_source_allowed, live_public_event
    started = datetime.utcnow()
    query = db.query(SportsEvent)
    point = _bound(cursor)
    if point:
        at, eid = point
        query = query.filter(or_(SportsEvent.updated_at > at,
                                 and_(SportsEvent.updated_at == at, SportsEvent.event_id > eid)))
    else:
        at = parse_datetime(since) or started - timedelta(minutes=2)
        query = query.filter(SportsEvent.updated_at >= at)
    if sport:
        query = query.filter(SportsEvent.sport_id == sport)
    rows = query.order_by(SportsEvent.updated_at.asc(), SportsEvent.event_id.asc()).limit(PAGE_SIZE + 1).all()
    more = len(rows) > PAGE_SIZE
    rows = rows[:PAGE_SIZE]
    blocked_ids, blocked_families = _blocked_public_sources(db)
    events = []
    for row in rows:
        metas = [load_json(getattr(row, key, None), {}) or {} for key in ('extra_json', 'list_extra_json')]
        removed = (automatic_promotion_blocked(row) or row.display_eligible is False
                   or any(isinstance(meta, dict) and meta.get('display_eligible') is False for meta in metas)
                   or not _row_public_source_allowed(row, blocked_ids, blocked_families))
        if removed:
            events.append({'id': row.event_id, 'removed': True,
                           'updated_at': row.updated_at.isoformat(timespec='microseconds') + 'Z'})
            continue
        event = provider._to_normalized(row, list_mode=True)
        if not event:
            events.append({'id': row.event_id, 'removed': True,
                           'updated_at': row.updated_at.isoformat(timespec='microseconds') + 'Z'})
            continue
        public = live_public_event(event)
        # Explicit false/null are essential when clients merge partial payloads.
        public['live'] = bool(event.get('live'))
        public['live_class'] = event.get('live_class')
        public['updated_at'] = row.updated_at.isoformat(timespec='microseconds') + 'Z'
        events.append(public)
    return {'events': events, 'has_more': more, 'next_cursor': _cursor(rows[-1]) if rows else cursor,
            'next_since': (started-timedelta(seconds=1)).isoformat(timespec='microseconds')+'Z'}
