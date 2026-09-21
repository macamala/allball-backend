"""Read-side provider over collected canonical rows. Never calls adapters."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from collector.cache import cache_get, cache_set
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
from collector.matrix_guard import frozen_competition_ids
from collector.util import isoformat, load_json
from sports_provider import (
    PROVIDER_NOT_CONNECTED,
    NormalizedEvent,
    TeamStandingRow,
)

LIVE_QUERY_STATUSES = ("live", "halftime", "break")
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
    return _public_value(payload)


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
        db = _session(self._session_factory)
        try:
            event_count = db.query(SportsEvent).count()
            source_count = db.query(SportsSource).filter_by(enabled=True).count()
            mapping_count = db.query(SportsSourceCompetition).filter_by(enabled=True).count()
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
        db = _session(self._session_factory)
        try:
            cache_key = f"events:p0v8:{sport}:{competition}:{status}:{date_from}:{date_to}:{int(allow_unfiltered)}"
            cached = cache_get(db, cache_key)
            if cached is not None:
                return cached
            query = db.query(SportsEvent)
            if sport:
                query = query.filter_by(sport_id=sport)
            if competition:
                query = query.filter_by(competition_id=competition)
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
            # Prefer the display_eligible column so dated queries can use
            # ix_sports_event_public_start. Only scan extra_json when the column is NULL.
            query = query.filter(
                or_(
                    SportsEvent.display_eligible.is_(True),
                    and_(
                        SportsEvent.display_eligible.is_(None),
                        or_(
                            SportsEvent.extra_json.is_(None),
                            ~SportsEvent.extra_json.like('%"display_eligible": false%'),
                        ),
                    ),
                )
            )
            query = query.order_by(SportsEvent.start_time.asc())
            unbounded = not date_from and not date_to
            if unbounded and not allow_unfiltered:
                query = query.limit(int(os.getenv("NINKO_EVENTS_UNFILTERED_LIMIT", "400")))
            rows = query.all()
            standing_ids = {
                item[0]
                for item in db.query(SportsStandingSnapshot.competition_id).distinct().all()
                if item[0]
            }
            events = [self._to_normalized(row, standing_ids=standing_ids) for row in rows]
            events = [row for row in events if row and is_display_eligible(row)]
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
                events = [public_event(row) for row in events]
            events = [row for row in events if is_frozen_public_competition(row)]
            cache_set(db, cache_key, events, "upcoming_fixtures" if status != "live" else "live_events")
            db.commit()
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
            payload = self._to_normalized(row, include_detail=True)
            if payload is None:
                return None
            extra = load_json(row.extra_json, {}) or {}
            try:
                from collector.detail_enrich import enrich_event_row

                enrich_event_row(db, row)
                extra = load_json(row.extra_json, {}) or {}
            except Exception:
                extra = load_json(row.extra_json, {}) or {}
            standing = (
                db.query(SportsStandingSnapshot.competition_id)
                .filter_by(competition_id=payload.get("competition_key"))
                .first()
            )
            payload["standings_available"] = bool(standing)
            for key in DETAIL_ONLY_KEYS:
                if extra.get(key) is not None and payload.get(key) is None:
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
            query = db.query(SportsStandingSnapshot)
            if competition_key:
                query = query.filter_by(competition_id=competition_key)
            row = query.order_by(SportsStandingSnapshot.captured_at.desc()).first()
            if row is None:
                return []
            return load_json(row.rows_json, []) or []
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
    ) -> NormalizedEvent:
        participants = load_json(row.participants_json, {}) or {}
        score = load_json(row.score_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
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
                for k, v in extra.items()
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
        payload["quality_flags"] = extra.get("quality_flags") or quality_flags_for_event(
            {**raw_sides, "sport": row.sport_id, "score": score}
        )
        if extra.get("display_eligible") is not None:
            payload["display_eligible"] = extra.get("display_eligible")
        else:
            payload["display_eligible"] = is_display_eligible(raw_sides)
        payload["observation_count"] = len(load_json(row.contributing_sources_json, []) or []) or 1
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
        corrected = correct_public_competition_id(
            stored_competition_id=row.competition_id,
            source_competition_name=extra.get("source_competition_name") or extra.get("competition"),
            sport_id=row.sport_id or "",
        )
        if corrected is None:
            return None
        payload["competition_key"] = corrected
        payload["competition"] = corrected
        payload = attach_competition_metadata(payload)
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
            payload["standings_available"] = payload.get("competition_key") in standing_ids
        if extra.get("provider_conflicts"):
            payload["conflicts"] = extra.get("provider_conflicts")
        if not include_detail:
            payload.pop("quality_flags", None)
        return payload
