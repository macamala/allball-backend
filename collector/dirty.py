"""Skip full upserts when a new observation matches stored canonical state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from collector.enrichment import OBSERVATION_ENRICH_KEYS, _section_filled
from collector.util import dump_json, load_json


def _logo_value(side: Any) -> Any:
    if not isinstance(side, dict):
        return None
    return (
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or side.get("logo_url")
        or side.get("logoUrl")
        or side.get("image_url")
        or side.get("imageUrl")
        or side.get("emblem")
        or side.get("icon")
    )


def _identity_asset_missing(existing, incoming: Dict[str, Any], extra: Dict[str, Any]) -> bool:
    if incoming.get("competition_logo") and not extra.get("competition_logo"):
        return True
    stored_participants = load_json(getattr(existing, "participants_json", None), {}) or {}
    for key in ("home", "away", "participant_a", "participant_b"):
        inc = incoming.get(key) if isinstance(incoming.get(key), dict) else {}
        stored = stored_participants.get(key) if isinstance(stored_participants.get(key), dict) else {}
        if _logo_value(inc) and not _logo_value(stored):
            return True
        inc_country = inc.get("country_id") or inc.get("country") or inc.get("nationality")
        stored_country = stored.get("country_id") or stored.get("country") or stored.get("nationality")
        inc_countries = [str(value) for value in (inc.get("country_ids") or []) if value]
        stored_countries = [str(value) for value in (stored.get("country_ids") or []) if value]
        if inc_country and not stored_country:
            return True
        if inc_countries and not stored_countries:
            return True
    return False


def observation_signature(incoming: Dict[str, Any]) -> str:
    home = incoming.get("home") if isinstance(incoming.get("home"), dict) else {}
    away = incoming.get("away") if isinstance(incoming.get("away"), dict) else {}
    return dump_json(
        {
            "status": incoming.get("status"),
            "score": incoming.get("score") or {},
            "start_time": incoming.get("start_time"),
            "home": (home or {}).get("name") or (home or {}).get("slug"),
            "away": (away or {}).get("name") or (away or {}).get("slug"),
            "venue": incoming.get("venue"),
        }
    )


def event_unchanged(existing, incoming: Dict[str, Any]) -> bool:
    if existing is None:
        return False
    extra = load_json(existing.extra_json, {}) or {}
    stored = extra.get("obs_signature")
    if not stored:
        return False
    if stored != observation_signature(incoming):
        return False
    if incoming.get("result_type") and extra.get("result_type") != incoming.get("result_type"):
        return False
    if incoming.get("walkover") and not extra.get("walkover"):
        return False
    from collector.source_ids import families_with_ids, merge_family_ids

    stored_ids = families_with_ids(extra)
    incoming_ids = merge_family_ids(
        incoming.get("source_event_ids"),
        family=str(incoming.get("source_family") or ""),
        source_event_id=incoming.get("source_event_id"),
    )
    if any(incoming_ids.get(key) and stored_ids.get(key) != incoming_ids.get(key) for key in incoming_ids):
        return False
    for key in OBSERVATION_ENRICH_KEYS:
        if _section_filled(incoming.get(key)) and not _section_filled(extra.get(key)):
            return False
    stored_round = str(extra.get("round") or "")
    if "vod" in stored_round.lower() and incoming.get("round") and incoming.get("round") != stored_round:
        return False
    if incoming.get("coverage") and extra.get("coverage") != incoming.get("coverage"):
        return False
    if incoming.get("source_competition_name") and not extra.get("source_competition_name"):
        return False
    if _identity_asset_missing(existing, incoming, extra):
        return False
    if incoming.get("start_time") and existing.start_time is None:
        return False
    return True
