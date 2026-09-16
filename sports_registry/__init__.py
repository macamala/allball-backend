"""NinkoSports Sports Registry — single authoritative sports catalog."""

from .schema import CATEGORY_LABELS, EVENT_MODELS, REGISTRY_VERSION, SPORT_CATEGORIES
from .sports import (
    SPORTS,
    all_sports,
    canonical_sport_slug,
    catalog_rows,
    directory_sport_slugs,
    followable_sports,
    get_sport,
    main_sport_slugs,
    prediction_market,
    prediction_sports,
    public_sport,
    taxonomy_sports_map,
)
from .compatibility import can_competition_belong_to_sport, compatible_competition
from .competitions import get_competition, resolve_competition_alias
from .api import competitions_payload, geography_payload, providers_payload, registry_payload

__all__ = [
    "CATEGORY_LABELS",
    "EVENT_MODELS",
    "REGISTRY_VERSION",
    "SPORTS",
    "SPORT_CATEGORIES",
    "all_sports",
    "can_competition_belong_to_sport",
    "canonical_sport_slug",
    "catalog_rows",
    "compatible_competition",
    "competitions_payload",
    "directory_sport_slugs",
    "followable_sports",
    "geography_payload",
    "get_competition",
    "get_sport",
    "main_sport_slugs",
    "prediction_market",
    "prediction_sports",
    "providers_payload",
    "public_sport",
    "registry_payload",
    "resolve_competition_alias",
    "taxonomy_sports_map",
]
