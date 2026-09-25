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
from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import Any

from collector.adapters import FetchResult
from collector.adapters_fotmob import _load_boards, match_to_event
from collector.cache import flush_list_invalidations, note_list_invalidation
from collector.collect import _consume_result
from collector.flags import collection_enabled, scheduler_enabled, writes_enabled
from collector.fotmob_crosswalk import _ensure_dynamic_fotmob_mapping, _fotmob_competition_identity, _fill_identity_assets
from collector.football_fixture_linkage import LINKAGE_REVISION, choose_indexed_keeper, link_accepted_duplicates
from collector.football_source_roots import plan_source_roots, plan_hidden_source_with_public_peer, apply_accepted_source_roots
from collector.football_board_priority import priority_plan, interleave_priority, record_priority_attempt, conflict_evidence
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
POLICY_REVISION = 3
MAX_DEFERRED_IDENTITIES = 1000
DEFERRED_REASONS = {"event_identity_conflict", "source_identity_conflict",
                    "broken_or_cyclic_lineage", "legacy_identity_unproven",
                    "legacy_fingerprint_conflict", "competition_acceptance"}
MAX_EVENTS_PER_PAGE = 100
PAGE_BUDGET_SECONDS = 8
HOT_INTERVAL_SECONDS = 15
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
        saved = _state(job)
        due = parse_datetime(saved.get("next_due_at")) if saved.get("policy_revision") == POLICY_REVISION else None
        upgrade_retry = bool(job and job.last_status == "partial" and not saved.get("error")
                             and any(entry.get("linkage_revision") != LINKAGE_REVISION
                                     for entry in (saved.get("deferred") or {}).values()))
        if due is None or due <= now or upgrade_retry:
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
        from collector.football_write_identity import _pointers, _manual, FootballIdentityConflict
        try:
            target = _pointers(row)
        except FootballIdentityConflict:
            return None
        if _manual(row):
            return row  # Caller retains the existing manual visibility policy.
        if not target:
            from collector.public_keeper import public_keeper_for_alias
            resolved = public_keeper_for_alias(db, row)
            if resolved is row:
                return row
            row = resolved
            continue
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


def _legacy_target(db, keeper: SportsEvent, parsed: dict, target: str, country: str,
                   observations: list[SportsEvent]) -> tuple[str, str | None]:
    """Authorize only exact-ID, fresh, same-event legacy classification repair.

    Known correct domestic canonical leagues remain canonical. Source-native
    labels and provably foreign-country buckets can be repaired in place, never
    by creating a replacement event or removing an existing alias.
    """
    from collector.competition_identity import canonical_country_matches, event_accepted_for_mapping
    from collector.integrity import _fingerprint_for
    old = str(keeper.competition_id or "")
    if old == target or event_accepted_for_mapping({**parsed, "competition_key": old}, old)[0]:
        return old, None
    fetched = parse_datetime(parsed.get("source_fetch_time"))
    sid = str(parsed.get("source_event_id") or "")
    exact = any(id_for_family(load_json(row.extra_json, {}) or {}, "fotmob") == sid
                for row in observations)
    if (not exact or not fetched or not -30 <= (datetime.utcnow() - fetched).total_seconds() <= 300
            or not event_accepted_for_mapping({**parsed, "competition_key": target}, target)[0]
            or not (old.startswith("football-") or (country and not canonical_country_matches(old, country)))):
        return old, "legacy_identity_unproven"
    fp = _fingerprint_for(keeper, target)
    collision = db.query(SportsEvent).filter(SportsEvent.fingerprint == fp,
                                            SportsEvent.event_id != keeper.event_id).first()
    if collision is not None:
        return old, "legacy_fingerprint_conflict"
    return target, None


