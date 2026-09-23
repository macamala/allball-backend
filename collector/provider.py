"""Read-side provider over collected canonical rows. Never calls adapters."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, load_only

from collector.cache import cache_get, cache_set, list_cache_key
from collector.models import (
    SportsCompetition,
    SportsEvent,
    SportsEventDetail,
    SportsSource,
    SportsSourceCompetition,
    SportsStandingSnapshot,
)
from collector.live_state import parse_ts, public_live_visible, reconcile_live_status
from collector.display import sanitize_side
from collector.enrichment import DETAIL_ONLY_KEYS, is_display_eligible, quality_flags_for_event
from collector.competition_identity import correct_public_competition_id
from collector.competition_presentation import attach_competition_metadata
from collector.list_extra import extra_for_list
from collector.matrix_guard import frozen_competition_ids
from collector.util import isoformat, load_json
from sports_provider import (
    PROVIDER_NOT_CONNECTED,
    NormalizedEvent,
    TeamStandingRow,
)

LIVE_QUERY_STATUSES = ("live", "halftime", "break")
LIST_EXTRA_KEYS = (
    "periods",
    "winner",
    "runners",
    "round",
    "live_class",
    "start_precision",
    "start_date",
    "best_of",
    "maps",
    "race_number",
    "tournament",
    "tournament_name",
    "current_set",
    "result_type",
    "walkover",
    "stage",
)
HEADER_KEYS = (
    "id",
    "sport",
    "competition",
    "competition_key",
    "event_family",
    "home",
    "away",
    "participant_a",
    "participant_b",
    "start_time",
    "status",
    "score",
    "venue",
    "live",
    "round",
    "stage",
    "series_id",
    "session_type",
    "winner",
    "country_id",
    "season",
    "start_date",
    "start_precision",
    "race_number",
    "game_id",
    "tournament",
    "tournament_id",
    "tournament_name",
    "surface",
    "category",
    "race_name",
    "periods",
    "best_of",
    "attendance",
    "referee",
    "live_class",
    "geography_label",
    "scope_type",
    "competition_name",
    "country_based",
    "standings_available",
)


LIST_LOAD_COLUMNS = (
    SportsEvent.event_id,
    SportsEvent.sport_id,
    SportsEvent.competition_id,
    SportsEvent.event_family,
    SportsEvent.status,
    SportsEvent.start_time,
    SportsEvent.season,
    SportsEvent.venue,
    SportsEvent.score_json,
    SportsEvent.participants_json,
    SportsEvent.list_extra_json,
    SportsEvent.series_id,
    SportsEvent.session_type,
    SportsEvent.game_id,
    SportsEvent.country_id,
    SportsEvent.meeting_id,
    SportsEvent.display_eligible,
    SportsEvent.canonical_event_id,
    SportsEvent.live,
    SportsEvent.retrieved_at,
    SportsEvent.stage,
    SportsEvent.updated_at,
)

_STATUS_CACHE: Dict[str, Any] = {"at": 0.0, "payload": None}
_STATUS_TTL_S = 20.0

INTERNAL_EVENT_KEYS = {
    "field_sources",
    "source_event_ids",
    "source_kickoffs",
    "source_competition_name",
    "source_competition_id",
    "canonical_competition_id",
    "resolution_method",
    "resolution_confidence",
    "quarantine_disposition",
    "source_family",
    "source_fetch_time",
    "last_contact_at",
    "source_status",
    "source_timezone",
    "source_local_datetime",
    "source_event_updated_at",
    "obs_signature",
    "observed_at",
    "canonical_last_observed_at",
    "status_reconciliation",
    "timezone_resolution_method",
    "contributing_sources",
    "primary_source_id",
    "source_url",
    "provenance",
    "attribution",
    "collector",
    "provider_conflicts",
    "field_freshness",
    "source_family",
    "source_status",
    "source_fetch_time",
    "last_contact_at",
    "canonical_last_observed_at",
    "observed_at",
    "source_event_updated_at",
    "status_inferred",
    "quality_flags",
    "detail_fetched_at",
    "bbc_cricket_checked_at",
    "rich_id_checked_at",
    "letour_rank_rev",
    "closure_id_rev",
    "fis_rev",
    "eurohockey_rev",
    "wec_prologue_rev",
    "fia_class_rev",
    "leaguepedia_rev",
    "leaguepedia_checked_at",
    "detail_empty",
    "detail_negative",
    "detail_families_tried",
    "source_event_id",
}

NESTED_SOURCE_ID_KEYS = {
    "source_event_id",
    "source_event_ids",
    "player_id",
    "team_id",
    "goalGetterID",
    "provenance",
}


def _public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _public_value(item)
            for key, item in value.items()
            if key not in INTERNAL_EVENT_KEYS
            and key not in NESTED_SOURCE_ID_KEYS
            and key not in {"provider", "provider_id"}
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def public_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = _public_value(payload)
    detail = cleaned.get("sport_detail") if isinstance(cleaned.get("sport_detail"), dict) else None
    if isinstance(detail, dict):
        detail.pop("series_id", None)
        games = detail.get("games")
        if isinstance(games, list):
            for game in games:
                if not isinstance(game, dict):
                    continue
                game.pop("id", None)
                for side in ("blue", "red"):
                    if isinstance(game.get(side), dict):
                        game[side].pop("id", None)
        if not detail:
            cleaned.pop("sport_detail", None)
    return cleaned


LIST_PUBLIC_KEYS = (
    "id",
    "sport",
    "competition",
    "competition_key",
    "competition_name",
    "event_family",
    "home",
    "away",
    "participant_a",
    "participant_b",
    "start_time",
    "status",
    "score",
    "live",
    "live_class",
    "periods",
    "start_precision",
    "start_date",
    "updated_at",
    "current_set",
    "geography_label",
    "scope_type",
    "country_id",
    "country_based",
    "standings_available",
    "venue",
    "series_id",
    "session_type",
    "stage",
    "walkover",
    "result_type",
    "maps",
    "round",
    "winner",
    "runners",
    "race_number",
    "best_of",
)


def _compact_mapping(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out: Dict[str, Any] = {}
    for key, item in value.items():
        if key in INTERNAL_EVENT_KEYS or key in NESTED_SOURCE_ID_KEYS:
            continue
        if item in (None, "", [], {}):
            continue
        out[key] = item
    return out


def _list_public_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    out: Dict[str, Any] = {}
    for key in LIST_PUBLIC_KEYS:
        if key == "score":
            continue
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        if key in {"home", "away", "participant_a", "participant_b"}:
            out[key] = _compact_mapping(value)
        else:
            out[key] = value
    lean_score = {
        key: value
        for key, value in score.items()
        if value is not None and key not in INTERNAL_EVENT_KEYS and key not in NESTED_SOURCE_ID_KEYS and key not in {"home", "away"}
    }
    lean_score["home"] = score.get("home")
    lean_score["away"] = score.get("away")
    out["score"] = lean_score
    return out


def public_event_detail(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Same public sanitizer as the list. Provenance stays internal."""
    return public_event(payload)


