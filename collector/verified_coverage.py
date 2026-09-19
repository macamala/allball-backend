"""Verified free/public source mappings.

Every competition listed here was probed against a live endpoint before
registration. Truncated free-tier responses still count as coverage of that
competition, not of the whole sport.
"""

from __future__ import annotations

from typing import Dict, List, TypedDict


class OpenFootballFile(TypedDict):
    paths: List[str]
    competition_id: str
    sport_id: str
    name: str
    country_id: str
    region_id: str


class OpenLigaMapping(TypedDict):
    shortcut: str
    competition_id: str
    sport_id: str
    name: str
    country_id: str
    region_id: str
    event_model: str


class SportsDbLeague(TypedDict):
    source_competition_id: str
    competition_id: str
    sport_id: str
    name: str
    country_id: str
    region_id: str
    event_model: str


OPENFOOTBALL_FILES: List[OpenFootballFile] = [
    {
        "paths": ["2026-27/en.1.json", "2025-26/en.1.json"],
        "competition_id": "england-premier-league",
        "sport_id": "football",
        "name": "Premier League",
        "country_id": "england",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/en.2.json", "2025-26/en.2.json"],
        "competition_id": "england-championship",
        "sport_id": "football",
        "name": "Championship",
        "country_id": "england",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/de.1.json", "2025-26/de.1.json"],
        "competition_id": "germany-bundesliga",
        "sport_id": "football",
        "name": "Bundesliga",
        "country_id": "de",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/es.1.json", "2025-26/es.1.json"],
        "competition_id": "spain-la-liga",
        "sport_id": "football",
        "name": "La Liga",
        "country_id": "es",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/fr.1.json", "2025-26/fr.1.json"],
        "competition_id": "france-ligue-1",
        "sport_id": "football",
        "name": "Ligue 1",
        "country_id": "fr",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/it.1.json", "2025-26/it.1.json"],
        "competition_id": "italy-serie-a",
        "sport_id": "football",
        "name": "Serie A",
        "country_id": "it",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/nl.1.json", "2025-26/nl.1.json"],
        "competition_id": "netherlands-eredivisie",
        "sport_id": "football",
        "name": "Eredivisie",
        "country_id": "nl",
        "region_id": "europe",
    },
    {
        "paths": ["2026-27/pt.1.json", "2025-26/pt.1.json"],
        "competition_id": "portugal-primeira-liga",
        "sport_id": "football",
        "name": "Primeira Liga",
        "country_id": "pt",
        "region_id": "europe",
    },
    {
        "paths": ["2026/br.1.json"],
        "competition_id": "brazil-serie-a",
        "sport_id": "football",
        "name": "Brasileirão",
        "country_id": "br",
        "region_id": "south-america",
    },
    {
        "paths": ["2025-26/at.1.json"],
        "competition_id": "austria-bundesliga",
        "sport_id": "football",
        "name": "Austrian Bundesliga",
        "country_id": "at",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/at.2.json"],
        "competition_id": "austria-2-liga",
        "sport_id": "football",
        "name": "Austrian 2. Liga",
        "country_id": "at",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/be.1.json"],
        "competition_id": "belgium-pro-league",
        "sport_id": "football",
        "name": "Belgian Pro League",
        "country_id": "be",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/en.3.json"],
        "competition_id": "england-league-one",
        "sport_id": "football",
        "name": "EFL League One",
        "country_id": "england",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/en.4.json"],
        "competition_id": "england-league-two",
        "sport_id": "football",
        "name": "EFL League Two",
        "country_id": "england",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/es.2.json"],
        "competition_id": "spain-segunda-division",
        "sport_id": "football",
        "name": "Spanish Segunda División",
        "country_id": "es",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/fr.2.json"],
        "competition_id": "france-ligue-2",
        "sport_id": "football",
        "name": "Ligue 2",
        "country_id": "fr",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/gr.1.json"],
        "competition_id": "greece-super-league",
        "sport_id": "football",
        "name": "Greek Super League",
        "country_id": "gr",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/it.2.json"],
        "competition_id": "italy-serie-b",
        "sport_id": "football",
        "name": "Serie B",
        "country_id": "it",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/sco.1.json"],
        "competition_id": "scotland-premiership",
        "sport_id": "football",
        "name": "Scottish Premiership",
        "country_id": "scotland",
        "region_id": "europe",
    },
    {
        "paths": ["2025-26/tr.1.json"],
        "competition_id": "turkey-super-lig",
        "sport_id": "football",
        "name": "Süper Lig",
        "country_id": "tr",
        "region_id": "europe",
    },
]

