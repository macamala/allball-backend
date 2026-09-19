"""Stable types for the NinkoSports Sports Registry.

This module is configuration/contracts only. It does not invent events,
fixtures, odds, or provider payloads.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TypedDict

REGISTRY_VERSION = "1.0.0"

EVENT_MODELS: Tuple[str, ...] = (
    "team_match",
    "individual_match",
    "combat",
    "motorsport_race",
    "racing",
    "tournament",
    "esports_match",
)

SPORT_CATEGORIES: Tuple[str, ...] = (
    "team",
    "racket",
    "combat",
    "motorsport",
    "racing",
    "esports",
    "individual",
    "other",
)

CATEGORY_LABELS = {
    "team": "Team Sports",
    "racket": "Racket / Cue",
    "combat": "Combat Sports",
    "motorsport": "Motorsport",
    "racing": "Racing",
    "esports": "Esports",
    "individual": "Individual Sports",
    "other": "Other",
}

PARTICIPANT_TYPES: Tuple[str, ...] = (
    "team",
    "person",
    "fighter",
    "driver",
    "runner",
    "mixed",
)

NAV_GROUPS: Tuple[str, ...] = ("main", "other")


class SportRecord(TypedDict, total=False):
    id: str
    slug: str
    name: str
    short_name: str
    category: str
    event_model: str
    participant_type: str
    country_based: bool
    supports_draw: bool
    supports_live: bool
    supports_standings: bool
    supports_rankings: bool
    supports_predictions: bool
    supports_odds: bool
    supports_news: bool
    active: bool
    display_priority: int
    nav_group: str
    path: str
    parent_id: Optional[str]
    followable: bool
    directory_visible: bool
    live_filter: bool
    esports_kind: Optional[str]
    aliases: List[str]


class GeographyRecord(TypedDict, total=False):
    id: str
    slug: str
    name: str
    kind: str
    iso_code: Optional[str]
    parent_id: Optional[str]


class CompetitionRecord(TypedDict, total=False):
    competition_id: str
    sport_id: str
    country_id: Optional[str]
    region_id: Optional[str]
    name: str
    official_name: str
    slug: str
    aliases: List[str]
    competition_type: str
    gender: Optional[str]
    level: Optional[str]
    active: bool
    provider_mappings: Dict[str, str]
    news_taxonomy: bool


class ProviderMapping(TypedDict, total=False):
    entity_kind: str
    ninko_id: str
    provider_id: str
    provider_entity_id: str


class ProviderDefinition(TypedDict, total=False):
    id: str
    name: str
    active: bool
    public_attribution_required: bool
    public_branding_required: bool
    attribution_required: bool
    attribution_text: Optional[str]
    licensed: bool
    sports_supported: List[str]
    capabilities: Dict[str, bool]
    push: List[str]


class CachePolicy(TypedDict, total=False):
    key: str
    ttl_seconds: int
    immutable: bool
    push: List[str]


class OddsIdentity(TypedDict, total=False):
    event_id: str
    market_type: str
    selection: str
    provider: Optional[str]
    odds: Optional[float]
    timestamp: Optional[str]
