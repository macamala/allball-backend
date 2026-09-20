"""Merge incoming normalized events into canonical rows.

Volatile live fields follow observation freshness and event progression.
Provider priority is only a tie-breaker. Blank fields may be filled by any
source. Field-level provenance is stored on the merged dict.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from collector.live_state import (
    AUTHORITATIVE_END,
    STATUS_RANK,
    canonical_status,
    is_live,
    observation_time,
    reconcile_live_status,
)
from collector.enrichment import EXTRA_PERSIST_KEYS
from collector.util import dump_json, load_json, parse_datetime

VOLATILE_SCORE_KEYS = (
    "home",
    "away",
    "period",
    "minute",
    "clock",
    "set",
    "quarter",
    "hits",
    "errors",
    "runs",
    "wickets",
    "overs",
    "inning",
    "inning_half",
    "outs",
)


def _filled(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if value == {}:
        return False
    if value == []:
        return False
    return True


def _ts(value: Any) -> datetime:
    parsed = parse_datetime(value) if not isinstance(value, datetime) else value
    return parsed or datetime.min


def _obs_ts(row: Dict[str, Any]) -> datetime:
    observed = observation_time(row)
    if observed is None:
        return datetime.min
    return observed.replace(tzinfo=None) if observed.tzinfo else observed


def _prefer(current: Any, incoming: Any, incoming_wins: bool) -> Any:
    if incoming_wins and _filled(incoming):
        return incoming
    if _filled(current):
        return current
    return incoming if _filled(incoming) else current


def contributing_sources(current_json: Optional[str], source_id: str) -> List[str]:
    values = load_json(current_json, []) or []
    if source_id not in values:
        values.append(source_id)
    return values


def _score_progress(score: Dict[str, Any]) -> int:
    try:
        home = int(score.get("home") or 0)
        away = int(score.get("away") or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, home) + max(0, away)


def volatile_incoming_wins(
    current: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    incoming_is_higher_priority: bool,
) -> bool:
    """Choose the better live/result observation.

    Order: identity is assumed already matched. Then freshness, progression,
    status confidence, then provider priority.
    """
    current_ts = _obs_ts(current)
    incoming_ts = _obs_ts(incoming)
    cur_status = canonical_status(current.get("status") or "")
    inc_status = canonical_status(incoming.get("status") or "")
    cur_score = current.get("score") or {}
    inc_score = incoming.get("score") or {}

    if inc_status in AUTHORITATIVE_END and is_live(cur_status):
        if incoming_ts < current_ts and incoming_ts != datetime.min and current_ts != datetime.min:
            return False
        return True
    if is_live(inc_status) and cur_status in AUTHORITATIVE_END:
        if incoming_ts > current_ts and incoming_ts != datetime.min:
            return True
        return False
    if inc_status == "finished" and cur_status == "finished" and incoming_ts < current_ts:
        return False

    if incoming_ts > current_ts and incoming_ts != datetime.min and (
        _filled(inc_score.get("home")) or _filled(inc_score.get("away")) or inc_status in {"live", "finished"}
    ):
        return True
    if incoming_ts < current_ts and incoming_ts != datetime.min:
        if inc_status == "finished" and cur_status in {"", "scheduled", "live"} and incoming_ts == datetime.min:
            return False
        if incoming_ts < current_ts:
            return False

    if STATUS_RANK.get(inc_status, 0) > STATUS_RANK.get(cur_status, 0):
        return True
    if STATUS_RANK.get(inc_status, 0) < STATUS_RANK.get(cur_status, 0):
        return False
    if _score_progress(inc_score) > _score_progress(cur_score) and inc_status == cur_status == "live":
        return True
    if _score_progress(inc_score) < _score_progress(cur_score) and inc_status == cur_status == "live":
        return False
    return incoming_is_higher_priority and (
        _filled(inc_score.get("home")) or _filled(inc_score.get("away")) or inc_status != cur_status
    )


def merge_event_fields(
    current: Dict[str, Any],
    incoming: Dict[str, Any],
    *,
    incoming_is_higher_priority: bool,
    incoming_source_id: str = "",
) -> Dict[str, Any]:
    out = dict(current)
    provenance = dict(current.get("field_sources") or {})
    current_ts = _obs_ts(current)
    incoming_ts = _obs_ts(incoming)
    live_wins = volatile_incoming_wins(
        current, incoming, incoming_is_higher_priority=incoming_is_higher_priority
    )
    freshness = dict(current.get("field_freshness") or {})
    stamp = incoming.get("source_fetch_time") or incoming.get("observed_at") or incoming.get("fetch_completed_at")

    if live_wins and _filled(incoming.get("status")):
        out["status"] = canonical_status(incoming.get("status") or current.get("status"))
        if incoming_source_id:
            provenance["status"] = incoming_source_id
            freshness["status"] = {"source": incoming_source_id, "at": stamp}
    cur_score = current.get("score") or {}
    inc_score = incoming.get("score") or {}
    if live_wins:
        out["score"] = dict(cur_score)
        for key in VOLATILE_SCORE_KEYS:
            if key in inc_score:
                out["score"][key] = inc_score.get(key)
        if incoming_source_id:
            provenance["score"] = incoming_source_id
            freshness["score"] = {"source": incoming_source_id, "at": stamp}
            if inc_score.get("clock") is not None or inc_score.get("minute") is not None:
                freshness["clock"] = {"source": incoming_source_id, "at": stamp}
        if "periods" in incoming:
            out["periods"] = incoming.get("periods")
            if incoming_source_id:
                provenance["periods"] = incoming_source_id
                freshness["periods"] = {"source": incoming_source_id, "at": stamp}
        if "incidents" in incoming:
            out["incidents"] = incoming.get("incidents")
            if incoming_source_id:
                provenance["incidents"] = incoming_source_id
                freshness["incidents"] = {"source": incoming_source_id, "at": stamp}
    else:
        score_from_incoming = False
        if not _filled(cur_score.get("home")) and _filled(inc_score.get("home")):
            score_from_incoming = True
        out["score"] = {key: _prefer(cur_score.get(key), inc_score.get(key), score_from_incoming) for key in VOLATILE_SCORE_KEYS}
        if score_from_incoming and incoming_source_id:
            provenance["score"] = incoming_source_id
            freshness["score"] = {"source": incoming_source_id, "at": stamp}
        if not _filled(current.get("periods")) and _filled(incoming.get("periods")):
            out["periods"] = incoming.get("periods")
            if incoming_source_id:
                provenance["periods"] = incoming_source_id
                freshness["periods"] = {"source": incoming_source_id, "at": stamp}
    for key in (
        "venue",
        "season",
        "series_id",
        "session_type",
        "game_id",
        "country_id",
        "meeting_id",
        "start_time",
        "lineups",
        "statistics",
        "incidents",
        "availability",
        "maps",
        "classification",
        "runners",
        "winner",
        "round",
        "best_of",
        "tournament_id",
        "tournament_name",
        "surface",
        "category",
        "location",
        "result_type",
    ):
        if key == "incidents" and live_wins and "incidents" in incoming:
            continue
        volatile_stats = key in {"statistics", "incidents"} and live_wins
        had = _filled(current.get(key))
        out[key] = _prefer(current.get(key), incoming.get(key), volatile_stats or incoming_is_higher_priority)
        if incoming_source_id and _filled(out.get(key)) and (not had or ((volatile_stats or incoming_is_higher_priority) and _filled(incoming.get(key)))):
            if not had or volatile_stats or incoming_is_higher_priority:
                provenance[key] = incoming_source_id
            elif not provenance.get(key):
                provenance[key] = incoming_source_id
    out["live"] = is_live(out.get("status") or "")
    out["home"] = current.get("home") or incoming.get("home") or {}
    out["away"] = current.get("away") or incoming.get("away") or {}
    if incoming_is_higher_priority:
        if _filled((incoming.get("home") or {}).get("name")):
            out["home"] = incoming.get("home")
            provenance["home"] = incoming_source_id
        if _filled((incoming.get("away") or {}).get("name")):
            out["away"] = incoming.get("away")
            provenance["away"] = incoming_source_id
    elif not _filled((out.get("home") or {}).get("name")) and _filled((incoming.get("home") or {}).get("name")):
        out["home"] = incoming.get("home")
        provenance["home"] = incoming_source_id
    out["participant_a"] = incoming.get("participant_a") or out.get("home") or current.get("participant_a") or {}
    out["participant_b"] = incoming.get("participant_b") or out.get("away") or current.get("participant_b") or {}
    if incoming_is_higher_priority:
        out["participant_a"] = incoming.get("participant_a") or out.get("home") or {}
        out["participant_b"] = incoming.get("participant_b") or out.get("away") or {}
    home_name = (out.get("home") or {}).get("name")
    away_name = (out.get("away") or {}).get("name")
    a_name = (out.get("participant_a") or {}).get("name")
    b_name = (out.get("participant_b") or {}).get("name")
    if home_name and a_name and a_name != home_name:
        out["participant_a"] = {**(out.get("home") or {}), "side": "a"}
    if away_name and b_name and b_name != away_name:
        out["participant_b"] = {**(out.get("away") or {}), "side": "b"}
    if not a_name:
        out["participant_a"] = {**(out.get("home") or {}), "side": "a"}
    if not b_name:
        out["participant_b"] = {**(out.get("away") or {}), "side": "b"}
    out["field_sources"] = provenance
    out["field_freshness"] = freshness
    out["source_status"] = current.get("source_status") or incoming.get("source_status") or current.get("status")
    if incoming.get("source_status") and live_wins:
        out["source_status_incoming"] = incoming.get("source_status")
    if incoming.get("source_event_updated_at") and (incoming_ts >= current_ts or not current.get("source_event_updated_at")):
        out["source_event_updated_at"] = incoming.get("source_event_updated_at")
    elif current.get("source_event_updated_at"):
        out["source_event_updated_at"] = current.get("source_event_updated_at")
    out["source_fetch_time"] = incoming.get("source_fetch_time") or current.get("source_fetch_time")
    if incoming_ts >= current_ts:
        out["retrieved_at"] = incoming.get("retrieved_at") or incoming.get("source_fetch_time") or current.get("retrieved_at")
        if incoming.get("observed_at") or incoming.get("source_event_updated_at"):
            out["observed_at"] = incoming.get("observed_at") or incoming.get("source_event_updated_at")
        if incoming.get("canonical_last_observed_at") or out.get("observed_at"):
            out["canonical_last_observed_at"] = incoming.get("canonical_last_observed_at") or out.get("observed_at")
    else:
        out["retrieved_at"] = current.get("retrieved_at") or incoming.get("retrieved_at")
    return out


def apply_row_fields(row, merged: Dict[str, Any], source_id: str, higher: bool) -> None:
    row.status = merged.get("status") or row.status
    row.live = bool(merged.get("live"))
    row.venue = merged.get("venue") or row.venue
    row.season = merged.get("season") or row.season
    row.series_id = merged.get("series_id") or row.series_id
    row.session_type = merged.get("session_type") or row.session_type
    row.game_id = merged.get("game_id") or row.game_id
    row.country_id = merged.get("country_id") or row.country_id
    row.meeting_id = merged.get("meeting_id") or row.meeting_id
    start = parse_datetime(merged.get("start_time"))
    if start and (higher or row.start_time is None):
        row.start_time = start
    row.score_json = dump_json(merged.get("score") or {})
    row.participants_json = dump_json(
        {
            "home": merged.get("home") or {},
            "away": merged.get("away") or {},
            "participant_a": merged.get("participant_a") or {},
            "participant_b": merged.get("participant_b") or {},
        }
    )
    extra = load_json(row.extra_json, {}) or {}
    for key in EXTRA_PERSIST_KEYS:
        if merged.get(key) is not None:
            extra[key] = merged.get(key)
    from collector.enrichment import is_display_eligible, quality_flags_for_event

    flags = quality_flags_for_event(merged)
    extra["quality_flags"] = flags
    extra["display_eligible"] = is_display_eligible(merged)
    if hasattr(row, "display_eligible"):
        row.display_eligible = extra["display_eligible"]
    ids = extra.get("source_event_ids") or []
    incoming_id = merged.get("source_event_id")
    if incoming_id and incoming_id not in ids:
        ids.append(incoming_id)
        extra["source_event_ids"] = ids
    extra["field_sources"] = merged.get("field_sources") or extra.get("field_sources") or {}
    extra["field_freshness"] = merged.get("field_freshness") or extra.get("field_freshness") or {}
    now = datetime.utcnow()
    merged["persisted_at"] = now.isoformat() + "Z"
    merged["canonical_updated_at"] = now.isoformat() + "Z"
    extra["persisted_at"] = merged["persisted_at"]
    extra["canonical_updated_at"] = merged["canonical_updated_at"]
    extra["fetch_started_at"] = merged.get("fetch_started_at") or extra.get("fetch_started_at")
    extra["fetch_completed_at"] = merged.get("fetch_completed_at") or extra.get("fetch_completed_at")
    extra["parsed_at"] = merged.get("parsed_at") or extra.get("parsed_at")
    try:
        from collector.latency import record_observation_latency

        record_observation_latency(merged)
    except Exception:
        pass
    kickoffs = extra.get("source_kickoffs") or []
    stamp = merged.get("source_local_datetime") or merged.get("start_time")
    if stamp:
        entry = {
            "source_id": source_id,
            "value": stamp,
            "timezone": merged.get("source_timezone"),
            "method": merged.get("timezone_resolution_method"),
            "utc": merged.get("start_time"),
        }
        if entry not in kickoffs:
            kickoffs.append(entry)
            extra["source_kickoffs"] = kickoffs
    if merged.get("observed_at") or merged.get("retrieved_at"):
        incoming_obs = merged.get("observed_at") or merged.get("retrieved_at")
        current_obs = extra.get("observed_at")
        if not current_obs or _ts(incoming_obs) >= _ts(current_obs):
            extra["observed_at"] = incoming_obs
    row.extra_json = dump_json(extra)
    if merged.get("stage") or merged.get("round"):
        row.stage = merged.get("stage") or merged.get("round") or row.stage
    if merged.get("gender"):
        row.gender = merged.get("gender")
    if merged.get("timezone"):
        row.timezone_name = merged.get("timezone")
    if merged.get("source_url"):
        row.source_url = merged.get("source_url")
    row.retrieved_at = datetime.utcnow()
    row.contributing_sources_json = dump_json(
        contributing_sources(row.contributing_sources_json, source_id)
    )
    if higher or not row.primary_source_id:
        row.primary_source_id = source_id
    row.updated_at = datetime.utcnow()
