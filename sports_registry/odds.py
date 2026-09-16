"""Future odds identity only. No bookmaker integration and no odds UI."""

from __future__ import annotations

from typing import Optional

from .schema import OddsIdentity


def odds_identity(
    event_id: str,
    market_type: str,
    selection: str,
    provider: Optional[str] = None,
) -> OddsIdentity:
    return {
        "event_id": event_id,
        "market_type": market_type,
        "selection": selection,
        "provider": provider,
        "odds": None,
        "timestamp": None,
    }
