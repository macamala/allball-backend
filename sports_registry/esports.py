"""Esports domain contracts.

Model: Esports → Game → Competition/Tournament → Match → Teams/Players.

Competitive esports and simulation products (EA FC / eFootball) are distinct
kinds. No matches are seeded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from .sports import all_sports


class EsportsGame(TypedDict, total=False):
    game_id: str
    sport_id: str
    name: str
    esports_kind: str
    parent_id: Optional[str]


class EsportsMatch(TypedDict, total=False):
    event_id: str
    game_id: str
    competition_id: Optional[str]
    teams: List[Dict[str, Any]]
    players: List[Dict[str, Any]]
    best_of: Optional[int]
    maps: List[Dict[str, Any]]
    score: Dict[str, Any]
    status: str


def esports_games() -> List[Dict[str, Any]]:
    rows = []
    for sport in all_sports(active_only=True):
        if sport.get("category") != "esports":
            continue
        rows.append(
            {
                "game_id": sport["id"],
                "sport_id": sport["id"],
                "name": sport["name"],
                "esports_kind": sport.get("esports_kind")
                or ("parent" if sport["id"] == "esports" else "competitive"),
                "parent_id": sport.get("parent_id"),
            }
        )
    return rows


def empty_esports_payload(game_id: Optional[str] = None) -> Dict[str, Any]:
    return {
        "sport_id": "esports",
        "game_id": game_id,
        "connected": False,
        "games": esports_games(),
        "competitions": [],
        "matches": [],
        "message": "Esports matches appear when a sports-data provider is connected.",
    }
