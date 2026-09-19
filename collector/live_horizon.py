"""Sport-aware live duration horizons.

The 8-hour audit threshold can flag a row as suspicious. Canonical truth uses
these horizons instead of a single wall-clock rule.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from collector.event_quality import (
    BRACKET,
    HEAD_TO_HEAD,
    MEET,
    MULTI_EVENT_MEET,
    RACE,
    TEAM_MATCH,
    TOURNAMENT,
    event_type_for,
)

FALLBACK_HORIZON = timedelta(hours=8)

TYPE_HORIZON = {
    TEAM_MATCH: timedelta(hours=4),
    HEAD_TO_HEAD: timedelta(hours=14),
    RACE: timedelta(hours=8),
    MEET: timedelta(hours=12),
    TOURNAMENT: timedelta(hours=14),
    BRACKET: timedelta(hours=16),
    MULTI_EVENT_MEET: timedelta(hours=18),
}

SPORT_HORIZON = {
    "football": timedelta(hours=4),
    "futsal": timedelta(hours=3),
    "basketball": timedelta(hours=4),
    "hockey": timedelta(hours=4, minutes=30),
    "ice-hockey": timedelta(hours=4, minutes=30),
    "handball": timedelta(hours=3),
    "volleyball": timedelta(hours=4),
    "water-polo": timedelta(hours=3),
    "rugby": timedelta(hours=3),
    "rugby-league": timedelta(hours=3),
    "netball": timedelta(hours=2, minutes=30),
    "lacrosse": timedelta(hours=3),
    "field-hockey": timedelta(hours=3),
    "australian-rules": timedelta(hours=4),
    "american-football": timedelta(hours=5),
    "baseball": timedelta(hours=6),
    "tennis": timedelta(hours=16),
    "badminton": timedelta(hours=8),
    "table-tennis": timedelta(hours=8),
    "cricket": timedelta(days=6),
    "golf": timedelta(hours=14),
    "motorsport": timedelta(hours=8),
    "cycling": timedelta(hours=10),
    "horse-racing": timedelta(hours=12),
    "greyhound-racing": timedelta(hours=8),
    "harness-racing": timedelta(hours=10),
    "athletics": timedelta(hours=18),
    "swimming": timedelta(hours=18),
    "winter-sports": timedelta(hours=8),
    "esports": timedelta(hours=16),
}

CRICKET_FORMAT_HORIZON = {
    "t20": timedelta(hours=5),
    "twenty20": timedelta(hours=5),
    "odi": timedelta(hours=10),
    "list-a": timedelta(hours=10),
    "test": timedelta(days=6),
    "first-class": timedelta(days=6),
}

PROVIDER_HORIZON: Dict[tuple, timedelta] = {}

ESPORTS_PARENT = "esports"


def _cricket_horizon(event: Optional[Dict[str, Any]]) -> Optional[timedelta]:
    if not event:
        return None
    blob = " ".join(
        str(event.get(key) or "")
        for key in ("session_type", "result_type", "stage", "round", "format", "event_family")
    ).lower()
    for token, horizon in CRICKET_FORMAT_HORIZON.items():
        if token in blob:
            return horizon
    return SPORT_HORIZON["cricket"]


def live_horizon(
    *,
    sport_id: str = "",
    competition_id: str = "",
    provider: str = "",
    event: Optional[Dict[str, Any]] = None,
) -> timedelta:
    family = (provider or (event or {}).get("source_family") or (event or {}).get("provider") or "").strip().lower()
    sport = (sport_id or (event or {}).get("sport") or "").strip().lower()
    competition = competition_id or (event or {}).get("competition_key") or (event or {}).get("competition") or ""
    if family and sport and (family, sport) in PROVIDER_HORIZON:
        return PROVIDER_HORIZON[(family, sport)]
    if sport == "cricket":
        return _cricket_horizon(event) or SPORT_HORIZON["cricket"]
    if sport in SPORT_HORIZON:
        return SPORT_HORIZON[sport]
    from sports_registry.sports import get_sport

    parent = (get_sport(sport) or {}).get("parent_id") or ""
    if parent == ESPORTS_PARENT or sport == ESPORTS_PARENT:
        return SPORT_HORIZON["esports"]
    kind = event_type_for(competition, sport)
    if kind in TYPE_HORIZON:
        return TYPE_HORIZON[kind]
    return FALLBACK_HORIZON
