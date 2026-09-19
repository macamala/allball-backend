"""Sport-aware polling windows. These never infer canonical LIVE."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

from collector.live_horizon import live_horizon

PRE_START = {
    "football": timedelta(minutes=5),
    "futsal": timedelta(minutes=5),
    "basketball": timedelta(minutes=5),
    "ice-hockey": timedelta(minutes=5),
    "hockey": timedelta(minutes=5),
    "handball": timedelta(minutes=5),
    "volleyball": timedelta(minutes=5),
    "rugby": timedelta(minutes=5),
    "rugby-league": timedelta(minutes=5),
    "american-football": timedelta(minutes=10),
    "australian-rules": timedelta(minutes=5),
    "baseball": timedelta(minutes=10),
    "tennis": timedelta(minutes=15),
    "table-tennis": timedelta(minutes=10),
    "badminton": timedelta(minutes=10),
    "cricket": timedelta(minutes=15),
    "golf": timedelta(minutes=20),
    "motorsport": timedelta(minutes=15),
    "cycling": timedelta(minutes=15),
    "horse-racing": timedelta(minutes=10),
    "greyhound-racing": timedelta(minutes=8),
    "harness-racing": timedelta(minutes=8),
    "boxing": timedelta(minutes=10),
    "mma": timedelta(minutes=10),
    "esports": timedelta(minutes=10),
}

DEFAULT_PRE_START = timedelta(minutes=5)


def pre_start_window(sport_id: str) -> timedelta:
    if (sport_id or "").startswith("ea-sports") or sport_id in {
        "counter-strike",
        "league-of-legends",
        "dota-2",
        "valorant",
        "call-of-duty",
        "overwatch",
        "rocket-league",
    }:
        return PRE_START["esports"]
    return PRE_START.get(sport_id or "", DEFAULT_PRE_START)


def watch_duration(sport_id: str, event: Optional[Dict[str, Any]] = None) -> timedelta:
    return live_horizon(sport_id=sport_id or "", event=event or {})