def is_frozen_public_competition(event: Dict[str, Any]) -> bool:
    cid = str(event.get("competition_key") or event.get("competition") or "")
    return bool(cid) and cid in frozen_competition_ids()


LIVE_PUBLIC_KEYS = (
    "id",
    "sport",
    "competition",
    "competition_key",
    "event_family",
    "home",
    "away",
    "participant_a",
    "participant_b",
    "start_time",
    "status",
    "score",
    "live",
    "live_class",
    "periods",
    "start_precision",
    "updated_at",
    "last_contact_at",
    "source_fetch_time",
    "canonical_updated_at",
    "current_set",
    "competition_key",
    "geography_label",
    "scope_type",
    "country_id",
    "competition",
)


def live_public_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    lean_score = {
        key: score.get(key)
        for key in ("home", "away", "minute", "clock", "period", "quarter", "set", "inning", "inning_half", "outs", "overs", "wickets", "runs")
        if score.get(key) is not None
    }
    row = {key: payload.get(key) for key in LIVE_PUBLIC_KEYS if payload.get(key) is not None}
    row["score"] = lean_score
    if payload.get("periods"):
        row["periods"] = payload.get("periods")
    return row

CORE_ROW_KEYS = {
    "id",
    "sport",
    "competition",
    "competition_key",
    "season",
    "event_family",
    "home",
    "away",
    "participant_a",
    "participant_b",
    "start_time",
    "status",
    "score",
    "venue",
    "provider",
    "provider_id",
    "updated_at",
    "series_id",
    "session_type",
    "game_id",
    "country_id",
    "meeting_id",
    "stage",
    "live",
}