OPENLIGADB_LEAGUES: List[OpenLigaMapping] = [
    {
        "shortcut": "bl1",
        "competition_id": "germany-bundesliga",
        "sport_id": "football",
        "name": "Bundesliga",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "bl2",
        "competition_id": "germany-2-bundesliga",
        "sport_id": "football",
        "name": "2. Bundesliga",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "bl3",
        "competition_id": "germany-3-liga",
        "sport_id": "football",
        "name": "3. Liga",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "dfb",
        "competition_id": "germany-dfb-pokal",
        "sport_id": "football",
        "name": "DFB-Pokal",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "del",
        "competition_id": "germany-del",
        "sport_id": "ice-hockey",
        "name": "DEL",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "ucl",
        "competition_id": "uefa-champions-league",
        "sport_id": "football",
        "name": "UEFA Champions League",
        "country_id": "",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "fbl1",
        "competition_id": "germany-frauen-bundesliga",
        "sport_id": "football",
        "name": "Frauen-Bundesliga",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "fbl2",
        "competition_id": "germany-frauen-2-bundesliga",
        "sport_id": "football",
        "name": "2. Frauen-Bundesliga",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "del2",
        "competition_id": "germany-del2",
        "sport_id": "ice-hockey",
        "name": "DEL2",
        "country_id": "de",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "CHL",
        "competition_id": "champions-hockey-league",
        "sport_id": "ice-hockey",
        "name": "Champions Hockey League",
        "country_id": "",
        "region_id": "europe",
        "event_model": "team_match",
    },
    {
        "shortcut": "PDCWM",
        "competition_id": "pdc-darts",
        "sport_id": "darts",
        "name": "PDC World Championship",
        "country_id": "",
        "region_id": "europe",
        "event_model": "individual_match",
    },
]