def _apply_legacy_target(db, keeper: SportsEvent, parsed: dict, target: str) -> None:
    """Change classification only; scores and lifecycle stay in normal ingest."""
    from collector.integrity import _fingerprint_for
    from collector.maintenance_policy import sync_public_visibility
    old = keeper.competition_id
    if old == target:
        return
    extra = load_json(keeper.extra_json, {}) or {}
    # Force re-evaluation after classification changes, even when the last raw
    # observation signature matches a stale canonical row.
    extra.pop("obs_signature", None)
    history = extra.get("competition_identity_repairs") or []
    history.append({"from": old, "to": target, "source_family": "fotmob",
                    "source_event_id": parsed.get("source_event_id"),
                    "source_fetch_time": parsed.get("source_fetch_time"),
                    "source_context": parsed.get("source_competition_context")})
    extra.update({"competition_identity_repairs": history[-8:],
                  "canonical_competition_id": target, "public_competition_key": target,
                  "source_competition_id": parsed.get("source_competition_id"),
                  "source_competition_name": parsed.get("source_competition_name")})
    keeper.fingerprint = _fingerprint_for(keeper, target)
    keeper.competition_id = target
    sync_public_visibility(keeper, extra, keeper.display_eligible is not False
                           and extra.get("display_eligible") is not False)
    # Match caches can span several date pages in one worker session.
    db.info.pop("events_by_comp", None)
    for cid in (old, target):
        note_list_invalidation(db, sport="football", competition=cid, start_time=keeper.start_time)
    db.flush()
    logger.info("FOOTBALL_LEGACY_CLASSIFICATION event=%s old=%s new=%s", keeper.event_id, old, target)


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
    source_root_plan = None
    if roots:
        # An exact provider ID cannot authorize changing participant orientation
        # or joining two independent keepers. Leave conflicts for review.
        kickoff = parse_datetime(parsed.get("start_time"))
        valid = [row for row in roots.values() if row.sport_id == "football"
                 and _same_pair(row, parsed) and kickoff and row.start_time
                 and abs((row.start_time - kickoff).total_seconds()) <= 180]
        if len(valid) == 1 and len(roots) == 1:
            keeper = valid[0]
        elif len(valid) == len(roots):
            keeper = choose_indexed_keeper(valid, {**parsed, "competition_key": cid})
            if keeper is None:
                source_root_plan = plan_source_roots(db, valid, {**parsed, "competition_key": cid})
                if source_root_plan is not None:
                    keeper = roots[source_root_plan.keeper_id]
        if keeper is None:
            return {"rejected": 1, "reason": "source_identity_conflict",
                    "evidence": conflict_evidence(roots, parsed)}
        if automatic_promotion_blocked(keeper):
            return {"rejected": 1, "reason": "visibility_policy"}
        if source_root_plan is None and len(roots) == 1:
            source_root_plan = plan_hidden_source_with_public_peer(db, [keeper], {**parsed, "competition_key": cid})
            if source_root_plan is not None:
                keeper = db.get(SportsEvent, source_root_plan.keeper_id)
        cid, reason = _legacy_target(db, keeper, parsed, cid, country, identity.get(sid, []))
        if reason:
            return {"rejected": 1, "reason": reason}
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
    if keeper is not None:
        _apply_legacy_target(db, keeper, parsed, cid)
    # A label-root consolidation must roll back as one unit even when a
    # caller does not wrap this helper in the normal date-page savepoint.
    with db.begin_nested() if source_root_plan is not None else nullcontext():
        result = _consume_result(db, source=source, mapping=mapping,
                                 competition=db.get(SportsCompetition, cid), capability="results",
                                 result=FetchResult(ok=True, http_status=200, events=[parsed], parse_status="ok"),
                                 verified_target_id=keeper.event_id if keeper is not None else None)
        if result.get("rejected"):
            if result.get("identity_conflicts") == result["rejected"]:
                return {"rejected": result["rejected"], "reason": "event_identity_conflict"}
            raise RuntimeError("Observation persistence rejected; cursor retained for retry")
        if source_root_plan is not None:
            if int(result.get("normalized") or 0) != 1:
                raise RuntimeError("Source root observation was not normalized")
            apply_accepted_source_roots(db, source_root_plan, parsed)
    # Artwork is independent of status/score signatures. Replace only a proven
    # old group badge with its actual parent badge, not arbitrary existing art.
    if keeper is not None:
        _fill_identity_assets(keeper, parsed)
        link_accepted_duplicates(db, keeper, parsed)
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
    deferred = dict(state.get("deferred") or {})
    # New validation rules retry prior rejections; this resets only the cursor,
    # never event rows, scores or canonical identities. Unversioned partial
    # cursors from v1 are replayed safely through the idempotent ingestion gate.
    after = str(state.get("after_id") or "") if state.get("policy_revision") == POLICY_REVISION else ""
    if "policy_revision" not in state and state.get("complete"):
        after = ""
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
    # Retry saved identity conflicts once under the new linkage policy, within
    # the SAME request/page budget, without rewinding the discovery cursor.
    for sid, entry in list(deferred.items()):
        if sid not in matches and entry.get("linkage_revision") != LINKAGE_REVISION:
            # Preserve unresolved IDs and their actual last-seen time. Absence
            # is not fresh evidence and must not create an eager retry loop.
            deferred[sid] = {**entry, "linkage_revision": LINKAGE_REVISION,
                             "present_on_last_board": False, "last_presence_check_at": isoformat(now)}
    retry_ids = {sid for sid, entry in deferred.items() if sid in matches
                 and entry.get("linkage_revision") != LINKAGE_REVISION}
    ordered = (sorted((sid, matches[sid]) for sid in retry_ids)
               + sorted((key, raw) for key, raw in matches.items() if key > after and key not in retry_ids))
    index = _identity_index(db, day)
    priority_receipts = dict(state.get("priority_receipts") or {})
    priorities = priority_plan(matches, index, priority_receipts, now, max_events)
    ordered = interleave_priority(ordered, matches, priorities)
    processed_ids = set()
    exhausted = False
    totals = {"seen": len(matches), "processed": 0, "written": 0, "rejected": 0, "skipped": 0,
              "priority_processed": 0}
    reasons = defaultdict(int)
    failed = False
    for sid, raw, is_priority in ordered:
        if sid in processed_ids:
            # Only sequential traversal may advance the coverage cursor.
            if not is_priority and sid not in retry_ids:
                after = sid
            continue
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
        reason = result.get("reason")
        if reason in DEFERRED_REASONS:
            if sid not in deferred and len(deferred) >= MAX_DEFERRED_IDENTITIES:
                # Do not acknowledge a conflict that cannot be durably recorded.
                state["error"] = "deferred_identity_capacity_reached"
                reasons["deferred_capacity"] += 1
                failed = True
                break
            previous = deferred.get(sid) or {}
            deferred[sid] = {"reason": reason, "attempts": int(previous.get("attempts") or 0) + 1,
                             "first_seen_at": previous.get("first_seen_at") or isoformat(now),
                             "last_seen_at": isoformat(now), "source_family": "fotmob",
                             "source_event_id": sid, "linkage_revision": LINKAGE_REVISION}
            evidence = result.get("evidence")
            if evidence:
                deferred[sid]["evidence"] = evidence
                if previous.get("evidence") != evidence:
                    logger.info("FOOTBALL_IDENTITY_EVIDENCE day=%s source_id=%s reason=%s proof=%s",
                                day, sid, reason, dump_json(evidence))
        elif not result.get("rejected"):
            deferred.pop(sid, None)
        elif sid in deferred:
            # Keep a now-policy-blocked conflict visible, but do not endlessly
            # promote it into the one-time upgrade retry lane.
            previous = deferred[sid]
            deferred[sid] = {**previous, "reason": reason or "rejected",
                             "attempts": int(previous.get("attempts") or 0)+1,
                             "last_seen_at": isoformat(now), "linkage_revision": LINKAGE_REVISION}
        processed_ids.add(sid)
        if sid in priorities:
            record_priority_attempt(priority_receipts, sid, priorities[sid], now)
        totals["priority_processed"] += int(is_priority)
        totals["processed"] += 1
        for key in ("written", "rejected", "skipped"):
            totals[key] += int(result.get(key) or 0)
        if result.get("reason"):
            reasons[result["reason"]] += 1
        if not is_priority and sid not in retry_ids:
            after = sid
    else:
        exhausted = True
    complete = not failed and exhausted
    date = datetime.strptime(day, "%Y%m%d").date()
    interval = (HOT_INTERVAL_SECONDS if date >= now.date()-timedelta(days=1) and date <= now.date()
                else FUTURE_INTERVAL_SECONDS if date > now.date() else HISTORY_INTERVAL_SECONDS)
    # A partial page stays due but rotates behind dates that have never run.
    delay = 120 if failed else interval if complete else 0
    state.update({"policy_revision": POLICY_REVISION, "after_id": "" if complete else after, "complete": complete,
                  "next_due_at": isoformat(now + timedelta(seconds=delay)), "totals": totals,
                  "reasons": dict(reasons), "deferred": deferred,
                  "priority_receipts": priority_receipts,
                  "data_complete": complete and not deferred})
    if not failed:
        state["last_success_at"] = isoformat(now)
        state.pop("error", None)
    job.last_run_at = now
    job.last_status = "failed" if failed else "partial" if deferred else "ok"
    job.items_written = totals["written"]
    job.last_error = dump_json(state)
    flush_list_invalidations(db)
    return {"day": day, "complete": complete, "data_complete": complete and not deferred,
            "deferred_count": len(deferred), **totals, "reasons": dict(reasons)}


def run_football_board_refresh(db, *, owner: str, now: datetime | None = None, getter=None, hot_only: bool = False) -> dict:
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
        for days in (rolling_dates(now)[:1] if hot_only else rolling_dates(now)):
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