def _session(factory) -> Session:
    return factory()


def _parse_bound(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            if len(str(value)) >= 10:
                return datetime.strptime(str(value)[:10], "%Y-%m-%d")
            return None
    if stamp.tzinfo is not None:
        stamp = stamp.replace(tzinfo=None)
    return stamp


def _start_within_to(start_time: Optional[str], date_to: str) -> bool:
    start = start_time or ""
    if not start:
        return False
    if "T" in date_to:
        return start <= date_to
    return start[:10] <= date_to[:10]


class NinkoCollectedSportsDataProvider:
    """Serves stored NinkoSports events. Empty store stays honestly disconnected."""

    def __init__(self, session_factory=None):
        if session_factory is None:
            from database import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def status(self) -> Dict[str, Any]:
        now = time.monotonic()
        cached = _STATUS_CACHE.get("payload")
        if cached is not None and now - float(_STATUS_CACHE.get("at") or 0) < _STATUS_TTL_S:
            return cached
        db = _session(self._session_factory)
        try:
            event_count = db.query(SportsEvent.event_id).count()
            source_count = db.query(SportsSource.source_id).filter_by(enabled=True).count()
            mapping_count = db.query(SportsSourceCompetition.competition_id).filter_by(enabled=True).count()
            connected = event_count > 0
            payload = {
                "connected": connected,
                "provider": None,
                "providers": [],
                "public_attribution_required": False,
                "message": (
                    PROVIDER_NOT_CONNECTED
                    if not connected
                    else "Live sports data is served from the NinkoSports collector."
                ),
                "collector": {
                    "enabled_sources": source_count,
                    "source_mappings": mapping_count,
                    "events": event_count,
                },
                "attribution": [],
            }
            _STATUS_CACHE["at"] = now
            _STATUS_CACHE["payload"] = payload
            return payload
        finally:
            db.close()

    def get_sports(self) -> List[Dict[str, Any]]:
        return []

    def get_competitions(self, sport: Optional[str] = None) -> List[Dict[str, Any]]:
        db = _session(self._session_factory)
        try:
            covered = (
                db.query(SportsEvent.competition_id)
                .distinct()
            )
            ids = {row[0] for row in covered.all()}
            if not ids:
                return []
            query = db.query(SportsCompetition).filter(SportsCompetition.competition_id.in_(ids))
            if sport:
                query = query.filter_by(sport_id=sport)
            rows = []
            for item in query.all():
                rows.append(
                    {
                        "key": item.competition_id,
                        "slug": item.slug,
                        "label": item.name,
                        "name": item.name,
                        "sport": item.sport_id,
                        "country_id": item.country_id,
                        "series_id": item.series_id,
                        "game_id": item.game_id,
                        "path": item.slug,
                    }
                )
            return rows
        finally:
            db.close()

    def get_events(
        self,
        sport: Optional[str] = None,
        competition: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        allow_unfiltered: bool = False,
    ) -> List[NormalizedEvent]:
        started = time.perf_counter()
        db = _session(self._session_factory)
        session_ms = round((time.perf_counter() - started) * 1000, 1)
        try:
            cache_key = list_cache_key(sport, competition, status, date_from, date_to, allow_unfiltered)
            cached = cache_get(db, cache_key)
            if cached is not None:
                self._last_profile = {
                    "cache": "hit",
                    "session_ms": session_ms,
                    "db_ms": round((time.perf_counter() - started) * 1000, 1),
                    "standings_ms": 0.0,
                    "taxonomy_ms": 0.0,
                    "serialize_ms": 0.0,
                    "total_ms": round((time.perf_counter() - started) * 1000, 1),
                    "rows": len(cached) if isinstance(cached, list) else 0,
                    "events": len(cached) if isinstance(cached, list) else 0,
                }
                return cached
            from collector.competition_identity import OFFICIAL_PUBLIC_COMPETITIONS

            frozen = frozen_competition_ids()
            public_ids = frozen | OFFICIAL_PUBLIC_COMPETITIONS
            query = db.query(SportsEvent).options(load_only(*LIST_LOAD_COLUMNS))
            if sport:
                query = query.filter_by(sport_id=sport)
            if competition:
                query = query.filter_by(competition_id=competition)
            else:
                query = query.filter(SportsEvent.competition_id.in_(public_ids))
            if status == "live":
                query = query.filter(SportsEvent.status.in_(LIVE_QUERY_STATUSES))
            elif status:
                query = query.filter_by(status=status)
            start_from = _parse_bound(date_from)
            start_to = _parse_bound(date_to)
            if start_from is not None:
                query = query.filter(SportsEvent.start_time >= start_from)
            if start_to is not None:
                query = query.filter(SportsEvent.start_time <= start_to)
            query = query.filter(SportsEvent.canonical_event_id.is_(None))
            query = query.filter(
                or_(
                    SportsEvent.display_eligible.is_(True),
                    SportsEvent.display_eligible.is_(None),
                )
            )
            unbounded = not date_from and not date_to
            db_start = time.perf_counter()
            if unbounded and not allow_unfiltered:
                query = query.order_by(SportsEvent.start_time.desc())
                query = query.limit(int(os.getenv("NINKO_EVENTS_UNFILTERED_LIMIT", "400")))
                rows = list(reversed(query.all()))
            else:
                query = query.order_by(SportsEvent.start_time.asc())
                rows = query.all()
            db_done = time.perf_counter()
            standings_start = time.perf_counter()
            standing_ids = {
                item[0]
                for item in db.query(SportsStandingSnapshot.competition_id).distinct().all()
                if item[0]
            }
            standings_done = time.perf_counter()
            taxonomy_start = time.perf_counter()
            warmed = set()
            for row in rows:
                key = (row.competition_id, row.sport_id or "")
                if key not in warmed:
                    attach_competition_metadata({"competition_key": key[0], "sport": key[1]})
                    warmed.add(key)
            taxonomy_done = time.perf_counter()
            serialize_start = time.perf_counter()
            events = [self._to_normalized(row, standing_ids=standing_ids, list_mode=True) for row in rows]
            events = [row for row in events if row]
            if date_from:
                events = [row for row in events if (row.get("start_time") or "") >= date_from]
            if date_to:
                events = [
                    row
                    for row in events
                    if _start_within_to(row.get("start_time"), date_to)
                ]
            if status == "live":
                events = [
                    live_public_event(row)
                    for row in events
                    if public_live_visible(row) and row.get("live_class") == "CONFIRMED_LIVE"
                ]
            else:
                events = [_list_public_event(row) for row in events]
            serialize_done = time.perf_counter()
            events = [row for row in events if (row.get("competition_key") or "") in public_ids]
            cache_set(db, cache_key, events, "upcoming_fixtures" if status != "live" else "live_events")
            db.commit()
            self._last_profile = {
                "cache": "miss",
                "session_ms": session_ms,
                "db_ms": round((db_done - db_start) * 1000, 1),
                "standings_ms": round((standings_done - standings_start) * 1000, 1),
                "taxonomy_ms": round((taxonomy_done - taxonomy_start) * 1000, 1),
                "serialize_ms": round((serialize_done - serialize_start) * 1000, 1),
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "rows": len(rows),
                "events": len(events),
            }
            return events
        finally:
            db.close()

    def get_status_delta(self, since: Optional[str] = None, sport: Optional[str] = None) -> List[Dict[str, Any]]:
        db = _session(self._session_factory)
        try:
            bound = _parse_bound(since)
            if bound is None:
                bound = datetime.utcnow() - timedelta(minutes=2)
            query = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None))
            query = query.filter(SportsEvent.updated_at >= bound)
            if sport:
                query = query.filter_by(sport_id=sport)
            rows = query.order_by(SportsEvent.updated_at.asc()).limit(400).all()
            out = []
            for row in rows:
                extra = load_json(row.extra_json, {}) or {}
                out.append(
                    {
                        "id": row.event_id,
                        "sport": row.sport_id,
                        "competition": row.competition_id,
                        "status": row.status,
                        "live_class": extra.get("live_class"),
                        "score": load_json(row.score_json, {}) or {},
                        "updated_at": isoformat(row.updated_at),
                    }
                )
            return out
        finally:
            db.close()

    def get_live_events(self) -> List[NormalizedEvent]:
        return self.get_events(status="live")

    def get_event(self, event_id: str) -> Optional[NormalizedEvent]:
        db = _session(self._session_factory)
        try:
            row = db.query(SportsEvent).filter_by(event_id=event_id).first()
            if row is None:
                return None
            if row.canonical_event_id:
                keeper = db.query(SportsEvent).filter_by(event_id=row.canonical_event_id).first()
                if keeper:
                    row = keeper
            try:
                from collector.detail_enrich import enrich_event_row

                enrich_event_row(db, row)
                db.commit()
                db.refresh(row)
            except Exception:
                db.rollback()
            payload = self._to_normalized(row, include_detail=True)
            if payload is None:
                return None
            extra = load_json(row.extra_json, {}) or {}
            from collector.standings_enrich import standings_supported

            standing = (
                db.query(SportsStandingSnapshot.competition_id)
                .filter_by(competition_id=payload.get("competition_key"))
                .first()
            )
            payload["standings_available"] = bool(standing) or standings_supported(payload.get("competition_key"))
            for key in DETAIL_ONLY_KEYS:
                if extra.get(key) is not None and payload.get(key) is None:
                    payload[key] = extra[key]
            for key in ("venue", "referee", "attendance"):
                if extra.get(key) and not payload.get(key):
                    payload[key] = extra[key]
            detail = db.query(SportsEventDetail).filter_by(event_id=row.event_id).first()
            if detail is None or not (
                load_json(detail.incidents_json)
                or load_json(detail.lineups_json)
                or load_json(detail.statistics_json)
            ):
                for oid in extra.get("collapsed_from") or []:
                    other = db.query(SportsEventDetail).filter_by(event_id=oid).first()
                    if other:
                        detail = other
                        break
            if detail:
                lineups = load_json(detail.lineups_json)
                statistics = load_json(detail.statistics_json)
                incidents = load_json(detail.incidents_json)
                if lineups:
                    payload["lineups"] = lineups
                if statistics:
                    payload["statistics"] = statistics
                if incidents:
                    payload["incidents"] = incidents
                payload["availability"] = load_json(detail.availability_json, []) or []
            from collector.canonical_detail import attach_canonical_detail

            payload = attach_canonical_detail(payload)
            return public_event_detail(payload)
        finally:
            db.close()

    def get_standings(self, competition_key: Optional[str] = None) -> List[TeamStandingRow]:
        db = _session(self._session_factory)
        try:
            from collector.standings_enrich import load_standings

            return load_standings(db, competition_key)
        finally:
            db.close()

    def get_team_form(self, team_id: str) -> Optional[Dict[str, Any]]:
        return None

    def get_statistics(self, event_id: str) -> Optional[Dict[str, Any]]:
        event = self.get_event(event_id)
        if not event:
            return None
        return event.get("statistics")

    def get_availability(self, event_id: str) -> List[Dict[str, Any]]:
        event = self.get_event(event_id)
        if not event:
            return []
        return event.get("availability") or []

    def event_header(self, event: NormalizedEvent) -> Dict[str, Any]:
        return {key: event.get(key) for key in HEADER_KEYS if event.get(key) is not None}

    def _to_normalized(
        self,
        row: SportsEvent,
        include_detail: bool = False,
        standing_ids: Optional[set] = None,
        list_mode: bool = False,
    ) -> NormalizedEvent:
        participants = load_json(row.participants_json, {}) or {}
        score = load_json(row.score_json, {}) or {}
        extra = extra_for_list(row) if not include_detail else (load_json(row.extra_json, {}) or {})
        extra_for_payload = extra if include_detail else extra
        raw_sides = {
            "home": participants.get("home") or {},
            "away": participants.get("away") or {},
            "participant_a": participants.get("participant_a") or {},
            "participant_b": participants.get("participant_b") or {},
        }
        payload = {
            "id": row.event_id,
            "sport": row.sport_id,
            "competition": row.competition_id,
            "competition_key": row.competition_id,
            "season": row.season,
            "event_family": row.event_family,
            "home": raw_sides["home"],
            "away": raw_sides["away"],
            "participant_a": raw_sides["participant_a"],
            "participant_b": raw_sides["participant_b"],
            "start_time": isoformat(row.start_time),
            "status": row.status,
            "score": score,
            "venue": row.venue,
            "provider": None,
            "provider_id": None,
            "updated_at": isoformat(row.updated_at),
            "series_id": row.series_id,
            "session_type": row.session_type,
            "game_id": row.game_id,
            "country_id": row.country_id,
            "meeting_id": row.meeting_id,
            "stage": row.stage,
            "live": bool(row.live),
            **{
                k: v
                for k, v in extra_for_payload.items()
                if k not in INTERNAL_EVENT_KEYS
                and k not in CORE_ROW_KEYS
                and (include_detail or k not in DETAIL_ONLY_KEYS)
            },
        }
        if payload.get("live"):
            score = dict(payload.get("score") or {})
            clock = score.get("clock")
            stamp = parse_ts(extra.get("last_contact_at") or extra.get("source_fetch_time")) or row.retrieved_at or row.updated_at
            if stamp is not None and getattr(stamp, "tzinfo", None) is not None:
                stamp = stamp.replace(tzinfo=None)
            if clock and stamp:
                age = (datetime.utcnow() - stamp).total_seconds()
                if age > 180:
                    score["clock"] = None
                    score["clock_stale"] = True
                    payload["score"] = score
        payload["quality_flags"] = extra.get("quality_flags") if include_detail else None
        if include_detail and payload["quality_flags"] is None:
            payload["quality_flags"] = quality_flags_for_event({**raw_sides, "sport": row.sport_id, "score": score})
        if list_mode:
            payload["display_eligible"] = True if row.display_eligible is None else bool(row.display_eligible)
        elif extra.get("display_eligible") is not None:
            payload["display_eligible"] = extra.get("display_eligible")
        else:
            payload["display_eligible"] = is_display_eligible(raw_sides)
        if include_detail:
            payload["observation_count"] = len(load_json(row.contributing_sources_json, []) or []) or 1
        else:
            payload["observation_count"] = 1
        payload["source_fetch_time"] = extra.get("source_fetch_time") or extra.get("last_contact_at") or isoformat(row.retrieved_at)
        payload["last_contact_at"] = extra.get("last_contact_at") or payload["source_fetch_time"]
        payload["canonical_updated_at"] = extra.get("canonical_updated_at") or isoformat(row.updated_at)
        payload["source_event_updated_at"] = extra.get("source_event_updated_at")
        payload["observed_at"] = extra.get("observed_at")
        payload["canonical_last_observed_at"] = extra.get("canonical_last_observed_at")
        payload["source_status"] = extra.get("source_status") or row.status
        payload["status_inferred"] = extra.get("status_inferred")
        payload["source_family"] = extra.get("source_family") or payload.get("source_family")
        payload["incidents"] = extra.get("incidents") or payload.get("incidents")
        payload["periods"] = extra.get("periods") or payload.get("periods")
        payload = reconcile_live_status(payload)
        if list_mode:
            from collector.competition_identity import OFFICIAL_PUBLIC_COMPETITIONS

            allowed = frozen_competition_ids() | OFFICIAL_PUBLIC_COMPETITIONS
            corrected = row.competition_id if row.competition_id in allowed else None
        else:
            corrected = correct_public_competition_id(
                stored_competition_id=row.competition_id,
                source_competition_name=extra.get("source_competition_name") or extra.get("competition"),
                sport_id=row.sport_id or "",
                source_family=str(extra.get("source_family") or ""),
            )
        if corrected is None:
            return None
        payload["competition_key"] = corrected
        payload["competition"] = corrected
        payload = attach_competition_metadata(payload)
        source_name = str(extra.get("source_competition_name") or extra.get("competition") or "").strip()
        if corrected == "fifa-connected-competitions" and "world cup" in source_name.lower():
            payload["competition"] = source_name
            payload["competition_name"] = source_name
        country = payload.get("country_id")
        payload["home"] = sanitize_side(raw_sides["home"], sport=row.sport_id, competition_country=country)
        payload["away"] = sanitize_side(raw_sides["away"], sport=row.sport_id, competition_country=country)
        payload["participant_a"] = sanitize_side(
            raw_sides["participant_a"], sport=row.sport_id, competition_country=country
        )
        payload["participant_b"] = sanitize_side(
            raw_sides["participant_b"], sport=row.sport_id, competition_country=country
        )
        if standing_ids is not None:
            from collector.standings_enrich import standings_supported

            payload["standings_available"] = payload.get("competition_key") in standing_ids or standings_supported(
                payload.get("competition_key")
            )
        if extra.get("provider_conflicts"):
            payload["conflicts"] = extra.get("provider_conflicts")
        if not include_detail:
            payload.pop("quality_flags", None)
        return payload
