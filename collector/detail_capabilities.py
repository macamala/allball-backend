"""Static capability map from existing family caps and known adapter fields.

Does not fetch upstream. Does not change polling.
"""

from __future__ import annotations

from typing import Any, Dict, List

from collector.family_caps import family_caps

# Observed collectors that already persist richer public fields when present.
_FAMILY_DETAIL: Dict[str, Dict[str, bool]] = {
    "openligadb": {"timeline": True, "periods": True, "stats": False, "lineups": False, "standings": True},
    "wta-json": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "espn-html": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "mlb-statsapi": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "nhl-web": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "pga-graphql": {"timeline": False, "periods": False, "stats": False, "lineups": False, "standings": False, "leaderboard": True},
    "sportscore": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "thesportsdb": {"timeline": False, "periods": False, "stats": False, "lineups": False, "standings": True},
    "fotmob": {"timeline": False, "periods": False, "stats": False, "lineups": False, "standings": False},
    "sofascore-web": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "dataproject-web": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
    "lolesports-json": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False, "maps": True},
    "f1-livetiming-index": {"timeline": False, "periods": False, "stats": False, "lineups": False, "standings": False, "classification": True},
    "gbgb-web": {"timeline": False, "periods": False, "stats": False, "lineups": False, "standings": False, "runners": True},
    "cricsheet": {"timeline": False, "periods": True, "stats": False, "lineups": False, "standings": False},
}


def capability_row(family: str) -> Dict[str, Any]:
    caps = family_caps(family)
    extra = dict(_FAMILY_DETAIL.get(family) or {})
    return {
        "provider_family": family,
        "live": bool(caps.get("supports_live")),
        "clock": bool(caps.get("live_clock")),
        "periods": bool(caps.get("partial_periods") or extra.get("periods")),
        "timeline": bool(extra.get("timeline")),
        "stats": bool(extra.get("stats")),
        "lineups": bool(extra.get("lineups")),
        "standings": bool(extra.get("standings")),
        "leaderboard": bool(extra.get("leaderboard")),
        "classification": bool(extra.get("classification")),
        "maps": bool(extra.get("maps")),
        "runners": bool(extra.get("runners")),
        "rapid_result": caps.get("capability_class") == "RAPID_RESULT",
        "rich_detail": bool(extra.get("timeline") or extra.get("stats") or extra.get("lineups") or extra.get("leaderboard")),
    }


def capability_inventory(families: List[str] | None = None) -> List[Dict[str, Any]]:
    names = families or sorted(set(list(_FAMILY_DETAIL) + ["openligadb", "thesportsdb", "sportscore", "wta-json"]))
    return [capability_row(name) for name in names]
