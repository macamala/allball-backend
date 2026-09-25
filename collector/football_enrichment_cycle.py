"""Small current-football enrichment share under the existing scheduler lease.

No new scheduler, fixture discovery, score writes or identity relinking. Normal
validated detail/table readers do the work. A durable cursor prevents every
restart from starting again at the first league.
"""
from datetime import datetime, timedelta
import time
from collector.adapters import FetchResult
from collector.models import SportsCollectorJob, SportsEvent
from collector.util import load_json, dump_json, parse_datetime
from collector.flags import writes_enabled
from collector.lock import lock_status
from collector.maintenance_policy import automatic_promotion_blocked
from collector.source_ids import id_for_family

JOB_KEY = 'football-current-enrichment-v1'


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
    from collector.provider import _blocked_public_sources, _row_public_source_allowed
    blocked, families = _blocked_public_sources(db)
    candidates = db.query(SportsEvent).filter(
        SportsEvent.sport_id == 'football',
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
        SportsEvent.start_time >= now-timedelta(hours=12),
        SportsEvent.start_time <= now+timedelta(hours=48),
    ).order_by(SportsEvent.start_time.asc()).limit(1200).all()
    rows = []
    for row in candidates:
        if automatic_promotion_blocked(row) or not _row_public_source_allowed(row, blocked, families):
            continue
        meta = load_json(row.extra_json, {}) or {}
        slim = load_json(row.list_extra_json, {}) or {}
        if meta.get('display_eligible') is False or slim.get('display_eligible') is False:
            continue
        if id_for_family(meta, 'fotmob'):
            rows.append(row)
    state = load_json(job.last_error, {}) if job else {}
    state = state if isinstance(state, dict) else {}
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
        # One urgent slot followed by one oldest due slot avoids starving
        # announced future lineups while some football match is always live.
        return (parse_datetime(meta.get('detail_fetched_at')) or datetime.min, row.start_time, row.event_id)
    due = sorted([r for r in rows if not _fresh(load_json(r.extra_json, {}) or {}, r.status)], key=detail_order)
    urgent = next((r for r in due if r.status in ('live','halftime','break')), None)
    plan = ([urgent] if urgent else []) + [r for r in due if r is not urgent]
    attempted = 0
    for row in plan[:2]:
        if time.monotonic() >= deadline:
            break
        enrich_event_row(db, row, getter=bounded_get)
        attempted += 1
    keys = sorted({r.competition_id for r in rows if r.competition_id})
    after = str(state.get('after_competition') or '')
    ordered = [key for key in keys if key > after] + [key for key in keys if key <= after]
    live_keys = sorted({r.competition_id for r in rows if r.status in ('live','halftime','break')})
    cycle = int(state.get('cycle') or 0)
    # Every second pass is a fair league slot even during continuous live play.
    table_key = (live_keys[cycle//2 % len(live_keys)] if cycle % 2 == 0 and live_keys else (ordered[0] if ordered else None))
    table_rows = 0
    if table_key and time.monotonic() < deadline:
        table_rows = len(load_standings(db, table_key, getter=bounded_get))
        if cycle % 2 or not live_keys:
            state['after_competition'] = table_key
    state['cycle'] = cycle+1
    job.last_run_at = now
    job.last_status = 'ok'
    job.last_error = dump_json(state)
    job.items_written = attempted
    db.flush()
    return {'detail_attempts': attempted, 'table_competition': table_key, 'table_rows': table_rows, 'candidates': len(rows)}
