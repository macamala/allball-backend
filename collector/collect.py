"""Collector orchestrator: competition → ordered sources → ingest → merge.

This module is imported by the worker process. FastAPI request handlers must
not call run_cycle.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters import (
    AccessRestricted,
    AdapterNotRegistered,
    FetchRequest,
    FetchResult,
    make_adapter,
)
from collector.cache import cache_clear
from collector.competition_identity import event_accepted_for_mapping
from collector.coverage import constraints_for, filter_partial_events
from collector.health import (
    mark_attempt,
    mark_failure,
    mark_success,
    record_competition_health,
    record_ingest,
    record_ingestion_error,
)
from collector.models import (
    SportsCompetition,
    SportsCompetitionHealth,
    SportsEvent,
    SportsEventDetail,
    SportsEventObservation,
    SportsIngestionRun,
    SportsRankingSnapshot,
    SportsSource,
    SportsSourceCompetition,
    SportsStandingSnapshot,
)
from collector.identity import ensure_entity, remember_mapping
from collector.limits import is_rate_limited, mark_rate_limited, record_hit, retry_call
from collector.live_state import is_live, reconcile_live_status
from collector.merge import apply_row_fields, merge_event_fields
from collector.status_transitions import apply_or_reject
from collector.latency import record_observation_latency
from collector.normalize import fingerprint, normalize_event
from collector.family_health import family_access_blocked, family_rate_limited
from collector.family_plan import family_priority
from collector.dirty import event_unchanged, observation_signature
from collector.flags import collection_enabled, writes_enabled
from collector.metrics import incr
from collector.http import begin_budget, end_budget, family_host_blocked
from collector.cadence import cadence_seconds_for
from collector.ids import bound_source_key
from collector.lock import acquire_write_lock, owner_identity, release_write_lock
from collector.progress import persist_progress, stage
from collector.schedule import due_capabilities, mark_job
from collector.sources import plan_sources, source_collectable, source_config_missing
from collector.util import dump_json, isoformat, load_json, payload_hash, sha_id, slugify
from collector.match import _register_event, match_event
from sports_registry.sports import get_sport

BATCH_COMMIT = 10
persist_fail_after: Optional[int] = None


def _count_persisted_enrichment(incoming: Dict[str, Any]) -> None:
    from collector.enrichment import _section_filled

    if _section_filled(incoming.get("periods")):
        incr("periods_persisted")
    if _section_filled(incoming.get("incidents")):
        incr("incidents_persisted")
    if _section_filled(incoming.get("runners")):
        incr("runners_persisted")
    if incoming.get("best_of") not in (None, "", 0, "0"):
        incr("best_of_persisted")


def _entity_kind(sport_id: str) -> str:
    sport = get_sport(sport_id) or {}
    return sport.get("participant_type") or "team"


def _classification_from_result(result: FetchResult, *, used_fallback: bool, coverage: str, events: int) -> str:
    if result.config_missing or result.classification == "CONFIG_MISSING":
        return "CONFIG_MISSING"
    if result.http_status == 429 or result.classification == "RATE_LIMITED":
        return "RATE_LIMITED"
    if result.parse_status == "failed" or result.classification == "PARSE_FAILURE":
        return "PARSE_FAILURE"
    if result.restricted or result.http_status in {401, 403, 404, 410}:
        return "SOURCE_CHANGED"
    if not result.ok:
        err = (result.error or "").lower()
        if result.http_status == 0 or "timeout" in err or "timed out" in err:
            return "NETWORK_FAILURE"
        return result.classification or "OTHER_ERROR"
    if events == 0:
        return "NO_CURRENT_EVENTS"
    if coverage == "partial":
        return "WORKING_PARTIAL"
    if used_fallback:
        return "WORKING_FALLBACK"
    return "WORKING_PRIMARY"


def _fetch(
    source: SportsSource,
    request: FetchRequest,
    sleeper=None,
) -> FetchResult:
    adapter = make_adapter(source.adapter_key, source.source_id)

    def _call() -> FetchResult:
        try:
            result = adapter.fetch(request)
        except AccessRestricted as exc:
            return FetchResult(
                ok=False,
                restricted=True,
                error=str(exc) or "access restricted",
                http_status=403,
                classification="SOURCE_CHANGED",
            )
        if result.restricted or result.http_status in {401, 403, 429}:
            return result
        if result.http_status == 0:
            return result
        if result.parse_status == "failed" or result.classification in {"PARSE_FAILURE", "RATE_LIMITED"}:
            return result
        if not result.ok:
            raise RuntimeError(result.error or f"{source.source_id} fetch failed")
        return result

    kwargs = {"attempts": 3, "base_delay": 0.01}
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    begin_budget(max_requests=8, max_seconds=18)
    started = datetime.utcnow()
    try:
        result = retry_call(_call, **kwargs)
    except Exception as exc:
        return FetchResult(ok=False, error=str(exc), http_status=0, classification="NETWORK_FAILURE")
    finally:
        end_budget()
    completed = datetime.utcnow()
    stamp = {
        "fetch_started_at": started.isoformat() + "Z",
        "fetch_completed_at": completed.isoformat() + "Z",
        "parsed_at": completed.isoformat() + "Z",
    }
    for event in result.events or []:
        if isinstance(event, dict):
            event.update({k: v for k, v in stamp.items() if not event.get(k)})
    return result


def _upsert_event(
    db: Session,
    *,
    incoming: Dict[str, Any],
    source: SportsSource,
    mapping: SportsSourceCompetition,
    existing: Optional[SportsEvent],
) -> SportsEvent:
    if existing is not None and existing.competition_id and existing.competition_id != incoming.get("competition_key"):
        extra = load_json(existing.extra_json, {}) or {}
        conflicts = extra.get("provider_conflicts") or []
        conflicts.append(
            {
                "type": "competition_mismatch",
                "stored": existing.competition_id,
                "incoming": incoming.get("competition_key"),
                "source_id": source.source_id,
            }
        )
        extra["provider_conflicts"] = conflicts[-20:]
        existing.extra_json = dump_json(extra)
        return existing
    sport_id = incoming["sport"]
    kind = _entity_kind(sport_id)
    home = incoming.get("home") or {}
    away = incoming.get("away") or {}
    home_id = ensure_entity(
        db,
        sport_id=sport_id,
        kind=kind,
        name=home.get("name") or "",
        source_id=source.source_id,
        source_entity_id=home.get("id") or home.get("slug"),
        country_id=incoming.get("country_id"),
    )
    away_id = ensure_entity(
        db,
        sport_id=sport_id,
        kind=kind,
        name=away.get("name") or "",
        source_id=source.source_id,
        source_entity_id=away.get("id") or away.get("slug"),
        country_id=incoming.get("country_id"),
    )
    if existing is None:
        event_id = sha_id("ninko-evt-", fingerprint(incoming))
        existing = SportsEvent(
            event_id=event_id,
            sport_id=sport_id,
            competition_id=incoming["competition_key"],
            event_family=incoming.get("event_family") or "team_match",
            fingerprint=fingerprint(incoming),
            home_entity_id=home_id,
            away_entity_id=away_id,
        )
        db.add(existing)
        _register_event(db, existing)
        fetch_now = datetime.utcnow().isoformat() + "Z"
        incoming["source_fetch_time"] = incoming.get("source_fetch_time") or fetch_now
        incoming["last_contact_at"] = incoming.get("last_contact_at") or incoming["source_fetch_time"]
        incoming["retrieved_at"] = incoming.get("source_fetch_time")
        incoming["sport"] = sport_id
        incoming = reconcile_live_status(incoming)
        apply_row_fields(existing, incoming, source.source_id, True)
        extra = load_json(existing.extra_json, {}) or {}
        extra["obs_signature"] = observation_signature(incoming)
        existing.extra_json = dump_json(extra)
    else:
        extra = load_json(existing.extra_json, {}) or {}
        parts = load_json(existing.participants_json, {}) or {}
        current = {
            "status": existing.status,
            "score": load_json(existing.score_json, {}) or {},
            "venue": existing.venue,
            "season": existing.season,
            "series_id": existing.series_id,
            "session_type": existing.session_type,
            "game_id": existing.game_id,
            "country_id": existing.country_id,
            "meeting_id": existing.meeting_id,
            "start_time": existing.start_time.isoformat() + "Z" if existing.start_time else None,
            "sport": sport_id,
            "competition_key": existing.competition_id,
            "home": parts.get("home") or home,
            "away": parts.get("away") or away,
            "participant_a": parts.get("participant_a"),
            "participant_b": parts.get("participant_b"),
            "lineups": extra.get("lineups"),
            "statistics": extra.get("statistics"),
            "incidents": extra.get("incidents"),
            "availability": extra.get("availability"),
            "periods": extra.get("periods"),
            "maps": extra.get("maps"),
            "classification": extra.get("classification"),
            "runners": extra.get("runners"),
            "winner": extra.get("winner"),
            "round": extra.get("round"),
            "best_of": extra.get("best_of"),
            "form": extra.get("form"),
            "season": existing.season,
            "source_family": extra.get("source_family"),
            "source_event_updated_at": extra.get("source_event_updated_at"),
            "source_fetch_time": extra.get("source_fetch_time"),
            "source_status": extra.get("source_status") or existing.status,
            "retrieved_at": extra.get("source_fetch_time")
            or (existing.retrieved_at.isoformat() + "Z" if existing.retrieved_at else None),
            "observed_at": extra.get("observed_at") or extra.get("source_event_updated_at"),
            "canonical_last_observed_at": extra.get("canonical_last_observed_at"),
            "field_sources": extra.get("field_sources") or {},
        }
        higher = _is_higher_priority(
            db, source.source_id, existing.primary_source_id, mapping.competition_id
        )
        fetch_now = datetime.utcnow().isoformat() + "Z"
        incoming["source_fetch_time"] = incoming.get("source_fetch_time") or fetch_now
        incoming["last_contact_at"] = incoming.get("last_contact_at") or incoming["source_fetch_time"]
        incoming["retrieved_at"] = incoming.get("source_fetch_time")
        incoming["sport"] = incoming.get("sport") or sport_id
        incoming = apply_or_reject(current, incoming)
        merged = merge_event_fields(
            current,
            incoming,
            incoming_is_higher_priority=higher,
            incoming_source_id=source.source_id,
        )
        merged = reconcile_live_status(merged, counterparts=[current, incoming])
        merged["source_event_id"] = incoming.get("source_event_id") or merged.get("source_event_id")
        apply_row_fields(existing, merged, source.source_id, higher)
        extra = load_json(existing.extra_json, {}) or {}
        extra["obs_signature"] = observation_signature(merged)
        existing.extra_json = dump_json(extra)
        incoming = merged
        if home_id and not existing.home_entity_id:
            existing.home_entity_id = home_id
        if away_id and not existing.away_entity_id:
            existing.away_entity_id = away_id
    remember_mapping(
        db,
        entity_kind="event",
        ninko_id=existing.event_id,
        source_id=source.source_id,
        source_entity_id=incoming.get("source_event_id"),
    )
    _upsert_details(db, existing.event_id, incoming, incoming_is_higher=_is_higher_priority(
        db, source.source_id, existing.primary_source_id, mapping.competition_id
    ))
    _register_event(db, existing)
    return existing


def _is_higher_priority(db: Session, source_id: str, primary_source_id: Optional[str], competition_id: str) -> bool:
    if not primary_source_id or primary_source_id == source_id:
        return True
    cache = db.info.setdefault("src_priority", {})
    rows = cache.get(competition_id)
    if rows is None:
        rows = {
            row.source_id: row.priority
            for row in db.query(SportsSourceCompetition).filter_by(competition_id=competition_id).all()
        }
        cache[competition_id] = rows
    incoming = rows.get(source_id, 999)
    current = rows.get(primary_source_id, 999)
    return incoming <= current


def _upsert_details(db: Session, event_id: str, incoming: Dict[str, Any], incoming_is_higher: bool) -> None:
    cache = db.info.setdefault("event_details", {})
    detail = cache.get(event_id)
    if detail is None:
        detail = db.get(SportsEventDetail, event_id)
    if detail is None:
        for pending in db.new:
            if isinstance(pending, SportsEventDetail) and pending.event_id == event_id:
                detail = pending
                break
    if detail is None:
        detail = SportsEventDetail(event_id=event_id)
        db.add(detail)
    cache[event_id] = detail
    if incoming_is_higher or not detail.lineups_json:
        if incoming.get("lineups") is not None:
            detail.lineups_json = dump_json(incoming.get("lineups"))
    if incoming_is_higher or not detail.statistics_json:
        if incoming.get("statistics") is not None:
            detail.statistics_json = dump_json(incoming.get("statistics"))
    if incoming_is_higher or not detail.incidents_json:
        if incoming.get("incidents") is not None:
            detail.incidents_json = dump_json(incoming.get("incidents"))
    if incoming_is_higher or not detail.availability_json:
        if incoming.get("availability"):
            detail.availability_json = dump_json(incoming.get("availability"))
    detail.updated_at = datetime.utcnow()


def _consume_result(
    db: Session,
    *,
    source: SportsSource,
    mapping: SportsSourceCompetition,
    competition: SportsCompetition,
    capability: str,
    result: FetchResult,
) -> Dict[str, int]:
    record_ingest(
        db,
        source_id=source.source_id,
        entity_kind="event" if capability != "standings" else "standings",
        payload=result.payload if result.payload is not None else {"events": result.events},
        capability=capability,
        competition_id=competition.competition_id,
        http_status=result.http_status,
        restricted=result.restricted,
        error=result.error,
    )
    mark_attempt(
        db,
        source.source_id,
        latency_ms=result.latency_ms,
        parse_status=result.parse_status,
        events_returned=len(result.events or []),
        http_status=result.http_status,
        error_type=result.classification,
    )
    if result.http_status == 429:
        mark_rate_limited(db, source.source_id)
    if result.config_missing:
        mark_failure(
            db,
            source.source_id,
            result.error or "config missing",
            http_status=result.http_status,
            error_type="CONFIG_MISSING",
        )
        return {"written": 0, "merged": 0}
    if result.restricted or result.http_status in {401, 403}:
        mark_failure(
            db,
            source.source_id,
            result.error or "access restricted",
            http_status=result.http_status,
            restricted=True,
            error_type="SOURCE_CHANGED",
        )
        return {"written": 0, "merged": 0}
    if not result.ok:
        mark_failure(
            db,
            source.source_id,
            result.error or "fetch failed",
            http_status=result.http_status,
            error_type=result.classification or "OTHER_ERROR",
        )
        return {"written": 0, "merged": 0}
    events = list(result.events or [])
    coverage = mapping.coverage_scope or "full"
    if coverage == "partial":
        family = mapping.upstream_family or source.upstream_family or ""
        events = filter_partial_events(events, constraints_for(competition.competition_id, family))
    mark_success(db, source.source_id, result.http_status, events_returned=len(events))
    if not writes_enabled():
        return {"written": 0, "merged": 0, "normalized": len(events)}
    written = 0
    merged = 0
    rejected = 0
    config = load_json(mapping.source_config_json, {}) or {}
    totals = db.info.setdefault("persist_totals", {"done": 0, "target": 0})
    cid = competition.competition_id
    by_comp = db.info.setdefault("events_by_comp", {})
    if cid not in by_comp:
        cached_events = db.query(SportsEvent).filter_by(competition_id=cid).all()
        by_comp[cid] = list(cached_events)
        for row in cached_events:
            _register_event(db, row)
    details_cache = db.info.setdefault("event_details", {})
    cached_events = by_comp.get(cid) or []
    missing = [row.event_id for row in cached_events if row.event_id not in details_cache]
    if missing:
        for detail in db.query(SportsEventDetail).filter(SportsEventDetail.event_id.in_(missing)).all():
            details_cache[detail.event_id] = detail
    for raw in events:
        skipped = False
        accepted, resolved = event_accepted_for_mapping(
            {**raw, "source_family": raw.get("source_family") or mapping.upstream_family or source.upstream_family or source.source_id},
            competition.competition_id,
        )
        if not accepted:
            incr("competition_mismatch_skipped")
            totals["skipped"] = int(totals.get("skipped") or 0) + 1
            continue
        try:
            with db.begin_nested():
                raw = {
                    **raw,
                    "source_family": raw.get("source_family")
                    or mapping.upstream_family
                    or source.upstream_family
                    or source.source_id,
                }
                incoming = normalize_event(
                    raw, sport_id=competition.sport_id, competition_id=competition.competition_id
                )
                incoming.update(resolved)
                incoming["source_family"] = raw["source_family"]
                incoming["source_url"] = config.get("url")
                incoming = reconcile_live_status(incoming)
                existing = match_event(db, incoming, source_id=source.source_id)
                if existing is not None and event_unchanged(existing, incoming):
                    incr("unchanged_skipped")
                    totals["skipped"] = int(totals.get("skipped") or 0) + 1
                    skipped = True
                    contact = datetime.utcnow()
                    existing.retrieved_at = contact
                    extra = load_json(existing.extra_json, {}) or {}
                    stamp = isoformat(contact)
                    extra["source_fetch_time"] = stamp
                    extra["last_contact_at"] = stamp
                    existing.extra_json = dump_json(extra)
                else:
                    if existing is not None:
                        merged += 1
                    event_row = _upsert_event(db, incoming=incoming, source=source, mapping=mapping, existing=existing)
                    original_sid = str(incoming.get("source_event_id") or "")
                    db.add(
                        SportsEventObservation(
                            event_id=event_row.event_id,
                            source_id=source.source_id,
                            source_family=mapping.upstream_family or source.upstream_family,
                            source_event_id=original_sid or None,
                            source_event_key=bound_source_key(source.source_id, original_sid) if original_sid else None,
                            source_url=config.get("url"),
                            payload_json=dump_json({"payload_hash": payload_hash(raw)}),
                            retrieved_at=datetime.utcnow(),
                        )
                    )
                    if persist_fail_after is not None and (int(totals.get("done") or 0) + 1) >= persist_fail_after:
                        raise RuntimeError("simulated persist failure")
        except Exception as exc:  # noqa: BLE001
            for key in ("event_details", "events_by_fp", "events_by_comp", "events_by_id", "id_map", "entities"):
                db.info.pop(key, None)
            rejected += 1
            record_ingestion_error(
                db,
                competition_id=competition.competition_id,
                source_id=source.source_id,
                error_type="DB_FAILURE",
                message=str(exc),
            )
            if str(exc) == "simulated persist failure":
                break
            continue
        if skipped:
            continue
        written += 1
        _count_persisted_enrichment(incoming)
        totals["done"] = int(totals.get("done") or 0) + 1
        persist_progress(totals["done"], int(totals.get("target") or 0) or max(totals["done"], 1))
    if result.standings:
        db.add(
            SportsStandingSnapshot(
                competition_id=competition.competition_id,
                sport_id=competition.sport_id,
                source_id=source.source_id,
                rows_json=dump_json(result.standings),
                captured_at=datetime.utcnow(),
            )
        )
        written += 1
    if result.rankings:
        db.add(
            SportsRankingSnapshot(
                sport_id=competition.sport_id,
                competition_id=competition.competition_id,
                source_id=source.source_id,
                rows_json=dump_json(result.rankings),
                captured_at=datetime.utcnow(),
            )
        )
        written += 1
    if capability == "live_scores":
        stamp_live_contact(db, competition_id=competition.competition_id)
    return {"written": written, "merged": merged, "rejected": rejected, "normalized": len(events)}


def stamp_live_contact(
    db: Session,
    *,
    competition_id: Optional[str] = None,
    family: Optional[str] = None,
    now: Optional[datetime] = None,
) -> int:
    """Record feed contact on live rows even when scores did not change."""
    now = now or datetime.utcnow()
    stamp = isoformat(now)
    query = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None), SportsEvent.live.is_(True))
    if competition_id:
        query = query.filter(SportsEvent.competition_id == competition_id)
    updated = 0
    for row in query.all():
        extra = load_json(row.extra_json, {}) or {}
        if family:
            row_family = extra.get("source_family") or row.primary_source_id or ""
            if row_family and row_family != family:
                continue
        if not is_live(row.status or ""):
            continue
        extra["last_contact_at"] = stamp
        extra["source_fetch_time"] = stamp
        row.retrieved_at = now
        row.extra_json = dump_json(extra)
        updated += 1
    return updated


def collect_competition(
    db: Session,
    competition: SportsCompetition,
    capability: str,
    *,
    sleeper=None,
    coverage_context: Optional[str] = None,
    include_fallback: bool = True,
    source_family: Optional[str] = None,
) -> Dict[str, Any]:
    plan = plan_sources(
        db, competition.competition_id, capability, coverage_context=coverage_context
    )
    queues = [("primary", plan["primary"])]
    if include_fallback:
        queues.append(("fallback", plan["fallback"]))
    if source_family:
        wanted = str(source_family)

        def _keep(queue):
            return [
                (mapping, source)
                for mapping, source in queue
                if (mapping.upstream_family or source.upstream_family or source.source_id) == wanted
            ]

        filtered = [(label, _keep(queue)) for label, queue in queues if _keep(queue)]
        if not filtered:
            combined = list(plan["primary"] or []) + list(plan["fallback"] or [])
            kept = _keep(combined)
            filtered = [("mapped", kept)] if kept else []
        queues = filtered
    written = 0
    merged = 0
    rejected = 0
    primary_ok = False
    last_result = FetchResult(ok=False, error="no sources", classification="NO_VALID_FALLBACK")
    active_source = None
    used_fallback = False
    coverage_used = "full"
    primary_status = "missing"
    fallback_status = "unused"
    if not plan["primary"] and not plan["fallback"]:
        record_competition_health(
            db,
            competition.competition_id,
            primary_status="missing",
            fallback_status="missing",
            classification="NO_VALID_FALLBACK",
            error="no collectable sources",
        )
        return {"written": 0, "merged": 0, "classification": "NO_VALID_FALLBACK"}
    succeeded_families = set()
    winning = None
    for label, queue in queues:
        for mapping, source in queue:
            family = mapping.upstream_family or source.upstream_family or source.source_id
            if family in succeeded_families:
                continue
            if family_host_blocked(family) or family_rate_limited(family) or family_access_blocked(family):
                blocked = family_access_blocked(family)
                last_result = FetchResult(
                    ok=False,
                    http_status=403 if blocked else 429,
                    error=f"{family} family cooldown",
                    classification="ACCESS_BLOCKED" if blocked else "RATE_LIMITED",
                )
                if label == "primary":
                    primary_status = "ACCESS_BLOCKED" if blocked else "RATE_LIMITED_FAMILY"
                else:
                    fallback_status = "ACCESS_BLOCKED" if blocked else "RATE_LIMITED_FAMILY"
                continue
            if source_config_missing(source):
                last_result = FetchResult(
                    ok=False,
                    error="credentials missing",
                    classification="CONFIG_MISSING",
                    config_missing=True,
                )
                mark_attempt(db, source.source_id, error_type="CONFIG_MISSING")
                if label == "primary":
                    primary_status = "CONFIG_MISSING"
                else:
                    fallback_status = "CONFIG_MISSING"
                continue
            record_hit(source.source_id)
            config = load_json(mapping.source_config_json, {}) or {}
            request = FetchRequest(
                capability=capability,
                sport_id=competition.sport_id,
                competition_id=competition.competition_id,
                source_competition_id=mapping.source_competition_id or competition.competition_id,
                series_id=competition.series_id,
                game_id=competition.game_id,
                country_id=competition.country_id,
                parent_sport_id=competition.parent_sport_id,
                source_config=config,
                coverage_scope=mapping.coverage_scope or "full",
                coverage_context=coverage_context,
                upstream_family=mapping.upstream_family or source.upstream_family,
            )
            try:
                result = _fetch(source, request, sleeper=sleeper)
            except AdapterNotRegistered as exc:
                mark_failure(db, source.source_id, str(exc), error_type="OTHER_ERROR")
                last_result = FetchResult(ok=False, error=str(exc), classification="OTHER_ERROR")
                continue
            last_result = result
            stats = _consume_result(
                db,
                source=source,
                mapping=mapping,
                competition=competition,
                capability=capability,
                result=result,
            )
            written += stats["written"]
            merged += stats["merged"]
            rejected += int(stats.get("rejected") or 0)
            produced = bool(stats["written"] or (result.ok and (result.events or result.standings)))
            if produced:
                winning = result
                succeeded_families.add(family)
                active_source = source.source_id
                coverage_used = mapping.coverage_scope or "full"
                if label == "primary":
                    primary_ok = True
                    primary_status = "ok"
                else:
                    used_fallback = True
                    fallback_status = "ok"
            elif label == "primary":
                primary_status = result.classification or "failed"
            else:
                fallback_status = result.classification or "failed"
            if result.http_status == 429 or result.classification == "RATE_LIMITED":
                continue
            if result.restricted:
                continue
    if winning is not None:
        last_result = winning
    if not plan["fallback"] and not primary_ok:
        classification = _classification_from_result(
            last_result, used_fallback=False, coverage=coverage_used, events=written
        )
        if classification in {"NETWORK_FAILURE", "SOURCE_CHANGED", "PARSE_FAILURE", "RATE_LIMITED", "CONFIG_MISSING"}:
            classification = classification
        elif written == 0 and not last_result.ok:
            classification = "NO_VALID_FALLBACK"
    else:
        classification = _classification_from_result(
            last_result, used_fallback=used_fallback, coverage=coverage_used, events=written
        )
        if used_fallback and written == 0 and not last_result.ok:
            classification = "NO_VALID_FALLBACK"
    record_competition_health(
        db,
        competition.competition_id,
        primary_status=primary_status,
        fallback_status=fallback_status,
        active_source_id=active_source,
        events_ingested=written,
        duplicates_merged=merged,
        error=None if last_result.ok else last_result.error,
        classification=classification,
        success=written > 0 or last_result.ok,
    )
    return {"written": written, "merged": merged, "rejected": rejected, "classification": classification}


def _ensure_competition_from_event(db: Session, incoming: Dict[str, Any], source: SportsSource) -> SportsCompetition:
    competition_id = incoming.get("competition_key") or slugify(incoming.get("competition") or "unknown")
    sport_id = incoming.get("sport") or ""
    sport = get_sport(sport_id) or {}
    row = db.query(SportsCompetition).filter_by(competition_id=competition_id).first()
    if row is None:
        row = SportsCompetition(
            competition_id=competition_id,
            sport_id=sport_id,
            name=incoming.get("competition") or competition_id,
            official_name=incoming.get("competition") or competition_id,
            slug=competition_id,
            event_model=incoming.get("event_family") or sport.get("event_model") or "team_match",
            game_id=incoming.get("game_id"),
            parent_sport_id=incoming.get("parent_sport_id") or sport.get("parent_id"),
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(row)
        db.flush()
    else:
        row.identity_only = False
    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        db.add(
            SportsSourceCompetition(
                competition_id=competition_id,
                source_id=source.source_id,
                priority=40,
                source_competition_id=competition_id,
                enabled=True,
            )
        )
        db.flush()
    return row


def collect_dynamic_sources(db: Session, capability: str, *, sleeper=None) -> int:
    written = 0
    sources = [
        row
        for row in db.query(SportsSource).filter_by(kind="dynamic", enabled=True).all()
        if source_collectable(row)
    ]
    for source in sources:
        if is_rate_limited(db, source.source_id):
            continue
        record_hit(source.source_id)
        request = FetchRequest(capability=capability, sport_id=None)
        try:
            result = _fetch(source, request, sleeper=sleeper)
        except AdapterNotRegistered as exc:
            mark_failure(db, source.source_id, str(exc))
            continue
        if result.restricted or not result.ok:
            record_ingest(
                db,
                source_id=source.source_id,
                entity_kind="event",
                payload=result.payload,
                capability=capability,
                http_status=result.http_status,
                restricted=result.restricted,
                error=result.error,
            )
            mark_failure(
                db,
                source.source_id,
                result.error or "fetch failed",
                http_status=result.http_status,
                restricted=result.restricted,
            )
            continue
        for raw in result.events:
            sport_id = raw.get("sport") or "dota-2"
            incoming = normalize_event(
                raw,
                sport_id=sport_id,
                competition_id=raw.get("competition_key") or slugify(raw.get("competition") or "unknown"),
            )
            competition = _ensure_competition_from_event(db, incoming, source)
            incoming["competition_key"] = competition.competition_id
            mapping = (
                db.query(SportsSourceCompetition)
                .filter_by(competition_id=competition.competition_id, source_id=source.source_id)
                .one()
            )
            existing = match_event(db, incoming, source_id=source.source_id)
            if writes_enabled():
                _upsert_event(db, incoming=incoming, source=source, mapping=mapping, existing=existing)
                written += 1
        record_ingest(
            db,
            source_id=source.source_id,
            entity_kind="event",
            payload=result.payload,
            capability=capability,
            http_status=result.http_status,
        )
        mark_success(db, source.source_id, result.http_status)
    return written


def _schedule_weight(db: Session, competition: SportsCompetition) -> Tuple[int, str]:
    maps = db.query(SportsSourceCompetition).filter_by(competition_id=competition.competition_id, enabled=True).all()
    families = [row.upstream_family or "" for row in maps]
    if not families:
        return (5, competition.competition_id)
    best = min(family_priority(fam) for fam in families)
    return (best, competition.competition_id)


def _competition_due(db: Session, competition: SportsCompetition, *, force: bool) -> bool:
    if force:
        return True
    health = db.query(SportsCompetitionHealth).filter_by(competition_id=competition.competition_id).first()
    if health is None or health.last_attempt_at is None:
        return True
    maps = db.query(SportsSourceCompetition).filter_by(competition_id=competition.competition_id, enabled=True).all()
    seconds = [
        cadence_seconds_for(row.upstream_family or "", row.polling_class)
        for row in maps
    ] or [900]
    return health.last_attempt_at + timedelta(seconds=min(seconds)) <= datetime.utcnow()


def run_cycle(
    db: Session,
    *,
    capabilities: Optional[List[str]] = None,
    sleeper=None,
    sport_id: Optional[str] = None,
    competition_id: Optional[str] = None,
    source_family: Optional[str] = None,
    force: bool = True,
    max_workers: int = 1,
) -> Dict[str, int]:
    """Collect due capabilities. One competition failure never aborts the batch."""
    if not collection_enabled():
        return {}
    stage("PROCESS START")
    caps = capabilities or due_capabilities(db)
    summary = {cap: 0 for cap in caps}
    for stale in (
        db.query(SportsIngestionRun)
        .filter_by(status="running")
        .filter(SportsIngestionRun.finished_at.is_(None))
        .all()
    ):
        stale.status = "INCOMPLETE"
        stale.finished_at = datetime.utcnow()
    write_owner = owner_identity()
    held_write = False
    if writes_enabled():
        held_write = acquire_write_lock(db, owner=write_owner)
        if not held_write:
            stage("WRITE LOCK DENIED")
            run = SportsIngestionRun(scope="cycle", status="FAILED", started_at=datetime.utcnow(), finished_at=datetime.utcnow())
            run.summary_json = dump_json({"reason": "write_lock_held"})
            db.add(run)
            return {"write_lock": 0}
    run = SportsIngestionRun(scope="cycle", status="running", started_at=datetime.utcnow(), jobs=len(caps))
    db.add(run)
    db.flush()
    run_id = run.id
    stage("DB CONNECT", run_id=run_id)
    stage("SCHEMA CHECK")
    query = db.query(SportsCompetition).filter_by(active=True)
    if sport_id:
        query = query.filter_by(sport_id=sport_id)
    if competition_id:
        query = query.filter_by(competition_id=competition_id)
    competitions = query.all()
    mapped = {
        row.competition_id
        for row in db.query(SportsSourceCompetition).filter_by(enabled=True).all()
    }
    competitions = [row for row in competitions if row.competition_id in mapped]
    competitions.sort(key=lambda row: _schedule_weight(db, row))
    stage("COLLECTION START", competitions=len(competitions), jobs=len(caps))
    db.info["persist_totals"] = {"done": 0, "target": max(1, len(competitions) * 20)}
    try:
        for capability in caps:
            written = 0
            errors = 0
            rejected = 0
            try:
                written += collect_dynamic_sources(db, capability, sleeper=sleeper)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                record_ingestion_error(
                    db,
                    competition_id=None,
                    source_id=None,
                    error_type="OTHER_ERROR",
                    message=str(exc),
                    run_id=run_id,
                )
            batch = 0
            for competition in competitions:
                if not _competition_due(db, competition, force=force):
                    continue
                if source_family:
                    maps = (
                        db.query(SportsSourceCompetition)
                        .filter_by(competition_id=competition.competition_id, enabled=True)
                        .all()
                    )
                    families = {row.upstream_family for row in maps}
                    if source_family not in families:
                        continue
                try:
                    with db.begin_nested():
                        stats = collect_competition(db, competition, capability, sleeper=sleeper)
                    written += int(stats.get("written") or 0)
                    rejected += int(stats.get("rejected") or 0)
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    record_ingestion_error(
                        db,
                        competition_id=competition.competition_id,
                        source_id=None,
                        error_type="OTHER_ERROR",
                        message=str(exc),
                        run_id=run_id,
                    )
                    record_competition_health(
                        db,
                        competition.competition_id,
                        primary_status="failed",
                        classification="OTHER_ERROR",
                        error=str(exc),
                    )
                batch += 1
                if writes_enabled() and batch % BATCH_COMMIT == 0:
                    stage("PERSIST progress", batch=batch, written=written)
                    db.commit()
                    run = db.get(SportsIngestionRun, run_id)
            mark_job(db, capability, "ok" if errors == 0 else "degraded", written, None if errors == 0 else f"{errors} competition errors")
            summary[capability] = written
            run = db.get(SportsIngestionRun, run_id) or run
            run.competitions_attempted = (run.competitions_attempted or 0) + len(competitions)
            run.events_written = (run.events_written or 0) + written
            run.errors = (run.errors or 0) + errors
            run.rejected = (run.rejected or 0) + rejected
            run.db_failures = (run.db_failures or 0) + errors
        stage("COLLECTION COMPLETE")
        stage("NORMALIZATION COMPLETE")
        stage("PERSIST START")
        run = db.get(SportsIngestionRun, run_id) or run
        run.finished_at = datetime.utcnow()
        run.status = "ok" if (run.errors or 0) == 0 else "FAILED"
        run.summary_json = dump_json(
            {
                **summary,
                "writes_enabled": writes_enabled(),
                "run_id": run_id,
                "jobs": len(caps),
                "inserted": run.events_written,
                "rejected": run.rejected,
                "provider_failures": run.provider_failures,
                "db_failures": run.db_failures,
                "status": run.status,
            }
        )
        stage("COMMIT")
        if any(summary.values()) and writes_enabled():
            cache_clear(db)
        stage("POST-WRITE VALIDATION")
        stage("SUMMARY", written=run.events_written, errors=run.errors, rejected=run.rejected)
        stage("PROCESS END")
        return summary
    finally:
        if held_write:
            try:
                release_write_lock(db, owner=write_owner)
            except Exception:
                pass
