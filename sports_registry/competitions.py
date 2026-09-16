"""Provider-independent competition registry.

News-taxonomy competitions stay in bot.taxonomy.COMPETITIONS so resolver
behaviour is unchanged. This module wraps those records with stable IDs,
regions, official names, and extra sports-data-only competitions that are
NOT scored by the news resolver.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .geography import canonical_geo_id, region_for_country
from .schema import CompetitionRecord
from .sports import get_sport

# Extra competitions for future sports-data / directory discovery.
# news_taxonomy=False means they do not enter the article resolver catalog.
EXTRA_COMPETITIONS: Dict[str, CompetitionRecord] = {
    "formula-2": {
        "competition_id": "formula-2",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "Formula 2",
        "official_name": "FIA Formula 2 Championship",
        "slug": "formula-2",
        "aliases": ["formula 2", "formula two"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "formula-3": {
        "competition_id": "formula-3",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "Formula 3",
        "official_name": "FIA Formula 3 Championship",
        "slug": "formula-3",
        "aliases": ["formula 3", "formula three"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "motogp": {
        "competition_id": "motogp",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "MotoGP",
        "official_name": "MotoGP World Championship",
        "slug": "motogp",
        "aliases": ["motogp"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "moto2": {
        "competition_id": "moto2",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "Moto2",
        "official_name": "Moto2 World Championship",
        "slug": "moto2",
        "aliases": ["moto2"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "moto3": {
        "competition_id": "moto3",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "Moto3",
        "official_name": "Moto3 World Championship",
        "slug": "moto3",
        "aliases": ["moto3"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "nascar": {
        "competition_id": "nascar",
        "sport_id": "motorsport",
        "country_id": "us",
        "region_id": "north-america",
        "name": "NASCAR",
        "official_name": "NASCAR Cup Series",
        "slug": "nascar",
        "aliases": ["nascar"],
        "competition_type": "series",
        "gender": None,
        "level": "national",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "indycar": {
        "competition_id": "indycar",
        "sport_id": "motorsport",
        "country_id": "us",
        "region_id": "north-america",
        "name": "IndyCar",
        "official_name": "NTT IndyCar Series",
        "slug": "indycar",
        "aliases": ["indycar", "indy car"],
        "competition_type": "series",
        "gender": None,
        "level": "national",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "wec": {
        "competition_id": "wec",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "WEC",
        "official_name": "FIA World Endurance Championship",
        "slug": "wec",
        "aliases": ["world endurance championship", " wec "],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "wrc": {
        "competition_id": "wrc",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "WRC",
        "official_name": "FIA World Rally Championship",
        "slug": "wrc",
        "aliases": ["world rally championship", " wrc "],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "formula-e": {
        "competition_id": "formula-e",
        "sport_id": "motorsport",
        "country_id": None,
        "region_id": "world",
        "name": "Formula E",
        "official_name": "ABB FIA Formula E World Championship",
        "slug": "formula-e",
        "aliases": ["formula e"],
        "competition_type": "series",
        "gender": None,
        "level": "international",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
    "supercars": {
        "competition_id": "supercars",
        "sport_id": "motorsport",
        "country_id": "au",
        "region_id": "oceania",
        "name": "Supercars",
        "official_name": "Repco Supercars Championship",
        "slug": "supercars",
        "aliases": ["supercars"],
        "competition_type": "series",
        "gender": None,
        "level": "national",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": False,
    },
}

OFFICIAL_NAMES = {
    "uefa-champions-league": "UEFA Champions League",
    "uefa-europa-league": "UEFA Europa League",
    "uefa-conference-league": "UEFA Conference League",
    "roland-garros": "Roland-Garros",
    "australian-open": "Australian Open",
    "wimbledon": "The Championships, Wimbledon",
    "us-open": "US Open",
    "fifa-world-cup": "FIFA World Cup",
    "formula-1": "FIA Formula One World Championship",
}

COMPETITION_TYPES = {
    "uefa-champions-league": "continental",
    "uefa-europa-league": "continental",
    "uefa-conference-league": "continental",
    "fifa-world-cup": "international",
    "uefa-euro": "continental",
    "formula-1": "series",
    "atp-tour": "tour",
    "wta-tour": "tour",
    "pga-tour": "tour",
    "wimbledon": "tournament",
    "roland-garros": "tournament",
    "australian-open": "tournament",
    "us-open": "tournament",
    "euroleague": "continental",
}

EUROPE_COMPETITIONS = {
    "uefa-champions-league",
    "uefa-europa-league",
    "uefa-conference-league",
    "uefa-euro",
    "euroleague",
}

# Aliases that are valid only with matching sport evidence.
SHARED_NAME_ALIASES = {
    "wimbledon": "wimbledon",
    "australian open": "australian-open",
    "us open": "us-open",
    "the open": None,
}


def _taxonomy_competitions() -> Dict[str, dict]:
    from bot.taxonomy import COMPETITIONS

    return COMPETITIONS


def _wrap_taxonomy(key: str, meta: dict) -> CompetitionRecord:
    country_raw = meta.get("country")
    country_id = None
    region_id = None
    if country_raw in {"international", "global", "world", "europe"}:
        region_id = canonical_geo_id(country_raw) or country_raw
        if country_raw == "europe":
            region_id = "europe"
        elif country_raw in {"international", "global", "world"}:
            region_id = "international" if country_raw != "world" else "world"
    else:
        country_id = canonical_geo_id(country_raw) or country_raw
        region_id = region_for_country(country_id) or region_for_country(country_raw)
    if key in EUROPE_COMPETITIONS:
        region_id = "europe"
        country_id = None
    return {
        "competition_id": key,
        "sport_id": meta.get("sport"),
        "country_id": country_id,
        "region_id": region_id,
        "name": meta.get("label") or key,
        "official_name": OFFICIAL_NAMES.get(key) or meta.get("label") or key,
        "slug": key,
        "aliases": list(meta.get("aliases") or []),
        "competition_type": COMPETITION_TYPES.get(key) or "league",
        "gender": None,
        "level": "international" if not country_id else "national",
        "active": True,
        "provider_mappings": {},
        "news_taxonomy": True,
    }


def all_competitions() -> Dict[str, CompetitionRecord]:
    out: Dict[str, CompetitionRecord] = {}
    for key, meta in _taxonomy_competitions().items():
        out[key] = _wrap_taxonomy(key, meta)
    for key, row in EXTRA_COMPETITIONS.items():
        out.setdefault(key, row)
    return out


def get_competition(competition_id: Optional[str]) -> Optional[CompetitionRecord]:
    if not competition_id:
        return None
    from bot.taxonomy import canonical_competition_key

    key = canonical_competition_key(competition_id) or competition_id
    return all_competitions().get(key)


def competitions_for_sport(sport_id: Optional[str]) -> List[CompetitionRecord]:
    if not sport_id:
        return list(all_competitions().values())
    return [row for row in all_competitions().values() if row.get("sport_id") == sport_id]


def motorsport_series() -> List[CompetitionRecord]:
    return [
        row
        for row in all_competitions().values()
        if row.get("sport_id") == "motorsport" and row.get("competition_type") == "series"
    ]


def _alias_index() -> Dict[str, str]:
    index: Dict[str, str] = {}
    for key, row in all_competitions().items():
        index[key] = key
        index[key.replace("-", " ")] = key
        for alias in row.get("aliases") or []:
            needle = str(alias).strip().lower()
            if needle:
                index[needle] = key
                index[needle.strip()] = key
    index["ucl"] = "uefa-champions-league"
    index["champions league"] = "uefa-champions-league"
    index["french open"] = "roland-garros"
    index["roland garros"] = "roland-garros"
    index["roland-garros"] = "roland-garros"
    return index


def resolve_competition_alias(text: Optional[str], sport_id: Optional[str] = None) -> Optional[str]:
    """Map an alias onto a canonical competition.

    An alias alone must not override contradictory sport evidence.
    Example: "Wimbledon" does not become tennis if sport_id is football.
    """
    if not text:
        return None
    needle = " ".join(str(text).strip().lower().split())
    key = _alias_index().get(needle)
    if not key:
        key = _alias_index().get(needle.replace("-", " "))
    if not key:
        return None
    row = get_competition(key)
    if not row:
        return None
    owner = row.get("sport_id")
    if sport_id and owner and owner != sport_id:
        return None
    sport = get_sport(sport_id) if sport_id else None
    if sport and owner and owner != sport.get("id"):
        return None
    return key


def public_competition(row: CompetitionRecord) -> Dict[str, object]:
    return {
        "competition_id": row["competition_id"],
        "sport_id": row.get("sport_id"),
        "country_id": row.get("country_id"),
        "region_id": row.get("region_id"),
        "name": row.get("name"),
        "official_name": row.get("official_name") or row.get("name"),
        "slug": row.get("slug") or row["competition_id"],
        "aliases": list(row.get("aliases") or []),
        "competition_type": row.get("competition_type"),
        "gender": row.get("gender"),
        "level": row.get("level"),
        "active": bool(row.get("active", True)),
        "provider_mappings": dict(row.get("provider_mappings") or {}),
        "news_taxonomy": bool(row.get("news_taxonomy", False)),
        "path": _competition_path(row),
    }


def _competition_path(row: CompetitionRecord) -> str:
    sport = get_sport(row.get("sport_id"))
    sport_path = (sport or {}).get("path") or f"/{row.get('sport_id') or 'other'}"
    return f"{sport_path}/{row.get('slug') or row['competition_id']}"
