"""Capability router: request → lookup → primary → fallback → normalized object.

This phase has no real providers. The disconnected adapter remains the only
implementation. Providers that require public branding are never selected.
"""

from __future__ import annotations

from typing import Optional

from .providers import empty_provider_status, list_providers


def select_provider(capability: str, sport: Optional[str] = None):
    """Return a public-safe provider for a capability, or None."""
    for row in list_providers(public_ok_only=True):
        if not row.get("active"):
            continue
        caps = row.get("capabilities") or {}
        if capability and not caps.get(capability):
            continue
        sports = row.get("sports_supported") or []
        if sport and sports and sport not in sports:
            continue
        if row.get("public_attribution_required"):
            continue
        return row
    return None


def get_sports_data_provider():
    """Always the disconnected adapter until a real provider is registered."""
    from sports_provider import DisconnectedSportsDataProvider

    _selected = select_provider("live_scores")
    if _selected is None:
        return DisconnectedSportsDataProvider()
    return DisconnectedSportsDataProvider()


def router_status() -> dict:
    payload = empty_provider_status()
    payload["capabilities"] = {}
    payload["primary"] = None
    payload["fallback"] = None
    return payload
