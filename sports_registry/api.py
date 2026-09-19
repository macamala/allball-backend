"""Public registry API payloads. Empty sports-data stays honest."""

from __future__ import annotations

from typing import Optional

from .cache_policy import CACHE_POLICIES
from .competitions import competitions_for_sport, motorsport_series, public_competition
from .esports import esports_games
from .geography import all_geography, public_geo
from .providers import empty_provider_status
from .schema import CATEGORY_LABELS, EVENT_MODELS, REGISTRY_VERSION, SPORT_CATEGORIES
from .sports import catalog_rows, followable_sports, public_sport
from .motorsport import SERIES_IDS


def registry_payload(sport: Optional[str] = None) -> dict:
    sports = catalog_rows()
    if sport:
        sports = [row for row in sports if row["slug"] == sport]
    return {
        "version": REGISTRY_VERSION,
        "event_models": list(EVENT_MODELS),
        "categories": [
            {"id": key, "label": CATEGORY_LABELS[key]} for key in SPORT_CATEGORIES
        ],
        "sports": sports,
        "followable_sports": [public_sport(row) for row in followable_sports()],
        "motorsport_series": [public_competition(row) for row in motorsport_series()],
        "esports_games": esports_games(),
        "provider": empty_provider_status(),
    }


def geography_payload() -> dict:
    return {
        "version": REGISTRY_VERSION,
        "places": [public_geo(row) for row in all_geography()],
    }


def competitions_payload(sport: Optional[str] = None) -> dict:
    rows = competitions_for_sport(sport)
    return {
        "version": REGISTRY_VERSION,
        "sport": sport,
        "competitions": [public_competition(row) for row in rows],
    }


def providers_payload() -> dict:
    return {
        "version": REGISTRY_VERSION,
        **empty_provider_status(),
        "cache_policy": CACHE_POLICIES,
        "motorsport_series_ids": list(SERIES_IDS),
        "public_branding_rule": (
            "NinkoSports does not display external sports-data provider "
            "branding, logos, or powered-by marks on Live Scores. Legally "
            "required credits appear only on the Data Sources page."
        ),
        "attribution_mode": "global-data-sources",
        "architecture": "sport-to-many-competitions-to-ordered-sources",
    }
