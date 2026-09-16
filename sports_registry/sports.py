"""Authoritative worldwide sport catalog.

IDs and slugs are stable and provider-independent. Adding a sport later is a
data change here, not a frontend rebuild. This catalog is not a hard limit.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .schema import EVENT_MODELS, REGISTRY_VERSION, SportRecord

# Existing public URLs that must keep working for SEO.
_FLAT_PATHS = {
    "football",
    "basketball",
    "tennis",
    "motorsport",
    "american-football",
    "ice-hockey",
    "baseball",
    "rugby",
    "cricket",
    "volleyball",
    "handball",
    "golf",
    "boxing",
    "mma",
    "cycling",
    "snooker",
}

# Non-canonical slugs that must resolve to a stable sport id.
SPORT_SLUG_ALIASES = {
    "rugby-union": "rugby",
    "afl": "australian-rules",
    "australian-rules-football": "australian-rules",
    "aussie-rules": "australian-rules",
    "formula-1": "motorsport",
    "f1": "motorsport",
    "efootball": "ea-sports-fc",
    "ea-fc": "ea-sports-fc",
    "cs2": "counter-strike",
    "csgo": "counter-strike",
    "lol": "league-of-legends",
    "greyhounds": "greyhound-racing",
    "harness": "harness-racing",
    "horseracing": "horse-racing",
}


def _path_for(slug: str, nav_group: str) -> str:
    if slug in _FLAT_PATHS or nav_group == "main":
        return f"/{slug}"
    return f"/sports/{slug}"


def _sport(
    slug: str,
    name: str,
    category: str,
    event_model: str,
    *,
    short_name: Optional[str] = None,
    participant_type: str = "team",
    country_based: bool = False,
    supports_draw: bool = False,
    supports_live: bool = True,
    supports_standings: bool = False,
    supports_rankings: bool = False,
    supports_predictions: bool = False,
    supports_odds: bool = False,
    supports_news: bool = True,
    active: bool = True,
    display_priority: int = 200,
    nav_group: str = "other",
    parent_id: Optional[str] = None,
    followable: bool = True,
    directory_visible: bool = True,
    live_filter: bool = False,
    esports_kind: Optional[str] = None,
    aliases: Optional[List[str]] = None,
) -> SportRecord:
    if event_model not in EVENT_MODELS:
        raise ValueError(f"Invalid event_model for {slug}: {event_model}")
    return {
        "id": slug,
        "slug": slug,
        "name": name,
        "short_name": short_name or name,
        "category": category,
        "event_model": event_model,
        "participant_type": participant_type,
        "country_based": country_based,
        "supports_draw": supports_draw,
        "supports_live": supports_live,
        "supports_standings": supports_standings,
        "supports_rankings": supports_rankings,
        "supports_predictions": supports_predictions,
        "supports_odds": supports_odds,
        "supports_news": supports_news,
        "active": active,
        "display_priority": display_priority,
        "nav_group": nav_group,
        "path": _path_for(slug, nav_group),
        "parent_id": parent_id,
        "followable": followable,
        "directory_visible": directory_visible,
        "live_filter": live_filter,
        "esports_kind": esports_kind,
        "aliases": aliases or [],
    }


SPORTS: List[SportRecord] = [
    _sport(
        "football",
        "Football",
        "team",
        "team_match",
        participant_type="team",
        country_based=True,
        supports_draw=True,
        supports_standings=True,
        supports_predictions=True,
        display_priority=10,
        nav_group="main",
        live_filter=True,
        aliases=["soccer"],
    ),
    _sport(
        "basketball",
        "Basketball",
        "team",
        "team_match",
        supports_standings=True,
        supports_predictions=True,
        display_priority=20,
        nav_group="main",
        live_filter=True,
    ),
    _sport(
        "tennis",
        "Tennis",
        "racket",
        "individual_match",
        participant_type="person",
        supports_rankings=True,
        supports_predictions=True,
        display_priority=30,
        nav_group="main",
        live_filter=True,
        directory_visible=False,
    ),
    _sport(
        "motorsport",
        "Motorsport",
        "motorsport",
        "motorsport_race",
        participant_type="driver",
        supports_standings=True,
        supports_rankings=True,
        display_priority=40,
        nav_group="main",
        live_filter=True,
        directory_visible=False,
    ),
    _sport(
        "american-football",
        "American Football",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=110,
    ),
    _sport(
        "ice-hockey",
        "Ice Hockey",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=120,
    ),
    _sport(
        "baseball",
        "Baseball",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=130,
    ),
    _sport(
        "rugby",
        "Rugby Union",
        "team",
        "team_match",
        short_name="Rugby",
        supports_draw=True,
        supports_standings=True,
        display_priority=140,
        aliases=["rugby union", "rugby-union"],
    ),
    _sport(
        "rugby-league",
        "Rugby League",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=141,
    ),
    _sport(
        "cricket",
        "Cricket",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=150,
    ),
    _sport(
        "volleyball",
        "Volleyball",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=160,
    ),
    _sport(
        "handball",
        "Handball",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=170,
    ),
    _sport(
        "futsal",
        "Futsal",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=180,
    ),
    _sport(
        "water-polo",
        "Water Polo",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=190,
    ),
    _sport(
        "field-hockey",
        "Field Hockey",
        "team",
        "team_match",
        supports_draw=True,
        supports_standings=True,
        display_priority=200,
    ),
    _sport(
        "australian-rules",
        "Australian Rules",
        "team",
        "team_match",
        short_name="AFL",
        supports_standings=True,
        display_priority=210,
        aliases=["afl"],
    ),
    _sport(
        "netball",
        "Netball",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=220,
    ),
    _sport(
        "lacrosse",
        "Lacrosse",
        "team",
        "team_match",
        supports_standings=True,
        display_priority=230,
    ),
    _sport(
        "table-tennis",
        "Table Tennis",
        "racket",
        "individual_match",
        participant_type="person",
        supports_rankings=True,
        display_priority=310,
    ),
    _sport(
        "badminton",
        "Badminton",
        "racket",
        "individual_match",
        participant_type="person",
        supports_rankings=True,
        display_priority=320,
    ),
    _sport(
        "snooker",
        "Snooker",
        "racket",
        "individual_match",
        participant_type="person",
        supports_rankings=True,
        display_priority=330,
    ),
    _sport(
        "darts",
        "Darts",
        "racket",
        "individual_match",
        participant_type="person",
        supports_rankings=True,
        display_priority=340,
    ),
    _sport(
        "boxing",
        "Boxing",
        "combat",
        "combat",
        participant_type="fighter",
        supports_rankings=True,
        display_priority=410,
    ),
    _sport(
        "mma",
        "MMA",
        "combat",
        "combat",
        participant_type="fighter",
        supports_rankings=True,
        display_priority=420,
    ),
    _sport(
        "horse-racing",
        "Horse Racing",
        "racing",
        "racing",
        participant_type="runner",
        country_based=True,
        supports_standings=False,
        display_priority=510,
    ),
    _sport(
        "greyhound-racing",
        "Greyhound Racing",
        "racing",
        "racing",
        participant_type="runner",
        country_based=True,
        display_priority=520,
    ),
    _sport(
        "harness-racing",
        "Harness Racing",
        "racing",
        "racing",
        participant_type="runner",
        country_based=True,
        display_priority=530,
    ),
    _sport(
        "golf",
        "Golf",
        "individual",
        "tournament",
        participant_type="person",
        supports_rankings=True,
        display_priority=610,
    ),
    _sport(
        "cycling",
        "Cycling",
        "individual",
        "tournament",
        participant_type="person",
        supports_rankings=True,
        display_priority=620,
    ),
    _sport(
        "athletics",
        "Athletics",
        "individual",
        "tournament",
        participant_type="person",
        supports_rankings=True,
        display_priority=630,
    ),
    _sport(
        "swimming",
        "Swimming",
        "individual",
        "tournament",
        participant_type="person",
        supports_rankings=True,
        display_priority=640,
    ),
    _sport(
        "winter-sports",
        "Winter Sports",
        "individual",
        "tournament",
        participant_type="mixed",
        supports_rankings=True,
        display_priority=650,
    ),
    _sport(
        "esports",
        "Esports",
        "esports",
        "esports_match",
        participant_type="mixed",
        display_priority=700,
        followable=True,
    ),
    _sport(
        "ea-sports-fc",
        "EA Sports FC",
        "esports",
        "esports_match",
        short_name="EA FC",
        parent_id="esports",
        esports_kind="simulation",
        display_priority=710,
        aliases=["efootball", "ea fc"],
    ),
    _sport(
        "counter-strike",
        "Counter-Strike",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=720,
    ),
    _sport(
        "league-of-legends",
        "League of Legends",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=730,
    ),
    _sport(
        "dota-2",
        "Dota 2",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=740,
    ),
    _sport(
        "valorant",
        "Valorant",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=750,
    ),
    _sport(
        "call-of-duty",
        "Call of Duty",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=760,
    ),
    _sport(
        "overwatch",
        "Overwatch",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=770,
    ),
    _sport(
        "rocket-league",
        "Rocket League",
        "esports",
        "esports_match",
        parent_id="esports",
        esports_kind="competitive",
        display_priority=780,
    ),
]


def canonical_sport_slug(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip().lower()
    if raw in {"other", "other-sports"}:
        return "other"
    return SPORT_SLUG_ALIASES.get(raw, raw)


def _index() -> Dict[str, SportRecord]:
    return {row["id"]: row for row in SPORTS}


def get_sport(slug: Optional[str]) -> Optional[SportRecord]:
    key = canonical_sport_slug(slug)
    if not key or key == "other":
        return None
    return _index().get(key)


def all_sports(*, active_only: bool = False) -> List[SportRecord]:
    rows = list(SPORTS)
    if active_only:
        rows = [row for row in rows if row.get("active")]
    return sorted(rows, key=lambda row: (row.get("display_priority") or 999, row["slug"]))


def main_sport_slugs() -> tuple:
    return tuple(row["slug"] for row in SPORTS if row.get("nav_group") == "main")


def directory_sport_slugs() -> tuple:
    return tuple(
        row["slug"]
        for row in SPORTS
        if row.get("nav_group") != "main" and row.get("directory_visible")
    )


def followable_sports() -> List[SportRecord]:
    return [row for row in all_sports(active_only=True) if row.get("followable")]


def prediction_sports() -> List[SportRecord]:
    return [row for row in all_sports(active_only=True) if row.get("supports_predictions")]


def live_filter_sports() -> List[SportRecord]:
    return [row for row in all_sports(active_only=True) if row.get("live_filter")]


def prediction_market(sport: Optional[str]) -> Optional[str]:
    row = get_sport(sport)
    if not row or not row.get("supports_predictions"):
        return None
    if row.get("event_model") == "team_match" and row.get("supports_draw"):
        return "1x2"
    if row.get("event_model") in {"team_match", "individual_match", "combat", "esports_match"}:
        return "winner"
    return None


def taxonomy_sports_map() -> Dict[str, Dict[str, str]]:
    return {
        row["slug"]: {
            "label": row["name"],
            "group": row.get("nav_group") or "other",
            "path": row.get("path") or f"/{row['slug']}",
        }
        for row in SPORTS
        if row.get("active")
    }


def catalog_rows(group: Optional[str] = None) -> List[Dict[str, object]]:
    rows = []
    for sport in all_sports(active_only=True):
        if group and sport.get("nav_group") != group:
            continue
        rows.append(public_sport(sport))
    return rows


def public_sport(sport: SportRecord) -> Dict[str, object]:
    return {
        "sport": sport["slug"],
        "id": sport["id"],
        "slug": sport["slug"],
        "label": sport["name"],
        "name": sport["name"],
        "short_name": sport.get("short_name") or sport["name"],
        "group": sport.get("nav_group") or "other",
        "category": sport.get("category"),
        "event_model": sport.get("event_model"),
        "participant_type": sport.get("participant_type"),
        "country_based": bool(sport.get("country_based")),
        "supports_draw": bool(sport.get("supports_draw")),
        "supports_live": bool(sport.get("supports_live")),
        "supports_standings": bool(sport.get("supports_standings")),
        "supports_rankings": bool(sport.get("supports_rankings")),
        "supports_predictions": bool(sport.get("supports_predictions")),
        "supports_odds": bool(sport.get("supports_odds")),
        "supports_news": bool(sport.get("supports_news")),
        "active": bool(sport.get("active")),
        "display_priority": sport.get("display_priority"),
        "path": sport.get("path") or f"/{sport['slug']}",
        "parent_id": sport.get("parent_id"),
        "followable": bool(sport.get("followable")),
        "directory_visible": bool(sport.get("directory_visible")),
        "live_filter": bool(sport.get("live_filter")),
        "esports_kind": sport.get("esports_kind"),
        "aliases": list(sport.get("aliases") or []),
    }


def sitemap_sport_paths() -> List[str]:
    seen = []
    for row in all_sports(active_only=True):
        path = row.get("path") or f"/{row['slug']}"
        if path not in seen:
            seen.append(path)
    return seen


def sport_id_set() -> set:
    return {row["id"] for row in SPORTS}


def validate_catalog() -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    seen_slugs = set()
    for row in SPORTS:
        sid = row.get("id")
        slug = row.get("slug")
        if not sid or not slug:
            errors.append(f"missing id/slug: {row}")
            continue
        if sid in seen_ids:
            errors.append(f"duplicate id: {sid}")
        if slug in seen_slugs:
            errors.append(f"duplicate slug: {slug}")
        seen_ids.add(sid)
        seen_slugs.add(slug)
        if row.get("event_model") not in EVENT_MODELS:
            errors.append(f"{slug} has invalid event_model")
        parent = row.get("parent_id")
        if parent and parent not in seen_ids and parent not in {item['id'] for item in SPORTS}:
            errors.append(f"{slug} parent {parent} is unknown")
    return errors


def registry_meta() -> Dict[str, object]:
    return {
        "version": REGISTRY_VERSION,
        "sport_count": len(SPORTS),
        "provider_independent": True,
    }
