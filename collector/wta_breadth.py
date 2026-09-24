"""Official WTA global schedule breadth.

Uses api.wtatennis.com, the public backend used by wtatennis.com. Unlike the
incremental live lane, this job walks every tournament overlapping the near
date window and persists all matching fixtures/results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.adapters_wta import (
    BASE,
    _countries_for_name,
    _player_country_map,
    discover_current_tournaments,
    match_to_event,
)
from collector.cache import note_list_invalidation
from collector.competition_identity import unique_label_competition
from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsEvent, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "wta-global-breadth-v7"
SOURCE_ID = "wta-global"
PUBLIC_BREADTH_STATUS = "single-source-breadth"

_COUNTRY_ASSET_INTERVAL_S = 300
_country_asset_next_run_at = 0.0


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    row = db.get(SportsSource, SOURCE_ID)
    if row is not None and source_collectable(row):
        return row
    return None


def _day(value: Any):
    raw = str(value or "")[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _tournament_overlaps(meta: Dict[str, Any], *, low, high) -> bool:
    start = _day(meta.get("startDate"))
    end = _day(meta.get("endDate")) or start
    if start is None:
        return False
    return start <= high and (end or start) >= low


def _competition_identity(meta: Dict[str, Any]) -> tuple[str, str, str]:
    group = meta.get("tournamentGroup") if isinstance(meta.get("tournamentGroup"), dict) else {}
    group_id = str(group.get("id") or meta.get("id") or "").strip()
    name = str(group.get("name") or meta.get("title") or meta.get("name") or "WTA").strip()
    canonical = unique_label_competition(name, sport_id="tennis")
    if canonical:
        return canonical, name, group_id or slugify(name)
    suffix = slugify(name)
    native = group_id or suffix
    return f"tennis-wta-{native}-{suffix}"[:120].rstrip("-"), name, native


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
    source_competition_id: str,
    meta: Dict[str, Any],
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="tennis",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            country_id=str(meta.get("country") or "").strip() or None,
            region_id="world",
            event_model="individual_match",
            competition_type="tournament",
            country_based=False,
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()

    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=source.source_id,
            priority=10,
            source_competition_id=source_competition_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="Official WTA tournament schedule/results",
            verification="api.wtatennis.com tournament matches",
            polling_class="MEDIUM",
            source_config_json=dump_json({
                "group_id": source_competition_id,
                "year": meta.get("year"),
                "source_competition_name": competition_name,
            }),
            independence_status=PUBLIC_BREADTH_STATUS,
            upstream_family="wta-json",
        )
        db.add(mapping)
        db.flush()
    mapping.independence_status = PUBLIC_BREADTH_STATUS
    mapping.upstream_family = "wta-json"
    mapping.enabled = True
    mapping.coverage_scope = "full"
    mapping.verification = "api.wtatennis.com tournament matches"
    return mapping


def _repair_legacy_wta_rows(db: Session) -> int:
    """Repair WTA breadth rows written with stale sport/family identity."""
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.primary_source_id == SOURCE_ID)
        .all()
    )
    repaired = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        changed = False
        if row.sport_id != "tennis":
            row.sport_id = "tennis"
            changed = True
        if row.event_family != "individual_match":
            row.event_family = "individual_match"
            changed = True
        if extra.get("source_family") != "wta-json":
            extra["source_family"] = "wta-json"
            changed = True
        if not extra.get("public_competition_key"):
            extra["public_competition_key"] = row.competition_id
            changed = True
        if extra.get("display_eligible") is not True or row.display_eligible is not True:
            extra["display_eligible"] = True
            row.display_eligible = True
            changed = True
        if not changed:
            continue
        row.extra_json = dump_json(extra)
        from collector.list_extra import store_list_extra
        store_list_extra(row, extra)
        repaired += 1
    if repaired:
        db.flush()
    return repaired


def _event_in_window(event: Dict[str, Any], *, low: datetime, high: datetime) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return False
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return low <= stamp <= high


def _merge_country_index(
    target: Dict[str, str],
    incoming: Dict[str, str],
    ambiguous: Set[str],
) -> None:
    """Merge exact WTA player-country keys without accepting conflicts."""
    for key, country in (incoming or {}).items():
        value = str(country or "").strip()
        if not key or not value or key in ambiguous:
            continue
        previous = target.get(key)
        if previous and previous != value:
            target.pop(key, None)
            ambiguous.add(key)
            continue
        target[key] = value


def _side_has_country(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    if str(side.get("country_id") or side.get("country") or "").strip():
        return True
    return any(str(value or "").strip() for value in (side.get("country_ids") or []))


def _repair_visible_wta_countries(
    db: Session,
    *,
    player_countries: Dict[str, str],
    low: datetime,
    high: datetime,
) -> Dict[str, int]:
    """Fill blank WTA participant countries from official active player lists.

    This is identity-only. It never changes score, status, start time,
    competition identity, or event visibility.
    """
    stats = {
        "rows_scanned": 0,
        "rows_updated": 0,
        "participant_sides_filled": 0,
    }
    if not player_countries:
        return stats

    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "tennis",
            or_(SportsEvent.display_eligible.is_(True), SportsEvent.display_eligible.is_(None)),
            SportsEvent.start_time >= low,
            SportsEvent.start_time <= high,
        )
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        source_family = str(extra.get("source_family") or "").strip().lower()
        primary = str(row.primary_source_id or "").strip().lower()
        competition = str(row.competition_id or "").strip().lower()
        is_wta = (
            primary.startswith("wta")
            or source_family.startswith("wta")
            or competition == "wta-tour"
            or competition.startswith("tennis-wta-")
        )
        if not is_wta:
            continue

        stats["rows_scanned"] += 1
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _side_has_country(side):
                continue
            name = str(side.get("display_name") or side.get("name") or "").strip()
            countries = _countries_for_name(name, player_countries)
            if not countries:
                continue
            merged = dict(side)
            if len(countries) == 1:
                merged["country_id"] = countries[0]
            else:
                merged["country_ids"] = countries
            participants[side_name] = merged

            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and not _side_has_country(mirror):
                mirror_merged = dict(mirror)
                if len(countries) == 1:
                    mirror_merged["country_id"] = countries[0]
                else:
                    mirror_merged["country_ids"] = countries
                participants[mirror_name] = mirror_merged
            changed = True
            stats["participant_sides_filled"] += 1

        if not changed:
            continue
        row.participants_json = dump_json(participants)
        note_list_invalidation(
            db,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
        )
        stats["rows_updated"] += 1

    if stats["rows_updated"]:
        db.flush()
    return stats


def run_country_asset_repair(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_tournaments: int = 24,
) -> Dict[str, Any]:
    """Repair visible WTA participant country identity without touching fixtures."""
    fetch = getter or fetch_url
    now = datetime.utcnow()
    low = now - timedelta(days=2)
    high = now + timedelta(days=4)
    discovered = discover_current_tournaments(fetch, now=now)
    active = [
        row
        for row in discovered
        if _tournament_overlaps(
            row,
            low=(now - timedelta(days=2)).date(),
            high=(now + timedelta(days=4)).date(),
        )
    ][:max_tournaments]

    countries: Dict[str, str] = {}
    ambiguous: Set[str] = set()
    stats: Dict[str, Any] = {
        "status": "ok",
        "calendar_rows": len(discovered),
        "tournaments": len(active),
        "requests": 0,
        "http_errors": 0,
        "country_keys": 0,
        "rows_scanned": 0,
        "rows_updated": 0,
        "participant_sides_filled": 0,
    }

    for meta in active:
        group = meta.get("tournamentGroup") if isinstance(meta.get("tournamentGroup"), dict) else {}
        try:
            group_id = int(group.get("id"))
            year = int(meta.get("year"))
        except (TypeError, ValueError):
            continue
        result = fetch(f"{BASE}/tournaments/{group_id}/{year}/players")
        stats["requests"] += 1
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue
        _merge_country_index(
            countries,
            _player_country_map(getattr(result, "payload", None)),
            ambiguous,
        )
        if heartbeat:
            heartbeat()

    stats["country_keys"] = len(countries)
    repaired = _repair_visible_wta_countries(
        db,
        player_countries=countries,
        low=low,
        high=high,
    )
    stats.update(repaired)
    if stats["rows_updated"]:
        db.commit()
    return stats


def run_country_assets_if_due(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Optional[Dict[str, Any]]:
    global _country_asset_next_run_at
    now_mono = time.monotonic()
    if now_mono < _country_asset_next_run_at:
        return None
    _country_asset_next_run_at = now_mono + _COUNTRY_ASSET_INTERVAL_S
    return run_country_asset_repair(db, getter=getter, heartbeat=heartbeat)


def run_breadth_ingest(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    days_back: int = 1,
    days_forward: int = 4,
    max_tournaments: int = 48,
    max_ingest: int = 1800,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "tournaments": 0, "events": 0, "ingested": 0}

    repaired = _repair_legacy_wta_rows(db)
    db.commit()
    if heartbeat:
        heartbeat()

    fetch = getter or fetch_url
    now = datetime.utcnow()
    low = now - timedelta(days=days_back + 1)
    high = now + timedelta(days=days_forward + 1)
    low_day = (now - timedelta(days=days_back)).date()
    high_day = (now + timedelta(days=days_forward)).date()

    discovered = discover_current_tournaments(fetch, now=now)
    active = [row for row in discovered if _tournament_overlaps(row, low=low_day, high=high_day)]
    active.sort(key=lambda row: str(row.get("startDate") or ""))
    active = active[:max_tournaments]

    stats: Dict[str, Any] = {
        "status": "ok",
        "legacy_rows_repaired": repaired,
        "calendar_rows": len(discovered),
        "tournaments": len(active),
        "requests": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "http_errors": 0,
        "country_repair": {},
        "by_competition": {},
    }
    competitions: Set[str] = set()
    global_player_countries: Dict[str, str] = {}
    ambiguous_player_country_keys: Set[str] = set()

    for meta in active:
        group = meta.get("tournamentGroup") if isinstance(meta.get("tournamentGroup"), dict) else {}
        try:
            group_id = int(group.get("id"))
            year = int(meta.get("year"))
        except (TypeError, ValueError):
            continue

        competition_id, competition_name, native_id = _competition_identity(meta)
        mapping = _ensure_mapping(
            db,
            source=source,
            competition_id=competition_id,
            competition_name=competition_name,
            source_competition_id=native_id,
            meta=meta,
        )
        player_countries: Dict[str, str] = {}
        players_result = fetch(f"{BASE}/tournaments/{group_id}/{year}/players")
        stats["requests"] += 1
        if getattr(players_result, "ok", False):
            player_countries = _player_country_map(getattr(players_result, "payload", None))
            _merge_country_index(
                global_player_countries,
                player_countries,
                ambiguous_player_country_keys,
            )

        result = fetch(f"{BASE}/tournaments/{group_id}/{year}/matches")
        stats["requests"] += 1
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), dict):
            stats["http_errors"] += 1
            continue

        rows = [row for row in (result.payload.get("matches") or []) if isinstance(row, dict)]
        stats["events"] += len(rows)
        written = eligible = 0
        participant_country_hits = 0
        unresolved_players: List[str] = []
        for row in rows:
            event = match_to_event(
                row,
                competition_id,
                meta,
                player_countries=player_countries,
            )
            if not event:
                continue
            if not _event_in_window(event, low=low, high=high):
                continue
            for side_name in ("home", "away"):
                side = event.get(side_name) if isinstance(event.get(side_name), dict) else {}
                country_values = [side.get("country_id")]
                if isinstance(side.get("country_ids"), list):
                    country_values.extend(side.get("country_ids") or [])
                if any(value for value in country_values):
                    participant_country_hits += 1
                elif side.get("name") and len(unresolved_players) < 12:
                    unresolved_players.append(str(side.get("name")))
            event["sport"] = "tennis"
            event["competition"] = competition_name
            event["competition_key"] = competition_id
            event["source_competition_id"] = native_id
            event["source_competition_name"] = competition_name
            extra = dict(event.get("extra") or {})
            extra.update({
                "source_family": "wta-json",
                "source_competition_id": native_id,
                "source_competition_name": competition_name,
                "public_competition_key": competition_id,
                "wta_group_id": group_id,
                "wta_year": year,
            })
            event["extra"] = extra
            eligible += 1
            stats["eligible"] += 1
            if _ingest(db, event, mapping.source_id):
                written += 1
                stats["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                stats["status"] = "bounded"
                break

        competitions.add(competition_id)
        stats["by_competition"][competition_id] = {
            "upstream": len(rows),
            "eligible": eligible,
            "ingested": written,
            "player_country_keys": len(player_countries),
            "participant_country_hits": participant_country_hits,
            "unresolved_players": unresolved_players,
        }
        db.commit()
        if heartbeat:
            heartbeat()
        if stats["ingested"] >= max_ingest:
            break

    stats["competitions"] = len(competitions)
    stats["country_repair"] = _repair_visible_wta_countries(
        db,
        player_countries=global_player_countries,
        low=low,
        high=high,
    )
    if stats["country_repair"].get("rows_updated"):
        db.commit()
        if heartbeat:
            heartbeat()
    cache_clear(db, prefix="events:")
    job = _job(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = stats["status"]
    job.items_written = int(stats["ingested"])
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats


def run_if_due(
    db: Session,
    *,
    min_interval_minutes: int = 60,
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
    if (
        payload.get("state") == "done"
        and job.last_run_at
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
    ):
        return None
    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(db, getter=getter, heartbeat=heartbeat)
