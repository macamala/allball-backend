"""Source and collector-facing registry metadata.

Live Scores UI must not show provider logos or "Powered by..." branding.
Legally required credits are returned as a discreet Data Sources list.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .schema import ProviderDefinition

CAPABILITY_KEYS = (
    "sports",
    "live_scores",
    "fixtures",
    "results",
    "standings",
    "rankings",
    "statistics",
    "teams",
    "players",
    "racing",
    "odds",
    "push_websocket",
    "push_sse",
    "push_webhook",
)


PROVIDERS: List[ProviderDefinition] = []

# Internal ID maps. External provider IDs never become canonical NinkoSports IDs.
PROVIDER_MAPPINGS: Dict[str, Dict[str, Dict[str, str]]] = {
    "team": {},
    "competition": {},
    "event": {},
    "player": {},
}


def list_providers(*, public_ok_only: bool = True) -> List[ProviderDefinition]:
    rows = list(PROVIDERS)
    if public_ok_only:
        rows = [
            row
            for row in rows
            if not row.get("public_branding_required")
        ]
    return rows


def get_provider(provider_id: Optional[str]) -> Optional[ProviderDefinition]:
    if not provider_id:
        return None
    for row in PROVIDERS:
        if row.get("id") == provider_id:
            return row
    return None


def mapping_for(entity_kind: str, ninko_id: str) -> Dict[str, str]:
    return dict((PROVIDER_MAPPINGS.get(entity_kind) or {}).get(ninko_id) or {})


def empty_provider_status() -> Dict[str, object]:
    return {
        "connected": False,
        "provider": None,
        "providers": [],
        "public_attribution_required": False,
        "attribution": [],
        "message": "Live sports data will appear when a sports-data provider is connected.",
    }
