"""Event matching / deduplication against the canonical store."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from collector.aliases import canonical_name_key
from collector.event_quality import HEAD_TO_HEAD, TEAM_MATCH, event_type_for
from collector.ids import bound_source_key
from collector.identity import mapped_ninko_id
from collector.models import SportsEvent
from collector.normalize import fingerprint
from collector.timezones import ResolvedTime, iso_utc, resolve_event_time, utc_naive_for_storage
from collector.util import load_json, parse_datetime, slugify

# Legacy wide window used only as a hard cap. Team identity uses TEAM_KICKOFF_TOLERANCE.
TIME_WINDOW = timedelta(hours=12)
TEAM_KICKOFF_TOLERANCE = timedelta(hours=3)


def _name_key(participant: Any) -> str:
    return canonical_name_key(participant)


def _participants(event: Dict[str, Any]) -> tuple[str, str]:
    home = _name_key(event.get("home") or event.get("participant_a"))
    away = _name_key(event.get("away") or event.get("participant_b"))
    return home, away


def _kickoff(event: Dict[str, Any]) -> Optional[Any]:
    resolved = event.get("_resolved_time")
    if isinstance(resolved, ResolvedTime) and resolved.utc is not None:
        return utc_naive_for_storage(resolved)
    iso = event.get("start_time")
    if iso:
        parsed = parse_datetime(iso)
        if parsed:
            return parsed
        resolved = resolve_event_time(
            iso,
            competition_id=str(event.get("competition_key") or ""),
            country_id=str(event.get("country_id") or ""),
            provider=str(event.get("source_family") or ""),
            source_timezone=event.get("source_timezone") or event.get("timezone"),
        )
        return utc_naive_for_storage(resolved)
    return None


def rounds_conflict(left: Any, right: Any) -> bool:
    a = str(left or "").strip().lower()
    b = str(right or "").strip().lower()
    if not a or not b:
        return False
    return a != b


def seasons_match(left: Any, right: Any) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return True
    return a == b


def kickoffs_compatible(left: Optional[Any], right: Optional[Any], *, kind: str) -> bool:
    if left is None or right is None:
        return True
    delta = abs((left - right).total_seconds())
    if kind in {TEAM_MATCH, HEAD_TO_HEAD}:
        return delta <= TEAM_KICKOFF_TOLERANCE.total_seconds()
    return delta <= TIME_WINDOW.total_seconds()


def same_canonical_event(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    if str(left.get("sport") or "") != str(right.get("sport") or ""):
        return False
    if str(left.get("competition_key") or "") != str(right.get("competition_key") or ""):
        return False
    if not seasons_match(left.get("season"), right.get("season")):
        return False
    lh, la = _participants(left)
    rh, ra = _participants(right)
    if not lh:
        return False
    if {lh, la} != {rh, ra}:
        from collector.participant_alias import participants_equivalent

        def _raw(event: Dict[str, Any], side: str) -> str:
            value = event.get(side) or event.get("participant_a" if side == "home" else "participant_b") or {}
            if isinstance(value, dict):
                return str(value.get("name") or "")
            return str(value or "")

        if not participants_equivalent(
            _raw(left, "home"),
            _raw(left, "away"),
            _raw(right, "home"),
            _raw(right, "away"),
        ):
            return False
    left_round = left.get("round") or left.get("stage")
    right_round = right.get("round") or right.get("stage")
    if rounds_conflict(left_round, right_round):
        return False
    kind = event_type_for(str(left.get("competition_key") or ""), str(left.get("sport") or ""))
    return kickoffs_compatible(_kickoff(left), _kickoff(right), kind=kind)


def _register_event(db: Session, row: SportsEvent) -> None:
    if row is None:
        return
    db.info.setdefault("events_by_id", {})[row.event_id] = row
    if row.fingerprint:
        db.info.setdefault("events_by_fp", {})[row.fingerprint] = row
    if row.competition_id:
        db.info.setdefault("events_by_comp", {}).setdefault(row.competition_id, []).append(row)


def _stored_pair(row: SportsEvent) -> set[str]:
    parts = load_json(row.participants_json, {}) or {}
    return {
        _name_key(parts.get("home") or parts.get("participant_a")),
        _name_key(parts.get("away") or parts.get("participant_b")),
    }


def _incoming_pair(event: Dict[str, Any]) -> set[str]:
    home, away = _participants(event)
    return {home, away}


def match_event(
    db: Session,
    event: Dict[str, Any],
    *,
    source_id: str,
) -> Optional[SportsEvent]:
    source_event_id = event.get("source_event_id")
    if source_event_id:
        ninko_id = mapped_ninko_id(db, "event", source_id, source_event_id)
        if ninko_id:
            row = db.info.get("events_by_id", {}).get(ninko_id)
            if row is None:
                row = db.get(SportsEvent, ninko_id) or db.query(SportsEvent).filter_by(event_id=ninko_id).first()
            if row:
                stored = _stored_pair(row)
                incoming = _incoming_pair(event)
                if not incoming - {""} or stored == incoming:
                    _register_event(db, row)
                    return row
        key = bound_source_key(source_id, str(source_event_id))
        competition_id = event.get("competition_key")
        if competition_id:
            cached = db.info.get("events_by_comp", {}).get(competition_id)
            cross = cached if cached is not None else db.query(SportsEvent).filter(SportsEvent.competition_id == competition_id).all()
            if cached is None:
                db.info.setdefault("events_by_comp", {})[competition_id] = list(cross)
            for row in cross:
                extra = load_json(row.extra_json, {}) or {}
                from collector.source_ids import as_family_map

                ids = as_family_map(extra.get("source_event_ids"))
                values = set(ids.values())
                if str(source_event_id) in values or key in values or extra.get("source_event_id") == source_event_id:
                    if _stored_pair(row) == _incoming_pair(event):
                        _register_event(db, row)
                        return row
    mark = fingerprint(event)
    exact = db.info.get("events_by_fp", {}).get(mark)
    if exact is None:
        exact = db.query(SportsEvent).filter_by(fingerprint=mark).first()
        if exact:
            _register_event(db, exact)
    if exact:
        return exact
    home, away = _participants(event)
    if not home:
        return None
    competition_id = event.get("competition_key")
    if not competition_id:
        return None
    kind = event_type_for(str(competition_id), str(event.get("sport") or ""))
    start = _kickoff(event)
    cached = db.info.get("events_by_comp", {}).get(competition_id)
    candidates = cached if cached is not None else db.query(SportsEvent).filter_by(competition_id=competition_id).all()
    if cached is None:
        db.info.setdefault("events_by_comp", {})[competition_id] = list(candidates)
    for row in candidates:
        parts = load_json(row.participants_json, {}) or {}
        incoming = {
            "sport": event.get("sport") or row.sport_id,
            "competition_key": competition_id,
            "season": event.get("season") or row.season,
            "home": event.get("home") or parts.get("home"),
            "away": event.get("away") or parts.get("away"),
            "round": event.get("round"),
            "stage": event.get("stage"),
            "start_time": event.get("start_time"),
            "source_family": event.get("source_family"),
            "country_id": event.get("country_id"),
            "_resolved_time": event.get("_resolved_time"),
        }
        stored = {
            "sport": row.sport_id,
            "competition_key": row.competition_id,
            "season": row.season,
            "home": parts.get("home") or parts.get("participant_a"),
            "away": parts.get("away") or parts.get("participant_b"),
            "round": row.stage,
            "stage": row.stage,
            "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        }
        extra = load_json(row.extra_json, {}) or {}
        incoming_sid = str(event.get("source_event_id") or "")
        incoming_family = str(event.get("source_family") or "")
        from collector.source_ids import as_family_map

        stored_for_family = str(as_family_map(extra.get("source_event_ids")).get(incoming_family) or "")
        if incoming_sid and stored_for_family and incoming_sid != stored_for_family:
            continue
        if same_canonical_event(incoming, stored):
            return row
        row_home = _name_key(parts.get("home") or parts.get("participant_a"))
        row_away = _name_key(parts.get("away") or parts.get("participant_b"))
        if event.get("venue") and row.venue and start is not None and row.start_time is not None:
            if kind == HEAD_TO_HEAD:
                continue
            delta = abs((row.start_time - start).total_seconds())
            if slugify(event.get("venue")) == slugify(row.venue) and delta <= 3600:
                if home and away and {home, away} == {row_home, row_away}:
                    if not rounds_conflict(event.get("round") or event.get("stage"), row.stage):
                        return row
    return None
