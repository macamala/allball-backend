"""Keyed provider event IDs on a canonical event.

A list of bare IDs cannot tell FotMob from SofaScore. Store {family: id}.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def as_family_map(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value in (None, ""):
                continue
            out[str(key)] = str(value).split(":")[-1]
        return out
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.update(as_family_map(item))
            elif item not in (None, ""):
                text = str(item)
                if ":" in text and not text.split(":", 1)[0].isdigit():
                    family, _, rest = text.partition(":")
                    out[family] = rest.split(":")[-1]
                else:
                    out.setdefault("_untyped", text.split(":")[-1])
    return out


def merge_family_ids(*parts: Any, family: str = "", source_event_id: Any = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in parts:
        out.update(as_family_map(part))
    if family and source_event_id not in (None, ""):
        out[str(family)] = str(source_event_id).split(":")[-1]
    return out


def id_for_family(extra: Dict[str, Any], family: str) -> Optional[str]:
    ids = as_family_map(extra.get("source_event_ids"))
    if ids.get(family):
        return ids[family]
    aliases = {
        "fotmob": ("fotmob",),
        "sofascore-web": ("sofascore-web", "sofascore"),
        "mlb-statsapi": ("mlb-statsapi", "mlb"),
        "nhl-web": ("nhl-web", "nhl"),
        "wta-json": ("wta-json", "wta"),
    }
    for key in aliases.get(family, (family,)):
        if ids.get(key):
            return ids[key]
    raw = extra.get("source_event_id")
    if raw and extra.get("source_family") == family:
        return str(raw).split(":")[-1]
    return None


def families_with_ids(extra: Dict[str, Any]) -> Dict[str, str]:
    ids = as_family_map(extra.get("source_event_ids"))
    family = str(extra.get("source_family") or "")
    sid = extra.get("source_event_id")
    if family and sid and family not in ids:
        ids[family] = str(sid).split(":")[-1]
    return ids
