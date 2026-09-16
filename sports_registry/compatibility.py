"""One authoritative competition ↔ sport compatibility check."""

from __future__ import annotations

from typing import Optional

from .competitions import EXTRA_COMPETITIONS, get_competition
from .sports import canonical_sport_slug, get_sport


def can_competition_belong_to_sport(competition_id: Optional[str], sport_id: Optional[str]) -> bool:
    """True when competition X is allowed to belong to sport Y."""
    return compatible_competition(sport_id, competition_id) is not None


def compatible_competition(sport: Optional[str], competition: Optional[str]) -> Optional[str]:
    """Return the canonical competition key only when it belongs to the sport.

    Same contract as bot.taxonomy.compatible_competition, including extras that
    exist only in the sports registry.
    """
    from bot.taxonomy import COMPETITIONS, canonical_competition_key

    key = canonical_competition_key(competition)
    if not key:
        return None
    sport_key = canonical_sport_slug(sport) if sport else None
    extra = EXTRA_COMPETITIONS.get(key)
    if extra:
        owner = extra.get("sport_id")
        if sport_key and owner and owner != sport_key:
            return None
        return key
    meta = COMPETITIONS.get(key)
    if not meta:
        row = get_competition(key)
        if not row:
            return None
        owner = row.get("sport_id")
        if sport_key and owner and owner != sport_key:
            return None
        return key
    owner = meta.get("sport")
    if sport_key and owner and owner != sport_key:
        return None
    if sport_key and get_sport(sport_key) is None:
        return None
    return key
