"""Keyed provider event IDs on a canonical event.

A list of bare IDs cannot tell FotMob from SofaScore. Store {family: id}.
Compound IDs (season:round, season:gamecode) must be kept intact.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_FAMILY_PREFIXES = (
    "jolpica:",
    "euroleague:",
    "worldrugby:",
    "cfl:",
    "lolesports:",
    "squiggle:",
    "pga:",
    "nhl:",
    "mlb:",
    "fotmob:",
    "opendota:",
    "championdata:",
)


def normalize_source_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    folded = text.lower()
    for prefix in _FAMILY_PREFIXES:
        if folded.startswith(prefix):
            return text[len(prefix) :]
    return text


def as_family_map(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if value in (None, ""):
                continue
            out[str(key)] = normalize_source_id(value)
        return out
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                out.update(as_family_map(item))
            elif item not in (None, ""):
                text = str(item)
                if ":" in text and not text.split(":", 1)[0].isdigit():
                    family, _, rest = text.partition(":")
                    out[family] = normalize_source_id(rest)
                else:
                    out.setdefault("_untyped", normalize_source_id(text))
    return out


def merge_family_ids(*parts: Any, family: str = "", source_event_id: Any = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in parts:
        for key, value in as_family_map(part).items():
            if not value:
                continue
            if key in out and out[key] != value:
                continue
            out[key] = value
    if family and source_event_id not in (None, ""):
        incoming = normalize_source_id(source_event_id)
        if incoming and (family not in out or out[family] == incoming):
            out[str(family)] = incoming
    return {key: value for key, value in out.items() if value}


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
        "pulselive-family": ("pulselive-family", "pulselive", "world-rugby-rims"),
        "pulselive": ("pulselive", "pulselive-family", "world-rugby-rims"),
        "cfl-scoreboard-json": ("cfl-scoreboard-json", "cfl"),
        "lolesports-json": ("lolesports-json", "lolesports"),
        "jolpica-f1": ("jolpica-f1", "jolpica", "jolpica-ergast"),
        "squiggle-afl": ("squiggle-afl", "squiggle"),
        "opendota": ("opendota",),
        "euroleague-live": ("euroleague-live", "euroleague"),
        "pga-graphql": ("pga-graphql", "pga"),
        "openligadb": ("openligadb",),
        "championdata-netball": ("championdata-netball", "championdata"),
        "click-tt-remix": ("click-tt-remix", "click-tt"),
        "dataproject-web": ("dataproject-web", "dataproject", "dataproject-wcm"),
        "cricsheet": ("cricsheet", "cricsheet-json"),
    }
    for key in aliases.get(family, (family,)):
        if ids.get(key):
            return ids[key]
    raw = extra.get("source_event_id")
    if raw and extra.get("source_family") == family:
        return normalize_source_id(raw)
    return None


_CANONICAL_FAMILY = {
    "jolpica": "jolpica-f1",
    "jolpica-ergast": "jolpica-f1",
    "euroleague": "euroleague-live",
    "squiggle": "squiggle-afl",
    "cfl": "cfl-scoreboard-json",
    "lolesports": "lolesports-json",
    "pga": "pga-graphql",
    "click-tt": "click-tt-remix",
    "championdata": "championdata-netball",
    "world-rugby-rims": "pulselive",
    "pulselive-family": "pulselive",
    "dataproject": "dataproject-web",
    "dataproject-wcm": "dataproject-web",
    "cricsheet-json": "cricsheet",
}


def families_with_ids(extra: Dict[str, Any]) -> Dict[str, str]:
    ids = as_family_map(extra.get("source_event_ids"))
    family = str(extra.get("source_family") or "")
    if family and ids.get("_untyped") and family not in ids:
        ids[family] = ids.pop("_untyped")
    sid = extra.get("source_event_id")
    if family and sid and family not in ids:
        ids[family] = normalize_source_id(sid)
    out: Dict[str, str] = {}
    for key, value in ids.items():
        if not value:
            continue
        out[_CANONICAL_FAMILY.get(key, key)] = value
    return out
