"""Canonical event collapse, time-precision backfill, quarantine recovery.

Does not delete SportsEvent rows or SportsEventObservation rows.
Public API hides observation-only duplicates via display_eligible + canonical_event_id.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from collector.cache import flush_list_invalidations, note_list_invalidation
from collector.competition_identity import COMPETITION_LABELS, correct_public_competition_id
from collector.enrichment import (
    OBSERVATION_ENRICH_KEYS,
    copy_missing_enrichment,
    is_display_eligible,
    quality_flags_for_event,
)
from collector.identity_events import identity_confidence
from collector.merge import _filled, merge_event_fields
from collector.models import SportsEvent, SportsEventDetail, SportsEventObservation
from collector.participant_alias import (
    canonical_display_name,
    contextual_pair_match,
    discover_aliases_from_pair,
    prefer_display,
)
from collector.participant_text import clean_participant_name, extract_parenthetical_country
from collector.timezones import DATE_ONLY, EXACT_TIME, UNKNOWN_PRECISION
from collector.util import dump_json, load_json

HUB_FAMILIES = {"bbc-sport", "sportscore", "espn-html"}
BLOCKING_FLAGS = {
    "name_is_date",
    "name_is_time",
    "name_is_score",
    "html_in_name",
    "generic_heading",
    "url_in_name",
}


FINISHED_STATUSES = {
    "finished",
    "ft",
    "final",
    "ended",
    "complete",
    "completed",
    "aet",
    "pen",
    "awarded",
}
LIVE_STATUSES = {"live", "inplay", "in_play", "halftime", "ht", "break"}


def _score_present(score: Any) -> bool:
    if not isinstance(score, dict):
        return False
    return score.get("home") not in (None, "") and score.get("away") not in (None, "")


def _status_rank(status: Any) -> int:
    value = str(status or "").lower()
    if value in LIVE_STATUSES:
        return 3
    if value in FINISHED_STATUSES or value in {"postponed", "cancelled", "canceled", "abandoned"}:
        return 2
    return 1


def _keeper_rank(item: Dict[str, Any]) -> Tuple:
    extra = item.get("extra") or {}
    family = extra.get("source_family") or item.get("primary_source_id") or ""
    home = (item.get("home") or {}).get("name") or ""
    away = (item.get("away") or {}).get("name") or ""
    return (
        1 if _score_present(item.get("score")) else 0,
        _status_rank(item.get("status")),
        1 if family in HUB_FAMILIES else 0,
        len(extra.get("collapsed_from") or []),
        -(len(home) + len(away)),
        str(item.get("event_id") or ""),
    )


def _prefer_result(keeper: SportsEvent, loser: SportsEvent) -> None:
    k_dict = _event_dict(keeper)
    l_dict = _event_dict(loser)
    merged = merge_event_fields(
        k_dict,
        l_dict,
        incoming_is_higher_priority=False,
        incoming_source_id=str(loser.primary_source_id or ""),
    )
    keeper.score_json = dump_json(merged.get("score") or {})
    if merged.get("status"):
        keeper.status = merged.get("status")


def _event_dict(row: SportsEvent) -> Dict[str, Any]:
    parts = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}
    return {
        "home": parts.get("home") or {},
        "away": parts.get("away") or {},
        "sport": row.sport_id,
        "score": load_json(row.score_json, {}) or {},
        "competition_key": row.competition_id,
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "event_id": row.event_id,
        "primary_source_id": row.primary_source_id,
        "extra": extra,
        "updated_at": row.updated_at,
        "source_event_ids": extra.get("source_event_ids") or {},
        "event_family": row.event_family,
        "status": row.status,
        "observed_at": extra.get("observed_at") or extra.get("canonical_last_observed_at"),
        "retrieved_at": extra.get("source_fetch_time")
        or (row.retrieved_at.isoformat() + "Z" if row.retrieved_at else None),
        "source_fetch_time": extra.get("source_fetch_time"),
        "field_sources": extra.get("field_sources") or {},
        "periods": extra.get("periods"),
    }


def _repair_participants(row: SportsEvent) -> bool:
    parts = load_json(row.participants_json, {}) or {}
    dirty = False
    for key in ("home", "away", "participant_a", "participant_b"):
        side = parts.get(key)
        if not isinstance(side, dict) or not side.get("name"):
            continue
        cleaned, country = extract_parenthetical_country(side["name"])
        cleaned = clean_participant_name(
            cleaned,
            sport=row.sport_id,
            competition_country=row.country_id,
            participant_country=side.get("country_id"),
        )
        from collector.participant_alias import canonical_display_name

        shown = canonical_display_name(cleaned, sport=row.sport_id)
        if shown != side["name"]:
            if not side.get("source_name"):
                side["source_name"] = side["name"]
            side["name"] = shown
            side["display_name"] = shown
            dirty = True
        if country and not side.get("country_id"):
            side["country_id"] = country
            dirty = True
    if dirty:
        row.participants_json = dump_json(parts)
    return dirty


def _sync_public_flags(row: SportsEvent, extra: Dict[str, Any], eligible: bool) -> None:
    extra["display_eligible"] = eligible
    row.display_eligible = eligible
    row.extra_json = dump_json(extra)


def collapse_canonical_events(db: Session, *, competition_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    query = db.query(SportsEvent)
    if competition_ids:
        query = query.filter(SportsEvent.competition_id.in_(list(competition_ids)))
    rows = query.all()
    events = []
    by_id = {}
    repaired = 0
    for row in rows:
        if _repair_participants(row):
            repaired += 1
        event = _event_dict(row)
        events.append(event)
        by_id[row.event_id] = event
    db.flush()
    db.expire_all()

    same_comp: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        if not event.get("start_time"):
            continue
        same_comp[(event.get("sport") or "", event.get("competition_key") or "")].append(event)

    aliases_created = 0
    for group in same_comp.values():
        if len(group) < 2:
            continue
        for i, left in enumerate(group):
            for right in group[i + 1 :]:
                ok, _reason = contextual_pair_match(left, right, db=db)
                if ok:
                    aliases_created += discover_aliases_from_pair(db, left, right)

    parent: Dict[str, str] = {}

    def find(eid: str) -> str:
        parent.setdefault(eid, eid)
        while parent[eid] != eid:
            parent[eid] = parent[parent[eid]]
            eid = parent[eid]
        return eid

    def union(left_id: str, right_id: str) -> None:
        ra, rb = find(left_id), find(right_id)
        if ra != rb:
            parent[rb] = ra

    for group in same_comp.values():
        public_group = [
            item
            for item in group
            if (item.get("extra") or {}).get("display_eligible") is not False
            and not (item.get("extra") or {}).get("canonical_event_id")
        ]
        for event in public_group:
            parent.setdefault(event["event_id"], event["event_id"])
        for i, left in enumerate(public_group):
            for right in public_group[i + 1 :]:
                ok, _reason = contextual_pair_match(left, right, db=db)
                if ok:
                    union(left["event_id"], right["event_id"])

    clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_event = {item["event_id"]: item for item in events}
    for eid in parent:
        event = by_event.get(eid)
        if event:
            clusters[find(eid)].append(event)

    collapsed = 0
    conflicts = 0
    likely = 0
    false_positive = 0
    for items in clusters.values():
        public = [
            item
            for item in items
            if (item.get("extra") or {}).get("display_eligible") is not False
            and not (item.get("extra") or {}).get("canonical_event_id")
        ]
        if len(public) < 2:
            continue
        keeper = sorted(public, key=_keeper_rank, reverse=True)[0]
        for other in public:
            if other["event_id"] == keeper["event_id"]:
                continue
            conf = identity_confidence(keeper, other)
            ok, reason = contextual_pair_match(keeper, other, db=db)
            if not ok:
                false_positive += 1
                continue
            ks = keeper.get("score") or {}
            os_ = other.get("score") or {}
            if (
                ks.get("home") not in (None, "")
                and os_.get("home") not in (None, "")
                and (ks.get("home"), ks.get("away")) != (os_.get("home"), os_.get("away"))
                and (ks.get("home"), ks.get("away")) != (os_.get("away"), os_.get("home"))
            ):
                conflicts += 1
                _record_conflict(db, keeper["event_id"], other["event_id"], ks, os_)
            if conf >= 90 or ok:
                if _collapse_pair(db, keeper["event_id"], other["event_id"]):
                    collapsed += 1
                    note_list_invalidation(
                        db,
                        sport=keeper.get("sport"),
                        competition=keeper.get("competition") or keeper.get("competition_id"),
                        start_time=keeper.get("start_time"),
                        scoreboard_visible=True,
                    )
                    keeper = _event_dict(db.query(SportsEvent).filter_by(event_id=keeper["event_id"]).one())
            else:
                likely += 1
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        time.sleep(0.4)
        db.commit()
    flush_list_invalidations(db)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
    return {
        "aliases_created": aliases_created,
        "collapsed": collapsed,
        "conflicts": conflicts,
        "likely_review": likely,
        "false_positive": false_positive,
        "participant_repairs": repaired,
        "candidate_clusters": sum(1 for items in clusters.values() if len(items) > 1),
    }


def _record_conflict(db: Session, keeper_id: str, other_id: str, left_score: Dict, right_score: Dict) -> None:
    row = db.query(SportsEvent).filter_by(event_id=keeper_id).first()
    if not row:
        return
    extra = load_json(row.extra_json, {}) or {}
    conflicts = extra.get("provider_conflicts") or []
    entry = {"event_id": other_id, "scores": [left_score, right_score], "category": "CONFLICTING_PROVIDER_DATA"}
    if entry not in conflicts:
        conflicts.append(entry)
        extra["provider_conflicts"] = conflicts[-20:]
        row.extra_json = dump_json(extra)


def _collapse_pair(db: Session, keeper_id: str, loser_id: str) -> bool:
    keeper = db.query(SportsEvent).filter_by(event_id=keeper_id).first()
    loser = db.query(SportsEvent).filter_by(event_id=loser_id).first()
    if not keeper or not loser or keeper_id == loser_id:
        return False
    if loser.canonical_event_id:
        return False
    k_extra = load_json(keeper.extra_json, {}) or {}
    l_extra = load_json(loser.extra_json, {}) or {}
    from collector.source_ids import merge_family_ids

    k_extra["source_event_ids"] = merge_family_ids(
        k_extra.get("source_event_ids"),
        l_extra.get("source_event_ids"),
        family=str(l_extra.get("source_family") or k_extra.get("source_family") or ""),
        source_event_id=l_extra.get("source_event_id") or k_extra.get("source_event_id"),
    )
    k_extra["collapsed_from"] = list(dict.fromkeys((k_extra.get("collapsed_from") or []) + [loser_id]))
    if l_extra.get("provider_conflicts"):
        k_extra["provider_conflicts"] = (k_extra.get("provider_conflicts") or []) + l_extra.get("provider_conflicts")
    sources = load_json(keeper.contributing_sources_json, []) or []
    for item in load_json(loser.contributing_sources_json, []) or []:
        if item not in sources:
            sources.append(item)
    if loser.primary_source_id and loser.primary_source_id not in sources:
        sources.append(loser.primary_source_id)
    keeper.contributing_sources_json = dump_json(sources)
    _prefer_result(keeper, loser)
    k_parts = load_json(keeper.participants_json, {}) or {}
    l_parts = load_json(loser.participants_json, {}) or {}
    for key in ("home", "away"):
        k_name = (k_parts.get(key) or {}).get("name") or ""
        l_name = (l_parts.get(key) or {}).get("name") or ""
        chosen = prefer_display(k_name, l_name)
        if chosen and k_parts.get(key):
            k_parts[key]["name"] = canonical_display_name(clean_participant_name(chosen, sport=keeper.sport_id))
            k_parts[key]["display_name"] = k_parts[key]["name"]
            k_parts[key]["source_name"] = k_parts[key].get("source_name") or k_name
        l_country = (l_parts.get(key) or {}).get("country_id")
        if l_country and k_parts.get(key) and not k_parts[key].get("country_id"):
            k_parts[key]["country_id"] = l_country
    keeper.participants_json = dump_json(k_parts)
    if keeper.sport_id == "tennis":
        from collector.wta_orientation import tennis_sets_agree_with_match_score

        k_score = load_json(keeper.score_json, {}) or {}
        incoming_periods = l_extra.get("periods")
        if incoming_periods and not tennis_sets_agree_with_match_score(k_score, incoming_periods):
            l_extra = {**l_extra, "periods": None}
            conflicts = k_extra.get("provider_conflicts") or []
            conflicts.append(
                {
                    "event_id": loser_id,
                    "category": "CONFLICTING_PERIOD_ORIENTATION",
                    "scores": [k_score, load_json(loser.score_json, {}) or {}],
                }
            )
            k_extra["provider_conflicts"] = conflicts[-20:]
    k_extra = copy_missing_enrichment(k_extra, l_extra)
    k_extra["display_eligible"] = True
    keeper.display_eligible = True
    keeper.canonical_event_id = None
    keeper.extra_json = dump_json(k_extra)
    _merge_event_details(db, keeper_id, loser_id)
    l_extra["display_eligible"] = False
    l_extra["canonical_event_id"] = keeper_id
    l_extra["collapse_role"] = "observation_only"
    loser.display_eligible = False
    loser.canonical_event_id = keeper_id
    loser.extra_json = dump_json(l_extra)
    db.query(SportsEventObservation).filter_by(event_id=loser_id).update(
        {SportsEventObservation.event_id: keeper_id}, synchronize_session=False
    )
    db.add(
        SportsEventObservation(
            event_id=keeper_id,
            source_id=loser.primary_source_id or "collapsed",
            source_family=(l_extra.get("source_family") or ""),
            source_event_id=loser_id,
            source_event_key=loser_id[:80],
            payload_json=dump_json({"collapsed_event_id": loser_id}),
        )
    )
    return True


def backfill_start_precision(db: Session) -> Dict[str, Any]:
    counts = {
        "exact_midnight": 0,
        "date_only_corrected": 0,
        "unknown": 0,
        "unable": 0,
        "by_family": {},
    }
    for row in db.query(SportsEvent).yield_per(200):
        extra = load_json(row.extra_json, {}) or {}
        family = extra.get("source_family") or row.primary_source_id or "unknown"
        family_counts = counts["by_family"].setdefault(
            family, {"exact_midnight": 0, "date_only_corrected": 0, "unknown": 0, "unable": 0}
        )
        precision = extra.get("start_precision")
        kickoffs = extra.get("source_kickoffs") or []
        has_nonzero_clock = any(
            str(item.get("value") or "")[11:16] not in {"", "00:00"}
            for item in kickoffs
            if isinstance(item, dict)
        )
        midnight = bool(row.start_time and row.start_time.hour == 0 and row.start_time.minute == 0)
        local_midnight_like = bool(
            row.start_time and row.start_time.minute == 0 and str(extra.get("source_local_datetime") or "").endswith("T00:00:00")
        )
        if precision == DATE_ONLY:
            continue
        if has_nonzero_clock:
            if midnight:
                extra["start_precision"] = EXACT_TIME
                counts["exact_midnight"] += 1
                family_counts["exact_midnight"] += 1
                row.extra_json = dump_json(extra)
            continue
        if midnight or local_midnight_like or (
            extra.get("start_date") and midnight
        ) or str(extra.get("timezone_resolution_method") or "") in {"DATE_ONLY", "date_only"}:
            extra["start_precision"] = DATE_ONLY
            if extra.get("start_date") is None and row.start_time:
                extra["start_date"] = row.start_time.date().isoformat()
            counts["date_only_corrected"] += 1
            family_counts["date_only_corrected"] += 1
            row.extra_json = dump_json(extra)
        elif precision == UNKNOWN_PRECISION:
            counts["unknown"] += 1
            family_counts["unknown"] += 1
        elif midnight:
            extra["start_precision"] = UNKNOWN_PRECISION
            counts["unknown"] += 1
            family_counts["unknown"] += 1
            row.extra_json = dump_json(extra)
        else:
            counts["unable"] += 1
            family_counts["unable"] += 1
    db.commit()
    return counts


def classify_quarantine(db: Session) -> Dict[str, Any]:
    recovered = 0
    still = {
        "TRUE_GARBAGE": 0,
        "RECOVERABLE_BY_LABELLED_RECRAWL": 0,
        "AMBIGUOUS — KEEP QUARANTINED": 0,
        "COLLAPSED_OBSERVATION": 0,
        "RECOVERABLE_FROM_STORED_RAW": 0,
    }
    recrawl: List[Dict[str, Any]] = []
    for row in db.query(SportsEvent).all():
        extra = load_json(row.extra_json, {}) or {}
        if extra.get("canonical_event_id") or row.canonical_event_id:
            still["COLLAPSED_OBSERVATION"] += 1
            row.display_eligible = False
            continue
        flags = extra.get("quality_flags") or quality_flags_for_event(_event_dict(row))
        kinds = {str(flag).split(":")[-1] for flag in flags}
        if kinds & BLOCKING_FLAGS or "implausible_football_score" in kinds:
            still["TRUE_GARBAGE"] += 1
            extra["display_eligible"] = False
            extra["quarantine_disposition"] = "TRUE_GARBAGE"
            _sync_public_flags(row, extra, False)
            continue
        family = extra.get("source_family") or ""
        src_name = extra.get("source_competition_name") or extra.get("competition") or ""
        cid = row.competition_id
        hub = family in HUB_FAMILIES
        corrected = correct_public_competition_id(
            stored_competition_id=cid,
            source_competition_name=str(src_name or ""),
            sport_id=row.sport_id or "",
            source_family=str(family or ""),
        )
        if hub and src_name and corrected:
            if corrected != cid:
                row.competition_id = corrected
                extra["canonical_competition_id"] = corrected
                extra["quarantine_disposition"] = "RECOVERED_REMAPPED"
            else:
                extra["quarantine_disposition"] = "RECOVERED_LABEL_MATCH"
            extra["display_eligible"] = True
            extra["quality_flags"] = [flag for flag in flags if flag != "duplicate_or_contaminated"]
            _sync_public_flags(row, extra, True)
            recovered += 1
            still["RECOVERABLE_FROM_STORED_RAW"] += 1
            continue
        if extra.get("display_eligible") is False:
            if hub and cid in COMPETITION_LABELS and not src_name:
                still["RECOVERABLE_BY_LABELLED_RECRAWL"] += 1
                extra["quarantine_disposition"] = "RECOVERABLE_BY_LABELLED_RECRAWL"
                recrawl.append(
                    {
                        "event_id": row.event_id,
                        "family": family,
                        "competition_id": cid,
                        "source_url": row.source_url,
                    }
                )
            else:
                still["AMBIGUOUS — KEEP QUARANTINED"] += 1
                extra["quarantine_disposition"] = "AMBIGUOUS"
            row.extra_json = dump_json(extra)
            row.display_eligible = False
        else:
            row.display_eligible = True if extra.get("display_eligible") is not False else False
    db.commit()
    flush_list_invalidations(db)
    db.commit()
    return {
        "recovered": recovered,
        "still": still,
        "recrawl_required": len(recrawl),
        "recrawl_sample": recrawl[:25],
        "recrawl_request_impact": "No extra upstream requests executed. Worker labelled recrawl uses existing scheduled jobs only.",
    }


def _merge_event_details(db: Session, keeper_id: str, loser_id: str) -> None:
    keeper = db.get(SportsEventDetail, keeper_id)
    loser = db.get(SportsEventDetail, loser_id)
    if loser is None:
        return
    if keeper is None:
        keeper = SportsEventDetail(event_id=keeper_id)
        db.add(keeper)
    if _filled(load_json(loser.incidents_json)) and not _filled(load_json(keeper.incidents_json)):
        keeper.incidents_json = loser.incidents_json
    if _filled(load_json(loser.lineups_json)) and not _filled(load_json(keeper.lineups_json)):
        keeper.lineups_json = loser.lineups_json
    if _filled(load_json(loser.statistics_json)) and not _filled(load_json(keeper.statistics_json)):
        keeper.statistics_json = loser.statistics_json


def promote_observation_enrichment(db: Session) -> Dict[str, Any]:
    """Copy missing enrichment from collapsed observations onto public keepers.

    Does not resurrect quarantined rows (no canonical_event_id).
    Does not copy competition, participant identity, precision, or scores.
    """
    copied = 0
    skipped_quarantine = 0
    for loser in db.query(SportsEvent).filter(SportsEvent.canonical_event_id.isnot(None)).yield_per(200):
        if not loser.canonical_event_id:
            continue
        extra = load_json(loser.extra_json, {}) or {}
        if extra.get("collapse_role") != "observation_only" and not loser.canonical_event_id:
            skipped_quarantine += 1
            continue
        keeper = db.query(SportsEvent).filter_by(event_id=loser.canonical_event_id).first()
        if keeper is None or keeper.display_eligible is False:
            skipped_quarantine += 1
            continue
        k_extra = load_json(keeper.extra_json, {}) or {}
        merged = copy_missing_enrichment(k_extra, extra)
        changed = any(merged.get(key) != k_extra.get(key) for key in OBSERVATION_ENRICH_KEYS)
        if changed:
            merged["display_eligible"] = k_extra.get("display_eligible", True)
            keeper.extra_json = dump_json(merged)
            copied += 1
        _merge_event_details(db, keeper.event_id, loser.event_id)
    if copied:
        db.commit()
        flush_list_invalidations(db)
        db.commit()
    return {"copied": copied, "skipped_quarantine": skipped_quarantine}


def apply_phase2(db: Session) -> Dict[str, Any]:
    collapse = collapse_canonical_events(db)
    precision = backfill_start_precision(db)
    from collector.integrity import apply_competition_attribution

    attribution = apply_competition_attribution(db)
    quarantine = classify_quarantine(db)

    # Final safety pass: startup integrity is allowed to merge/correct rows, but
    # it must not leave already-valid source-native football hidden because a
    # generic competition-attribution heuristic was inconclusive.
    from collector.source_native_reconcile import revalidate_current_source_native

    source_native = revalidate_current_source_native(
        db,
        days_back=3,
        days_forward=14,
    )
    if source_native.get("promoted"):
        db.commit()

    enrichment = promote_observation_enrichment(db)
    return {
        "collapse": collapse,
        "precision": precision,
        "attribution": attribution,
        "quarantine": quarantine,
        "source_native_revalidated": source_native,
        "enrichment": enrichment,
    }
