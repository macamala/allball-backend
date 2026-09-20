"""Redundancy discovery inventory.

technically_collectable is independent of production_reuse_status
(permitted | unclear | restricted).

upstream_family identifies the underlying system. Two sites that wrap the
same family are not strong independent fallbacks.

derived_from, when set, means the source is compiled from another family
and does not add true independence from that family.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, TypedDict

from sports_registry.sports import SPORTS


class SourceRow(TypedDict, total=False):
    sport_id: str
    source: str
    coverage: str
    method: str
    live: str
    fixtures: str
    results: str
    standings: str
    technically_collectable: bool
    production_reuse_status: str
    implemented: str
    upstream_family: str
    derived_from: str


class CoverageRow(TypedDict, total=False):
    sport: str
    country: str
    competition: str
    source: str
    upstream_family: str
    collection_method: str
    live: str
    fixtures: str
    results: str
    standings: str
    stats: str
    lineups: str
    incidents: str
    technically_collectable: bool
    production_reuse_status: str
    priority_candidate: int
    derived_from: str
    probe: str
    coverage_scope: str
    independence_status: str


def _c(
    *args,
    derived_from: str = "",
    probe: str = "",
    coverage_scope: str = "full",
    independence_status: str = "established",
) -> CoverageRow:
    collectable, reuse, priority = args[-3], args[-2], args[-1]
    sport, country, competition, source, family, method = args[:6]
    caps = list(args[6:-3])
    while len(caps) < 7:
        caps.append("N")
    live, fixtures, results, standings, stats, lineups, incidents = caps[:7]
    return {
        "sport": sport,
        "country": country,
        "competition": competition,
        "source": source,
        "upstream_family": family,
        "collection_method": method,
        "live": live,
        "fixtures": fixtures,
        "results": results,
        "standings": standings,
        "stats": stats,
        "lineups": lineups,
        "incidents": incidents,
        "technically_collectable": collectable,
        "production_reuse_status": reuse,
        "priority_candidate": priority,
        "derived_from": derived_from,
        "probe": probe,
        "coverage_scope": coverage_scope,
        "independence_status": independence_status,
    }


# Probes 17 Sep 2026 from this environment unless noted as prior-pass.
COVERAGE: List[CoverageRow] = [
    # --- football (competition-level) ---
    _c("football", "england", "england-premier-league", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="prior+mapped"),
    _c("football", "england", "england-premier-league", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="prior+mapped"),
    _c("football", "england", "england-premier-league", "BBC Sport scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("football", "england", "england-premier-league", "premierleague.com tables", "premier-league-official", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 4, probe="200"),
    _c("football", "england", "england-premier-league", "Wikipedia/Wikidata", "wikimedia", "public HTML/SPARQL", "N", "partial", "Y", "Y", "N", "N", "N", True, "permitted", 5, probe="200"),
    _c("football", "england", "england-championship", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "england", "england-league-one", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "england", "england-league-two", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "de", "germany-bundesliga", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "de", "germany-bundesliga", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "de", "germany-bundesliga", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="mapped"),
    _c("football", "de", "germany-2-bundesliga", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "de", "germany-2-bundesliga", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "de", "germany-3-liga", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "de", "germany-dfb-pokal", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "de", "germany-frauen-bundesliga", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "es", "spain-la-liga", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "es", "spain-la-liga", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "it", "italy-serie-a", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "it", "italy-serie-a", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "fr", "france-ligue-1", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "fr", "france-ligue-1", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "nl", "netherlands-eredivisie", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "pt", "portugal-primeira-liga", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "br", "brazil-serie-a", "openfootball/football.json", "openfootball", "GitHub raw JSON", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "br", "brazil-serie-a", "Wikipedia/Wikidata", "wikimedia", "public HTML/SPARQL", "N", "partial", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="family"),
    _c("football", "europe", "uefa-champions-league", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "europe", "uefa-champions-league", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "europe", "uefa-champions-league", "FIFA Digital JSON", "fifa-digital", "unauthenticated JSON", "when listed", "when listed", "when listed", "N", "N", "N", "N", True, "restricted", 3, probe="prior JSON 200"),
    _c("football", "europe", "uefa-conference-league", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("football", "world", "fifa-connected-competitions", "FIFA api.fifa.com v3", "fifa-digital", "unauthenticated JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 1, probe="prior JSON 200"),
    _c("football", "us", "usa-usl-championship", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("football", "rs", "serbia-superliga", "Wikipedia SuperLiga pages", "wikimedia", "public HTML", "N", "partial", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="wiki family; no second independent feed found this pass"),
    _c("football", "england", "england-premier-league", "ESPN site.api JSON", "espn-site-api", "unauthenticated JSON", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("football", "world", "multi-league", "football-data.co.uk CSV", "football-data-co-uk", "public CSV", "N", "N", "Y", "N", "shots", "N", "N", False, "restricted", 99, derived_from="aggregator-incl-flashscore-bbc-espn", probe="connection refused this host"),
    # --- basketball ---
    _c("basketball", "europe", "euroleague", "live.euroleague.net Header JSON", "euroleague-live", "unauthenticated JSON", "Y", "partial", "Y", "N", "boxscore", "N", "N", True, "unclear", 1, probe="prior JSON 200"),
    _c("basketball", "europe", "euroleague", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("basketball", "us", "nba", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("basketball", "us", "nba", "nba.com/games HTML", "nba-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "Y", "N", True, "restricted", 2, probe="200"),
    _c("basketball", "us", "nba", "Basketball-Reference", "sports-reference", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 3, derived_from="nba-compiled", probe="200"),
    _c("basketball", "us", "nba", "cdn.nba.com live JSON", "nba-cdn", "unauthenticated JSON", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("basketball", "us", "nba", "ESPN NBA scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="www.espn.com/nba/scoreboard __espnfitt__"),
    _c("basketball", "us", "wnba", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("basketball", "mx", "mexico-lnbp", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    # --- tennis ---
    _c("tennis", "world", "atp-tour", "Jeff Sackmann GitHub CSV", "sackmann-tennis", "public GitHub CSV", "N", "N", "Y", "rankings", "Y", "N", "N", True, "restricted", 1, probe="github public"),
    _c("tennis", "world", "atp-tour", "Wikipedia 2026 ATP Tour", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200"),
    _c("tennis", "world", "wta-tour", "Jeff Sackmann GitHub CSV", "sackmann-tennis", "public GitHub CSV", "N", "N", "Y", "rankings", "Y", "N", "N", True, "restricted", 1, probe="github public"),
    _c("tennis", "world", "wta-tour", "Wikipedia WTA pages", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- motorsport ---
    _c("motorsport", "world", "formula-1", "Jolpica F1 JSON", "jolpica-ergast", "unauthenticated JSON", "N", "Y", "Y", "Y", "laps", "N", "N", True, "restricted", 1, probe="prior JSON 200"),
    _c("motorsport", "world", "formula-1", "OpenF1", "openf1", "unauthenticated JSON", "session", "Y", "Y", "N", "telemetry", "N", "flags", True, "restricted", 2, probe="prior"),
    _c("motorsport", "world", "formula-1", "formula1.com results HTML", "formula1-web", "public HTML", "session", "Y", "Y", "Y", "Y", "Y", "N", True, "restricted", 3, probe="200"),
    _c("motorsport", "world", "motogp", "api.motogp.pulselive.com", "pulselive", "unauthenticated JSON", "timing", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 1, probe="200 seasons JSON"),
    _c("motorsport", "us", "nascar-truck", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("motorsport", "us", "nascar-arca", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    # --- american football ---
    _c("american-football", "us", "nfl", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("american-football", "us", "nfl", "ESPN.com scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="202 HTML"),
    _c("american-football", "us", "nfl", "Wikipedia NFL season", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="wiki family"),
    _c("american-football", "us", "ncaa-football", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("american-football", "us", "ncaa-football", "Wikipedia NCAA pages", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- ice hockey ---
    _c("ice-hockey", "us", "nhl", "NHL api-web.nhle.com", "nhl-web", "unauthenticated JSON", "Y", "Y", "Y", "N", "Y", "Y", "Y", True, "unclear", 1, probe="prior JSON 200"),
    _c("ice-hockey", "us", "nhl", "ESPN NHL scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="www.espn.com/nhl/scoreboard __espnfitt__"),
    _c("ice-hockey", "us", "nhl", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("ice-hockey", "us", "nhl", "Hockey-Reference", "sports-reference", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 3, derived_from="nhl-compiled", probe="200"),
    _c("ice-hockey", "us", "nhl", "MoneyPuck CSV downloads", "moneypuck", "public CSV", "N", "N", "Y", "N", "Y", "N", "shots", True, "restricted", 4, derived_from="nhl-web", probe="200"),
    _c("ice-hockey", "ru", "khl", "KHL mobile JSON", "khl-mobile", "unauthenticated JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="prior JSON 200"),
    _c("ice-hockey", "ru", "khl", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("ice-hockey", "de", "germany-del", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("ice-hockey", "de", "germany-del2", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("ice-hockey", "europe", "champions-hockey-league", "OpenLigaDB", "openligadb", "public JSON", "inferred", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("ice-hockey", "fi", "finland-liiga", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    # --- baseball ---
    _c("baseball", "us", "mlb", "MLB Stats API schedule", "mlb-statsapi", "unauthenticated JSON", "Y", "Y", "Y", "Y", "Y", "Y", "N", True, "restricted", 1, probe="prior JSON 200"),
    _c("baseball", "us", "mlb", "ESPN MLB scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="espnfitt lnescrs R/H/E not innings"),
    _c("baseball", "us", "mlb", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("baseball", "us", "mlb", "Retrosheet gamelogs", "retrosheet", "public HTML/files", "N", "N", "Y", "N", "Y", "Y", "Y", True, "permitted", 3, probe="200"),
    _c("baseball", "jp", "npb", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("baseball", "kr", "kbo", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("baseball", "tw", "cpbl", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    # --- rugby ---
    _c("rugby", "world", "internationals-rwc", "World Rugby RIMS JSON", "pulselive", "unauthenticated JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 1, probe="prior JSON 200"),
    _c("rugby", "fr", "france-pro-d2", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("rugby", "nz", "nz-npc", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("rugby", "world", "internationals-rwc", "Wikipedia rugby pages", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- rugby league ---
    _c("rugby-league", "england", "super-league", "superleague.co.uk", "super-league-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("rugby-league", "au", "nrl", "nrl.com/draw HTML", "nrl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 1, probe="200 HTML; /draw/data still interstitial"),
    _c("rugby-league", "au", "nrl", "nrl.com/draw/data JSON", "nrl-web", "JSON behind interstitial", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="bot interstitial"),
    _c("rugby-league", "england", "super-league", "Wikipedia Super League", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- cricket ---
    _c("cricket", "world", "internationals-and-leagues", "Cricsheet zip JSON", "cricsheet", "ODC-By zip JSON", "N", "rare", "Y", "N", "ball-by-ball", "Y", "N", True, "permitted", 1, probe="prior"),
    _c("cricket", "world", "t20-internationals", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("cricket", "world", "internationals-and-leagues", "Wikipedia cricket scorecards", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "partial", "N", "N", True, "permitted", 3, probe="wiki family"),
    _c("cricket", "world", "live-scorecards", "ESPNcricinfo HTML", "espncricinfo", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    # --- volleyball ---
    _c("volleyball", "europe", "cev-eurovolley-men", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("volleyball", "world", "fivb-competitions", "volleyballworld.com", "fivb-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="200"),
    _c("volleyball", "it", "italy-superlega", "DataProject WCM HTML", "dataproject-wcm", "public HTML", "Y", "Y", "Y", "Y", "Y", "Y", "N", True, "unclear", 1, probe="timeout this pass; prior family HTML 200"),
    # --- handball ---
    _c("handball", "de", "germany-handball-bundesliga", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("handball", "dk", "denmark-handball-league", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("handball", "europe", "ehf-champions-league", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("handball", "europe", "ehf-champions-league", "ehfcl.eurohandball.com", "ehf-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("handball", "europe", "ehf-competitions", "eurohandball.com", "ehf-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    # --- futsal ---
    _c("futsal", "world", "fifa-futsal-when-listed", "FIFA Digital JSON", "fifa-digital", "unauthenticated JSON", "when listed", "when listed", "when listed", "N", "N", "N", "N", True, "restricted", 1, probe="prior"),
    _c("futsal", "world", "fifa-futsal-when-listed", "en.wikipedia.org 2024 FIFA Futsal World Cup", "wikipedia-fifa-futsal-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="Brazil 2-1 Argentina 6 Oct 2024"),
    # --- water polo ---
    _c("water-polo", "world", "world-aquatics-events", "Omega Timing HTML", "omega-timing", "public HTML", "event", "Y", "Y", "N", "Y", "N", "N", True, "unclear", 1, probe="prior 200; DNS fail this pass"),
    _c("water-polo", "world", "world-aquatics-events", "Wikipedia water polo", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- field hockey ---
    _c("field-hockey", "world", "fih-eurohockey", "Altiusrt public HTML", "altiusrt", "public HTML", "Y", "Y", "Y", "Y", "Y", "Y", "N", True, "unclear", 1, probe="prior HTML 200 REST 401"),
    _c("field-hockey", "world", "fih-eurohockey", "fih.hockey", "fih-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    # --- australian rules ---
    _c("australian-rules", "au", "australia-afl", "Squiggle AFL JSON", "squiggle", "unauthenticated JSON", "Y", "Y", "Y", "via games", "Y", "N", "N", True, "permitted", 1, probe="prior+mapped"),
    _c("australian-rules", "au", "australia-afl", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("australian-rules", "au", "australia-afl", "AFL Tables HTML", "afltables", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 3, probe="200"),
    _c("australian-rules", "au", "australia-afl", "Footywire HTML", "footywire", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="200"),
    # --- netball ---
    _c("netball", "world", "world-netball", "netball.sport", "world-netball-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("netball", "au", "ssn-australia", "netball.com.au", "netball-australia-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    # --- lacrosse ---
    _c("lacrosse", "world", "world-lacrosse", "worldlacrosse.sport", "world-lacrosse-web", "public HTML", "when published", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("lacrosse", "world", "world-lacrosse", "Wikipedia lacrosse", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- table tennis ---
    _c("table-tennis", "de", "germany-click-tt", "mytischtennis.de", "click-tt", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 1, probe="200"),
    _c("table-tennis", "world", "ittf-events", "Wikipedia ITTF", "wikimedia", "public HTML", "N", "Y", "Y", "rankings", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- badminton ---
    _c("badminton", "world", "bwf-world-tour", "bwfbadminton.com calendar", "bwf-web", "HTTP 403", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403 not bypassed"),
    _c("badminton", "world", "indonesia-open", "en.wikipedia.org 2026 Indonesia Open", "wikipedia-indonesia-open-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="Victor Lai 21-19 21-8 Jonatan Christie 7 Jun 2026"),
    _c("badminton", "world", "bwf-world-tour", "Wikipedia BWF World Tour", "wikimedia", "public HTML", "N", "Y", "champions", "Y", "N", "N", "N", True, "permitted", 2, probe="200 2026 BWF World Tour"),
    _c("badminton", "world", "bwf-historical-matches", "SahilMotyar/bwf-match-data CSV", "bwf-match-data-github", "public GitHub CSV/JSON", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, derived_from="tournamentsoftware", probe="200 README"),
    _c("badminton", "world", "all-england-open", "en.wikipedia.org 2026 All England Open", "wikipedia-all-england-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="Lin Chun-Yi 21-15 22-20 Lakshya Sen 8 Mar 2026"),
    # --- snooker ---
    _c("snooker", "world", "wst-events", "World Snooker HTML", "wst-web", "public HTML", "HTML", "HTML", "HTML", "HTML", "N", "N", "N", True, "restricted", 1, probe="prior"),
    _c("snooker", "world", "wst-events", "Wikipedia snooker", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    _c("snooker", "world", "snooker-org-api", "snooker.org API", "snooker-org", "JSON 401", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="PERMISSION_REQUIRED commercial contact; keep BBC/WST until granted"),
    # --- darts ---
    _c("darts", "world", "pdc-darts", "OpenLigaDB PDCWM", "openligadb", "public JSON", "inferred", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("darts", "world", "pdc-darts", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="mapped"),
    _c("darts", "world", "pdc-darts", "pdc.tv tournaments", "pdc-web", "public HTML", "HTML", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 3, probe="200"),
    # --- boxing ---
    _c("boxing", "world", "title-fights", "Sanctioning-body HTML", "sanctioning-bodies", "public HTML", "N", "Y", "Y", "rankings", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("boxing", "world", "title-fights", "Wikipedia boxing", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- mma ---
    _c("mma", "us", "ufc", "ufc.com/events", "ufc-web", "public HTML", "Y", "Y", "Y", "rankings", "N", "Y", "N", True, "restricted", 1, probe="200"),
    _c("mma", "us", "ufc", "Wikipedia UFC events", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- racing ---
    _c("horse-racing", "gb", "bha-meetings", "britishhorseracing.com results", "bha-web", "public HTML/XHR", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("horse-racing", "gb", "bha-meetings", "Wikipedia horse racing", "wikimedia", "public HTML", "N", "partial", "partial", "N", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    _c("greyhound-racing", "gb", "gbgb-meetings", "gbgb.org.uk/results", "gbgb-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("greyhound-racing", "gb", "gbgb-meetings", "Wikipedia greyhound racing", "wikimedia", "public HTML", "N", "partial", "partial", "N", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "USTA/HRNSW/Travsport/LeTrot lumped HTML", "jurisdiction-harness", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="over-coarse grouping of independent authorities; split into usta/hrnsw/letrot/standardbred-canada rows"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "Wikipedia harness racing", "wikimedia", "public HTML", "N", "partial", "partial", "N", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- golf ---
    _c("golf", "europe", "european-challenge-tour", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("golf", "kr", "korean-golf-tour", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("golf", "us", "korn-ferry-tour", "TheSportsDB", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="mapped"),
    _c("golf", "world", "tours", "Wikipedia golf tours", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- cycling ---
    _c("cycling", "world", "uci-calendar", "uci.org", "uci-web", "public HTML", "event", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("cycling", "world", "uci-calendar", "Wikipedia cycling", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    _c("cycling", "world", "uci-calendar", "firstcycling.com", "firstcycling", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="403"),
    # --- athletics ---
    _c("athletics", "world", "wa-calendar", "worldathletics.org calendar-results", "world-athletics-web", "public HTML", "Y", "Y", "Y", "rankings", "Y", "N", "N", True, "restricted", 1, probe="200"),
    _c("athletics", "world", "wa-calendar", "Wikipedia athletics", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- swimming ---
    _c("swimming", "world", "world-aquatics-meets", "Omega Timing HTML", "omega-timing", "public HTML", "Y", "Y", "Y", "N", "Y", "N", "N", True, "unclear", 1, probe="prior 200"),
    _c("swimming", "world", "world-aquatics-meets", "Wikipedia swimming", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="wiki family"),
    # --- winter ---
    _c("winter-sports", "world", "fis-disciplines", "FIS calendar HTML", "fis-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 1, probe="prior calendar 200; news URL 404"),
    _c("winter-sports", "world", "biathlon", "IBU biathlonresults.com sportapi JSON", "ibu-web", "unauthenticated JSON", "event", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 1, probe="modules/sportapi/api/Events JSON; MEET renderer not team-match"),
    _c("winter-sports", "world", "fis-disciplines", "Wikipedia winter sports", "wikimedia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="wiki family"),
    # --- esports ---
    _c("esports", "world", "cross-game-brackets", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", False, "unclear", 1, probe="MODEL_SCOPE_BLOCKER umbrella; replaced by formula-2"),
    _c("esports", "world", "cross-game-wiki", "Liquipedia gzip API", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="parent-category results/schedule only; not live; no HLTV/VLR"),
    _c("ea-sports-fc", "world", "competitive-ea-fc", "Liquipedia FIFA wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("ea-sports-fc", "world", "competitive-ea-fc", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family"),
    _c("counter-strike", "world", "tier1", "Liquipedia CS wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("counter-strike", "world", "tier1", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family"),
    _c("league-of-legends", "world", "lol-world-championship", "Liquipedia LoL wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("league-of-legends", "world", "lol-world-championship", "en.wikipedia.org 2025 LoL World Championship", "wikipedia-lol-worlds-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="T1 3-2 KT Rolster Worlds final"),
    _c("dota-2", "world", "professional", "OpenDota", "opendota", "unauthenticated JSON", "partial", "Y", "Y", "N", "Y", "Y", "N", True, "permitted", 1, probe="prior"),
    _c("dota-2", "world", "professional", "Liquipedia Dota wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="prior"),
    _c("dota-2", "world", "professional", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200 family"),
    _c("valorant", "world", "vct", "Liquipedia Valorant wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("valorant", "world", "vct", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family"),
    _c("call-of-duty", "world", "cdl-majors", "Liquipedia COD wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("call-of-duty", "world", "cdl-majors", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family"),
    _c("overwatch", "world", "owcs-historical", "Liquipedia Overwatch wiki", "liquipedia", "gzip JSON/HTML", "N", "historical", "Y", "historical", "N", "N", "N", False, "unclear", 1, probe="MODEL_SCOPE_BLOCKER historical bucket; replaced by owcs-world-finals"),
    _c("overwatch", "world", "owcs-historical", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", False, "unclear", 4, probe="MODEL_SCOPE_BLOCKER historical bucket; replaced by owcs-world-finals"),
    _c("rocket-league", "world", "rlcs", "Liquipedia RL wiki", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="prior"),
    _c("rocket-league", "world", "rlcs", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family"),
    # --- competition-gap pass 17 Sep 2026 (Wikimedia not used as live redundancy) ---
    _c("football", "rs", "serbia-superliga", "superliga.rs schedule/results HTML", "superliga-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "rs", "serbia-superliga", "TheSportsDB id 4671", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200 lookupleague"),
    _c("football", "england", "england-championship", "TheSportsDB id 4329", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200 lookupleague"),
    _c("football", "england", "england-championship", "BBC Championship scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("football", "england", "england-championship", "EFL Championship pages", "efl-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 4, probe="200"),
    _c("football", "england", "england-league-one", "TheSportsDB id 4396", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "england", "england-league-one", "BBC League One scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("football", "england", "england-league-two", "TheSportsDB id 4397", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "england", "england-league-two", "BBC League Two scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("football", "nl", "netherlands-eredivisie", "TheSportsDB id 4337", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200 lookupleague"),
    _c("football", "nl", "netherlands-eredivisie", "eredivisie.nl", "eredivisie-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 3, probe="200"),
    _c("football", "pt", "portugal-primeira-liga", "TheSportsDB id 4344", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200 lookupleague"),
    _c("football", "pt", "portugal-primeira-liga", "ligaportugal.pt", "liga-portugal-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 3, probe="200"),
    _c("football", "europe", "uefa-conference-league", "BBC Conference League scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "europe", "uefa-conference-league", "uefa.com conference", "uefa-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="timeout"),
    _c("football", "us", "usa-usl-championship", "uslchampionship.com schedule", "usl-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "us", "mls", "TheSportsDB id 4346", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="200 lookupleague"),
    _c("football", "us", "mls", "mlssoccer.com schedule", "mls-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("football", "se", "sweden-allsvenskan", "TheSportsDB id 4347", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "se", "sweden-allsvenskan", "allsvenskan.se", "allsvenskan-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "pl", "poland-ekstraklasa", "TheSportsDB id 4422", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "pl", "poland-ekstraklasa", "ekstraklasa.org", "ekstraklasa-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "no", "norway-eliteserien", "TheSportsDB id 4358", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "no", "norway-eliteserien", "eliteserien.no", "eliteserien-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "dk", "denmark-superliga", "TheSportsDB id 4340", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "dk", "denmark-superliga", "superliga.dk", "denmark-superliga-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "ar", "argentina-primera", "TheSportsDB id 4406", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map"),
    _c("football", "ar", "argentina-primera", "ligaprofesional.ar", "liga-profesional-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "au", "australia-a-league", "TheSportsDB id 4356", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "au", "australia-a-league", "a-league.com.au", "a-league-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "jp", "japan-j1", "jleague.jp fixtures/standings", "jleague-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "za", "south-africa-psl", "psl.co.za", "psl-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "europe", "uefa-europa-league", "TheSportsDB id 4481", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="200 lookupleague"),
    _c("football", "england", "fa-cup", "TheSportsDB id 4482", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("football", "england", "fa-cup", "BBC football family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="BBC football 200"),
    _c("football", "england", "womens-super-league", "BBC WSL scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "south-america", "copa-libertadores", "conmebol.com", "conmebol-web", "public HTML", "when published", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 1, probe="200"),
    _c("football", "de", "germany-3-liga", "dfb.de datencenter", "dfb-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "de", "germany-dfb-pokal", "dfb.de datencenter", "dfb-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "de", "germany-frauen-bundesliga", "dfb.de datencenter", "dfb-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "de", "kicker-blocked", "kicker.de spieltag", "kicker-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("basketball", "us", "wnba", "wnba.com/schedule HTML", "wnba-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("basketball", "us", "wnba", "ESPN WNBA scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="espnfitt lnescrs Q1-Q4"),
    _c("basketball", "us", "wnba", "cdn.wnba.com schedule JSON", "wnba-cdn", "JSON", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="200 HTML not JSON"),
    _c("basketball", "es", "spain-acb", "TheSportsDB id 4408", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("baseball", "jp", "npb", "npb.jp HTML", "npb-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("baseball", "jp", "npb", "Yahoo Sportsnavi NPB HTML", "yahoo-sportsnavi", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 3, probe="200"),
    _c("baseball", "kr", "kbo", "koreabaseball.com scoreboard", "kbo-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="200"),
    _c("baseball", "tw", "cpbl", "cpbl.com.tw", "cpbl-web", "HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="428"),
    _c("ice-hockey", "fi", "finland-liiga", "liiga.fi API v1 games JSON", "liiga-web", "unauthenticated JSON", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 1, probe="https://liiga.fi/api/v1/games JSON; official Liiga family"),
    _c("ice-hockey", "de", "germany-del", "del.org", "del-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("ice-hockey", "de", "germany-del2", "del.org", "del-web", "public HTML", "when listed", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200 family site"),
    _c("ice-hockey", "europe", "champions-hockey-league", "championshockeyleague.com schedule", "chl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("ice-hockey", "se", "sweden-shl", "TheSportsDB id 4419", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("ice-hockey", "se", "sweden-shl", "shl.se", "shl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("rugby-league", "au", "nrl", "ABC NRL Score Centre", "abc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("rugby-league", "au", "nrl", "TheSportsDB id 4416", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="TSDB map"),
    _c("rugby", "england", "premiership-rugby", "TheSportsDB id 4414", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("rugby", "england", "premiership-rugby", "premiershiprugby.com", "prem-rugby-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("motorsport", "world", "motogp", "motogp.com calendar HTML", "pulselive", "public HTML", "timing", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 2, probe="200 same PulseLive family as JSON"),
    _c("motorsport", "world", "motogp", "Crash.net MotoGP results", "crash-net", "public HTML", "N", "N", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("motorsport", "world", "motogp", "TheSportsDB id 4407", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 4, probe="200 lookupleague"),
    _c("motorsport", "us", "nascar-truck", "racing-reference.info", "racing-reference", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="403"),
    _c("motorsport", "us", "nascar-truck", "nascar.com results", "nascar-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("motorsport", "world", "formula-e", "TheSportsDB id 4371", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("motorsport", "world", "wec", "TheSportsDB id 4413", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("tennis", "world", "wta-tour", "wtatennis.com/scores", "wta-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 3, probe="200"),
    _c("tennis", "world", "atp-tour", "atptour.com scores", "atp-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("tennis", "world", "atp-tour", "BBC Sport tennis", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("handball", "de", "germany-handball-bundesliga", "handball-bundesliga.de", "hbl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("volleyball", "pl", "plusliga", "plusliga.pl", "plusliga-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 1, probe="200"),
    _c("golf", "us", "pga-tour", "pgatour.com/schedule", "pga-tour-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 1, probe="200"),
    _c("golf", "us", "pga-tour", "TheSportsDB PGA Tour", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB map"),
    _c("cycling", "world", "uci-calendar", "cyclingnews.com/races", "cyclingnews", "public HTML", "event", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("table-tennis", "europe", "ettu-events", "ettu.org", "ettu-web", "public HTML", "when published", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("league-of-legends", "world", "lol-world-championship", "start.gg HTML", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200 family"),
    _c("american-football", "ca", "cfl", "TheSportsDB id 4405", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map"),
    _c("cricket", "world", "t20-internationals", "Cricsheet T20I zip", "cricsheet", "ODC-By zip JSON", "N", "rare", "Y", "N", "ball-by-ball", "Y", "N", True, "permitted", 2, probe="prior family covers T20I"),
    # --- gap pass 17 Sep 2026 continued: singles + sport families + worldwide football ---
    _c("baseball", "tw", "cpbl", "Yahoo Taiwan CPBL scoreboard", "yahoo-taiwan", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("motorsport", "us", "nascar-truck", "ESPN Truck results HTML", "espn-html", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="202 HTML"),
    _c("motorsport", "us", "nascar-arca", "ESPN ARCA results HTML", "espn-html", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="202 HTML"),
    _c("motorsport", "us", "nascar-truck", "jayski.com truck series", "jayski-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403; PDFs likely NASCAR Statistics dumps not independent"),
    _c("motorsport", "us", "nascar-arca", "arcaracing.com results", "arca-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("motorsport", "world", "formula-e", "fiaformulae.com results", "formula-e-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("motorsport", "world", "wec", "fiawec.com results", "fiawec-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("football", "jp", "japan-j1", "TheSportsDB id 4633", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "jp", "japan-j1", "BBC Japanese J-League scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("football", "za", "south-africa-psl", "BBC South Africa PSL scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "za", "south-africa-psl", "TheSportsDB id 4802", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="TSDB map + family JSON 200"),
    _c("football", "england", "womens-super-league", "TheSportsDB id 4849", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "england", "womens-super-league", "womenssuperleague.com", "wsl-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="DNS getaddrinfo failed"),
    _c("football", "south-america", "copa-libertadores", "BBC Copa Libertadores scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("football", "south-america", "copa-libertadores", "TheSportsDB id 4501", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="TSDB map + family JSON 200"),
    _c("football", "europe", "uefa-europa-league", "BBC Europa League scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("volleyball", "pl", "plusliga", "TheSportsDB id 5619", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("american-football", "ca", "cfl", "cfl.ca schedule/game tracker", "cfl-web", "public HTML", "Y", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 2, probe="200"),
    _c("basketball", "es", "spain-acb", "acb.com", "acb-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="200"),
    _c("football", "br", "brazil-serie-a", "TheSportsDB id 4351", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "br", "brazil-serie-a", "BBC Brazilian Serie A scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("american-football", "us", "ncaa-football", "ESPN college football scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="espn-html family 202 NFL/NASCAR this pass"),
    _c("mma", "us", "ufc", "TheSportsDB id 4443", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("mma", "us", "ufc", "ESPN UFC schedule HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 3, probe="202 HTML"),
    _c("mma", "us", "ufc", "ufcstats.com completed events", "ufcstats", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="connection refused"),
    _c("mma", "us", "ufc", "tapology.com fightcenter", "tapology", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("boxing", "world", "title-fights", "TheSportsDB Boxing id 4445", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("boxing", "world", "title-fights", "BBC Sport boxing", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("snooker", "world", "wst-events", "CueTracker tournaments", "cue-tracker", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="200"),
    _c("snooker", "world", "wst-events", "BBC Sport snooker", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("athletics", "world", "wa-calendar", "OpenTrack public results JSON/HTML", "opentrack", "unauthenticated JSON/HTML", "meet", "Y", "Y", "N", "Y", "N", "N", True, "permitted", 2, probe="200 opentrack.run; docs say unauth read"),
    _c("athletics", "world", "wa-calendar", "BBC Sport athletics", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="bbc-sport family 200 this pass"),
    _c("athletics", "europe", "european-athletics", "european-athletics.com competitions", "european-athletics-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("horse-racing", "gb", "bha-meetings", "Sporting Life racing results", "sporting-life", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="200"),
    _c("horse-racing", "gb", "bha-meetings", "BBC Sport horse racing", "bbc-sport", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="200"),
    _c("greyhound-racing", "gb", "gbgb-meetings", "Sporting Life greyhound results", "sporting-life", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200 meeting cards"),
    _c("swimming", "world", "world-aquatics-meets", "swimrankings.net", "swimrankings", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="timeout"),
    _c("swimming", "world", "world-aquatics-meets", "BBC Sport swimming", "bbc-sport", "public HTML", "event", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200 this pass"),
    _c("water-polo", "nordic", "nordic-water-polo-league", "nordicwaterpololeague.com results", "nordic-wpl-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 results-and-standings"),
    _c("lacrosse", "us", "nll", "nll.com schedule", "nll-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("lacrosse", "us", "pll", "premierlacrosseleague.com schedule", "pll-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("rugby", "fr", "france-pro-d2", "lnr.fr professional rugby", "lnr-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="fetch 200 LNR/Pro D2"),
    _c("handball", "dk", "denmark-handball-league", "tophaandbold.dk", "tophaandbold-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("volleyball", "europe", "cev-eurovolley-men", "cev.eu", "cev-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 EuroVolley recaps/results"),
    _c("basketball", "mx", "mexico-lnbp", "lnbp.mx", "lnbp-web", "public HTML", "when published", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 official"),
    _c("golf", "europe", "european-challenge-tour", "europeantour.com Challenge/DP World family", "europeantour-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="fetch 200 europeantour.com"),
    _c("golf", "us", "korn-ferry-tour", "pgatour.com Korn Ferry schedule family", "pga-tour-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="pga-tour-web family 200 prior"),
    _c("futsal", "es", "spain-lnfs", "lnfs.es", "lnfs-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="fetch 500"),
    # worldwide football expansion
    _c("football", "hr", "croatia-hnl", "hnl.hr", "hnl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "hr", "croatia-hnl", "TheSportsDB id 4629", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "ro", "romania-superliga", "superliga.ro", "romania-superliga-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="200"),
    _c("football", "ro", "romania-superliga", "TheSportsDB id 4691", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "scotland", "scotland-premiership", "spfl.co.uk", "spfl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 1, probe="200"),
    _c("football", "scotland", "scotland-premiership", "TheSportsDB id 4330", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "be", "belgium-pro-league", "TheSportsDB id 4338", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "be", "belgium-pro-league", "BBC Belgian football family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "be", "belgium-pro-league", "proleague.be/en", "belgium-proleague-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="404"),
    _c("football", "tr", "turkey-super-lig", "TheSportsDB id 4339", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "tr", "turkey-super-lig", "BBC Turkish Super Lig family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "gr", "greece-super-league", "TheSportsDB id 4336", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "gr", "greece-super-league", "BBC Greek Super League family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "ua", "ukraine-premier-league", "TheSportsDB id 4354", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ua", "ukraine-premier-league", "BBC Ukrainian Premier League family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "ch", "switzerland-super-league", "TheSportsDB id 4675", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "at", "austria-bundesliga", "TheSportsDB id 4621", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "cz", "czech-first-league", "TheSportsDB id 4631", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "hu", "hungary-nb-i", "TheSportsDB id 4690", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "sk", "slovakia-super-liga", "TheSportsDB id 4672", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "si", "slovenia-1-snl", "TheSportsDB id 4692", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ba", "bosnia-premier-liga", "TheSportsDB id 4624", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "al", "albania-superliga", "TheSportsDB id 4617", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "bg", "bulgaria-first-league", "TheSportsDB id 4626", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "fi", "finland-veikkausliiga", "TheSportsDB id 4636", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ie", "ireland-premier-division", "TheSportsDB id 4643", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "is", "iceland-urvalsdeild", "TheSportsDB id 4642", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "cn", "china-super-league", "TheSportsDB id 4359", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "kr", "korea-k-league-1", "kleague.com results/tables", "kleague-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="fetch 200"),
    _c("football", "kr", "korea-k-league-1", "TheSportsDB id 4689", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "th", "thai-league-1", "TheSportsDB id 4743", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "id", "indonesia-liga-1", "TheSportsDB id 4790", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "vn", "vietnam-v-league-1", "TheSportsDB id 4803", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "my", "malaysia-super-league", "TheSportsDB id 4792", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "in", "india-super-league", "TheSportsDB id 4791", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "uz", "uzbekistan-super-league", "TheSportsDB id 4794", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "kz", "kazakhstan-premier-league", "TheSportsDB id 4649", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "sa", "saudi-pro-league", "TheSportsDB id 4668", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ir", "iran-pro-league", "TheSportsDB id 4742", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "eg", "egypt-premier-league", "TheSportsDB id 4829", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ma", "morocco-botola", "TheSportsDB id 4520", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "tn", "tunisia-ligue-1", "TheSportsDB id 4828", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "mx", "mexico-liga-mx", "TheSportsDB id 4350", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "us", "usa-nwsl", "nwslsoccer.com schedule", "nwsl-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 1, probe="fetch 200"),
    _c("football", "us", "usa-nwsl", "TheSportsDB id 4521", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "co", "colombia-primera-a", "dimayor.com.co", "dimayor-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="fetch 200 match list"),
    _c("football", "co", "colombia-primera-a", "TheSportsDB id 4497", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "cl", "chile-primera", "TheSportsDB id 4627", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "ec", "ecuador-serie-a", "TheSportsDB id 4686", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "uy", "uruguay-primera", "TheSportsDB id 4432", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "py", "paraguay-primera", "TheSportsDB id 4687", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "nz", "nz-national-league", "TheSportsDB id 4814", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "cr", "costa-rica-liga-fpd", "TheSportsDB id 4815", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "au", "australia-a-league-women", "TheSportsDB id 4805", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "au", "australia-a-league-women", "a-league.com.au women family", "a-league-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="a-league-web family 200 prior"),
    _c("football", "south-america", "copa-sudamericana", "TheSportsDB id 4724", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "south-america", "copa-sudamericana", "conmebol.com", "conmebol-web", "public HTML", "when published", "Y", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="conmebol-web family 200 prior"),
    _c("football", "asia", "afc-champions-league", "TheSportsDB id 4719", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "asia", "afc-champions-league", "the-afc.com ACL Elite", "afc-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200 match reports"),
    _c("football", "africa", "caf-champions-league", "TheSportsDB id 4720", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("football", "africa", "caf-champions-league", "cafonline.com CAF CL", "caf-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200"),
    _c("football", "namerica", "concacaf-champions-cup", "TheSportsDB id 4721", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "namerica", "concacaf-champions-cup", "concacaf.com Champions Cup", "concacaf-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200"),
    _c("football", "europe", "uefa-nations-league", "TheSportsDB id 4490", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "europe", "uefa-nations-league", "BBC Nations League family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "es", "spain-copa-del-rey", "TheSportsDB id 4483", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "es", "spain-copa-del-rey", "BBC Copa del Rey family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "it", "italy-coppa-italia", "TheSportsDB id 4506", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "africa", "africa-cup-of-nations", "TheSportsDB id 4496", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("football", "africa", "africa-cup-of-nations", "FIFA Digital JSON when listed", "fifa-digital", "unauthenticated JSON", "when listed", "when listed", "when listed", "N", "N", "N", "N", True, "restricted", 2, probe="fifa-digital family prior JSON 200"),
    _c("rugby", "world", "super-rugby", "TheSportsDB id 4551", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("rugby", "fr", "france-top-14", "TheSportsDB id 4430", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("rugby", "fr", "france-top-14", "lnr.fr", "lnr-web", "public HTML", "when published", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="lnr-web family fetch 200"),
    _c("esports", "world", "cross-game-brackets", "Liquipedia gzip API", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", False, "unclear", 4, probe="MODEL_SCOPE_BLOCKER umbrella"),
    _c("handball", "es", "spain-asobal", "TheSportsDB id 4534", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("handball", "fr", "france-lnh", "TheSportsDB id 4536", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    _c("rugby", "world", "internationals-rwc", "BBC Sport rugby union scores", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="fetch 200"),
    _c("cricket", "world", "internationals-and-leagues", "BBC Sport cricket scores", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("rugby-league", "england", "super-league", "TheSportsDB id 4415", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("rugby-league", "england", "super-league", "BBC Sport rugby league scores", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="fetch 200"),
    _c("netball", "au", "ssn-australia", "TheSportsDB id 4540", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB map + family JSON 200"),
    _c("netball", "england", "uk-netball-superleague", "TheSportsDB id 4539", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="TSDB map + family JSON 200"),
    # --- 17 Sep 2026 redundancy pass: singles + futsal/harness split + third families ---
    _c("futsal", "br", "brazil-lnf", "lnfoficial.com.br tabela/classificacao", "lnf-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="fetch 200 match scores"),
    _c("futsal", "br", "brazil-lnf", "futsalplanet.com leagues", "futsalplanet", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="futsalplanet family 200"),
    _c("futsal", "world", "uefa-futsal-champions-league", "uefa.com Futsal Champions League recap", "uefa-futsal-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="Sporting CP 2-0 Palma 10 May 2026"),
    _c("futsal", "pt", "portugal-liga-placard", "resultados.fpf.pt", "fpf-resultados", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="IP banned by FPF automated security"),
    _c("futsal", "es", "spain-lnfs", "lnfs.es", "lnfs-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="prior fetch 500 not retried"),
    _c("harness-racing", "us", "usa-usta-meetings", "racing.ustrotting.com entries/results", "usta-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "restricted", 1, probe="fetch 200; site says personal non-commercial"),
    _c("harness-racing", "au", "nsw-hrnsw-meetings", "hrnsw.com.au racing/results", "hrnsw-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="fetch 200 meeting list"),
    _c("harness-racing", "fr", "france-letrot-meetings", "letrot.com results", "letrot-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "restricted", 1, probe="fetch 200"),
    _c("harness-racing", "ca", "canada-standardbred-meetings", "standardbredcanada.ca/results", "standardbred-canada-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="fetch 200"),
    _c("harness-racing", "se", "sweden-travsport-meetings", "travsport.se / sportapp.travsport.se", "travsport-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403 homepage and sportapp; not retried"),
    _c("harness-racing", "nz", "nz-hrnz-meetings", "hrnz.co.nz/racing/results/", "hrnz-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="404"),
    _c("football", "at", "austria-bundesliga", "bundesliga.at tabelle", "austria-bundesliga-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 standings"),
    _c("football", "at", "austria-bundesliga", "openfootball/austria Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="fetch 200 README+sample scores"),
    _c("football", "cz", "czech-first-league", "fortunaliga.cz zapasy", "fortuna-liga-cz-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200 scores"),
    _c("football", "cz", "czech-first-league", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="europe repo lists Czech First League"),
    _c("football", "ch", "switzerland-super-league", "sfl.ch spielplan", "sfl-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200 calendar hub"),
    _c("football", "ch", "switzerland-super-league", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="europe repo lists Super League"),
    _c("football", "si", "slovenia-1-snl", "prvaliga.si match scores", "prvaliga-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 round scores"),
    _c("football", "mx", "mexico-liga-mx", "ligamx.net cancha/partidos", "liga-mx-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200 jornada scores"),
    _c("football", "mx", "mexico-liga-mx", "openfootball/world Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="world repo lists Liga MX"),
    _c("football", "th", "thai-league-1", "thaileague.co.th score-board", "thaileague-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("football", "sa", "saudi-pro-league", "spl.com.sa fixtures", "spl-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200"),
    _c("football", "fi", "finland-veikkausliiga", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="europe repo lists Veikkausliiga"),
    _c("football", "hu", "hungary-nb-i", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="europe repo lists NB I"),
    _c("football", "is", "iceland-urvalsdeild", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="europe repo lists Urvalsdeild"),
    _c("football", "ie", "ireland-premier-division", "openfootball/europe Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="europe repo lists Premier Division"),
    _c("football", "ie", "ireland-premier-division", "sseairtricityleague.ie", "loi-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="500"),
    _c("football", "cn", "china-super-league", "openfootball/world Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="world repo lists CSL"),
    _c("football", "eg", "egypt-premier-league", "openfootball/world Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="world repo lists Egypt Premiership"),
    _c("football", "ma", "morocco-botola", "openfootball/world Football.TXT", "openfootball", "GitHub public TXT", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="world repo lists Botola"),
    _c("football", "it", "italy-coppa-italia", "BBC Coppa Italia family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "world", "fifa-connected-competitions", "BBC football internationals family", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("football", "sk", "slovakia-super-liga", "fortunaliga.sk zapasy", "fortuna-liga-sk-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("rugby", "world", "super-rugby", "super.rugby fixtures/tables", "super-rugby-web", "public HTML", "when in season", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 99, probe="fetch 200 fixtures hub; official API/HTML restricted to collector UA"),
    _c("handball", "es", "spain-asobal", "asobal.es liga/resultados", "asobal-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200 jornada scores"),
    _c("handball", "fr", "france-lnh", "lnh.fr StarLigue scores", "lnh-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200; calendrier path 404"),
    _c("handball", "europe", "ehf-competitions", "TheSportsDB EHF family", "thesportsdb", "free JSON truncated", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="TSDB family 200; CL already mapped"),
    _c("lacrosse", "us", "nll", "ESPN lacrosse/NLL HTML family", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="espn-html family 202 prior; nll espn path timed out"),
    _c("lacrosse", "us", "pll", "ESPN lacrosse HTML family", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="espn-html family 202 prior"),
    _c("netball", "world", "world-netball", "BBC Sport netball", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("netball", "england", "uk-netball-superleague", "BBC Sport netball Super League", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("netball", "england", "uk-netball-superleague", "netballsfl.com fixtures-results", "nsl-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="500"),
    _c("winter-sports", "world", "fis-disciplines", "BBC Sport winter sports family", "bbc-sport", "public HTML", "event", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("winter-sports", "world", "biathlon", "BBC Sport biathlon family", "bbc-sport", "public HTML", "event", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="bbc-sport family 200"),
    _c("greyhound-racing", "ie", "ireland-gri-meetings", "igb.ie/grireland results", "gri-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", False, "unclear", 1, probe="STRUCTURAL_SINGLE_UPSTREAM; replaced by irish-greyhound-derby"),
    _c("cycling", "fr", "tour-de-france", "letour.fr rankings", "aso-letour", "public HTML", "stage", "Y", "Y", "Y", "Y", "N", "N", True, "restricted", 1, probe="fetch 200 stage classifications"),
    _c("cycling", "fr", "tour-de-france", "cyclingnews.com/races Tour family", "cyclingnews", "public HTML", "stage", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="cyclingnews family 200 prior"),
    _c("cycling", "fr", "tour-de-france", "uci.org calendar family", "uci-web", "public HTML", "event", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="uci-web family 200 prior"),
    _c("league-of-legends", "world", "lol-world-championship", "lolesports.com schedule/results", "lolesports-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 3, probe="fetch 200 Bo3/Bo5 scores"),
    _c("futsal", "world", "fifa-futsal-when-listed", "futsalplanet.com championships", "futsalplanet", "public HTML", "N", "Y", "Y", "rankings", "N", "N", "N", True, "unclear", 4, probe="fetch 200"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "racing.ustrotting.com", "usta-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "restricted", 2, probe="fetch 200"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "hrnsw.com.au racing/results", "hrnsw-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="fetch 200"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "letrot.com results", "letrot-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "restricted", 4, probe="fetch 200"),
    _c("harness-racing", "multi", "jurisdiction-meetings", "standardbredcanada.ca/results", "standardbred-canada-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 5, probe="fetch 200"),
    # --- 17 Sep 2026 targeted redundancy: remaining singles + two-family sports ---
    _c("football", "cl", "chile-primera", "BBC Chilean Primera scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 league-titled page with FT scores"),
    _c("football", "cl", "chile-primera", "campeonatochileno.cl fechas/tabla", "chile-anfp-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="fetch 200 round scores + table"),
    _c("football", "ba", "bosnia-premier-liga", "nfsbih.ba Premijer liga scores/table", "nfsbih-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 round scores 3:2 etc + standings"),
    _c("football", "vn", "vietnam-v-league-1", "vpf.vn V.League 1 table", "vpf-web", "public HTML", "N", "N", "standings", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 points table"),
    _c("football", "py", "paraguay-primera", "apf.org.py tabla Primera", "apf-web", "public HTML", "N", "N", "standings", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 Apertura table"),
    _c("football", "kz", "kazakhstan-premier-league", "pflk.kz Premier Liga scores", "pflk-web", "public HTML", "N", "Y", "Y", "N", "Y", "N", "N", True, "unclear", 4, probe="fetch 200 Kaisar 2-0 Tobol and other scores"),
    _c("football", "id", "indonesia-liga-1", "ligaindonesiabaru.com match scores", "lib-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="fetch 200 e.g. BOR 1:3 DUB"),
    _c("football", "in", "india-super-league", "indiansuperleague.com standings/scorecards", "isl-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "restricted", 2, probe="fetch 200 standings with match scores"),
    _c("football", "in", "india-super-league", "BBC ISL scores-fixtures", "bbc-sport", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 but no events; generic empty calendar not counted"),
    _c("football", "bg", "bulgaria-first-league", "BBC Bulgarian football scores-fixtures", "bbc-sport", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="empty/generic football; not league events"),
    _c("football", "sk", "slovakia-super-liga", "BBC Slovak football scores-fixtures", "bbc-sport", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="empty/generic football; not league events"),
    _c("football", "uy", "uruguay-primera", "BBC Uruguayan football scores-fixtures", "bbc-sport", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="empty/generic football; not league events"),
    _c("football", "bg", "bulgaria-first-league", "fpleague.bg / bfu-tournaments.com", "fpleague-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Cloudflare challenge; not bypassed"),
    _c("football", "id", "indonesia-liga-1", "liga1match.id", "liga1match-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="parked Hostinger domain"),
    _c("football", "my", "malaysia-super-league", "malaysianfootballleague.com", "mfl-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 SPA placeholders; no parseable scores"),
    _c("football", "nz", "nz-national-league", "nzfootball.co.nz national-league", "nzfootball-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 contact page; no scores"),
    _c("football", "tn", "tunisia-ligue-1", "lnf.tn", "lnf-tn-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="timeout this pass"),
    _c("football", "pe", "peru-liga-1", "liga1.pe results", "liga1-pe-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="fixtures widget Sofascore; forbidden/derived; not added as competition"),
    _c("valorant", "world", "vct", "valorantesports.com schedule", "valorantesports-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "restricted", 3, probe="TECHNICALLY_WORKING Paper Rex 3-1 NRG 2026-03-14; TERMS_RESTRICTED Riot ToS; not ingested"),
    _c("overwatch", "world", "owcs-historical", "esports.overwatch.com schedule", "overwatch-esports-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", False, "restricted", 3, probe="TERMS_RESTRICTED Blizzard; historical bucket replaced by owcs-world-finals"),
    _c("call-of-duty", "world", "cdl-majors", "callofdutyleague.com schedule", "cdl-web", "public HTML + embedded JSON", "when listed", "Y", "Y", "N", "N", "N", "N", True, "restricted", 3, probe="fetch 200 pageProps schedule JSON"),
    _c("rocket-league", "world", "rlcs", "rocketleagueesports.com/schedule", "rlcs-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="500"),
    _c("counter-strike", "world", "tier1", "play.eslgaming.com results", "esl-play", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="ESL Play shut down; FACEIT redirect; no public results"),
    _c("table-tennis", "world", "ittf-events", "ittf.com", "ittf-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Cloudflare challenge; not bypassed"),
    _c("table-tennis", "world", "wtt-events", "worldtabletennis.com", "wtt-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 homepage with no parseable scores"),
    _c("swimming", "world", "world-aquatics-meets", "worldaquatics.com/swimming/results", "world-aquatics-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 empty results dataset"),
    _c("water-polo", "europe", "european-aquatics", "european-aquatics.sport/water-polo", "european-aquatics-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="500"),
    _c("field-hockey", "europe", "eurohockey", "eurohockey.org", "eurohockey-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 homepage too thin; likely Altiusrt-powered events"),
    _c("lacrosse", "world", "world-lacrosse", "insidelacrosse.com/scores", "inside-lacrosse", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Cloudflare challenge; not bypassed"),
    _c("volleyball", "it", "italy-superlega", "legavolley.it risultati", "dataproject-wcm", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 99, derived_from="dataproject-wcm", probe="200 HTML tables; same DataProject WCM family as existing Superlega row"),
    _c("volleyball", "world", "fivb-competitions", "BBC Sport volleyball", "bbc-sport", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="news/features only; no scores-fixtures"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr tournament schedule", "kpga-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="404 Next.js error page; not retried"),
    _c("rugby", "nz", "nz-npc", "provincial.rugby", "npc-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 round recap news; not a score centre"),
    # --- 17 Sep 2026 singles-only pass: independent second families ---
    _c("football", "bg", "bulgaria-first-league", "a-pfg.com round scores/matrix", "a-pfg-web", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="fetch 200 round 9 scores 2:2 4:1 plus result matrix"),
    _c("football", "bg", "bulgaria-first-league", "parvaliga.bg results/klasirane", "parvaliga-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="fetch 200 match scores and table; naturally found while hunting second source"),
    _c("football", "sk", "slovakia-super-liga", "sportnet.sme.sk Futbalnet Niké liga výsledky", "futbalnet", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 5-2 3-2 etc; Futbalnet/ULK published via Sportnet"),
    _c("football", "ir", "iran-pro-league", "varzesh3.com لیگ برتر table/matches", "varzesh3-web", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="fetch 200 live table + week scores 1-0 2-3"),
    _c("football", "tn", "tunisia-ligue-1", "kawarji.com classement/résultats Ligue 1", "kawarji-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 full 30-match table"),
    _c("football", "uy", "uruguay-primera", "estadisticas.tenfield.com.uy tablas", "tenfield-stats", "public HTML", "N", "N", "standings", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 Apertura/Anual/Descenso tables"),
    _c("football", "uz", "uzbekistan-super-league", "championat.asia Superliga results", "championat-asia", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 3-0 1-4 2-1 completed matches"),
    _c("football", "ec", "ecuador-serie-a", "golmates.com LigaPro 2026 results/table", "golmates-web", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="fetch 200 last results with scorers e.g. 2-1 2-3"),
    _c("football", "cr", "costa-rica-liga-fpd", "nacion.com Apertura tabla + jornada scores", "nacion-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 round scores 0-2 2-3 0-2 1-3 1-0 plus standings table"),
    _c("rugby", "nz", "nz-npc", "ultimaterugby.com NPC table/results", "ultimate-rugby", "public HTML", "N", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="fetch 200 table plus 57-42 47-24 14-36 scores"),
    _c("volleyball", "world", "fivb-competitions", "volleytimes.com VNL 2026 set scores", "volleytimes-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 pool/finals with set scores 25:23 etc"),
    _c("table-tennis", "europe", "ettu-events", "sport.de ETTU Champions League table", "sport-de-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="fetch 200 group scores 3-1 and standings"),
    _c("badminton", "world", "all-england-open", "BBC Sport All England live blog", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Lin 21-15 Sen All England 2026 live blog"),
    _c("esports", "world", "cross-game-wiki", "start.gg HTML family", "startgg", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", False, "unclear", 4, probe="MODEL_SCOPE_BLOCKER umbrella"),
    _c("football", "al", "albania-superliga", "fshf.org/competition/abissnet-superiore", "fshf-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 regulations/contact only; no scores"),
    _c("football", "bg", "bulgaria-first-league", "efbetleague.com/standings", "efbetleague-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="403"),
    _c("football", "ec", "ecuador-serie-a", "espn.com.ec posiciones ecu.1", "espn-html", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="200 Sin información disponible"),
    _c("football", "cr", "costa-rica-liga-fpd", "unafut.com/posiciones", "unafut-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 heading only; empty SPA"),
    _c("football", "nz", "nz-national-league", "nrf.org.nz northern-league", "nrf-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 noticeboard; no scores"),
    _c("badminton", "world", "indonesia-open", "bwfworldtour.bwfbadminton.com results", "bwf-worldtour-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Cloudflare blocked; not bypassed"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr tours/leaderboard", "kpga-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="200 SPA chrome; no parseable scores/leaderboard numbers"),
    _c("harness-racing", "au", "nsw-hrnsw-meetings", "natsite.harness.org.au racing/results", "hra-natsite", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="451 Unavailable For Legal Reasons"),
    _c("harness-racing", "fr", "france-letrot-meetings", "paris-turf.com/trot/reunions", "paris-turf", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Cloudflare challenge; not bypassed"),
    _c("water-polo", "world", "world-aquatics-events", "ea.microplustimingservices.com EWPC Belgrade", "microplus-timing", "public HTML/PDF", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="European Aquatics event not World Aquatics; empty test include page"),
    # --- 17 Sep 2026 event-driven singles pass ---
    _c("harness-racing", "fr", "france-letrot-meetings", "equidia.fr courses arrivées", "equidia-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="event Beaumont-de-Lomagne 14 Sep 2026 GP Jean Dumouch; HTML finish order JUGEMENT D'AVE 1st, km times, DQ"),
    _c("futsal", "world", "uefa-futsal-champions-league", "en.wikipedia.org 2025-26 UEFA Futsal CL", "wikipedia-uefa-futsal-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="Sporting CP 2-0 Palma"),
    _c("volleyball", "it", "italy-superlega", "volleyballworld.com Superlega standings", "volleyballworld", "public HTML", "N", "N", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="event Perugia 3-0 Lube Gara1 30 Apr 2026; VW Superlega page 200 Perugia 20-2 58pts not DataProject WCM"),
    _c("badminton", "world", "indonesia-open", "bwfworldchampionships.bwfbadminton.com results", "bwf-worldtour-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="event Lanier 21-11 Naraoka 23 Aug 2026; Cloudflare blocked; not bypassed"),
    _c("harness-racing", "ca", "canada-standardbred-meetings", "woodbine.com Mohawk official Simcoe recap", "woodbine-mohawk-web", "public HTML", "meeting", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="woodbine.com Mohawk Redland Rocket Man Simcoe 12 Sep 2026"),
    _c("harness-racing", "us", "usa-usta-meetings", "playmeadowlands.com chart-archive", "meadowlands-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="event Apex NJ Classic 11 Sep 2026; chart archive empty; PDFs are programs not result charts"),
    _c("water-polo", "nordic", "nordic-water-polo-league", "nordicwaterpololeague.com results-and-standings", "nordic-wpl-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="event-driven refetch empty (email only); not a second family"),
    # --- 17 Sep 2026 13-deep singles pass (event/portal search; no third sources) ---
    _c("football", "al", "albania-superliga", "the-sports.org Albanian Superliga 2026/27 HTML", "the-sports-org", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="event Vllaznia 2-3 Partizani 5 Sep 2026 + Round 4 HTML Partizani 2-4 Dinamo, Teuta 2-0 Vora, table Egnatia 9pts; Info Média Conseil DB not TheSportsDB/FSHF"),
    _c("football", "nz", "nz-national-league", "soccerpunter.com season 27525 NZ National League 2026", "soccerpunter-web", "public HTML", "livescore claim", "Y", "Y", "Y", "Y", "N", "N", True, "unclear", 4, probe="event Cashmere Technical 11-0 Wanaka 12 Sep 2026; Northern table Birkenhead 22/18/4/0 58-13 58pts; corporate.php expert network not TSDB; odds present unused"),
    _c("football", "my", "malaysia-super-league", "futbol24.com Super League 2026/27 match pages", "futbol24-web", "public HTML", "Y", "Y", "Y", "N", "Y", "Y", "Y", True, "unclear", 4, probe="event Terengganu 0-3 Selangor 28 Aug 2026 HTML FT/HT + minute goals/lineups; not TSDB; vendor vs Opta/Sportradar UNKNOWN"),
    _c("football", "al", "albania-superliga", "worldfootball.net Kategoria Superiore 2026/27", "worldfootball-net", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="crawler-indexed Matchday 3 Vllaznia 2-3 Partizani + table; WebFetch timeout; not counted as third beside the-sports-org"),
    _c("football", "nz", "nz-national-league", "futbol24.com NZ match pages", "futbol24-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="Birkenhead 6-1 Manukau HTML exists; not added as third beside soccerpunter"),
    _c("football", "nz", "nz-national-league", "forebet.com / predictz.com NZ 2026", "prediction-portals", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="Forebet tables without verified FT for probe event; PredictZ Island Bay page lacked scores"),
    _c("football", "my", "malaysia-super-league", "soccerpunter.com Malaysia Super League", "soccerpunter-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Selangor–Melaka 6 Sep 2026 still listed fixture; later 403; not retried"),
    _c("football", "my", "malaysia-super-league", "the-sports.org Selangor/Terengganu pages", "the-sports-org", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="club pages stale (friendlies/AFC); no 2026/27 Super League scores"),
    _c("table-tennis", "de", "germany-click-tt", "non-click-TT independent league mirrors", "unknown", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="Seelze 1:9 Fuhlen 13 Sep 2026 only on myTischtennis/click-TT/TTVN; same family as primary"),
    _c("badminton", "world", "indonesia-open", "ffbad.org Worlds 2026 recap", "ffbad-web", "public HTML news", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="event Lanier 21-11 Naraoka 23 Aug 2026; news recap only, not a reusable result system"),
    _c("lacrosse", "world", "world-lacrosse", "lacrosse.gr.jp JLA championship recaps", "jla-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="host recaps point at WL official; not reusable across world-lacrosse events"),
    _c("water-polo", "world", "world-aquatics-events", "omegatiming.com Singapore 2025 PDFs", "omega-timing", "public PDF", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="ESP 15-13 HUN 24 Jul 2025 is same Omega family as primary; no Microplus/Swiss Timing for this championship"),
    _c("water-polo", "nordic", "nordic-water-polo-league", "cetus.fi / uimaliitto.fi tournament pages", "club-news", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="Espoo Dec 2025 schedule only; no completed NWPL scores"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr/tour/leaderboard SPA", "kpga-web", "SPA XHR unknown", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="leaderboard URL 200 chrome; browser tab about:blank this pass; XHR path not captured; Korean news not a scoreboard"),
    _c("harness-racing", "us", "usa-usta-meetings", "playmeadowlands.com race-day-information/results", "meadowlands-web", "public HTML", "meeting", "Y", "Y", "N", "Y", "N", "N", True, "unclear", 2, probe="21 Aug 2026 Just My Mama 1:54.1 race-day charts"),
    _c("harness-racing", "us", "usa-usta-meetings", "harringtonraceway.com official recaps", "harrington-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Disturbed Hanover 1:53.1 Harrington feature recap"),
    _c("harness-racing", "ca", "canada-standardbred-meetings", "grandriverraceway.com results links", "grand-river-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="explicitly sends entries/results to standardbredcanada.ca; not independent"),
    _c("harness-racing", "au", "nsw-hrnsw-meetings", "bookmaker Menangle result pages", "bookmaker", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="Perfect Stride Menangle 11 Jul 2026 on BetNova/VicBet; bookmaker feeds excluded"),
    _c("greyhound-racing", "ie", "ireland-gri-meetings", "TrapStats Irish racing", "trapstats", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, derived_from="gri-web", probe="TrapStats states Irish racing is single-source GRI"),
    # --- 17 Sep 2026 final-10 pass: full or PARTIAL independent fallbacks ---
    _c("table-tennis", "de", "germany-click-tt", "bettv.tischtennislive.de Spielbericht", "tischtennislive", "public HTML", "N", "Y", "Y", "Y", "Y", "Y", "N", True, "unclear", 2, probe="Berlin Verbandsliga 2 Sep 2026 Ajax 3:7 OSC Spielbericht HTML"),
    _c("table-tennis", "de", "germany-click-tt", "ttbl.de Spielplan 2026/27", "ttbl-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="Saarbrücken-TT 3 Post SV Mühlhausen 1 Spieltag 2 21.08.2026"),
    _c("water-polo", "nordic", "nordic-water-polo-league", "cetus.fi miesten ottelut NWPL table", "cetus-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Espoo 5-7 Dec 2025 HTML: Cetus 25-8 Neptun, Zaibas 27-8 Slagelse"),
    _c("badminton", "world", "indonesia-open", "kompas.com Indonesia Open 2026 final recap", "kompas-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Victor Lai 21-19 21-8 Jonatan Christie"),
    _c("lacrosse", "world", "world-lacrosse", "lacrosse.gr.jp/worlds/tokyo2026 scores", "jla-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 99, derived_from="world-lacrosse-web", probe="host WP stores finals; 試合結果の詳細はこちら → worldlacrosse.sport/game-details (game_id 63/87/106); hub+news defer to WL; QF 4-5 OT scorers/officials match Swiss Timing ODF; gold CMS modified 20:43 vs ODF created 20:41; CAN-AUS page never posted FT", coverage_scope="partial", independence_status="derived"),
    _c("harness-racing", "us", "usa-usta-meetings", "littlebrownjug.com race-results + PDFs", "delaware-lbj-web", "public HTML/PDF", "N", "N", "Y", "N", "Y", "N", "N", True, "unclear", 99, probe="Delaware 18 Sep 2025 PDF charts Cruising Zone 1st 1:53.0; 2026 Jug not yet raced; official-chart format may be USTA", coverage_scope="partial", independence_status="unknown"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr tours/leaderboard Next.js", "kpga-web", "SPA empty pageProps", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="srhGameId=202611000001M fetch returns empty Next pageProps; browser tab about:blank/black; public XHR not observed"),
    _c("greyhound-racing", "ie", "ireland-gri-meetings", "timeform.com greyhound results", "timeform", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="UK cards (Dunstall); no Irish Shelbourne 2026 charts found independent of GRI"),
    # --- 17 Sep 2026 six-remaining parallel pass ---
    _c("water-polo", "world", "world-aquatics-events", "results.microplustimingservices.com World Aquatics WP", "microplus-timing", "public HTML", "event", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="WA contracted Microplus for WP; treat as shared-upstream of official WA result system", coverage_scope="partial", independence_status="shared-upstream"),
    _c("lacrosse", "world", "world-lacrosse", "englandlacrosse.co.uk senior-womens-results", "england-lacrosse-web", "public HTML recap list", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="England-only Tokyo 2026 six scores (15-8 PUR … 8-7 OT AUS); no quarters/IDs; matches WL; independence not established"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr/app/liveLeaderboard Next export", "kpga-web", "SPA empty pageProps", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="Gunsan 2026 Jung Han-mil 271 in news only; liveLeaderboard pageProps empty like tours/leaderboard; UNBIZ is KPGA official scorer"),
    _c("harness-racing", "au", "nsw-hrnsw-meetings", "clubmenangle.com.au race reports", "club-menangle-web", "public HTML news", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Verbici NSW Trot Final 7 Jul 2026 1:59.6 independent recap"),
    _c("harness-racing", "ca", "canada-standardbred-meetings", "redshores.ca/racing", "red-shores-web", "public HTML programs", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="2026 calendar/programs/picks; Gold Cup news; stake payments via Standardbred Canada; no independent result tables"),
    _c("greyhound-racing", "ie", "ireland-gri-meetings", "greyhounds1.attheraces.com IRE results", "at-the-races", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, derived_from="gri-web", probe="Shelbourne 4 Sep 2026 R8 Jacktavern Adam 29.80; 550y shown as 503m; same GRI comments/times as grireland.ie"),
    _c("rugby", "world", "super-rugby", "pulselive World Rugby match/results JSON", "pulselive", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="independent of super.rugby restricted API; Super Rugby keywords on pulselive family", coverage_scope="partial"),
    _c("football", "ar", "argentina-primera", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com/soccer/scoreboard/_/league/arg.1"),
    _c("football", "dk", "denmark-superliga", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com den.1 scoreboard"),
    _c("football", "se", "sweden-allsvenskan", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com swe.1 scoreboard"),
    _c("football", "mx", "mexico-liga-mx", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com mex.1 scoreboard"),
    _c("football", "au", "australia-a-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com aus.1 scoreboard"),
    _c("football", "au", "australia-a-league-women", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com aus.w.1 scoreboard"),
    _c("football", "us", "usa-nwsl", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com usa.nwsl scoreboard"),
    _c("football", "us", "usa-usl-championship", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com usa.usl.1 scoreboard"),
    _c("football", "asia", "afc-champions-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com afc.champions scoreboard"),
    _c("football", "africa", "caf-champions-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com caf.champions scoreboard"),
    _c("football", "south-america", "copa-libertadores", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com libertadores scoreboard"),
    _c("football", "south-america", "copa-sudamericana", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com sudamericana scoreboard"),
    _c("football", "rs", "serbia-superliga", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com srb.1 scoreboard"),
    _c("football", "sk", "slovakia-super-liga", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com svk.1 scoreboard"),
    _c("football", "my", "malaysia-super-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com mas.1 scoreboard"),
    _c("football", "th", "thai-league-1", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com tha.1 scoreboard"),
    _c("football", "cz", "czech-first-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com cze.1 scoreboard"),
    _c("football", "in", "india-super-league", "ESPN soccer scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com ind.1 scoreboard"),
    _c("rugby", "fr", "france-top-14", "ESPN rugby scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com rugby scoreboard"),
    _c("rugby", "fr", "france-pro-d2", "ESPN rugby scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com rugby scoreboard"),
    _c("rugby", "world", "super-rugby", "ESPN rugby scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 4, probe="espn.com super rugby scoreboard"),
    _c("rugby-league", "england", "super-league", "ESPN rugby scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="espn rugby board may not isolate Super League"),
    _c("tennis", "world", "atp-tour", "ESPN tennis scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="espn.com/tennis/scoreboard"),
    _c("tennis", "world", "wta-tour", "ESPN tennis scoreboard HTML", "espn-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="espn.com/tennis/scoreboard"),
    _c("football", "ar", "argentina-primera", "BBC Sport scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="BBC Argentine Primera path"),
    _c("football", "au", "australia-a-league", "BBC Sport scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 3, probe="BBC A-League path"),
    _c("horse-racing", "gb", "bha-meetings", "Sporting Life racing results JSON", "sporting-life", "public JSON", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="sportinglife.com/api/horse-racing/racing/results"),
    _c("greyhound-racing", "gb", "gbgb-meetings", "GBGB public results JSON", "gbgb-web", "public JSON", "meeting", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="api.gbgb.org.uk/api/results"),
    _c("tennis", "world", "wta-tour", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="Kayla Day vs Liudmila Samsonova 2026-09-17; attribution required; upstream TheSports"),
    _c("tennis", "world", "atp-tour", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="Martin Borisiouk vs Florent Bax 2026-09-17; attribution required; upstream TheSports"),
    _c("tennis", "world", "wta-tour", "api.wtatennis.com tennis JSON", "wta-json", "unauthenticated JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="tournaments/901/2026/matches Nikola Bartunkova vs Selena Janicijevic 2026-01-11"),
    _c("football", "asia", "afc-champions-league", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/asia/afc-champions-league/"),
    _c("football", "au", "australia-a-league-women", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/australia/a-league-women/"),
    _c("football", "africa", "caf-champions-league", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/africa/caf-champions-league/"),
    _c("football", "south-america", "copa-sudamericana", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/south-america/copa-sudamericana/"),
    _c("football", "rs", "serbia-superliga", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway Serbia Super Liga family page"),
    _c("football", "sk", "slovakia-super-liga", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/slovakia/nike-liga/"),
    _c("football", "th", "thai-league-1", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/thailand/thai-league-1/"),
    _c("football", "uz", "uzbekistan-super-league", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/uzbekistan/super-league/"),
    _c("football", "my", "malaysia-super-league", "Soccerway public competition HTML", "soccerway", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="soccerway.com/malaysia/super-league/"),
    _c("football", "in", "india-super-league", "AIFF ISL competition HTML/JSON", "aiff-web", "public HTML", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="the-aiff.com/competitions/isl Chennaiyin 1-2 Bengaluru 16 May 2026"),
    _c("rugby", "fr", "france-top-14", "RTÉ Rugby Top 14 results/fixtures", "rte-rugby", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="rte.ie/sport/results/rugby/top-14/43093/"),
    _c("rugby", "world", "super-rugby", "super.rugby public Match Centre HTML", "super-rugby-html", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="super.rugby/superrugby/match-centre match-packs HTML"),
    _c("ice-hockey", "fi", "finland-liiga", "EliteProspects Liiga scores", "eliteprospects", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="eliteprospects.com/league/liiga/scores"),
    _c("volleyball", "europe", "cev-eurovolley-men", "CEV Competition Area HTML", "cev-competition-area", "public HTML", "Y", "Y", "Y", "N", "Y", "N", "N", True, "permitted", 2, probe="www-old.cev.eu CompetitionView.aspx?ID=1572"),
    _c("rugby", "fr", "france-pro-d2", "prod2.lnr.fr calendrier-et-resultats", "prod2-web", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="prod2.lnr.fr J4 Aurillac-Brive"),
    _c("netball", "au", "ssn-australia", "NetballPass Suncorp Super Netball results", "netballpass", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="netballpass.com/results/2026/suncorp-super-netball"),
    _c("field-hockey", "world", "fih-eurohockey", "eurohockey.org championship event pages", "eurohockey-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="eurohockey.org/calendar/event Qualifier I Men 2026"),
    _c("volleyball", "pl", "plusliga", "Eurosport/TNT PlusLiga calendar-results", "eurosport-volleyball", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="eurosport.tvn24.pl plusliga Aluron Lublin"),
    _c("cycling", "world", "uci-calendar", "ProCyclingStats UCI race results", "pcs-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="procyclingstats.com/race/gp-montreal/2026/result"),
    _c("ea-sports-fc", "world", "competitive-ea-fc", "EA FC Pro official results/archive", "fcpro-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="ea.com fc-pro world championship 26 review"),
    _c("water-polo", "europe", "nordic-water-polo-league", "Total Waterpolo Nordic League pages", "total-waterpolo", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="total-waterpolo.com/nordic-league-men-2025-26"),
    _c("cycling", "fr", "tour-de-france", "RTÉ cycling results", "rte-cycling", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="rte.ie/sport/results/cycling"),
    _c("cycling", "fr", "tour-de-france", "BBC Sport cycling", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="bbc.com/sport/cycling"),
    _c("cycling", "world", "uci-calendar", "BBC Sport cycling", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="bbc.com/sport/cycling"),
    _c("cycling", "world", "uci-calendar", "RTÉ cycling results calendar", "rte-cycling", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="rte.ie/sport/results/cycling"),
    _c("rugby-league", "au", "nrl", "NRL 2026 Telstra Premiership draw", "nrl-draw-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="nrl.com/draw 2026"),
    _c("rugby-league", "au", "nrl", "BBC Sport NRL scores-fixtures", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="bbc.com/sport/rugby-league/nrl"),
    _c("field-hockey", "world", "fih-eurohockey", "England Hockey international results", "england-hockey-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="englandhockey.co.uk"),
    _c("lacrosse", "world", "world-lacrosse", "Lacrosse Canada results", "lacrosse-canada-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="lacrosse.ca"),
    _c("motorsport", "world", "formula-2", "BBC Sport motorsport", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="bbc.com/sport/formula1"),
    _c("motorsport", "world", "formula-2", "FIA Formula 2 official results", "fiaf2-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 2, probe="fiaformula2.com/Standings/Driver Melbourne SR/FR"),
    _c("motorsport", "world", "formula-2", "FIA steward F2 classifications", "fia-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="fia.com formula-2 melbourne sprint-race-classification Durksen"),
    _c("motorsport", "world", "formula-3", "BBC Sport motorsport", "bbc-sport", "public HTML", "Y", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="bbc.com/sport/formula1"),
    _c("motorsport", "world", "formula-3", "FIA Formula 3 official results", "fiaf3-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 2, probe="fiaformula3.com/Standings/Driver Melbourne SR/FR"),
    _c("motorsport", "world", "formula-3", "FIA steward F3 classifications", "fia-web", "public HTML", "session", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="fia.com formula-3 melbourne sprint-race-classification"),
    _c("field-hockey", "world", "fih-eurohockey", "Scottish Hockey Rome 2026 match recap", "scottish-hockey-web", "public HTML", "N", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="scottish-hockey.org.uk Scotland 6-1 Turkiye 9 Jul 2026"),
    _c("cycling", "world", "uci-calendar", "GPCQM official Montreal classement", "gpcqm-web", "public HTML", "N", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="gpcqm.ca Del Toro 5:13:16 13 Sep 2026"),
    _c("lacrosse", "world", "world-lacrosse", "Lacrosse Canada After the Final Whistle Japan QF", "lacrosse-canada-web", "public HTML", "N", "Y", "Y", "N", "N", "N", True, "permitted", 2, probe="lacrosse.ca CAN 5 JPN 4 OT 29 Jul 2026"),
    _c("futsal", "br", "brazil-lnf", "lnfoficial.com.br tabela de jogos finished scores", "lnf-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 2, probe="lnfoficial Minas 5x3 Atlantico 28 Jul 2026"),
    _c("basketball", "mx", "mexico-lnbp", "Wikipedia LNBP 2026 jornada tables", "wikipedia-lnbp-web", "public HTML CC BY-SA", "N", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 3, probe="es.wikipedia Fuerza Regia 105-94 Freseros 15 ago 2026"),
    _c("athletics", "world", "wa-calendar", "Diamond League Meeting de Paris official result PDF", "diamond-league-pdf", "public PDF", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="PDF 1.7 Flate streams; athlete names not plaintext without OCR"),
    _c("futsal", "world", "fifa-futsal-when-listed", "CBF FIFA Futsal World Cup recap", "cbf-fifa-futsal-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Brazil 2-1 Argentina FIFA Futsal WC 6 Oct 2024; Copa America rejected"),
    _c("futsal", "world", "fifa-futsal-when-listed", "AFA FIFA Futsal World Cup recap", "afa-fifa-futsal-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 4, probe="Argentina 1-2 Brazil Mundial de Futsal final"),
    _c("water-polo", "nordic", "nordic-water-polo-league", "nordicwaterpololeague.com Final Eight native results", "nordic-waterpolo-native", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="Tenerife 17-20 Galatasaray 2025-05-31 native page not TW iframe"),
    _c("table-tennis", "europe", "ettu-events", "ettu.org 2026 competition result articles", "ettu-news-results", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="France 3-2 Germany U15 Girls team final"),
    _c("table-tennis", "europe", "ettu-events", "fftt.com CEJ 2026 recap", "fftt-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="France 3-2 Allemagne U15 filles CEJ"),
    _c("golf", "kr", "korean-golf-tour", "kpga.co.kr tours/leaderboard HTML rows", "kpga-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="leaderboard rank/country/player/total/R1-R4; terms reviewed before ingest"),
    _c("rocket-league", "world", "rlcs", "rocketleague.com RLCS recap articles", "rocketleague-recaps", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="Karmine Corp 4-1 Twisted Minds Paris Major GF 2026-05-24"),
    _c("overwatch", "world", "owcs-historical", "Blizzard/OWCS Stage recap articles", "blizzard-owcs-recaps", "public HTML", "N", "N", "Y", "N", "N", "N", "N", False, "restricted", 2, probe="TERMS_RESTRICTED Blizzard; historical bucket replaced by owcs-world-finals"),
    _c("water-polo", "world", "world-aquatics-events", "worldaquatics.com event+unit result URLs", "world-aquatics-web", "public HTML", "event", "Y", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="France 11-15 Montenegro SF 2026-04-12 unit URL"),
    _c("water-polo", "world", "world-aquatics-events", "en.wikipedia.org 2026 Men's Water Polo World Cup", "wikipedia-wa-wp-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="Montenegro 19-17 Georgia gold 2026-04-13"),
    _c("counter-strike", "world", "tier1", "pglesports.com PGL Bucharest 2026", "pgl-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 2, probe="FUT 3-1 Astralis 2026-04-11"),
    _c("rocket-league", "world", "rlcs", "en.wikipedia.org Rocket League Championship Series", "wikipedia-rlcs-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="Paris Major Karmine Corp 4-1 Twisted Minds 20-24 May 2026"),
    _c("valorant", "world", "vct", "en.wikipedia.org Valorant Champions Tour", "wikipedia-vct-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="Masters Santiago Nongshim RedForce 3-0 Paper Rex"),
    _c("overwatch", "world", "owcs-historical", "esportsworldcup.com Overwatch 2026 competition", "ewc-owcs-web", "public HTML", "N", "Y", "Y", "Y", "N", "N", "N", False, "restricted", 3, probe="TERMS_RESTRICTED EWC; historical bucket replaced by owcs-world-finals"),
    _c("table-tennis", "europe", "ettu-events", "tischtennis.de DTTB Jugend-EM recap", "dttb-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="U15 Maedchen Finale Deutschland-Frankreich 2:3 Eva Lam"),
    _c("winter-sports", "world", "biathlon", "skidskytte.se Ruhpolding jaktstart recap", "skidskytte-web", "public HTML", "N", "N", "Y", "N", "N", "N", "N", True, "unclear", 3, probe="Hanna Oeberg 2nd 10s behind Lou Jeanmonnot 18 Jan 2026"),
    _c("golf", "kr", "korean-golf-tour", "en.wikipedia.org 2026 Korean Tour season table", "wikipedia-korean-tour-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 3, probe="DB Insurance Promy Open 19 Apr 2026 Lee Sang-yeop; overlaps TSDB Korean Tour 4766"),
    _c("overwatch", "world", "owcs-historical", "esportscommunity.net tournament 31 OWCS MSC", "esportscommunity-owcs-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, derived_from="liquipedia", probe="ZETA 4-2 Twisted Minds; terms forbid scrape/crawl dashboard; privacy states tournament data sourced from Liquipedia CC-BY-SA"),
    _c("overwatch", "world", "owcs-historical", "strafe.com OWCS scores", "strafe-web", "public HTML", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "restricted", 99, probe="ZETA 4-2 Twisted Minds 02 Aug 2026; Strafe ToS private/non-commercial only and no license to copy/reproduce"),
    _c("greyhound-racing", "ie", "ireland-gri-meetings", "independent Irish race-result publishers", "unknown", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", "n/a", False, "unclear", 99, probe="STRUCTURAL_SINGLE_UPSTREAM: replaced by irish-greyhound-derby GRI+Wikipedia"),
    _c("greyhound-racing", "ie", "irish-greyhound-derby", "grireland.ie Irish Greyhound Derby results/history", "gri-web", "public HTML", "N", "Y", "Y", "N", "N", "N", "N", True, "unclear", 1, probe="2025 Final Cheap Sandwiches 29.37 27-Sep-25 SPK; 2026 Bockos Gold 29.05 12-Sep-26"),
    _c("greyhound-racing", "ie", "irish-greyhound-derby", "en.wikipedia.org {year}_Irish_Greyhound_Derby", "wikipedia-irish-greyhound-derby-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="2025 Final Cheap Sandwiches 29.37 Barefoot On Song 29.58 27 Sep 2025 Shelbourne Park"),
    _c("overwatch", "world", "owcs-world-finals", "Liquipedia OWCS World Finals", "liquipedia", "gzip JSON/HTML", "N", "Y", "Y", "Y", "N", "N", "N", True, "unclear", 1, probe="2025 World Finals Twisted Minds 4-1 Al Qadsiah 2025-11-30"),
    _c("overwatch", "world", "owcs-world-finals", "en.wikipedia.org Overwatch Champions Series World Finals results", "wikipedia-owcs-world-finals-web", "public HTML CC BY-SA", "N", "Y", "Y", "N", "N", "N", "N", True, "permitted", 2, probe="2025 Twisted Minds 4-1 Al Qadsiah Stockholm; 2024 Team Falcons 4-1 Crazy Raccoon"),
    _c("football", "us", "usa-usl-championship", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget competition=USL Championship status+score; attribution; upstream TheSports not independent of TSDB"),
    _c("football", "us", "mls", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 United States Major League Soccer live 7; status_text 2nd half; img.thesports.com"),
    _c("football", "mx", "mexico-liga-mx", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget competition=Mexico Liga MX"),
    _c("football", "ar", "argentina-primera", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget competition=Argentine Division 1"),
    _c("football", "br", "brazil-serie-a", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget competition=Brazilian Serie A"),
    _c("football", "us", "usa-nwsl", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget United States Women's National Soccer League"),
    _c("basketball", "mx", "mexico-lnbp", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget Liga Nacional de Baloncesto Profesional"),
    _c("basketball", "us", "wnba", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 widget Women's National Basketball Association"),
    _c("cricket", "world", "internationals-and-leagues", "SportScore widget JSON", "sportscore", "public JSON", "Y", "Y", "Y", "N", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 ODI Series Zimbabwe vs Australia in cricket widget; cricket-native scores if present; upstream TheSports"),
    _c("football", "in", "india-super-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=indian-super-league tables=1; same widget schema via team fixtures"),
    _c("football", "th", "thai-league-1", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=thai-league-1 tables=1"),
    _c("football", "africa", "caf-champions-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=caf-champions-league tables=1"),
    _c("football", "asia", "afc-champions-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=afc-champions-league tables=10"),
    _c("football", "scotland", "scotland-premiership", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=scottish-premiership tables=1"),
    _c("football", "at", "austria-bundesliga", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=austrian-bundesliga tables=1"),
    _c("football", "na", "concacaf-champions-cup", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=concacaf-champions-cup tables=1 competition=CONCACAF Champions Cup"),
    _c("football", "ir", "iran-pro-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=iran-pro-league tables=1"),
    _c("football", "ie", "ireland-premier-division", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=ireland-premier-division tables=1"),
    _c("football", "kz", "kazakhstan-premier-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=kazakhstan-premier-league tables=1"),
    _c("football", "es", "spain-la-liga", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=spanish-la-liga tables=1"),
    _c("football", "ch", "switzerland-super-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=switzerland-super-league tables=1"),
    _c("football", "uz", "uzbekistan-super-league", "SportScore standings+team JSON", "sportscore", "public JSON", "Y", "Y", "Y", "Y", "N", "N", "N", True, "permitted", 1, probe="2026-09-20 standings slug=uzbekistan-super-league tables=1"),
]


def competition_operational_family_scopes() -> Dict[str, Dict[str, Set[str]]]:
    grouped: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in COVERAGE:
        family = _operational_family(row)
        if not family:
            continue
        scope = row.get("coverage_scope") or "full"
        grouped[row["competition"]][family].add(scope)
    return grouped


def competitions_full_operational_fallback(n: int = 2) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for comp, families in competition_operational_family_scopes().items():
        full = sorted(fam for fam, scopes in families.items() if "full" in scopes)
        if len(full) >= n:
            out[comp] = full
    return out


def competitions_partial_only_operational_fallback() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for comp, families in competition_operational_family_scopes().items():
        full = [fam for fam, scopes in families.items() if "full" in scopes]
        partial_only = sorted(fam for fam, scopes in families.items() if "full" not in scopes)
        if len(full) == 1 and partial_only:
            out[comp] = partial_only
    return out



def unique_operational_families() -> List[str]:
    families: Set[str] = set()
    for row in COVERAGE:
        family = _operational_family(row)
        if family:
            families.add(family)
    return sorted(families)



NON_OPERATIONAL_FAMILIES = {"wikimedia"}


def _independent_family(row: CoverageRow) -> Optional[str]:
    if not row.get("technically_collectable"):
        return None
    derived = (row.get("derived_from") or "").strip()
    if derived:
        return None
    status = (row.get("independence_status") or "established").strip()
    if status in {"unknown", "derived", "shared-upstream"}:
        return None
    return row["upstream_family"]


def _operational_family(row: CoverageRow) -> Optional[str]:
    family = _independent_family(row)
    if family is None or family in NON_OPERATIONAL_FAMILIES:
        return None
    return family


def operational_families_for_sport(sport_id: str) -> Set[str]:
    families: Set[str] = set()
    for row in COVERAGE:
        if row["sport"] != sport_id:
            continue
        family = _operational_family(row)
        if family:
            families.add(family)
    return families


def operational_families_for_competition(competition: str) -> Set[str]:
    families: Set[str] = set()
    for row in COVERAGE:
        if row["competition"] != competition:
            continue
        family = _operational_family(row)
        if family:
            families.add(family)
    return families


def independent_families_for_sport(sport_id: str) -> Set[str]:
    families: Set[str] = set()
    for row in COVERAGE:
        if row["sport"] != sport_id:
            continue
        family = _independent_family(row)
        if family:
            families.add(family)
    return families


def independent_families_for_competition(competition: str) -> Set[str]:
    families: Set[str] = set()
    for row in COVERAGE:
        if row["competition"] != competition:
            continue
        family = _independent_family(row)
        if family:
            families.add(family)
    return families


def sports_with_technically_collectable_source() -> List[str]:
    have = {row["sport"] for row in COVERAGE if row["technically_collectable"]}
    return sorted(have)


def sports_missing_technically_collectable_source() -> List[str]:
    have = set(sports_with_technically_collectable_source())
    return sorted(row["slug"] for row in SPORTS if row["slug"] not in have)


def sports_with_at_least_n_independent_families(n: int) -> List[str]:
    return sorted(
        row["slug"]
        for row in SPORTS
        if len(independent_families_for_sport(row["slug"])) >= n
    )


def sports_with_exactly_n_independent_families(n: int) -> List[str]:
    return sorted(
        row["slug"]
        for row in SPORTS
        if len(independent_families_for_sport(row["slug"])) == n
    )


def unique_source_families() -> List[str]:
    return sorted({row["upstream_family"] for row in COVERAGE if row["technically_collectable"]})


def competitions_covered() -> List[str]:
    return sorted({row["competition"] for row in COVERAGE if row["technically_collectable"]})


def competitions_with_true_fallback() -> Dict[str, List[str]]:
    grouped: Dict[str, Set[str]] = defaultdict(set)
    for row in COVERAGE:
        family = _independent_family(row)
        if family:
            grouped[row["competition"]].add(family)
    return {comp: sorted(families) for comp, families in grouped.items() if len(families) >= 2}


def competitions_with_operational_fallback(n: int = 2) -> Dict[str, List[str]]:
    grouped: Dict[str, Set[str]] = defaultdict(set)
    for row in COVERAGE:
        family = _operational_family(row)
        if family:
            grouped[row["competition"]].add(family)
    return {comp: sorted(families) for comp, families in grouped.items() if len(families) >= n}


def competitions_single_operational_family() -> Dict[str, List[str]]:
    grouped: Dict[str, Set[str]] = defaultdict(set)
    for row in COVERAGE:
        family = _operational_family(row)
        if family:
            grouped[row["competition"]].add(family)
    return {comp: sorted(families) for comp, families in grouped.items() if len(families) == 1}


def sports_with_at_least_n_operational_families(n: int) -> List[str]:
    return sorted(
        row["slug"]
        for row in SPORTS
        if len(operational_families_for_sport(row["slug"])) >= n
    )


# Backward-compatible sport-level list used by existing tests.
SOURCES: List[SourceRow] = []
_seen_source = set()
for _row in COVERAGE:
    key = (_row["sport"], _row["source"])
    if key in _seen_source:
        continue
    _seen_source.add(key)
    SOURCES.append(
        {
            "sport_id": _row["sport"],
            "source": _row["source"],
            "coverage": _row["competition"],
            "method": _row["collection_method"],
            "live": _row["live"],
            "fixtures": _row["fixtures"],
            "results": _row["results"],
            "standings": _row["standings"],
            "technically_collectable": _row["technically_collectable"],
            "production_reuse_status": _row["production_reuse_status"],
            "implemented": "see production.py",
            "upstream_family": _row["upstream_family"],
            "derived_from": _row.get("derived_from") or "",
        }
    )
