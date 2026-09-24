"""Attach FotMob match IDs onto existing canonical football events.

Uses competition + kickoff + participants. Does not create duplicate fixtures.
Does not match on title text alone. Date-board backfill is bounded and checkpointed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, object_session

from collector.adapters_fotmob import (
    FOTMOB_LEAGUES,
    _BOARD,
    _load_boards,
    board_dates,
    match_to_event,
)
from collector.competition_identity import unique_label_competition
from collector.identity_events import identity_confidence
from collector.competition_presentation import SOURCE_ALPHA3_TO_GEO
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsEvent, SportsSource, SportsSourceCompetition
from collector.source_ids import families_with_ids, merge_family_ids
from collector.util import dump_json, load_json, slugify
from sports_registry.geography import label_for

logger = logging.getLogger(__name__)

DATE_BOARD_JOB = "fotmob-date-boards-v7"
_YOUTH = ("u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior")
_WOMEN = ("women", "womens", "woms")
_RESERVE = ("reserve", " ii", "2nd", "b team")


def _tokens(name: str) -> set:
    folded = " ".join(str(name or "").lower().replace("-", " ").split())
    marks = set()
    for item in _YOUTH:
        if item in folded:
            marks.add("youth")
    for item in _WOMEN:
        if item in folded:
            marks.add("women")
    for item in _RESERVE:
        if item in folded:
            marks.add("reserve")
    return marks


def _protected_conflict(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    l_home = ((left.get("home") or {}).get("name") or "") + " " + ((left.get("away") or {}).get("name") or "")
    r_home = ((right.get("home") or {}).get("name") or "") + " " + ((right.get("away") or {}).get("name") or "")
    return bool(_tokens(l_home) ^ _tokens(r_home))


def _league_to_competition() -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for competition_id, spec in FOTMOB_LEAGUES.items():
        if spec.get("id") not in (None, ""):
            mapped[str(spec["id"])] = competition_id
        raw_ids = spec.get("ids") or []
        values = raw_ids if isinstance(raw_ids, (list, tuple, set)) else [raw_ids]
        for value in values:
            if value not in (None, ""):
                mapped[str(value)] = competition_id
    return mapped


def _canonical_fotmob_competition(league_name: str, ccode: str) -> Optional[str]:
    """Resolve a known canonical league before creating a source-native key.

    Generic names such as "Premier League" need country context; otherwise a
    Ghana/Bosnia/Egypt league can be mistaken for England or fail closed.
    """
    name = str(league_name or "").strip()
    if not name:
        return None
    direct = unique_label_competition(name, sport_id="football")
    if direct:
        return direct
    code = str(ccode or "").strip().upper()
    if not code or code in {"INT", "WORLD"}:
        return None
    geo = SOURCE_ALPHA3_TO_GEO.get(code, code.lower())
    country = str(label_for(geo) or geo or "").strip()
    if not country:
        return None
    return unique_label_competition(f"{name} {country}", sport_id="football")


def _fotmob_competition_identity(match: Dict[str, Any]) -> Tuple[Optional[str], str, str, str]:
    league = match.get("_league") if isinstance(match.get("_league"), dict) else {}
    league_id = str(league.get("id") or "").strip()
    league_name = str(league.get("name") or "").strip()
    ccode = str(league.get("ccode") or league.get("countryCode") or "").strip().upper()
    known = _league_to_competition().get(league_id)
    if known:
        return known, league_id, league_name, ccode
    canonical = _canonical_fotmob_competition(league_name, ccode)
    if canonical:
        return canonical, league_id, league_name, ccode
    if not league_id or not league_name:
        return None, league_id, league_name, ccode
    suffix = slugify(league_name)
    if not suffix:
        return None, league_id, league_name, ccode
    country = ccode.lower() if ccode and ccode not in {"INT", "WORLD"} else ""
    competition_id = f"football-{country}-{suffix}" if country else f"football-{suffix}"
    return competition_id[:120], league_id, league_name, ccode


def _ensure_dynamic_fotmob_mapping(
    db: Session,
    *,
    competition_id: str,
    league_id: str,
    league_name: str,
    ccode: str,
) -> Optional[SportsSourceCompetition]:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="football",
            name=league_name or competition_id,
            official_name=league_name or competition_id,
            slug=competition_id,
            country_id=ccode or None,
            event_model="team_match",
            country_based=bool(ccode and ccode not in {"INT", "WORLD"}),
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()
    source = db.query(SportsSource).filter_by(source_id="fotmob-global", enabled=True).first()
    if source is None:
        return None

    # v4 accidentally used the first enabled FotMob source in the database,
    # which could be a competition-specific source (for example Albania).
    # Disable only those dynamically-created legacy mappings; verified static
    # competition mappings are left untouched.
    legacy_dynamic = (
        db.query(SportsSourceCompetition)
        .filter(
            SportsSourceCompetition.competition_id == competition_id,
            SportsSourceCompetition.source_id != source.source_id,
            SportsSourceCompetition.upstream_family == "fotmob",
            SportsSourceCompetition.coverage_notes == "FotMob source-native daily-board breadth",
            SportsSourceCompetition.enabled.is_(True),
        )
        .all()
    )
    for legacy in legacy_dynamic:
        legacy.enabled = False

    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=source.source_id,
            priority=40,
            source_competition_id=league_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="FotMob source-native daily-board breadth",
            verification="source-native league id and daily board",
            polling_class="NORMAL",
            source_config_json=dump_json({"fotmob_league_id": league_id, "fotmob_league_name": league_name}),
            independence_status="single-source-breadth",
            upstream_family="fotmob",
        )
        db.add(mapping)
        db.flush()
    return mapping



def repair_legacy_dynamic_source_bindings(db: Session) -> Dict[str, int]:
    """Repair only v4/v5 dynamic mappings that were bound to a specific FotMob source."""
    global_source = db.get(SportsSource, "fotmob-global")
    if global_source is None or not global_source.enabled:
        return {"mappings": 0, "events": 0}

    legacy_rows = (
        db.query(SportsSourceCompetition)
        .filter(
            SportsSourceCompetition.upstream_family == "fotmob",
            SportsSourceCompetition.coverage_notes == "FotMob source-native daily-board breadth",
            SportsSourceCompetition.source_id != "fotmob-global",
        )
        .all()
    )
    repaired_mappings = 0
    repaired_events = 0
    for legacy in legacy_rows:
        competition = db.get(SportsCompetition, legacy.competition_id)
        if competition is None:
            continue
        cfg = load_json(legacy.source_config_json, {}) or {}
        league_id = str(cfg.get("fotmob_league_id") or legacy.source_competition_id or "").strip()
        league_name = str(cfg.get("fotmob_league_name") or competition.official_name or competition.name or legacy.competition_id).strip()
        ccode = str(competition.country_id or "").strip().upper()
        mapping = _ensure_dynamic_fotmob_mapping(
            db,
            competition_id=legacy.competition_id,
            league_id=league_id,
            league_name=league_name,
            ccode=ccode,
        )
        if mapping is None:
            continue
        if legacy.enabled:
            legacy.enabled = False
        changed = (
            db.query(SportsEvent)
            .filter(
                SportsEvent.competition_id == legacy.competition_id,
                SportsEvent.primary_source_id == legacy.source_id,
            )
            .update(
                {SportsEvent.primary_source_id: "fotmob-global"},
                synchronize_session=False,
            )
        )
        repaired_events += int(changed or 0)
        repaired_mappings += 1

    db.flush()
    return {"mappings": repaired_mappings, "events": repaired_events}

def _persist_missing_fotmob(
    db: Session,
    *,
    match: Dict[str, Any],
    parsed: Dict[str, Any],
    competition_id: str,
) -> bool:
    from collector.provider_crosswalk import _ingest

    league = match.get("_league") if isinstance(match.get("_league"), dict) else {}
    league_id = str(league.get("id") or "").strip()
    league_name = str(league.get("name") or "").strip()
    ccode = str(league.get("ccode") or league.get("countryCode") or "").strip().upper()
    mapping = _ensure_dynamic_fotmob_mapping(
        db,
        competition_id=competition_id,
        league_id=league_id,
        league_name=league_name,
        ccode=ccode,
    )
    if mapping is None:
        return False
    incoming = {
        **parsed,
        "sport": "football",
        "competition": league_name or competition_id,
        "competition_key": competition_id,
        "country_id": ccode or None,
        "source_family": "fotmob",
        "source_competition_id": league_id or None,
        "source_competition_name": league_name or None,
        "source_event_ids": {"fotmob": str(parsed.get("source_event_id") or "")},
    }
    return _ingest(db, incoming, mapping.source_id)


def _event_view(row: SportsEvent) -> Dict[str, Any]:
    parts = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}
    return {
        "sport": row.sport_id,
        "competition": row.competition_id,
        "competition_key": row.competition_id,
        "home": parts.get("home") or {},
        "away": parts.get("away") or {},
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "source_event_ids": families_with_ids(extra),
    }


def _fill_identity_assets(row: SportsEvent, parsed: Dict[str, Any]) -> bool:
    participants = load_json(row.participants_json, {}) or {}
    changed = False
    for key in ("home", "away"):
        incoming = parsed.get(key) if isinstance(parsed.get(key), dict) else {}
        current = participants.get(key) if isinstance(participants.get(key), dict) else {}
        if not current:
            current = {}
        merged = dict(current)
        for field in ("id", "slug", "logo", "country_id"):
            if incoming.get(field) and not merged.get(field):
                merged[field] = incoming.get(field)
                changed = True
        if merged:
            participants[key] = merged
            alt = "participant_a" if key == "home" else "participant_b"
            alt_current = participants.get(alt) if isinstance(participants.get(alt), dict) else {}
            alt_merged = dict(alt_current or merged)
            for field in ("id", "slug", "logo", "country_id"):
                if merged.get(field) and not alt_merged.get(field):
                    alt_merged[field] = merged.get(field)
                    changed = True
            participants[alt] = alt_merged
    extra = load_json(row.extra_json, {}) or {}
    competition_logo = parsed.get("competition_logo")
    if competition_logo and not extra.get("competition_logo"):
        extra["competition_logo"] = competition_logo
        changed = True
    country_id = parsed.get("country_id")
    if country_id and not row.country_id:
        row.country_id = country_id
        changed = True
    if changed:
        row.participants_json = dump_json(participants)
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)
        session = object_session(row)
        if session is not None:
            note_list_invalidation(
            db=session,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
            )
    return changed


def _attach(row: SportsEvent, fotmob_id: str, parsed: Optional[Dict[str, Any]] = None) -> bool:
    extra = load_json(row.extra_json, {}) or {}
    before = dict(families_with_ids(extra))
    extra["source_event_ids"] = merge_family_ids(extra.get("source_event_ids"), family="fotmob", source_event_id=fotmob_id)
    id_changed = families_with_ids(extra) != before
    if id_changed:
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)
    asset_changed = _fill_identity_assets(row, parsed or {}) if parsed else False
    return id_changed or asset_changed


def _unique_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for match in matches:
        mid = str(match.get("id") or match.get("matchId") or "")
        if not mid:
            continue
        seen.setdefault(mid, match)
    return list(seen.values())


def _match_keepers(
    incoming: Dict[str, Any],
    rows: List[SportsEvent],
) -> Tuple[Optional[SportsEvent], int, int]:
    scored: List[Tuple[int, SportsEvent]] = []
    protected = 0
    for row in rows:
        view = _event_view(row)
        if _protected_conflict(view, incoming):
            protected += 1
            continue
        score = identity_confidence(view, incoming)
        if score < 90:
            continue
        scored.append((score, row))
    if not scored:
        return None, 0, protected
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[1][0] >= 90:
        return None, 2, protected
    return scored[0][1], 1, protected


def crosswalk_fotmob_ids(
    db: Session,
    *,
    hours: int = 504,
    getter=None,
    dates: Optional[List[str]] = None,
    past_days: Optional[int] = None,
    future_days: Optional[int] = None,
    persist_missing: bool = False,
    max_ingest: int = 1200,
) -> Dict[str, int]:
    from collector.http import fetch_url

    _BOARD.clear()
    if dates is None and (past_days is not None or future_days is not None):
        dates = board_dates(past_days=past_days if past_days is not None else 3, future_days=future_days if future_days is not None else 1)
    try:
        matches = _load_boards(getter or fetch_url, dates=dates)
    except Exception:
        matches = []
    matches = _unique_matches(matches)
    league_map = _league_to_competition()
    bound = datetime.utcnow() - timedelta(hours=hours)
    keepers = (
        db.query(SportsEvent)
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .all()
    )

    # Exact-ID enrichment first: if a canonical row already carries a FotMob
    # match id, attach artwork directly from the matching date-board row.
    # This avoids any competition/name ambiguity and prioritizes what users
    # actually see today/upcoming.
    parsed_by_id: Dict[str, Dict[str, Any]] = {}
    for match in matches:
        competition_id, _league_id, _league_name, _ccode = _fotmob_competition_identity(match)
        if not competition_id:
            continue
        parsed = match_to_event(match, competition_id)
        if parsed and parsed.get("source_event_id"):
            parsed_by_id[str(parsed["source_event_id"])] = parsed

    direct_asset_updates = 0
    for row in keepers:
        fid = families_with_ids(load_json(row.extra_json, {}) or {}).get("fotmob")
        parsed = parsed_by_id.get(str(fid)) if fid else None
        if parsed and _fill_identity_assets(row, parsed):
            direct_asset_updates += 1
    by_comp: Dict[str, List[SportsEvent]] = {}
    for row in keepers:
        by_comp.setdefault(row.competition_id, []).append(row)
    upstream_total = len(matches)
    eligible = attached = skipped_conflict = unmatched = ambiguous = ingested = 0
    eligible_ids: List[str] = []
    for match in matches:
        competition_id, league_id, _league_name, _ccode = _fotmob_competition_identity(match)
        if not competition_id:
            continue
        parsed = match_to_event(match, competition_id)
        if not parsed or not parsed.get("source_event_id"):
            continue
        eligible += 1
        eligible_ids.append(str(parsed["source_event_id"]))
        incoming = {
            "sport": "football",
            "competition": competition_id,
            "competition_key": competition_id,
            "home": parsed.get("home") or {},
            "away": parsed.get("away") or {},
            "start_time": parsed.get("start_time"),
            "source_event_ids": {"fotmob": str(parsed["source_event_id"])},
        }
        best, n_ok, protected = _match_keepers(incoming, by_comp.get(competition_id) or [])
        skipped_conflict += protected
        if n_ok >= 2:
            ambiguous += 1
            continue
        if best is None:
            unmatched += 1
            if persist_missing and ingested < max_ingest:
                if _persist_missing_fotmob(
                    db,
                    match=match,
                    parsed=parsed,
                    competition_id=competition_id,
                ):
                    ingested += 1
                    by_comp.setdefault(competition_id, [])
            continue
        if _attach(best, str(parsed["source_event_id"]), parsed):
            attached += 1
    db.flush()
    logger.info(
        "fotmob_crosswalk upstream_total=%s eligible=%s attached=%s unmatched=%s ingested=%s ambiguous=%s protected=%s",
        upstream_total,
        eligible,
        attached,
        unmatched,
        ingested,
        ambiguous,
        skipped_conflict,
    )
    if direct_asset_updates:
        logger.info("fotmob_exact_id_asset_updates=%s", direct_asset_updates)
    return {
        "upstream_total": upstream_total,
        "upstream_eligible": eligible,
        "attached": attached,
        "unmatched": unmatched,
        "ingested": ingested,
        "ambiguous": ambiguous,
        "protected_conflicts": skipped_conflict,
        "direct_asset_updates": direct_asset_updates,
    }


def eligible_coverage(
    db: Session,
    *,
    hours: int = 504,
    getter=None,
    dates: Optional[List[str]] = None,
    past_days: int = 7,
    future_days: int = 3,
) -> Dict[str, Any]:
    from collector.http import fetch_url

    _BOARD.clear()
    board = dates or board_dates(past_days=past_days, future_days=future_days)
    try:
        matches = _unique_matches(_load_boards(getter or fetch_url, dates=board))
    except Exception:
        matches = []
    league_map = _league_to_competition()
    bound = datetime.utcnow() - timedelta(hours=hours)
    eligible_ids: set[str] = set()
    upstream_total = 0
    for match in matches:
        mid = str(match.get("id") or match.get("matchId") or "")
        if not mid:
            continue
        upstream_total += 1
        league_id = str((match.get("_league") or {}).get("id") or "")
        if league_id in league_map:
            eligible_ids.add(mid)
    comps = set(FOTMOB_LEAGUES)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .filter(SportsEvent.competition_id.in_(comps))
        .all()
    )
    canonical_ids: set[str] = set()
    with_id = 0
    for row in rows:
        fid = families_with_ids(load_json(row.extra_json, {}) or {}).get("fotmob")
        if fid:
            with_id += 1
            canonical_ids.add(str(fid))
    matched_ids = eligible_ids & canonical_ids
    eligible = len(eligible_ids)
    pct = round((len(matched_ids) / eligible) * 100, 1) if eligible else 0.0
    payload = {
        "recent_football_total": db.query(SportsEvent)
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.start_time >= bound)
        .count(),
        "fotmob_competitions": len(comps),
        "canonical_in_fotmob_comps": len(rows),
        "canonical_with_fotmob_id": with_id,
        "upstream_total": upstream_total,
        "upstream_eligible": eligible,
        "ids_attached_intersection": len(matched_ids),
        "unmatched_eligible": eligible - len(matched_ids),
        "coverage_pct": pct,
        "board_days": board,
    }
    logger.info("fotmob_eligible_coverage %s", payload)
    return payload


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, DATE_BOARD_JOB)
    if row is None:
        row = SportsCollectorJob(job_key=DATE_BOARD_JOB)
        db.add(row)
        db.flush()
    return row


def _checkpoint(job: SportsCollectorJob, **fields: Any) -> None:
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(fields)
    job.last_error = dump_json(payload)[:4000]
    job.last_status = str(payload.get("state") or job.last_status or "")


def run_date_board_backfill(
    db: Session,
    *,
    getter=None,
    past_days: int = 7,
    future_days: int = 3,
    heartbeat: Optional[Callable[[], None]] = None,
    owner: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Owner-only bounded FotMob date boards. Attaches IDs only; no matchDetails crawl."""
    status = lock_status(db)
    if not status.get("held"):
        logger.info("skip fotmob date boards; scheduler lease is not held")
        return None
    if owner and status.get("owner_id") != owner:
        logger.info("skip fotmob date boards; process is not the scheduler owner")
        return None
    from collector.http import fetch_url

    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    dates = list(payload.get("dates") or board_dates(past_days=past_days, future_days=future_days))
    next_index = int(payload.get("next_index") or 0)
    repair = repair_legacy_dynamic_source_bindings(db)
    totals = {
        "source_rebound_mappings": int(repair.get("mappings") or 0),
        "source_rebound_events": int(repair.get("events") or 0),
        "upstream_total": int(payload.get("upstream_total") or 0),
        "upstream_eligible": int(payload.get("upstream_eligible") or 0),
        "attached": int(payload.get("attached") or 0),
        "unmatched": int(payload.get("unmatched") or 0),
        "ambiguous": int(payload.get("ambiguous") or 0),
        "ingested": int(payload.get("ingested") or 0),
        "days_processed": list(payload.get("days_processed") or []),
    }
    fetch = getter or fetch_url
    for index, day in enumerate(dates):
        if index < next_index:
            continue
        if heartbeat:
            heartbeat()
        _BOARD.clear()
        try:
            day_date = datetime.fromisoformat(day[:10]).date()
        except ValueError:
            day_date = datetime.utcnow().date()
        persist_day = day_date >= (datetime.utcnow().date() - timedelta(days=1))
        day_result = crosswalk_fotmob_ids(
            db,
            getter=fetch,
            dates=[day],
            persist_missing=persist_day,
        )
        for key in ("upstream_total", "upstream_eligible", "attached", "unmatched", "ingested", "ambiguous"):
            totals[key] = int(totals.get(key) or 0) + int(day_result.get(key) or 0)
        totals["days_processed"].append(day)
        _checkpoint(
            job,
            state="running",
            dates=dates,
            next_index=index + 1,
            **totals,
        )
        db.commit()
    coverage = eligible_coverage(db, getter=fetch, dates=dates)
    try:
        from collector.source_native_reconcile import revalidate_current_source_native

        source_native_revalidation = revalidate_current_source_native(db)
    except Exception:
        logger.exception("FotMob source-native revalidation failed")
        source_native_revalidation = {"scanned": 0, "promoted": 0, "blocked": 0}
    _checkpoint(
        job,
        state="done",
        dates=dates,
        next_index=len(dates),
        coverage=coverage,
        source_native_revalidation=source_native_revalidation,
        **totals,
    )
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    job.items_written = int(totals.get("attached") or 0) + int(totals.get("ingested") or 0)
    db.commit()
    logger.info(
        "fotmob_date_boards_complete %s coverage=%s revalidation=%s",
        totals,
        coverage,
        source_native_revalidation,
    )
    return {
        **totals,
        "coverage": coverage,
        "dates": dates,
        "source_native_revalidation": source_native_revalidation,
    }


def run_date_boards_if_due(
    db: Session,
    *,
    min_interval_hours: int = 6,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    getter=None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None
    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    state = payload.get("state")
    if state == "done" and job.last_run_at and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours):
        return None
    if state == "done":
        job.last_error = dump_json({"state": "pending"})
        db.flush()
    return run_date_board_backfill(db, getter=getter, heartbeat=heartbeat, owner=owner)
