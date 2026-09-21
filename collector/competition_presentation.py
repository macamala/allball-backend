"""Canonical public competition metadata for the frozen 180 registry.

Does not mutate source_matrix_final.json. Geography is never the sport name.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from collector.matrix_guard import frozen_competition_ids, matrix_status
from sports_registry.competitions import get_competition
from sports_registry.geography import get_geo, label_for

SPORT_GEOGRAPHY_BLOCKLIST = {
    "football",
    "soccer",
    "basketball",
    "tennis",
    "rugby",
    "rugby league",
    "rugby-league",
    "baseball",
    "ice hockey",
    "ice-hockey",
    "hockey",
    "cricket",
    "volleyball",
    "handball",
    "futsal",
    "motorsport",
    "golf",
    "esports",
}

SCOPE_DOMESTIC = "DOMESTIC"
SCOPE_CONTINENTAL = "CONTINENTAL"
SCOPE_WORLD = "WORLD"
SCOPE_INTERNATIONAL = "INTERNATIONAL"
SCOPE_REGIONAL = "REGIONAL"

# Sporting geography for domestic prefixes (not ISO UK collapse).
COUNTRY_PREFIX = {
    "albania": ("Albania", "al", SCOPE_DOMESTIC),
    "argentina": ("Argentina", "ar", SCOPE_DOMESTIC),
    "australia": ("Australia", "au", SCOPE_DOMESTIC),
    "austria": ("Austria", "at", SCOPE_DOMESTIC),
    "belgium": ("Belgium", "be", SCOPE_DOMESTIC),
    "bosnia": ("Bosnia and Herzegovina", "ba", SCOPE_DOMESTIC),
    "brazil": ("Brazil", "br", SCOPE_DOMESTIC),
    "bulgaria": ("Bulgaria", "bg", SCOPE_DOMESTIC),
    "canada": ("Canada", "ca", SCOPE_DOMESTIC),
    "chile": ("Chile", "cl", SCOPE_DOMESTIC),
    "china": ("China", "cn", SCOPE_DOMESTIC),
    "colombia": ("Colombia", "co", SCOPE_DOMESTIC),
    "costa-rica": ("Costa Rica", "cr", SCOPE_DOMESTIC),
    "croatia": ("Croatia", "hr", SCOPE_DOMESTIC),
    "czech": ("Czech Republic", "cz", SCOPE_DOMESTIC),
    "denmark": ("Denmark", "dk", SCOPE_DOMESTIC),
    "ecuador": ("Ecuador", "ec", SCOPE_DOMESTIC),
    "egypt": ("Egypt", "eg", SCOPE_DOMESTIC),
    "england": ("England", "england", SCOPE_DOMESTIC),
    "finland": ("Finland", "fi", SCOPE_DOMESTIC),
    "france": ("France", "fr", SCOPE_DOMESTIC),
    "germany": ("Germany", "de", SCOPE_DOMESTIC),
    "greece": ("Greece", "gr", SCOPE_DOMESTIC),
    "hungary": ("Hungary", "hu", SCOPE_DOMESTIC),
    "iceland": ("Iceland", "is", SCOPE_DOMESTIC),
    "india": ("India", "in", SCOPE_DOMESTIC),
    "indonesia": ("Indonesia", "id", SCOPE_DOMESTIC),
    "iran": ("Iran", "ir", SCOPE_DOMESTIC),
    "ireland": ("Ireland", "ie", SCOPE_DOMESTIC),
    "irish": ("Ireland", "ie", SCOPE_DOMESTIC),
    "italy": ("Italy", "it", SCOPE_DOMESTIC),
    "japan": ("Japan", "jp", SCOPE_DOMESTIC),
    "kazakhstan": ("Kazakhstan", "kz", SCOPE_DOMESTIC),
    "korea": ("South Korea", "kr", SCOPE_DOMESTIC),
    "korean": ("South Korea", "kr", SCOPE_DOMESTIC),
    "malaysia": ("Malaysia", "my", SCOPE_DOMESTIC),
    "mexico": ("Mexico", "mx", SCOPE_DOMESTIC),
    "morocco": ("Morocco", "ma", SCOPE_DOMESTIC),
    "netherlands": ("Netherlands", "nl", SCOPE_DOMESTIC),
    "norway": ("Norway", "no", SCOPE_DOMESTIC),
    "nsw": ("Australia", "au", SCOPE_DOMESTIC),
    "nz": ("New Zealand", "nz", SCOPE_DOMESTIC),
    "paraguay": ("Paraguay", "py", SCOPE_DOMESTIC),
    "poland": ("Poland", "pl", SCOPE_DOMESTIC),
    "portugal": ("Portugal", "pt", SCOPE_DOMESTIC),
    "romania": ("Romania", "ro", SCOPE_DOMESTIC),
    "saudi": ("Saudi Arabia", "sa", SCOPE_DOMESTIC),
    "scotland": ("Scotland", "scotland", SCOPE_DOMESTIC),
    "serbia": ("Serbia", "rs", SCOPE_DOMESTIC),
    "slovakia": ("Slovakia", "sk", SCOPE_DOMESTIC),
    "slovenia": ("Slovenia", "si", SCOPE_DOMESTIC),
    "south-africa": ("South Africa", "za", SCOPE_DOMESTIC),
    "spain": ("Spain", "es", SCOPE_DOMESTIC),
    "sweden": ("Sweden", "se", SCOPE_DOMESTIC),
    "switzerland": ("Switzerland", "ch", SCOPE_DOMESTIC),
    "thai": ("Thailand", "th", SCOPE_DOMESTIC),
    "tunisia": ("Tunisia", "tn", SCOPE_DOMESTIC),
    "turkey": ("Turkey", "tr", SCOPE_DOMESTIC),
    "ukraine": ("Ukraine", "ua", SCOPE_DOMESTIC),
    "uruguay": ("Uruguay", "uy", SCOPE_DOMESTIC),
    "usa": ("USA", "us", SCOPE_DOMESTIC),
    "uzbekistan": ("Uzbekistan", "uz", SCOPE_DOMESTIC),
    "vietnam": ("Vietnam", "vn", SCOPE_DOMESTIC),
    "wales": ("Wales", "wales", SCOPE_DOMESTIC),
    "northern-ireland": ("Northern Ireland", "northern-ireland", SCOPE_DOMESTIC),
}

EXPLICIT: Dict[str, Dict[str, str]] = {
    "afc-champions-league": {"geography_label": "Asia", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "AFC Champions League"},
    "africa-cup-of-nations": {"geography_label": "Africa", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "Africa Cup of Nations"},
    "all-england-open": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "All England Open"},
    "atp-tour": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "ATP Tour"},
    "bha-meetings": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "British Horseracing"},
    "biathlon": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Biathlon"},
    "caf-champions-league": {"geography_label": "Africa", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "CAF Champions League"},
    "cdl-majors": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Call of Duty League"},
    "cev-eurovolley-men": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "CEV EuroVolley"},
    "cfl": {"geography_label": "Canada", "country_code": "ca", "scope_type": SCOPE_DOMESTIC, "display_name": "CFL"},
    "champions-hockey-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "Champions Hockey League"},
    "competitive-ea-fc": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "EA Sports FC Pro"},
    "concacaf-champions-cup": {"geography_label": "North America", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "CONCACAF Champions Cup"},
    "copa-libertadores": {"geography_label": "South America", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "Copa Libertadores"},
    "copa-sudamericana": {"geography_label": "South America", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "Copa Sudamericana"},
    "cpbl": {"geography_label": "Taiwan", "country_code": "tw", "scope_type": SCOPE_DOMESTIC, "display_name": "CPBL"},
    "ehf-champions-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "EHF Champions League"},
    "ehf-competitions": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "EHF Competitions"},
    "ettu-events": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "ETTU Events"},
    "euroleague": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "EuroLeague"},
    "european-challenge-tour": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "Challenge Tour"},
    "fa-cup": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "FA Cup"},
    "fifa-connected-competitions": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "FIFA Competitions"},
    "fifa-futsal-when-listed": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "FIFA Futsal"},
    "fih-eurohockey": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "EuroHockey"},
    "fis-disciplines": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "FIS Winter Sports"},
    "fivb-competitions": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "FIVB Volleyball"},
    "formula-1": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Formula 1"},
    "formula-2": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Formula 2"},
    "formula-3": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Formula 3"},
    "formula-e": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Formula E"},
    "gbgb-meetings": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "GBGB Meetings"},
    "internationals-and-leagues": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "International Cricket"},
    "internationals-rwc": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Rugby Internationals"},
    "jurisdiction-meetings": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_INTERNATIONAL, "display_name": "Harness Meetings"},
    "kbo": {"geography_label": "South Korea", "country_code": "kr", "scope_type": SCOPE_DOMESTIC, "display_name": "KBO"},
    "khl": {"geography_label": "International", "country_code": None, "scope_type": SCOPE_INTERNATIONAL, "display_name": "KHL"},
    "korn-ferry-tour": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "Korn Ferry Tour"},
    "lol-world-championship": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "League of Legends Worlds"},
    "mlb": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "MLB"},
    "mls": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "MLS"},
    "motogp": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "MotoGP"},
    "nascar-arca": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NASCAR ARCA"},
    "nascar-truck": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NASCAR Truck"},
    "nba": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NBA"},
    "ncaa-football": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NCAA Football"},
    "nfl": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NFL"},
    "nhl": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "NHL"},
    "nll": {"geography_label": "North America", "country_code": None, "scope_type": SCOPE_REGIONAL, "display_name": "NLL"},
    "nordic-water-polo-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_REGIONAL, "display_name": "Nordic Water Polo"},
    "npb": {"geography_label": "Japan", "country_code": "jp", "scope_type": SCOPE_DOMESTIC, "display_name": "NPB"},
    "nrl": {"geography_label": "Australia", "country_code": "au", "scope_type": SCOPE_DOMESTIC, "display_name": "NRL"},
    "owcs-world-finals": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "OWCS World Finals"},
    "pdc-darts": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "PDC Darts"},
    "pga-tour": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "PGA Tour"},
    "pll": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "PLL"},
    "plusliga": {"geography_label": "Poland", "country_code": "pl", "scope_type": SCOPE_DOMESTIC, "display_name": "PlusLiga"},
    "premiership-rugby": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "Premiership Rugby"},
    "professional": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Dota 2 Professional"},
    "rlcs": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "RLCS"},
    "ssn-australia": {"geography_label": "Australia", "country_code": "au", "scope_type": SCOPE_DOMESTIC, "display_name": "Super Netball"},
    "super-league": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "Super League"},
    "super-rugby": {"geography_label": "Oceania", "country_code": None, "scope_type": SCOPE_REGIONAL, "display_name": "Super Rugby"},
    "t20-internationals": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "T20 Internationals"},
    "tier1": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Counter-Strike"},
    "title-fights": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "Boxing Title Fights"},
    "tour-de-france": {"geography_label": "France", "country_code": "fr", "scope_type": SCOPE_DOMESTIC, "display_name": "Tour de France"},
    "uci-calendar": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "UCI Cycling"},
    "uefa-champions-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "UEFA Champions League"},
    "uefa-conference-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "UEFA Conference League"},
    "uefa-europa-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "UEFA Europa League"},
    "uefa-futsal-champions-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "UEFA Futsal Champions League"},
    "uefa-nations-league": {"geography_label": "Europe", "country_code": None, "scope_type": SCOPE_CONTINENTAL, "display_name": "UEFA Nations League"},
    "ufc": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "UFC"},
    "uk-netball-superleague": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "Netball Super League"},
    "vct": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "VCT"},
    "wa-calendar": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Athletics"},
    "wec": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "WEC"},
    "wnba": {"geography_label": "USA", "country_code": "us", "scope_type": SCOPE_DOMESTIC, "display_name": "WNBA"},
    "womens-super-league": {"geography_label": "England", "country_code": "england", "scope_type": SCOPE_DOMESTIC, "display_name": "Women's Super League"},
    "world-aquatics-events": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Aquatics"},
    "world-aquatics-meets": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Aquatics Meets"},
    "world-lacrosse": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Lacrosse"},
    "world-netball": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Netball"},
    "wst-events": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "World Snooker"},
    "wta-tour": {"geography_label": "World", "country_code": None, "scope_type": SCOPE_WORLD, "display_name": "WTA Tour"},
}

DISPLAY_OVERRIDES = {
    "albania-superliga": "Kategoria Superiore",
    "argentina-primera": "Liga Profesional",
    "australia-a-league": "A-League Men",
    "australia-a-league-women": "A-League Women",
    "australia-afl": "AFL",
    "austria-bundesliga": "Austrian Bundesliga",
    "belgium-pro-league": "Belgian Pro League",
    "bosnia-premier-liga": "Premijer Liga",
    "brazil-lnf": "LNF",
    "brazil-serie-a": "Brasileirão",
    "bulgaria-first-league": "First League",
    "chile-primera": "Chilean Primera",
    "china-super-league": "Chinese Super League",
    "colombia-primera-a": "Categoría Primera A",
    "costa-rica-liga-fpd": "Liga FPD",
    "croatia-hnl": "HNL",
    "czech-first-league": "Czech First League",
    "denmark-handball-league": "Danish Handball League",
    "denmark-superliga": "Superliga",
    "ecuador-serie-a": "Liga Pro",
    "egypt-premier-league": "Egyptian Premier League",
    "england-championship": "Championship",
    "england-league-one": "League One",
    "england-league-two": "League Two",
    "england-premier-league": "Premier League",
    "finland-liiga": "Liiga",
    "finland-veikkausliiga": "Veikkausliiga",
    "france-letrot-meetings": "Le Trot",
    "france-ligue-1": "Ligue 1",
    "france-lnh": "LNH",
    "france-pro-d2": "Pro D2",
    "france-top-14": "Top 14",
    "germany-2-bundesliga": "2. Bundesliga",
    "germany-3-liga": "3. Liga",
    "germany-bundesliga": "Bundesliga",
    "germany-click-tt": "click-TT",
    "germany-del": "DEL",
    "germany-del2": "DEL2",
    "germany-dfb-pokal": "DFB-Pokal",
    "germany-frauen-bundesliga": "Frauen-Bundesliga",
    "germany-handball-bundesliga": "HBL",
    "greece-super-league": "Super League Greece",
    "hungary-nb-i": "NB I",
    "iceland-urvalsdeild": "Besta deild",
    "india-super-league": "Indian Super League",
    "indonesia-liga-1": "Liga 1",
    "indonesia-open": "Indonesia Open",
    "iran-pro-league": "Persian Gulf Pro League",
    "ireland-premier-division": "League of Ireland",
    "italy-coppa-italia": "Coppa Italia",
    "italy-serie-a": "Serie A",
    "italy-superlega": "SuperLega",
    "japan-j1": "J1 League",
    "korea-k-league-1": "K League 1",
    "korean-golf-tour": "Korean Golf Tour",
    "malaysia-super-league": "Malaysia Super League",
    "mexico-liga-mx": "Liga MX",
    "mexico-lnbp": "LNBP",
    "morocco-botola": "Botola",
    "netherlands-eredivisie": "Eredivisie",
    "norway-eliteserien": "Eliteserien",
    "npb": "NPB",
    "nsw-hrnsw-meetings": "HRNSW Meetings",
    "nz-national-league": "New Zealand National League",
    "nz-npc": "NPC",
    "paraguay-primera": "División Profesional",
    "poland-ekstraklasa": "Ekstraklasa",
    "portugal-primeira-liga": "Primeira Liga",
    "romania-superliga": "SuperLiga",
    "saudi-pro-league": "Saudi Pro League",
    "scotland-premiership": "Scottish Premiership",
    "serbia-superliga": "SuperLiga",
    "slovakia-super-liga": "Niké Liga",
    "slovenia-1-snl": "PrvaLiga",
    "south-africa-psl": "Premiership",
    "spain-acb": "Liga ACB",
    "spain-asobal": "Liga ASOBAL",
    "spain-copa-del-rey": "Copa del Rey",
    "spain-la-liga": "La Liga",
    "sweden-allsvenskan": "Allsvenskan",
    "sweden-shl": "SHL",
    "switzerland-super-league": "Swiss Super League",
    "thai-league-1": "Thai League 1",
    "tunisia-ligue-1": "Ligue 1",
    "turkey-super-lig": "Süper Lig",
    "ukraine-premier-league": "Ukrainian Premier League",
    "uruguay-primera": "Primera División",
    "usa-nwsl": "NWSL",
    "usa-usl-championship": "USL Championship",
    "usa-usta-meetings": "USTA Meetings",
    "uzbekistan-super-league": "Uzbekistan Super League",
    "vietnam-v-league-1": "V.League 1",
    "canada-standardbred-meetings": "Standardbred Canada",
}


def _title_from_key(key: str) -> str:
    text = str(key or "").replace("-", " ").strip()
    return " ".join(part.upper() if part in {"nba", "nfl", "nhl", "mlb", "mls", "ufc", "atp", "wta"} else part.capitalize() for part in text.split())


def _prefix_geo(key: str) -> Optional[tuple]:
    for slug in sorted(COUNTRY_PREFIX, key=len, reverse=True):
        if key == slug or key.startswith(f"{slug}-"):
            return COUNTRY_PREFIX[slug]
    return None


def _from_registry(key: str) -> Dict[str, Any]:
    row = get_competition(key) or {}
    country_id = row.get("country_id")
    region_id = row.get("region_id")
    if country_id in {"gb", "uk"}:
        country_id = None
    geo = ""
    code = country_id
    scope = SCOPE_DOMESTIC
    if country_id in {"england", "scotland", "wales", "northern-ireland"}:
        geo = label_for(country_id)
        code = country_id
        scope = SCOPE_DOMESTIC
    elif country_id:
        geo_row = get_geo(country_id)
        if geo_row and geo_row.get("kind") != "region":
            name = geo_row.get("name") or label_for(country_id)
            if name in {"United States", "United-States"}:
                name = "USA"
            geo = name
            code = country_id if country_id not in {"gb", "uk"} else None
            scope = SCOPE_DOMESTIC
    if not geo and region_id in {"europe", "asia", "africa", "north-america", "south-america", "oceania"}:
        geo = label_for(region_id)
        code = None
        scope = SCOPE_CONTINENTAL
    if not geo and region_id in {"world", "international", "global"}:
        geo = "World" if region_id == "world" else "International"
        code = None
        scope = SCOPE_WORLD if region_id == "world" else SCOPE_INTERNATIONAL
    return {
        "display_name": row.get("name") or row.get("official_name") or "",
        "geography_label": geo,
        "country_code": code,
        "scope_type": scope,
        "gender": row.get("gender"),
        "logo": row.get("logo") or row.get("artwork"),
    }


@lru_cache(maxsize=256)
def metadata_for(competition_key: str, sport: str = "") -> Dict[str, Any]:
    key = str(competition_key or "").strip()
    sport_id = str(sport or "").strip()
    explicit = dict(EXPLICIT.get(key) or {})
    registry = _from_registry(key)
    prefix = _prefix_geo(key)
    display = DISPLAY_OVERRIDES.get(key) or explicit.get("display_name") or registry.get("display_name") or _title_from_key(key)
    if prefix:
        geography, country_code, scope = prefix
    else:
        geography = explicit.get("geography_label") or registry.get("geography_label") or ""
        country_code = explicit.get("country_code") if "country_code" in explicit else registry.get("country_code")
        scope = explicit.get("scope_type") or registry.get("scope_type") or ""
    if explicit.get("geography_label"):
        geography = explicit["geography_label"]
        country_code = explicit.get("country_code")
        scope = explicit.get("scope_type") or scope
    if geography.lower().replace("-", " ") in SPORT_GEOGRAPHY_BLOCKLIST or geography.lower() == sport_id.replace("-", " "):
        geography = ""
        country_code = None
        scope = ""
    return {
        "competition_key": key,
        "sport": sport_id,
        "display_name": display,
        "geography_label": geography,
        "country_code": country_code or None,
        "scope_type": scope,
        "gender": registry.get("gender"),
        "logo": registry.get("logo"),
    }


def attach_competition_metadata(event: Dict[str, Any]) -> Dict[str, Any]:
    if not event:
        return event
    key = str(event.get("competition_key") or event.get("competition") or "")
    sport = str(event.get("sport") or "")
    meta = metadata_for(key, sport)
    event["competition_key"] = key
    event["competition"] = meta["display_name"]
    event["competition_name"] = meta["display_name"]
    event["geography_label"] = meta["geography_label"] or None
    event["scope_type"] = meta["scope_type"] or None
    event["country_id"] = meta["country_code"]
    event["country_based"] = meta["scope_type"] == SCOPE_DOMESTIC
    if meta.get("logo") and not event.get("competition_logo"):
        event["competition_logo"] = meta["logo"]
    return event


def frozen_metadata_rows() -> List[Dict[str, Any]]:
    from collector.matrix_guard import MATRIX_PATH
    import json

    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = payload.get("competitions") or []
    out = []
    for row in rows:
        key = str(row.get("competition") or "")
        sport = str(row.get("sport") or "")
        meta = metadata_for(key, sport)
        meta["sport"] = sport
        out.append(meta)
    return out


def validate_frozen_metadata() -> Dict[str, Any]:
    status = matrix_status()
    rows = frozen_metadata_rows()
    failures: List[Dict[str, Any]] = []
    sports = 0
    names = 0
    geos = 0
    sport_as_geo = 0
    for row in rows:
        if row.get("sport"):
            sports += 1
        else:
            failures.append({"competition_key": row.get("competition_key"), "reason": "missing_sport"})
        if row.get("display_name"):
            names += 1
        else:
            failures.append({"competition_key": row.get("competition_key"), "reason": "missing_display_name"})
        geo = str(row.get("geography_label") or "").strip()
        if geo:
            geos += 1
        else:
            failures.append({"competition_key": row.get("competition_key"), "reason": "missing_geography"})
        folded = geo.lower().replace("-", " ")
        if folded in SPORT_GEOGRAPHY_BLOCKLIST or folded == str(row.get("sport") or "").replace("-", " "):
            sport_as_geo += 1
            failures.append({"competition_key": row.get("competition_key"), "reason": "sport_as_geography", "value": geo})
        if row.get("scope_type") not in {SCOPE_DOMESTIC, SCOPE_CONTINENTAL, SCOPE_WORLD, SCOPE_INTERNATIONAL, SCOPE_REGIONAL}:
            failures.append({"competition_key": row.get("competition_key"), "reason": "invalid_scope", "value": row.get("scope_type")})
    return {
        "matrix_ok": status.get("clean_full_180"),
        "count": len(rows),
        "valid_sport": sports,
        "valid_display_name": names,
        "valid_geography": geos,
        "sport_as_geography": sport_as_geo,
        "failures": failures,
        "ok": status.get("clean_full_180") and not failures and len(rows) == 180,
    }