# League IDs probed on 2026-09-17 against TheSportsDB v1 free key.
THESPORTSDB_LEAGUES: List[SportsDbLeague] = [
    {"source_competition_id": "4328", "competition_id": "england-premier-league", "sport_id": "football", "name": "English Premier League", "country_id": "england", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4335", "competition_id": "spain-la-liga", "sport_id": "football", "name": "Spanish La Liga", "country_id": "es", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4331", "competition_id": "germany-bundesliga", "sport_id": "football", "name": "German Bundesliga", "country_id": "de", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4332", "competition_id": "italy-serie-a", "sport_id": "football", "name": "Italian Serie A", "country_id": "it", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4334", "competition_id": "france-ligue-1", "sport_id": "football", "name": "French Ligue 1", "country_id": "fr", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4399", "competition_id": "germany-2-bundesliga", "sport_id": "football", "name": "German 2. Bundesliga", "country_id": "de", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4480", "competition_id": "uefa-champions-league", "sport_id": "football", "name": "UEFA Champions League", "country_id": "", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "5071", "competition_id": "uefa-conference-league", "sport_id": "football", "name": "UEFA Conference League", "country_id": "", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4684", "competition_id": "usa-usl-championship", "sport_id": "football", "name": "USL Championship", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "5076", "competition_id": "usa-usl-league-one", "sport_id": "football", "name": "USL League One", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4845", "competition_id": "sweden-division-1-south", "sport_id": "football", "name": "Swedish Division 1 South", "country_id": "se", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4546", "competition_id": "euroleague", "sport_id": "basketball", "name": "EuroLeague Basketball", "country_id": "", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4387", "competition_id": "nba", "sport_id": "basketball", "name": "NBA", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4516", "competition_id": "wnba", "sport_id": "basketball", "name": "WNBA", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "5119", "competition_id": "mexico-lnbp", "sport_id": "basketball", "name": "Mexican LNBP", "country_id": "mx", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4391", "competition_id": "nfl", "sport_id": "american-football", "name": "NFL", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4479", "competition_id": "ncaa-football", "sport_id": "american-football", "name": "NCAA Division 1 Football", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4380", "competition_id": "nhl", "sport_id": "ice-hockey", "name": "NHL", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4931", "competition_id": "finland-liiga", "sport_id": "ice-hockey", "name": "Finnish Liiga", "country_id": "fi", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4920", "competition_id": "khl", "sport_id": "ice-hockey", "name": "KHL", "country_id": "ru", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4424", "competition_id": "mlb", "sport_id": "baseball", "name": "MLB", "country_id": "us", "region_id": "north-america", "event_model": "team_match"},
    {"source_competition_id": "4591", "competition_id": "npb", "sport_id": "baseball", "name": "Nippon Professional Baseball", "country_id": "jp", "region_id": "asia", "event_model": "team_match"},
    {"source_competition_id": "4830", "competition_id": "kbo", "sport_id": "baseball", "name": "KBO League", "country_id": "kr", "region_id": "asia", "event_model": "team_match"},
    {"source_competition_id": "5111", "competition_id": "cpbl", "sport_id": "baseball", "name": "Chinese Professional Baseball League", "country_id": "tw", "region_id": "asia", "event_model": "team_match"},
    {"source_competition_id": "5172", "competition_id": "france-pro-d2", "sport_id": "rugby", "name": "French Pro D2", "country_id": "fr", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "5278", "competition_id": "nz-npc", "sport_id": "rugby", "name": "New Zealand NPC", "country_id": "nz", "region_id": "oceania", "event_model": "team_match"},
    {"source_competition_id": "4979", "competition_id": "t20-internationals", "sport_id": "cricket", "name": "Twenty20 Internationals", "country_id": "", "region_id": "world", "event_model": "team_match"},
    {"source_competition_id": "5613", "competition_id": "cev-eurovolley-men", "sport_id": "volleyball", "name": "Men's European Volleyball Championship", "country_id": "", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4533", "competition_id": "germany-handball-bundesliga", "sport_id": "handball", "name": "German Handball-Bundesliga", "country_id": "de", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "5135", "competition_id": "denmark-handball-league", "sport_id": "handball", "name": "Danish Men's Handball League", "country_id": "dk", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4980", "competition_id": "ehf-champions-league", "sport_id": "handball", "name": "EHF Champions League", "country_id": "", "region_id": "europe", "event_model": "team_match"},
    {"source_competition_id": "4456", "competition_id": "australia-afl", "sport_id": "australian-rules", "name": "Australian AFL", "country_id": "au", "region_id": "oceania", "event_model": "team_match"},
    {"source_competition_id": "5093", "competition_id": "nascar-truck", "sport_id": "motorsport", "name": "NASCAR Truck Series", "country_id": "us", "region_id": "north-america", "event_model": "motorsport_race"},
    {"source_competition_id": "5094", "competition_id": "nascar-arca", "sport_id": "motorsport", "name": "NASCAR ARCA Series", "country_id": "us", "region_id": "north-america", "event_model": "motorsport_race"},
    {"source_competition_id": "4758", "competition_id": "european-challenge-tour", "sport_id": "golf", "name": "European Challenge Tour", "country_id": "", "region_id": "europe", "event_model": "tournament"},
    {"source_competition_id": "4766", "competition_id": "korean-golf-tour", "sport_id": "golf", "name": "Korean Tour", "country_id": "kr", "region_id": "asia", "event_model": "tournament"},
    {"source_competition_id": "4763", "competition_id": "korn-ferry-tour", "sport_id": "golf", "name": "Korn Ferry Tour", "country_id": "us", "region_id": "north-america", "event_model": "tournament"},
    {"source_competition_id": "4554", "competition_id": "pdc-darts", "sport_id": "darts", "name": "PDC Darts", "country_id": "", "region_id": "europe", "event_model": "individual_match"},
]


LICENSED_UNRESOLVED: List[Dict[str, str]] = [
    {"sport_id": "football", "source": "Sportradar / Stats Perform / football-data.org commercial", "reason": "Paid commercial live-data licences"},
    {"sport_id": "basketball", "source": "NBA official stats / Sportradar", "reason": "Official NBA redistribution requires a licence"},
    {"sport_id": "tennis", "source": "ATP/WTA/ITF official data", "reason": "No free commercial API; tournament feeds are licensed"},
    {"sport_id": "motorsport", "source": "Formula 1 official / Jolpica commercial / OpenF1 commercial", "reason": "Community F1 APIs are NC; official F1 is licensed"},
    {"sport_id": "american-football", "source": "NFL official data", "reason": "Commercial live feeds are licensed"},
    {"sport_id": "ice-hockey", "source": "NHL official data", "reason": "Commercial live feeds are licensed"},
    {"sport_id": "baseball", "source": "MLB Stats API commercial terms", "reason": "Republication typically requires an MLB licence"},
    {"sport_id": "snooker", "source": "snooker.org API", "reason": "Non-commercial unless permission; requires approved X-Requested-By"},
    {"sport_id": "esports", "source": "PandaScore / GRID / Abios", "reason": "Paid esports data platforms"},
    {"sport_id": "league-of-legends", "source": "Riot Games API", "reason": "Needs a registered production key and Riot terms review"},
    {"sport_id": "valorant", "source": "Riot Games API", "reason": "Needs a registered production key"},
    {"sport_id": "counter-strike", "source": "Licensed esports data; HLTV is disallowed", "reason": "No free official match API"},
    {"sport_id": "horse-racing", "source": "Racing API / Betfair / Racing Post", "reason": "Paid or bookmaker; bookmakers are disallowed"},
    {"sport_id": "cycling", "source": "UCI / ASO official", "reason": "No documented free commercial results API"},
    {"sport_id": "boxing", "source": "BoxRec is disallowed; CompuBox licensed", "reason": "No free official bout API"},
    {"sport_id": "mma", "source": "UFC official / licensed stats", "reason": "No free official fight API"},
    {"sport_id": "football", "source": "FIFA Digital Platforms API", "reason": "Public JSON works; FIFA ToS require permission for commercial republication"},
    {"sport_id": "field-hockey", "source": "Altiusrt / FIH TMS", "reason": "REST API requires an Altiusrt API key"},
    {"sport_id": "rugby", "source": "World Rugby PulseLive RIMS", "reason": "JSON works; terms forbid spidering/republication without written permission"},
    {"sport_id": "badminton", "source": "BWF extranet API", "reason": "Registration required; public Tournament Software fan site closed"},
    {"sport_id": "ice-hockey", "source": "SHL Open API", "reason": "Client ID/secret registration"},
    {"sport_id": "esports", "source": "start.gg GraphQL", "reason": "Personal access token required"},
]


def extra_competitions() -> List[Dict[str, str]]:
    seen = {}
    for row in OPENFOOTBALL_FILES + OPENLIGADB_LEAGUES + THESPORTSDB_LEAGUES:
        seen[row["competition_id"]] = row
    return list(seen.values())
