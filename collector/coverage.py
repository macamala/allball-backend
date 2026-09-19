"""Partial-coverage enforcement.

A partial source must never be treated as full competition coverage.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

PARTIAL_CONSTRAINTS = {
    ("world-aquatics-events", "microplus-timing"): {
        "allow_keywords": [
            "u20",
            "u18",
            "world cup",
            "worldcupwp",
            "zagreb",
            "salvador",
        ],
        "deny_keywords": ["singapore", "world championships", "worlds 2025"],
        "notes": (
            "Verified for World Aquatics water polo U20/U18 and World Cup. "
            "Senior Singapore Worlds water polo remained Omega Timing."
        ),
    },
    ("usa-usta-meetings", "meadowlands-web"): {
        "allow_keywords": ["meadowlands", "playmeadowlands", "nj classic"],
        "notes": "Meadowlands race-day charts only, not all USTA meetings.",
    },
    ("germany-click-tt", "tischtennislive"): {
        "allow_keywords": ["bettv", "verbandsliga", "ajax", "osc"],
        "notes": "Berlin Verbandsliga scorecards on tischtennislive, not full click-TT.",
    },
    ("nordic-water-polo-league", "cetus-web"): {
        "allow_keywords": ["cetus", "espoo", "neptun", "zaibas", "slagelse"],
        "notes": "Cetus club NWPL tables, not the league-wide portal.",
    },
    ("super-rugby", "pulselive"): {
        "allow_keywords": ["super rugby", "super rugby pacific"],
        "notes": "World Rugby pulselive match JSON filtered to Super Rugby competitions only.",
    },
    ("bwf-and-national-events", "nba-japan-web"): {
        "allow_keywords": ["singapore open", "badminton.or.jp", "naraoka", "super 750"],
        "notes": "Japan association result pages for selected Super 750 days, not BWF-wide.",
    },
    ("world-lacrosse", "jla-web"): {
        "allow_keywords": ["tokyo2026", "lacrosse.gr.jp"],
        "notes": "Host WP score hub; independence from World Lacrosse CMS is derived.",
    },
    ("usa-usta-meetings", "delaware-lbj-web"): {
        "allow_keywords": ["little brown jug", "littlebrownjug", "delaware"],
        "notes": "Little Brown Jug meeting charts only.",
    },
}


def constraints_for(competition_id: str, family: str) -> Dict[str, Any]:
    return dict(PARTIAL_CONSTRAINTS.get((competition_id, family)) or {})


def event_matches_partial(event: Dict[str, Any], constraints: Dict[str, Any]) -> bool:
    if not constraints:
        return False
    blob = " ".join(
        str(event.get(key) or "")
        for key in (
            "competition",
            "source_event_id",
            "venue",
            "round",
            "stage",
            "source_url",
            "tournament",
        )
    )
    home = ((event.get("home") or {}) if isinstance(event.get("home"), dict) else {}).get("name") or ""
    away = ((event.get("away") or {}) if isinstance(event.get("away"), dict) else {}).get("name") or ""
    blob = f"{blob} {home} {away}".lower()
    deny = [item.lower() for item in constraints.get("deny_keywords") or []]
    if any(item in blob for item in deny):
        return False
    allow = [item.lower() for item in constraints.get("allow_keywords") or []]
    if not allow:
        return False
    return any(item in blob for item in allow)


def context_matches_partial(context: Optional[str], constraints: Dict[str, Any]) -> bool:
    if not constraints:
        return False
    blob = (context or "").lower()
    deny = [item.lower() for item in constraints.get("deny_keywords") or []]
    if blob and any(item in blob for item in deny):
        return False
    allow = [item.lower() for item in constraints.get("allow_keywords") or []]
    if not allow:
        return False
    if not blob:
        return False
    return any(item in blob for item in allow)


def filter_partial_events(events: Iterable[Dict[str, Any]], constraints: Dict[str, Any]) -> list:
    return [row for row in events if event_matches_partial(row, constraints)]
