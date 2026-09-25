"""Bounded, resumable date-board coverage for ALL source-native football leagues.

This is a worker-owned discovery/result lane, not API-side fetching or a second
scheduler. Every observation uses the existing acceptance/score/identity pipeline.
A saved per-date cursor gives recent history/future fixtures a share even while
LIVE jobs keep the old bulk-maintenance path deferred. No fixture is deleted.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from collector.adapters import FetchResult
from collector.adapters_fotmob import _load_boards, match_to_event
from collector.cache import flush_list_invalidations
from collector.collect import _consume_result
from collector.flags import collection_enabled, scheduler_enabled, writes_enabled
from collector.fotmob_crosswalk import _ensure_dynamic_fotmob_mapping, _fotmob_competition_identity, _fill_identity_assets
from collector.keeper_revalidation import _same_pair
from collector.limits import is_rate_limited, record_hit
from collector.lock import acquire_write_lock, lock_status, release_write_lock
from collector.maintenance_policy import automatic_promotion_blocked
from collector.models import SportsCollectorJob, SportsEvent, SportsSource, SportsCompetition
from collector.source_ids import id_for_family
from collector.sources import source_collectable
from collector.util import dump_json, isoformat, load_json, parse_datetime

logger = logging.getLogger(__name__)
JOB_PREFIX = "football-board-refresh-v1:"
MAX_EVENTS_PER_PAGE = 100
PAGE_BUDGET_SECONDS = 8
HOT_INTERVAL_SECONDS = 30
HISTORY_INTERVAL_SECONDS = 21600
FUTURE_INTERVAL_SECONDS = 900


def rolling_dates(now: datetime) -> tuple[list[str], list[str]]:
    day = now.date()
    fmt = lambda offset: (day + timedelta(days=offset)).strftime("%Y%m%d")
    return [fmt(0), fmt(-1)], [fmt(x) for x in (-2, 1, 2, 3, -3, -4, -5, -6, -7)]


def _state(job: SportsCollectorJob | None) -> dict:
    value = load_json(job.last_error, {}) if job else {}
    return value if isinstance(value, dict) else {}


def _select_day(db, days: list[str], now: datetime) -> tuple[str, SportsCollectorJob | None] | None:
    jobs = {r.job_key: r for r in db.query(SportsCollectorJob).filter(
        SportsCollectorJob.job_key.in_([JOB_PREFIX + day for day in days])).all()}
    eligible = []
    for pos, day in enumerate(days):
        job = jobs.get(JOB_PREFIX + day)
        due = parse_datetime(_state(job).get("next_due_at"))
        if due is None or due <= now:
            eligible.append((job.last_run_at if job and job.last_run_at else datetime.min, pos, day, job))
    if not eligible:
        return None
    _, _, day, job = min(eligible, key=lambda x: (x[0], x[1]))
    return day, job


def _root(db, row: SportsEvent) -> SportsEvent | None:
    seen = set()
    for _ in range(9):
        if row.event_id in seen:
            return None
        seen.add(row.event_id)
        extra = load_json(row.extra_json, {}) or {}
        target = row.canonical_event_id or extra.get("canonical_event_id")
        if not target:
            return row
        row = db.get(SportsEvent, target)
        if row is None:
            return None
    return None


def _identity_index(db, day: str) -> dict[str, list[SportsEvent]]:
    start = datetime.strptime(day, "%Y%m%d")
    rows = db.query(SportsEvent).filter(
        SportsEvent.sport_id == "football",
        SportsEvent.start_time >= start - timedelta(hours=3),
        SportsEvent.start_time < start + timedelta(days=1, hours=3),
    ).all()
    index = defaultdict(list)
    for row in rows:
        source_id = id_for_family(load_json(row.extra_json, {}) or {}, "fotmob")
        if source_id:
            index[source_id].append(row)
    return index


def consume_board_match(db, raw: dict, source: SportsSource, identity: dict) -> dict:
    """Route exact existing source identity to its keeper, otherwise normal ingest."""
    cid, league_id, name, country = _fotmob_competition_identity(raw)
    parsed = match_to_event(raw, cid or "")
    if not cid or not league_id or not parsed:
        return {"rejected": 1, "reason": "missing_source_identity"}
    sid = str(parsed.get("source_event_id") or "")
    roots = {}
    for candidate in identity.get(sid, []):
        root = _root(db, candidate)
        if root is None:
            return {"rejected": 1, "reason": "broken_or_cyclic_lineage"}
        roots[root.event_id] = root
    keeper = None
    if roots:
        # An exact provider ID cannot authorize changing participant orientation
        # or joining two independent keepers. Leave conflicts for review.
        kickoff = parse_datetime(parsed.get("start_time"))
        valid = [row for row in roots.values() if row.sport_id == "football"
                 and _same_pair(row, parsed) and kickoff and row.start_time
                 and abs((row.start_time - kickoff).total_seconds()) <= 180]
        if len(valid) != 1 or len(roots) != 1:
            return {"rejected": 1, "reason": "source_identity_conflict"}
        keeper = valid[0]
        if automatic_promotion_blocked(keeper):
            return {"rejected": 1, "reason": "visibility_policy"}
        # Preserve canonical competition identity, aliases and source group ID.
        # The normal event_accepted_for_mapping gate still has the final say.
        cid = keeper.competition_id
    mapping = _ensure_dynamic_fotmob_mapping(db, competition_id=cid, league_id=league_id,
                                             league_name=name, ccode=country)
    if mapping is None or not mapping.enabled:
        return {"rejected": 1, "reason": "mapping_disabled_or_missing"}
    # Accumulate child IDs for a canonical competition instead of binding it
    # forever to the first season/group encountered. No static mapping is edited.
    config = load_json(mapping.source_config_json, {}) or {}
    ids = list(dict.fromkeys([str(v) for v in config.get("fotmob_league_ids", [])]
                            + [str(config.get("fotmob_league_id") or mapping.source_competition_id or league_id), league_id]))
    config["fotmob_league_ids"] = [v for v in ids if v]
    mapping.source_config_json = dump_json(config)
    parsed.update({"sport": "football", "competition_key": cid, "competition": name,
                   "source_family": "fotmob", "country_id": country or None})
    if keeper is not None:
        from collector.fotmob_crosswalk import _corrected_competition_logo
        original = load_json(keeper.extra_json, {}) or {}
        parsed["competition_logo"] = _corrected_competition_logo(str(original.get("competition_logo") or ""), parsed)
    from collector.competition_identity import event_accepted_for_mapping
    if not event_accepted_for_mapping(parsed, cid)[0]:
        return {"rejected": 1, "reason": "competition_acceptance"}
    result = _consume_result(db, source=source, mapping=mapping,
                             competition=db.get(SportsCompetition, cid), capability="results",
                             result=FetchResult(ok=True, http_status=200, events=[parsed], parse_status="ok"))
    if result.get("rejected"):
        raise RuntimeError("Observation persistence rejected; cursor retained for retry")
    # Artwork is independent of status/score signatures. Replace only a proven
    # old group badge with its actual parent badge, not arbitrary existing art.
    if keeper is not None:
        _fill_identity_assets(keeper, parsed)
    return {key: int(result.get(key) or 0) for key in ("written", "merged", "rejected", "skipped")}


def refresh_day(db, day: str, source: SportsSource, *, now: datetime, getter=None,
                max_events: int = MAX_EVENTS_PER_PAGE, budget_seconds: float = PAGE_BUDGET_SECONDS) -> dict:
    from collector.http import fetch_url, begin_budget, end_budget
    job = db.get(SportsCollectorJob, JOB_PREFIX + day)
    if job is None:
        job = SportsCollectorJob(job_key=JOB_PREFIX + day)
        db.add(job)
        db.flush()
    state = _state(job)
    after = str(state.get("after_id") or "")
    started = time.monotonic()
    record_hit(source.source_id)
    begin_budget(max_requests=1, max_seconds=6)
    try:
        bounded_getter = getter or (lambda url: fetch_url(url, timeout=6))
        matches = _load_boards(bounded_getter, dates=[day], ttl_seconds=HOT_INTERVAL_SECONDS)
    except Exception as exc:
        job.last_run_at = now
        job.last_status = "failed"
        state.update({"error": str(exc)[:300], "next_due_at": isoformat(now + timedelta(seconds=120))})
        job.last_error = dump_json(state)
        return {"day": day, "error": str(exc)[:300], "complete": False}
    finally:
        end_budget()
    matches = {str(r.get("id") or r.get("matchId") or ""): r for r in matches}
    matches.pop("", None)
    ordered = sorted((key, raw) for key, raw in matches.items() if key > after)
    index = _identity_index(db, day)
    totals = {"seen": len(matches), "processed": 0, "written": 0, "rejected": 0, "skipped": 0}
    reasons = defaultdict(int)
    failed = False
    for sid, raw in ordered:
        if totals["processed"] >= max_events or (totals["processed"] and time.monotonic() - started >= budget_seconds):
            break
        try:
            with db.begin_nested():
                result = consume_board_match(db, raw, source, index)
        except Exception as exc:
            logger.exception("FOOTBALL_BOARD observation failed day=%s id=%s", day, sid)
            reasons["exception"] += 1
            state["error"] = str(exc)[:300]
            failed = True
            break  # Failed observation is not acknowledged by the cursor.
        totals["processed"] += 1
        for key in ("written", "rejected", "skipped"):
            totals[key] += int(result.get(key) or 0)
        if result.get("reason"):
            reasons[result["reason"]] += 1
        after = sid
    complete = not failed and totals["processed"] == len(ordered)
    date = datetime.strptime(day, "%Y%m%d").date()
    interval = (HOT_INTERVAL_SECONDS if date >= now.date()-timedelta(days=1) and date <= now.date()
                else FUTURE_INTERVAL_SECONDS if date > now.date() else HISTORY_INTERVAL_SECONDS)
    # A partial page stays due but rotates behind dates that have never run.
    delay = 120 if failed else interval if complete else 0
    state.update({"after_id": "" if complete else after, "complete": complete,
                  "next_due_at": isoformat(now + timedelta(seconds=delay)), "totals": totals,
                  "reasons": dict(reasons)})
    if not failed:
        state["last_success_at"] = isoformat(now)
        state.pop("error", None)
    job.last_run_at = now
    job.last_status = "failed" if failed else "ok"
    job.items_written = totals["written"]
    job.last_error = dump_json(state)
    flush_list_invalidations(db)
    return {"day": day, "complete": complete, **totals, "reasons": dict(reasons)}


def run_football_board_refresh(db, *, owner: str, now: datetime | None = None, getter=None) -> dict:
    """At most one hot-day page + one rotating history/future page per cycle."""
    from collector.family_health import family_in_active_backoff, family_access_blocked
    from collector.http import family_host_blocked
    now = now or datetime.utcnow()
    if not (collection_enabled() and scheduler_enabled() and writes_enabled()):
        return {"skipped": "disabled"}
    lock = lock_status(db)
    if not lock.get("held") or lock.get("owner_id") != owner:
        return {"skipped": "not_scheduler_owner"}
    source = db.get(SportsSource, "fotmob-global")
    if source is None or not source_collectable(source) or source.adapter_key != "fotmob":
        return {"skipped": "source_unavailable"}
    capabilities = load_json(source.capabilities_json, {}) or {}
    if not capabilities.get("results") or not capabilities.get("fixtures"):
        return {"skipped": "capabilities_disabled"}
    if (family_in_active_backoff("fotmob") or family_access_blocked("fotmob")
            or family_host_blocked("fotmob") or is_rate_limited(db, source.source_id, now=now)):
        return {"skipped": "source_cooldown"}
    if not acquire_write_lock(db, owner=owner):
        return {"skipped": "write_lock_held"}
    pages = []
    try:
        for days in rolling_dates(now):
            if (family_in_active_backoff("fotmob") or family_access_blocked("fotmob")
                    or family_host_blocked("fotmob") or is_rate_limited(db, source.source_id, now=now)):
                break
            selected = _select_day(db, days, now)
            if selected is not None:
                pages.append(refresh_day(db, selected[0], source, now=now, getter=getter))
                db.commit()  # Cursor and observations commit together, including across restarts.
        return {"pages": pages}
    except Exception:
        db.rollback()
        raise
    finally:
        release_write_lock(db, owner=owner)
