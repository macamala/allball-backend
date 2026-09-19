"""Honest remaining gaps after Phase 2 free/public source work."""

from __future__ import annotations

from typing import Dict, List

from collector.discovery_inventory import sports_missing_technically_collectable_source, sports_with_technically_collectable_source
from sports_registry.sports import SPORTS

SPORTS_WITH_FREE_SOURCE = {
    "football",
    "basketball",
    "american-football",
    "ice-hockey",
    "baseball",
    "rugby",
    "cricket",
    "volleyball",
    "handball",
    "australian-rules",
    "motorsport",
    "golf",
    "darts",
    "dota-2",
}

SPORT_GAPS: Dict[str, str] = {
    "football": "OpenLigaDB + openfootball cover selected European/Brazilian leagues and UCL, not worldwide domestic cups. FIFA/PulseLive backends exist but are not licensed for republication.",
    "basketball": "NBA/EuroLeague/WNBA/LNBP truncated TheSportsDB. EuroLeague Competition Engine and FIBA/DataProject exist but need keys/permission.",
    "tennis": "No free commercial ATP/WTA/ITF API. Grand Slam official feeds are licensed.",
    "motorsport": "Only NASCAR Truck/ARCA events verified. F1/MotoGP/WEC community APIs are NC or paid.",
    "american-football": "NFL and NCAA D1 only, truncated. No CFL/UFL free API.",
    "ice-hockey": "OpenLigaDB DEL/DEL2/CHL plus truncated NHL/Liiga/KHL. Liiga old JSON redirected; SHL needs client credentials; NHL stats API is not a free commercial licence.",
    "baseball": "MLB/NPB/KBO/CPBL only. No NPB farm or MiLB.",
    "rugby": "World Rugby PulseLive JSON works technically; World Rugby terms forbid spidering/republication without permission. TheSportsDB Pro D2/NPC remain truncated.",
    "rugby-league": "NRL official draw endpoint returned a bot interstitial. Super League/NRL licensed feeds remain D. TheSportsDB NRL was rate-limited in Phase 2.",
    "cricket": "Cricsheet covers delayed international and domestic results (ODC-By). No free live scoring feed.",
    "volleyball": "Men's EuroVolley window only.",
    "handball": "German, Danish, EHF CL. No IHF world championship free API.",
    "futsal": "No verified free source.",
    "water-polo": "No verified free source.",
    "field-hockey": "Altiusrt is the FIH/EuroHockey platform family; the REST API requires a key (401 unauthenticated). Public pages exist.",
    "australian-rules": "Squiggle covers the AFL men's season. Official AFL/Champion Data and AFLW remain licensed. PulseLive AFL backend is 403 without permission.",
    "netball": "No events on probe day.",
    "lacrosse": "No verified free source.",
    "table-tennis": "No verified free source (ITTF licensed).",
    "badminton": "No verified free source (BWF licensed).",
    "snooker": "snooker.org is non-commercial without permission.",
    "darts": "OpenLigaDB PDC World Championship plus truncated TheSportsDB. No PDC live feed.",
    "boxing": "Fighting feed was wrestling; BoxRec disallowed.",
    "mma": "No free official UFC/ONE API.",
    "horse-racing": "No free official country-meeting API; bookmakers disallowed.",
    "greyhound-racing": "No free official API.",
    "harness-racing": "No free official API.",
    "golf": "Challenge/Korn Ferry/Korean tours only. PGA/DP World Tour licensed.",
    "cycling": "No documented free commercial UCI calendar API.",
    "athletics": "World Athletics Distribution API is not a documented public feed.",
    "swimming": "No World Aquatics public results API.",
    "winter-sports": "FIS pages are not a licensed bulk API.",
    "esports": "Parent catalog only; no generic esports bus.",
    "ea-sports-fc": "No free competitive API.",
    "counter-strike": "HLTV disallowed; no official free match API.",
    "league-of-legends": "Riot API needs a production key.",
    "dota-2": "OpenDota pro matches only, not pubs or every amateur league.",
    "valorant": "VLR disallowed; Riot key required.",
    "call-of-duty": "No free official match API.",
    "overwatch": "No free official match API.",
    "rocket-league": "No free official match API.",
}


def sports_without_free_source() -> List[str]:
    return sorted(row["slug"] for row in SPORTS if row["slug"] not in SPORTS_WITH_FREE_SOURCE)


def sports_without_technically_collectable_source() -> List[str]:
    return sports_missing_technically_collectable_source()


def technically_collectable_sport_count() -> int:
    return len(sports_with_technically_collectable_source())
