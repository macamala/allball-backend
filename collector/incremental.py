"""Incremental due-queue: urgency jobs, family coalescing, discovery backoff."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.cadence import interval_for
from collector.family_caps import family_caps, is_static_family, min_safe_interval, supports_live
from collector.family_health import (
    family_access_blocked,
    family_blocks_live_path,
    family_in_active_backoff,
    family_needs_failover,
    family_retry_eligible,
    family_state,
)
from collector.http import STATS
from collector.metrics import incr, set_metric, snapshot
from collector.models import (
    SportsCompetition,
    SportsCompetitionHealth,
    SportsEvent,
    SportsSchedulerSlot,
    SportsSource,
    SportsSourceCompetition,
)
from collector.urgency import URGENCY_PRIORITY, capability_for_urgency, classify_event, job_dict, workload_for_urgency
from collector.watch_set import in_kickoff_watch_window, rebuild_watch_set
from collector.util import load_json


MAX_LOGICAL = 80
MAX_PHYSICAL = 18
MAX_LIVE_PHYSICAL = 8
MAX_BACKGROUND_PHYSICAL = 8
VERIFICATION_EVERY = 12
STARVE_SECONDS = 600
LIVE_STARVE_SECONDS = 90
AGE_BAND_SECONDS = 600
MAX_AGE_BANDS = 2
MAX_FAMILY_NONLIVE = 1
FINISHED_LOOKBACK_HOURS = 48
TICK_LIVE_BUDGET_S = 20
PRIORITY_URGENCIES = frozenset({"LIVE", "LIVE_CANDIDATE", "IMMINENT", "RECENTLY_FINISHED"})
_family_rr = 0
_live_registry: Dict[str, Dict[str, Any]] = {}


def live_registry_snapshot() -> Dict[str, Dict[str, Any]]:
    return {key: dict(val) for key, val in _live_registry.items()}


def note_live_family(family: str, **fields: Any) -> Dict[str, Any]:
    if not family:
        return {}
    row = _live_registry.setdefault(
        family,
        {
            "family": family,
            "live_event_count": 0,
            "last_fetch_started_at": None,
            "last_fetch_completed_at": None,
            "last_success_at": None,
            "next_eligible_at": None,
            "failure_count": 0,
            "backoff_until": None,
            "oldest_live_canonical_age": None,
            "target_cadence_s": interval_for(family, "LIVE"),
            "minimum_safe_s": min_safe_interval(family),
        },
    )
    row.update({key: value for key, value in fields.items() if value is not None})
    return row


def live_idle_seconds(default: int = 20) -> int:
    """Shorten post-tick sleep while CONFIRMED_LIVE families are active."""
    if not _live_registry:
        return max(15, int(default))
    now = _now()
    waits: List[int] = []
    for row in _live_registry.values():
        if int(row.get("live_event_count") or 0) <= 0:
            continue
        if family_blocks_live_path(str(row.get("family") or "")):
            continue
        nxt = row.get("next_eligible_at")
        if isinstance(nxt, datetime):
            waits.append(max(0, int((nxt - now).total_seconds())))
        else:
            waits.append(0)
    if not waits:
        return max(15, int(default))
    return max(5, min(15, min(waits) if min(waits) > 0 else 5))
FAIL_STATUSES = {
    "NETWORK_FAILURE",
    "RATE_LIMITED",
    "SOURCE_CHANGED",
    "PARSE_FAILURE",
    "OTHER_ERROR",
    "NO_VALID_FALLBACK",
    "FAILED",
    "ACCESS_BLOCKED",
}


def _now() -> datetime:
    return datetime.utcnow()


def request_identity(mapping: SportsSourceCompetition, source: SportsSource) -> str:
    config = load_json(mapping.source_config_json, {}) or {}
    url = str(config.get("url") or source.attribution_url or "")
    family = mapping.upstream_family or source.upstream_family or source.source_id
    if url:
        return f"{family}|{url}"
    return f"{family}|{mapping.source_competition_id or mapping.competition_id}"


def _slot(db: Session, job_key: str) -> SportsSchedulerSlot:
    cache = db.info.setdefault("scheduler_slots", {})
    row = cache.get(job_key)
    if row is not None:
        return row
    row = db.get(SportsSchedulerSlot, job_key)
    if row is None:
        for pending in db.new:
            if isinstance(pending, SportsSchedulerSlot) and pending.job_key == job_key:
                row = pending
                break
    if row is None:
        row = db.query(SportsSchedulerSlot).filter_by(job_key=job_key).first()
    if row is None:
        row = SportsSchedulerSlot(job_key=job_key)
        db.add(row)
        try:
            with db.begin_nested():
                db.flush()
        except Exception:
            row = db.get(SportsSchedulerSlot, job_key) or db.query(SportsSchedulerSlot).filter_by(job_key=job_key).first()
            if row is None:
                raise
    cache[job_key] = row
    return row


def _due(slot: Optional[SportsSchedulerSlot], interval: int, now: datetime, family: str = "") -> bool:
    if family and family_in_active_backoff(family):
        return False
    if slot is not None and slot.last_status in FAIL_STATUSES and slot.last_run_at is not None:
        fails = int(family_state(family).get("consecutive_failures") or 1)
        backoff = min(900, 30 * (2 ** min(max(fails, 1) - 1, 4)))
        if now < slot.last_run_at + timedelta(seconds=backoff):
            return False
    if slot is None or slot.next_due_at is None:
        if slot is None or slot.last_run_at is None:
            return True
        return slot.last_run_at + timedelta(seconds=interval) <= now
    return slot.next_due_at <= now


def _mapping_family(mapping: SportsSourceCompetition, source: Optional[SportsSource]) -> str:
    return mapping.upstream_family or (source.upstream_family if source else None) or mapping.source_id


def _primary_family(db: Session, competition_id: str) -> Tuple[Optional[SportsSourceCompetition], Optional[SportsSource]]:
    maps = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, enabled=True)
        .order_by(SportsSourceCompetition.priority.asc())
        .all()
    )
    cache = db.info.setdefault("sources", {})
    for mapping in maps:
        source = cache.get(mapping.source_id)
        if source is None:
            source = db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
            if source:
                cache[mapping.source_id] = source
        if source and source.enabled:
            return mapping, source
    return None, None


def _fallback_family(db: Session, competition_id: str, primary_family: str) -> Tuple[Optional[SportsSourceCompetition], Optional[SportsSource]]:
    maps = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, enabled=True)
        .order_by(SportsSourceCompetition.priority.asc())
        .all()
    )
    cache = db.info.setdefault("sources", {})
    for mapping in maps:
        source = cache.get(mapping.source_id) or db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
        if source:
            cache[mapping.source_id] = source
        family = _mapping_family(mapping, source)
        if family == primary_family:
            continue
        if source and source.enabled:
            return mapping, source
    return None, None


def build_due_jobs(db: Session, *, now: Optional[datetime] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    now = now or _now()
    rebuild_watch_set(db, now=now)
    horizon = now + timedelta(days=30)
    past = now - timedelta(hours=FINISHED_LOOKBACK_HOURS)
    events = (
        db.query(SportsEvent)
        .filter(
            (SportsEvent.status.in_(["live", "stale"]))
            | ((SportsEvent.start_time >= past) & (SportsEvent.start_time <= horizon))
        )
        .all()
    )
    jobs: List[Dict[str, Any]] = []
    seen_comp_family: set = set()
    live_jobs = 0
    maps_by_comp: Dict[str, List[SportsSourceCompetition]] = {}
    for mapping in db.query(SportsSourceCompetition).filter_by(enabled=True).all():
        maps_by_comp.setdefault(mapping.competition_id, []).append(mapping)
    source_cache = db.info.setdefault("sources", {})
    for row in events:
        mappings = maps_by_comp.get(row.competition_id) or []
        if not mappings:
            mapping, source = _primary_family(db, row.competition_id)
            mappings = [mapping] if mapping is not None else []
        urgency = classify_event(row.status, row.start_time, now=now)
        if urgency != "LIVE" and in_kickoff_watch_window(row, now=now):
            urgency = "LIVE_CANDIDATE"
        if urgency == "LIVE":
            live_jobs += 1
        for mapping in mappings:
            if mapping is None:
                continue
            source = source_cache.get(mapping.source_id)
            if source is None:
                source = db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
                if source:
                    source_cache[mapping.source_id] = source
            if source is None or not source.enabled:
                continue
            family = _mapping_family(mapping, source)
            family_urgency = urgency
            if family_urgency == "LIVE":
                if is_static_family(family) or not supports_live(family):
                    family_urgency = "TODAY"
            if family_urgency == "LIVE_CANDIDATE":
                if is_static_family(family) or not supports_live(family):
                    family_urgency = "TODAY"
            if family_urgency in {"LIVE", "LIVE_CANDIDATE"} and family_needs_failover(family):
                fb_map, fb_src = _fallback_family(db, row.competition_id, family)
                fb_family = _mapping_family(fb_map, fb_src) if fb_map and fb_src else ""
                if (
                    fb_map
                    and fb_src
                    and supports_live(fb_family)
                    and not is_static_family(fb_family)
                    and not family_blocks_live_path(fb_family)
                ):
                    mapping, source, family = fb_map, fb_src, fb_family
                elif family_blocks_live_path(family) or family_in_active_backoff(family):
                    pass
                else:
                    continue
            interval = interval_for(family, family_urgency)
            job_key = f"refresh:{row.competition_id}:{family}:{capability_for_urgency(family_urgency)}"
            slot = db.get(SportsSchedulerSlot, job_key)
            if not _due(slot, interval, now, family):
                continue
            seen_key = (row.competition_id, family)
            if seen_key in seen_comp_family and family_urgency not in {"LIVE", "LIVE_CANDIDATE", "IMMINENT", "RECENTLY_FINISHED"}:
                continue
            seen_comp_family.add(seen_key)
            jobs.append(
                job_dict(
                    competition_id=row.competition_id,
                    family=family,
                    urgency=family_urgency,
                    reason=f"event:{row.event_id}:{family_urgency}",
                    source_id=source.source_id,
                    request_key=request_identity(mapping, source),
                    job_key=job_key,
                    interval=interval,
                    use_fallback=False,
                    sport=row.sport_id,
                    workload=workload_for_urgency(family_urgency),
                    last_run_at=slot.last_run_at if slot else None,
                    next_due_at=slot.next_due_at if slot else None,
                    last_status=slot.last_status if slot else None,
                )
            )
    health_rows = {row.competition_id: row for row in db.query(SportsCompetitionHealth).all()}
    mapped = (
        db.query(SportsSourceCompetition)
        .filter_by(enabled=True)
        .all()
    )
    comps_seen = {(job["competition_id"], job["family"]) for job in jobs}
    for mapping in mapped:
        cid = mapping.competition_id
        source = db.info.setdefault("sources", {}).get(mapping.source_id) or db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
        if source is None or not source.enabled:
            continue
        family = _mapping_family(mapping, source)
        if (cid, family) in comps_seen:
            continue
        health = health_rows.get(cid)
        empty_streak = 0
        if health and health.last_classification in {"NO_CURRENT_EVENTS", "EMPTY", "WORKING_EMPTY"}:
            empty_streak = 1
        urgency = "DISCOVERY_QUIET" if empty_streak else "DISCOVERY_ACTIVE"
        interval = interval_for(family, urgency)
        job_key = f"discover:{cid}:{family}"
        slot = db.get(SportsSchedulerSlot, job_key)
        if not _due(slot, interval, now, family):
            continue
        jobs.append(
            job_dict(
                competition_id=cid,
                family=family,
                urgency=urgency,
                reason="competition_discovery",
                source_id=source.source_id,
                request_key=request_identity(mapping, source),
                job_key=job_key,
                interval=interval,
                use_fallback=False,
                last_run_at=slot.last_run_at if slot else None,
                next_due_at=slot.next_due_at if slot else None,
                last_status=slot.last_status if slot else None,
                last_attempt_at=health.last_attempt_at if health else None,
                last_success_at=health.last_success_at if health else None,
                workload=workload_for_urgency(urgency),
            )
        )
        comps_seen.add((cid, family))
    jobs.sort(key=lambda row: (row["priority"], row["competition_id"]))
    deduped: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for job in jobs:
        key = job["job_key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(job)
    jobs = deduped
    set_metric("due_jobs", len(jobs))
    set_metric("live_jobs", live_jobs)
    if limit is not None:
        return jobs[:limit]
    return jobs


def filter_due_jobs(jobs: List[Dict[str, Any]], *, live_only: bool = False) -> List[Dict[str, Any]]:
    if not live_only:
        return jobs
    return [job for job in jobs if str(job.get("urgency") or "") in PRIORITY_URGENCIES]


def coalesce_jobs(jobs: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for job in jobs:
        family = str(job.get("family") or "")
        scope = str(family_caps(family).get("shared_request_scope") or "competition")
        if job.get("urgency") == "LIVE" and scope == "family":
            key = f"live-family|{family}"
        else:
            key = job.get("request_key") or job["job_key"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(job)
    return [groups[key] for key in order]


def job_lane(job: Dict[str, Any]) -> int:
    urgency = job.get("urgency") or ""
    family = str(job.get("family") or "")
    if urgency == "LIVE":
        if family_blocks_live_path(family):
            return 3
        return 0
    if urgency in {"LIVE_CANDIDATE", "IMMINENT"}:
        return 1
    if urgency == "RECENTLY_FINISHED":
        return 2
    return 3


def job_wait_seconds(job: Dict[str, Any], now: datetime) -> float:
    due = job.get("next_due_at") or job.get("last_run_at")
    if due is None:
        return 1_000_000.0
    if isinstance(due, str):
        try:
            due = datetime.fromisoformat(due.replace("Z", ""))
        except ValueError:
            return 1_000_000.0
    return max(0.0, (now - due).total_seconds())


def job_never_run(job: Dict[str, Any]) -> bool:
    return not job.get("last_run_at") and not job.get("next_due_at")


def job_sort_key(job: Dict[str, Any], now: datetime) -> Tuple:
    wait = job_wait_seconds(job, now)
    rank = int(URGENCY_PRIORITY.get(job.get("urgency") or "", 50))
    bump = min(MAX_AGE_BANDS, int(wait // AGE_BAND_SECONDS))
    effective = max(1, rank - bump)
    liveish = 0 if rank <= URGENCY_PRIORITY["RECENTLY_FINISHED"] else 1
    never = 0 if job_never_run(job) else 1
    last = job.get("last_run_at") or datetime.min
    # Do not tie-break on family name: that stably starves openligadb/wta-json.
    return (liveish, never, effective, -wait, last, job.get("competition_id") or "")


def select_fair_groups(
    jobs: List[Dict[str, Any]],
    now: datetime,
    *,
    max_physical: int = MAX_PHYSICAL,
) -> Tuple[List[List[Dict[str, Any]]], Dict[str, Any]]:
    """Pick up to max_physical request groups from the full due set.

    P0 CONFIRMED_LIVE families get reserved slots (one physical fetch per family
    first, up to MAX_PHYSICAL). Extra URLs of an already-selected live family wait
    for a later tick. P1 candidates/imminent and P2 finalization may use leftover
    live slots. Background discovery cannot consume live-family capacity.
    """
    global _family_rr
    ranked = sorted(jobs, key=lambda row: job_sort_key(row, now))
    groups = coalesce_jobs(ranked)
    selected: List[List[Dict[str, Any]]] = []
    family_count: Dict[str, int] = {}
    selected_keys: set = set()

    def _family(group: List[Dict[str, Any]]) -> str:
        return str(group[0].get("family") or "")

    def _lane(group: List[Dict[str, Any]]) -> int:
        return min(job_lane(job) for job in group)

    def _wait(group: List[Dict[str, Any]]) -> float:
        return max(job_wait_seconds(job, now) for job in group)

    def _never(group: List[Dict[str, Any]]) -> bool:
        return any(job_never_run(job) for job in group)

    def _starved(group: List[Dict[str, Any]]) -> bool:
        return _never(group) or _wait(group) >= STARVE_SECONDS

    def _take(group: List[Dict[str, Any]]) -> None:
        selected.append(group)
        family = _family(group)
        family_count[family] = family_count.get(family, 0) + 1
        selected_keys.update(job["job_key"] for job in group)

    def _family_first(lane_groups: List[List[Dict[str, Any]]], cap: int, *, extra_urls: bool = True) -> int:
        if cap <= 0 or not lane_groups:
            return 0
        by_family: Dict[str, List[List[Dict[str, Any]]]] = {}
        order: List[str] = []
        for group in lane_groups:
            family = _family(group)
            if family not in by_family:
                by_family[family] = []
                order.append(family)
            by_family[family].append(group)
        taken = 0
        for family in order:
            if taken >= cap:
                break
            pending = [group for group in by_family[family] if group not in selected]
            if not pending:
                continue
            _take(pending[0])
            taken += 1
        if not extra_urls:
            return taken
        leftover = [group for group in lane_groups if group not in selected]
        for group in leftover:
            if taken >= cap:
                break
            _take(group)
            taken += 1
        return taken

    p0 = [group for group in groups if _lane(group) == 0]
    p1 = [group for group in groups if _lane(group) == 1]
    p2 = [group for group in groups if _lane(group) == 2]
    other_groups = [group for group in groups if _lane(group) == 3]
    live_family_count = len({_family(group) for group in p0})
    background_due_families = len({_family(group) for group in other_groups if not family_blocks_live_path(_family(group))})
    has_liveish_work = bool(p0 or p1 or p2)
    live_cap = (
        min(max_physical, max(MAX_LIVE_PHYSICAL, live_family_count))
        if has_liveish_work
        else 0
    )
    background_cap = min(MAX_BACKGROUND_PHYSICAL, max(0, max_physical - live_cap))

    live_taken = _family_first(p0, live_cap, extra_urls=False)
    leftover_live = max(0, live_cap - live_taken)
    live_taken += _family_first(p1, leftover_live)
    leftover_live = max(0, live_cap - live_taken)
    live_taken += _family_first(p2, leftover_live)

    # Do not leave reserved live capacity idle when there are fewer live-ish
    # request groups than the reservation. Donate unused slots to the
    # background lane, still bounded by MAX_BACKGROUND_PHYSICAL.
    unused_live_capacity = max(0, live_cap - live_taken)
    if unused_live_capacity:
        background_cap = min(
            MAX_BACKGROUND_PHYSICAL,
            background_cap + unused_live_capacity,
        )

    selected_live_family = {_family(group) for group in selected if _lane(group) == 0}
    leftover_unselected_live = [
        group
        for group in p0
        if group not in selected and _family(group) not in selected_live_family
    ]
    leftover_p1p2 = [group for group in p1 + p2 if group not in selected]
    leftover_p0 = leftover_unselected_live + leftover_p1p2
    if background_due_families == 0:
        borrow = min(len(leftover_p0), background_cap)
        for group in leftover_p0[:borrow]:
            _take(group)
            live_taken += 1
            background_cap -= 1

    best_for_family: Dict[str, List[Dict[str, Any]]] = {}
    family_order: List[str] = []
    for group in other_groups:
        family = _family(group)
        if family not in best_for_family:
            best_for_family[family] = group
            family_order.append(family)
    coverage = [family for family in family_order if _starved(best_for_family[family])]
    remainder = [family for family in family_order if family not in coverage]
    if coverage:
        index = _family_rr % len(coverage)
        _family_rr += 1
        coverage = coverage[index:] + coverage[:index]
    background_taken = 0
    blocked_retries = 0
    for family in coverage + remainder:
        if background_taken >= background_cap:
            break
        if family_in_active_backoff(family):
            continue
        if family_blocks_live_path(family):
            if live_family_count > 0 or not family_retry_eligible(family) or blocked_retries >= 1:
                continue
        group = best_for_family[family]
        if (
            family_count.get(family, 0) >= MAX_FAMILY_NONLIVE
            and not _starved(group)
        ):
            continue
        _take(group)
        background_taken += 1
        if family_blocks_live_path(family):
            blocked_retries += 1

    never_run = sum(1 for job in jobs if job_never_run(job))
    real_waits = [job_wait_seconds(job, now) for job in jobs if job.get("last_run_at") or job.get("next_due_at")]
    oldest = max(real_waits, default=0.0)
    live_jobs = [job for job in jobs if job_lane(job) == 0]
    bg_jobs = [job for job in jobs if job_lane(job) == 3]
    live_families = {job.get("family") for job in live_jobs if job.get("family")}
    selected_live_families = {
        job.get("family")
        for group in selected
        for job in group
        if job_lane(job) == 0 and job.get("family")
    }
    live_families_waiting = len(live_families)
    live_families_starved = 0
    for family in live_families:
        family_jobs = [job for job in live_jobs if job.get("family") == family]
        if any(job["job_key"] in selected_keys for job in family_jobs):
            continue
        if any(job_never_run(job) or job_wait_seconds(job, now) >= LIVE_STARVE_SECONDS for job in family_jobs):
            live_families_starved += 1
    background_jobs_waiting = len(bg_jobs)
    background_jobs_starved = 0
    starved = 0
    for job in jobs:
        waiting = job_never_run(job) or (
            (job.get("last_run_at") or job.get("next_due_at"))
            and job_wait_seconds(job, now) >= STARVE_SECONDS
        )
        if job["job_key"] not in selected_keys and waiting:
            starved += 1
            if job_lane(job) == 3:
                background_jobs_starved += 1
    live_waits = [job_wait_seconds(job, now) for job in live_jobs if job.get("last_run_at") or job.get("next_due_at")]
    bg_waits = [job_wait_seconds(job, now) for job in bg_jobs if job.get("last_run_at") or job.get("next_due_at")]
    due_families = {job.get("family") for job in jobs if job.get("family")}
    live_jobs_selected = sum(1 for group in selected for job in group if job_lane(job) == 0)
    stats = {
        "due_jobs": len(jobs),
        "selected_jobs": sum(len(group) for group in selected),
        "selected_groups": len(selected),
        "oldest_due_age_s": int(oldest),
        "never_run": never_run,
        "jobs_starved": starved,
        "live_jobs_due": len(live_jobs),
        "live_jobs_selected": live_jobs_selected,
        "live_families_served": len(selected_live_families),
        "background_jobs_due": len(bg_jobs),
        "background_jobs_waiting": background_jobs_waiting,
        "background_jobs_starved": background_jobs_starved,
        "live_families_waiting": live_families_waiting,
        "live_families_starved": live_families_starved,
        "oldest_live_fetch_age_seconds": int(max(live_waits, default=0.0)),
        "oldest_background_fetch_age_seconds": int(max(bg_waits, default=0.0)),
        "due_family_count": len(due_families),
        "families_selected": sorted({job.get("family") for group in selected for job in group if job.get("family")}),
        "sports_selected": sorted({job.get("sport") for group in selected for job in group if job.get("sport")}),
        "urgencies_selected": sorted({job.get("urgency") for group in selected for job in group if job.get("urgency")}),
        "live_groups_selected": live_taken,
    }
    return selected, stats


def mark_slot(db: Session, job: Dict[str, Any], *, status: str, http_calls: int = 0, events_changed: int = 0, now: Optional[datetime] = None) -> None:
    now = now or _now()
    row = _slot(db, job["job_key"])
    row.kind = "discover" if job["job_key"].startswith("discover:") else "refresh"
    row.competition_id = job["competition_id"]
    row.family = job["family"]
    row.urgency = job["urgency"]
    row.reason = job.get("reason")
    row.last_run_at = now
    row.last_status = status
    row.http_calls = http_calls
    row.events_changed = events_changed
    row.next_due_at = now + timedelta(seconds=int(job.get("interval") or 600))
    row.priority = int(job.get("priority") or 50)


def run_incremental_tick(
    db: Session,
    *,
    sleeper=None,
    now: Optional[datetime] = None,
    live_only: bool = False,
) -> Dict[str, Any]:
    """Execute due incremental jobs. Kill switch: scheduler off returns immediately."""
    import time

    from collector.collect import collect_competition
    from collector.flags import collection_enabled, scheduler_enabled, writes_enabled
    from collector.http import STATS
    from collector.lock import acquire_write_lock, owner_identity, release_write_lock
    from collector.models import SportsCompetition

    if not collection_enabled() or not scheduler_enabled():
        return {"stopped": True, "reason": "kill_switch", "flags": {"scheduler": False}}
    write_owner = owner_identity()
    held_write = False
    if writes_enabled():
        held_write = acquire_write_lock(db, owner=write_owner)
        if not held_write:
            return {"stopped": True, "reason": "write_lock_held", "write_lock": 0}
    now = now or _now()
    started = time.perf_counter()
    from collector.recompute_status import recompute_display_eligible_live

    recompute_display_eligible_live(db, commit=False, only_blocked_families=True)
    due = filter_due_jobs(build_due_jobs(db, now=now), live_only=live_only)
    groups, schedule = select_fair_groups(due, now)
    groups = sorted(
        groups,
        key=lambda group: (
            job_lane(group[0]) if group else 3,
            min_safe_interval(str(group[0].get("family") or "")),
            str(group[0].get("family") or ""),
        ),
    )
    live_counts: Dict[str, int] = {}
    for job in due:
        if job_lane(job) != 0:
            continue
        family = str(job.get("family") or "")
        live_counts[family] = live_counts.get(family, 0) + 1
    active = set(live_counts)
    for family, count in live_counts.items():
        note_live_family(
            family,
            live_event_count=count,
            target_cadence_s=interval_for(family, "LIVE"),
            minimum_safe_s=min_safe_interval(family),
        )
    for family in list(_live_registry):
        if family not in active:
            _live_registry[family]["live_event_count"] = 0
    incr("cycles")
    incr("logical_jobs", schedule["selected_jobs"])
    set_metric("selected_jobs", schedule["selected_jobs"])
    set_metric("jobs_starved", schedule["jobs_starved"])
    set_metric("oldest_due_age_s", schedule["oldest_due_age_s"])
    set_metric("background_jobs_waiting", schedule.get("background_jobs_waiting") or 0)
    set_metric("background_jobs_starved", schedule.get("background_jobs_starved") or 0)
    set_metric("live_families_waiting", schedule.get("live_families_waiting") or 0)
    set_metric("live_families_starved", schedule.get("live_families_starved") or 0)
    set_metric("oldest_live_fetch_age_seconds", schedule.get("oldest_live_fetch_age_seconds") or 0)
    set_metric("oldest_background_fetch_age_seconds", schedule.get("oldest_background_fetch_age_seconds") or 0)
    physical = 0
    coalesced = 0
    changed = 0
    fail_classes = FAIL_STATUSES
    live_groups_this_tick = sum(1 for group in groups if group and job_lane(group[0]) == 0)
    groups_processed = 0
    for group in groups:
        elapsed = time.perf_counter() - started
        lane = job_lane(group[0]) if group else 3
        # A slow live-capable family must never hold every other sport behind it.
        # Always allow at least one group, then yield once this tick consumed its
        # short wall-clock budget. Unprocessed jobs stay due and rotate into the
        # next tick because only executed groups advance their scheduler slots.
        if groups_processed > 0 and elapsed >= TICK_LIVE_BUDGET_S:
            break
        coalesced += max(0, len(group) - 1)
        before_req = int(STATS.get("requests") or 0)
        group_written = 0
        last_classif = "ok"
        family = str(group[0].get("family") or "") if group else ""
        fetch_started = _now()
        blocked_live = bool(family and family_blocks_live_path(family))
        if family and lane == 0:
            note_live_family(family, last_fetch_started_at=fetch_started.isoformat() + "Z")
        run_jobs = group[:1] if lane == 0 or blocked_live else group
        for job in run_jobs:
            job = dict(job)
            family = job["family"]
            retry_ok = (
                family_retry_eligible(family)
                and not family_in_active_backoff(family)
                and live_groups_this_tick == 0
                and lane > 0
            )
            if family_in_active_backoff(family) or (family_blocks_live_path(family) and not retry_ok):
                fb_map, fb_src = _fallback_family(db, job["competition_id"], family)
                fb_family = _mapping_family(fb_map, fb_src) if fb_map and fb_src else ""
                if not (
                    fb_map
                    and fb_src
                    and supports_live(fb_family)
                    and not is_static_family(fb_family)
                    and not family_blocks_live_path(fb_family)
                ):
                    blocked = (
                        "ACCESS_BLOCKED"
                        if family_access_blocked(family) or family_blocks_live_path(family)
                        else "RATE_LIMITED"
                    )
                    mark_slot(db, job, status=blocked, now=now)
                    last_classif = blocked
                    continue
                incr("b_activations")
                job["family"] = fb_family
                job["use_fallback"] = True
            competition = db.get(SportsCompetition, job["competition_id"])
            if competition is None:
                mark_slot(db, job, status="NO_VALID_FALLBACK", now=now)
                last_classif = "NO_VALID_FALLBACK"
                continue
            include_fallback = bool(job.get("use_fallback"))
            try:
                stats = collect_competition(
                    db,
                    competition,
                    job.get("capability") or "fixtures",
                    sleeper=sleeper,
                    include_fallback=include_fallback,
                    source_family=None if include_fallback else job.get("family"),
                )
            except Exception:
                incr("a_failures")
                stats = {"classification": "FAILED", "written": 0}
            classif = stats.get("classification") or "ok"
            if not include_fallback and classif in fail_classes:
                incr("a_failures")
                incr("b_activations")
                try:
                    stats = collect_competition(
                        db,
                        competition,
                        job.get("capability") or "fixtures",
                        sleeper=sleeper,
                        include_fallback=True,
                    )
                except Exception:
                    stats = {"classification": "FAILED", "written": 0}
                classif = stats.get("classification") or "FAILED"
            last_classif = classif
            written = int(stats.get("written") or 0)
            group_written += written
            mark_slot(db, job, status=classif, http_calls=0, events_changed=written, now=now)
        if len(run_jobs) < len(group):
            for job in group[1:]:
                mark_slot(db, job, status=last_classif, events_changed=0, now=now)
        used = int(STATS.get("requests") or 0) - before_req
        completed = _now()
        if family and job_lane(group[0]) == 0:
            ok = last_classif not in fail_classes
            note_live_family(
                family,
                last_fetch_completed_at=completed.isoformat() + "Z",
                last_success_at=(completed.isoformat() + "Z") if ok else _live_registry.get(family, {}).get("last_success_at"),
                next_eligible_at=completed + timedelta(seconds=interval_for(family, "LIVE")),
                failure_count=(0 if ok else int(_live_registry.get(family, {}).get("failure_count") or 0) + 1),
            )
        if used:
            physical += 1
            incr("physical_requests")
        else:
            incr("cache_hits")
        if group:
            row = _slot(db, group[0]["job_key"])
            row.http_calls = used
        changed += group_written
        groups_processed += 1
    incr("coalesced", coalesced)
    incr("events_changed", changed)
    from collector.http import note_physical_requests, rolling_http_hour

    note_physical_requests(physical)
    rolling = rolling_http_hour()
    from collector.canonical_collapse import collapse_canonical_events, promote_observation_enrichment

    collapse = collapse_canonical_events(db)
    enrichment = promote_observation_enrichment(db)
    from collector.cache import flush_list_invalidations

    flush_list_invalidations(db)
    set_metric("enrichment_promoted", int((enrichment or {}).get("copied") or 0))
    duration = round(time.perf_counter() - started, 3)
    set_metric("last_cycle_s", duration)
    set_metric("last_cycle_at", now.isoformat() + "Z")
    metrics = snapshot()
    tick = {
        "due_jobs": schedule["due_jobs"],
        "selected_jobs": schedule["selected_jobs"],
        "live_only": live_only,
        "oldest_due_age_s": schedule["oldest_due_age_s"],
        "families_selected": schedule["families_selected"],
        "sports_selected": schedule["sports_selected"],
        "urgencies_selected": schedule["urgencies_selected"],
        "events_changed": changed,
        "periods_persisted": metrics.get("periods_persisted"),
        "incidents_persisted": metrics.get("incidents_persisted"),
        "runners_persisted": metrics.get("runners_persisted"),
        "best_of_persisted": metrics.get("best_of_persisted"),
        "enrichment_promoted": metrics.get("enrichment_promoted"),
        "jobs_starved": schedule["jobs_starved"],
        "live_jobs_due": schedule.get("live_jobs_due"),
        "live_jobs_selected": schedule.get("live_jobs_selected"),
        "live_families_served": schedule.get("live_families_served"),
        "background_jobs_due": schedule.get("background_jobs_due"),
        "background_jobs_waiting": schedule.get("background_jobs_waiting"),
        "background_jobs_starved": schedule.get("background_jobs_starved"),
        "live_families_waiting": schedule.get("live_families_waiting"),
        "live_families_starved": schedule.get("live_families_starved"),
        "oldest_live_fetch_age_seconds": schedule.get("oldest_live_fetch_age_seconds"),
        "oldest_background_fetch_age_seconds": schedule.get("oldest_background_fetch_age_seconds"),
        "never_run": schedule.get("never_run"),
        "due_family_count": schedule.get("due_family_count"),
        "physical_requests": physical,
        "http": {
            "requests": STATS.get("requests"),
            "http_403": STATS.get("http_403"),
            "http_429": STATS.get("http_429"),
            "timeouts": STATS.get("timeouts"),
            "by_family": STATS.get("by_family"),
            "rolling_hour": rolling,
        },
        "espn": (STATS.get("espn") or [])[-8:],
        "wta": {
            "calendar_http": STATS.get("wta_calendar_http"),
            "match_http": STATS.get("wta_match_http"),
            "tournaments_selected": STATS.get("wta_tournaments_selected"),
            "match_fetches": STATS.get("wta_match_fetches"),
            "calendar_rows": STATS.get("wta_calendar_rows"),
        },
        "duration_s": duration,
        "stopped": False,
        "enrichment": enrichment,
        "collapse": {key: collapse.get(key) for key in ("collapsed", "conflicts", "likely_review")},
        "metrics": metrics,
        "logical_jobs": schedule["selected_jobs"],
        "groups": len(groups),
        "groups_processed": groups_processed,
        "coalesced": coalesced,
    }
    if held_write:
        try:
            release_write_lock(db, owner=write_owner)
        except Exception:
            pass
    return tick


def scheduler_snapshot(db: Session) -> Dict[str, Any]:
    from collector.family_health import snapshot as family_snapshot
    from collector.http import STATS as HTTP_STATS
    from collector.lock import lock_status

    metrics = snapshot()
    families = family_snapshot()
    healthy = sum(1 for row in families.values() if row.get("status") in {"healthy", "empty"})
    degraded = sum(1 for row in families.values() if row.get("status") in {"degraded", "RATE_LIMITED", "ACCESS_BLOCKED"})
    return {
        "alive": True,
        "lease": lock_status(db),
        "metrics": metrics,
        "http": {
            "requests": HTTP_STATS.get("requests"),
            "cache_hits": HTTP_STATS.get("cache_hits"),
            "http_429": HTTP_STATS.get("http_429"),
            "http_403": HTTP_STATS.get("http_403"),
            "rolling_hour": HTTP_STATS.get("rolling_hour"),
        },
        "families": {"tracked": len(families), "healthy": healthy, "degraded": degraded},
        "due_jobs": metrics.get("due_jobs"),
        "live_jobs": metrics.get("live_jobs"),
    }
