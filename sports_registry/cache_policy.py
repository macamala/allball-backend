"""Cache policy contracts for future provider integration.

No polling is started in this phase. Push-capable providers should use
WebSocket, SSE, or webhooks instead of aggressive polling.
"""

from __future__ import annotations

from typing import Dict

from .schema import CachePolicy

PUSH_CHANNELS = ("websocket", "sse", "webhook")

CACHE_POLICIES: Dict[str, CachePolicy] = {
    "live_events": {
        "key": "live_events",
        "ttl_seconds": 8,
        "immutable": False,
        "push": list(PUSH_CHANNELS),
    },
    "upcoming_fixtures": {
        "key": "upcoming_fixtures",
        "ttl_seconds": 300,
        "immutable": False,
        "push": ["webhook"],
    },
    "standings": {
        "key": "standings",
        "ttl_seconds": 600,
        "immutable": False,
        "push": ["webhook"],
    },
    "teams_players": {
        "key": "teams_players",
        "ttl_seconds": 86400,
        "immutable": False,
        "push": ["webhook"],
    },
    "countries_registry": {
        "key": "countries_registry",
        "ttl_seconds": 604800,
        "immutable": False,
        "push": [],
    },
    "finished_events": {
        "key": "finished_events",
        "ttl_seconds": 2592000,
        "immutable": True,
        "push": [],
    },
}


def policy_for(key: str) -> CachePolicy:
    return CACHE_POLICIES.get(key) or {
        "key": key,
        "ttl_seconds": 300,
        "immutable": False,
        "push": [],
    }
