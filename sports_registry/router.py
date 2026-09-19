"""Capability router: request handlers read collected data only.

Collection workers select sources per competition. Providers that require
on-page logos are never selected for public UI. Attribution credits are
separate from branding.
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
        if row.get("public_branding_required") or row.get("public_attribution_required"):
            continue
        return row
    return None


def get_sports_data_provider():
    """Read collected canonical events. Never call source adapters here."""
    from collector.provider import NinkoCollectedSportsDataProvider

    return NinkoCollectedSportsDataProvider()


def router_status() -> dict:
    payload = empty_provider_status()
    payload["capabilities"] = {}
    payload["primary"] = None
    payload["fallback"] = None
    return payload
