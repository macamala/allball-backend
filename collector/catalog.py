"""Identity sync from the in-code sports registry.

Copies catalog sports' competition identities only. Does not create events,
source mappings, or coverage claims.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from collector.models import SportsCompetition
from sports_registry.competitions import all_competitions
from sports_registry.sports import get_sport


def sync_identity_catalog(db: Session) -> int:
    written = 0
    for key, row in all_competitions().items():
        sport = get_sport(row.get("sport_id"))
        existing = db.query(SportsCompetition).filter_by(competition_id=key).first()
        payload = dict(
            sport_id=row.get("sport_id") or "",
            name=row.get("name") or key,
            official_name=row.get("official_name") or row.get("name"),
            slug=row.get("slug") or key,
            country_id=row.get("country_id"),
            region_id=row.get("region_id"),
            series_id=key if row.get("competition_type") == "series" else None,
            game_id=row.get("sport_id") if (sport or {}).get("parent_id") == "esports" else None,
            parent_sport_id=(sport or {}).get("parent_id"),
            country_based=bool((sport or {}).get("country_based")),
            event_model=(sport or {}).get("event_model") or "team_match",
            competition_type=row.get("competition_type"),
            gender=row.get("gender"),
            level=row.get("level"),
            active=bool(row.get("active", True)),
            news_taxonomy=bool(row.get("news_taxonomy")),
            identity_only=True,
        )
        if existing is None:
            db.add(SportsCompetition(competition_id=key, **payload))
            written += 1
            continue
        for field, value in payload.items():
            if field == "identity_only":
                continue
            setattr(existing, field, value)
        written += 1
    db.flush()
    return written
