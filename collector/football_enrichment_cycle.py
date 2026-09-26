"""Bounded football-detail reconciliation under the existing scheduler lease.

Live, recent final and upcoming matches share a fair repair queue. No second
scheduler, fixture discovery, score writes, identity relinking or new service.
The persisted scan cursor prevents a busy date window hiding matches beyond the
candidate limit. Existing source restrictions and host backoffs remain in force.
"""
from datetime import datetime, timedelta
import time

from sqlalchemy import or_
from collector.adapters import FetchResult
from collector.models import SportsCollectorJob, SportsEvent
from collector.util import load_json, dump_json, parse_datetime
from collector.flags import writes_enabled
from collector.lock import lock_status
from collector.maintenance_policy import automatic_promotion_blocked
from collector.source_ids import families_with_ids
from collector.football_detail_retry import RECOVERY_HOURS, FINISHED_STATUSES

JOB_KEY = 'football-current-enrichment-v1'
MAX_CANDIDATES = 1200
MAX_LIVE_CANDIDATES = 128
FOOTBALL_DETAIL_FAMILIES = frozenset({'fotmob', 'sofascore-web', 'openligadb'})
LIVE_STATUSES = frozenset({'live', 'halftime', 'break'})
NONPLAYED_STATUSES = frozenset({'cancelled', 'canceled', 'abandoned', 'postponed', 'awarded'})


def _candidate_page(db, now, after):
    query = db.query(SportsEvent).filter(
        SportsEvent.sport_id == 'football',
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
        SportsEvent.status.notin_(NONPLAYED_STATUSES),
        SportsEvent.start_time >= now-timedelta(hours=RECOVERY_HOURS),
        SportsEvent.start_time <= now+timedelta(hours=48),
        or_(SportsEvent.status.in_(FINISHED_STATUSES),
            SportsEvent.start_time >= now-timedelta(hours=12)),
    )
    ordered = query.order_by(SportsEvent.event_id.asc())
    page = (ordered.filter(SportsEvent.event_id > after) if after else ordered).limit(MAX_CANDIDATES).all()
    if after and len(page) < MAX_CANDIDATES:
        page += ordered.filter(SportsEvent.event_id <= after).limit(MAX_CANDIDATES-len(page)).all()
    # Live detail is never delayed just because its ID lies on another page.
    urgent = query.filter(SportsEvent.status.in_(LIVE_STATUSES)).order_by(
        SportsEvent.start_time.asc(), SportsEvent.event_id.asc()
    ).limit(MAX_LIVE_CANDIDATES).all()
    by_id = {row.event_id: row for row in page}
    by_id.update({row.event_id: row for row in urgent})
    return list(by_id.values()), page[-1].event_id if page else after


def _detail_plan(due, cycle):
    lanes = [
        [row for row in due if row.status in LIVE_STATUSES],
        [row for row in due if row.status in FINISHED_STATUSES],
        [row for row in due if row.status not in LIVE_STATUSES | FINISHED_STATUSES],
    ]
    # Rotate the FIRST slot too. Otherwise a slow live request can consume the
    # entire six-second budget and starve finals forever despite a second slot.
    ordered = lanes[cycle % 3:] + lanes[:cycle % 3]
    heads = [lane[0] for lane in ordered if lane]
    picked = {row.event_id for row in heads}
    return (heads + [row for row in due if row.event_id not in picked])[:2]


def warm_current_football(db, *, owner, now=None, getter=None, budget_seconds=6):
    now = now or datetime.utcnow()
    if not writes_enabled():
        return {'skipped': 'writes_disabled'}
    lease = lock_status(db)
    if not lease.get('held') or lease.get('owner_id') != owner:
        return {'skipped': 'not_scheduler_owner'}
    job = db.get(SportsCollectorJob, JOB_KEY)
    if job and job.last_run_at and (now-job.last_run_at).total_seconds() < 30:
        return {'skipped': 'not_due'}
    state = load_json(job.last_error, {}) if job else {}
    state = state if isinstance(state, dict) else {}
    candidates, cursor = _candidate_page(db, now, str(state.get('after_detail_event') or ''))
    from collector.provider import _blocked_public_sources, _row_public_source_allowed
    blocked, families = _blocked_public_sources(db)
    rows = []
    for row in candidates:
        if automatic_promotion_blocked(row) or not _row_public_source_allowed(row, blocked, families):
            continue
        meta = load_json(row.extra_json, {}) or {}
        slim = load_json(row.list_extra_json, {}) or {}
        if meta.get('display_eligible') is False or slim.get('display_eligible') is False:
            continue
        ids = families_with_ids(meta)
        if any(ids.get(family) for family in FOOTBALL_DETAIL_FAMILIES):
            rows.append(row)
    if job is None:
        job = SportsCollectorJob(job_key=JOB_KEY)
        db.add(job)
    deadline = time.monotonic()+max(0, min(6, budget_seconds))
    from collector.http import fetch_url
    def bounded_get(url, **kwargs):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            return FetchResult(ok=False, error='enrichment time budget exhausted')
        return getter(url) if getter else fetch_url(url, timeout=min(3, remaining), **kwargs)
    from collector.detail_enrich import enrich_event_row, _fresh
    from collector.standings_enrich import load_standings
    def detail_order(row):
        meta = load_json(row.extra_json, {}) or {}
        return (parse_datetime(meta.get('detail_fetched_at')) or datetime.min, row.start_time, row.event_id)
    due = sorted([
        row for row in rows
        if not _fresh(load_json(row.extra_json, {}) or {}, row.status,
                      sport=row.sport_id, start_time=row.start_time, now=now)
    ], key=detail_order)
    cycle = int(state.get('cycle') or 0)
    attempted = []
    for row in _detail_plan(due, cycle):
        if time.monotonic() >= deadline:
            break
        enrich_event_row(db, row, getter=bounded_get)
        attempted.append(row.event_id)
    keys = sorted({row.competition_id for row in rows if row.competition_id})
    after = str(state.get('after_competition') or '')
    ordered = [key for key in keys if key > after] + [key for key in keys if key <= after]
    live_keys = sorted({row.competition_id for row in rows if row.status in LIVE_STATUSES})
    # Preserve the existing fair table slot and shared time budget.
    table_key = (live_keys[cycle//2 % len(live_keys)] if cycle % 2 == 0 and live_keys else (ordered[0] if ordered else None))
    table_rows = 0
    if table_key and time.monotonic() < deadline:
        table_rows = len(load_standings(db, table_key, getter=bounded_get))
        if cycle % 2 or not live_keys:
            state['after_competition'] = table_key
    state['cycle'] = cycle+1
    state['after_detail_event'] = cursor
    job.last_run_at = now
    job.last_status = 'ok'
    job.last_error = dump_json(state)
    job.items_written = len(attempted)
    db.flush()
    return {'detail_attempts': len(attempted), 'detail_event_ids': attempted,
            'table_competition': table_key, 'table_rows': table_rows,
            'candidates': len(rows)}
