"""Skip full upserts when a new observation matches stored canonical state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from collector.enrichment import OBSERVATION_ENRICH_KEYS, _section_filled
from collector.util import dump_json, load_json


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
    return True
