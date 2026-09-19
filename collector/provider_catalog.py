"""Shared no-key provider competition catalogs.

Built from live list endpoints (or recorded list payloads) then matched to
canonical NinkoSports competitions by sport + country + normalized name.
Does not install third-party MCP servers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collector.adapters_espn import ESPN_HTML
from collector.verified_coverage import THESPORTSDB_LEAGUES
from sports_registry.competitions import all_competitions

ROOT = Path(__file__).resolve().parent

# Live-listed 2026-09-17 from https://worldcup26.ir/get/soccer/leagues
WORLDCUP26_LEAGUES = [
    {"id": "eng.1", "name": "English Premier League", "country": "England", "sport": "football"},
    {"id": "eng.2", "name": "English League Championship", "country": "England", "sport": "football"},
    {"id": "eng.3", "name": "English League One", "country": "England", "sport": "football"},
    {"id": "eng.4", "name": "English League Two", "country": "England", "sport": "football"},
    {"id": "eng.fa", "name": "English FA Cup", "country": "England", "sport": "football"},
    {"id": "esp.1", "name": "Spanish LALIGA", "country": "Spain", "sport": "football"},
    {"id": "ger.1", "name": "German Bundesliga", "country": "Germany", "sport": "football"},
    {"id": "ita.1", "name": "Italian Serie A", "country": "Italy", "sport": "football"},
    {"id": "fra.1", "name": "French Ligue 1", "country": "France", "sport": "football"},
    {"id": "ned.1", "name": "Dutch Eredivisie", "country": "Netherlands", "sport": "football"},
    {"id": "sco.1", "name": "Scottish Premiership", "country": "Scotland", "sport": "football"},
    {"id": "por.1", "name": "Portuguese Primeira Liga", "country": "Portugal", "sport": "football"},
    {"id": "bel.1", "name": "Belgian Pro League", "country": "Belgium", "sport": "football"},
    {"id": "aut.1", "name": "Austrian Bundesliga", "country": "Austria", "sport": "football"},
    {"id": "tur.1", "name": "Turkish Super Lig", "country": "Turkey", "sport": "football"},
    {"id": "usa.1", "name": "MLS", "country": "United States", "sport": "football"},
    {"id": "mex.1", "name": "Mexican Liga BBVA MX", "country": "Mexico", "sport": "football"},
    {"id": "arg.1", "name": "Argentine Liga Profesional", "country": "Argentina", "sport": "football"},
    {"id": "bra.1", "name": "Brazilian Serie A", "country": "Brazil", "sport": "football"},
    {"id": "jpn.1", "name": "Japanese J.League", "country": "Japan", "sport": "football"},
]

# Live-listed 2026-09-17 from https://api.sportsrc.org/?data=results&category=leagues
SPORTSRC_LEAGUES = [
    {"id": "WC", "name": "World Cup", "country": "world", "sport": "football"},
    {"id": "CL", "name": "UEFA Champions League", "country": "europe", "sport": "football"},
    {"id": "BL1", "name": "Bundesliga", "country": "Germany", "sport": "football"},
    {"id": "DED", "name": "Eredivisie", "country": "Netherlands", "sport": "football"},
    {"id": "BSA", "name": "Campeonato Brasileiro Série A", "country": "Brazil", "sport": "football"},
    {"id": "PD", "name": "La Liga", "country": "Spain", "sport": "football"},
    {"id": "FL1", "name": "Ligue 1", "country": "France", "sport": "football"},
    {"id": "ELC", "name": "Championship", "country": "England", "sport": "football"},
    {"id": "PPL", "name": "Primeira Liga", "country": "Portugal", "sport": "football"},
    {"id": "EC", "name": "European Championship", "country": "europe", "sport": "football"},
    {"id": "SA", "name": "Serie A", "country": "Italy", "sport": "football"},
    {"id": "PL", "name": "Premier League", "country": "England", "sport": "football"},
]

SPORTING_EVENTS_DATASETS = [
    {"id": "football", "name": "Football", "sport": "football", "country": "", "coverage": "mixed-uefa-clubs-and-nations"},
    {"id": "rugby-union", "name": "Rugby Union", "sport": "rugby", "country": "world", "coverage": "nations-championship-six-nations"},
    {"id": "nrl", "name": "NRL", "sport": "rugby-league", "country": "au", "coverage": "empty-this-fetch"},
    {"id": "esports", "name": "Esports", "sport": "esports", "country": "world", "coverage": "tournament-titles-only"},
    {"id": "swimming", "name": "Swimming", "sport": "swimming", "country": "world", "coverage": "meet-titles-only"},
    {"id": "golf", "name": "Golf", "sport": "golf", "country": "world", "coverage": "pga-dp-world-not-korean-tour"},
    {"id": "motogp", "name": "MotoGP", "sport": "motorsport", "country": "world", "coverage": "calendar"},
    {"id": "tennis", "name": "Tennis", "sport": "tennis", "country": "world", "coverage": "tour-calendar"},
]

COUNTRY_ALIASES = {
    "england": {"england", "united kingdom", "uk"},
    "us": {"united states", "usa", "us"},
    "de": {"germany", "de"},
    "es": {"spain", "es"},
    "it": {"italy", "it"},
    "fr": {"france", "fr"},
    "nl": {"netherlands", "holland", "ned"},
    "pt": {"portugal", "por"},
    "ar": {"argentina", "arg"},
    "mx": {"mexico", "mex"},
    "br": {"brazil", "bra"},
    "jp": {"japan", "jpn"},
    "au": {"australia", "aus"},
    "tr": {"turkey", "türkiye", "turkiye"},
    "at": {"austria", "aut"},
    "be": {"belgium", "bel"},
    "sco": {"scotland"},
    "rs": {"serbia"},
    "sk": {"slovakia"},
    "cz": {"czechia", "czech republic"},
    "in": {"india"},
    "my": {"malaysia"},
    "th": {"thailand"},
    "uz": {"uzbekistan"},
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def catalog_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in THESPORTSDB_LEAGUES:
        rows.append(
            {
                "provider_family": "thesportsdb",
                "provider_competition_id": item["source_competition_id"],
                "sport": item["sport_id"],
                "competition_name": item["name"],
                "country": item.get("country_id") or "",
                "season": "",
                "coverage_type": "fixtures/results",
            }
        )
    for competition_id, url in ESPN_HTML.items():
        rows.append(
            {
                "provider_family": "espn-html",
                "provider_competition_id": url.rsplit("/", 1)[-1],
                "sport": "",
                "competition_name": competition_id.replace("-", " "),
                "country": "",
                "season": "",
                "coverage_type": "scoreboard",
                "canonical_hint": competition_id,
            }
        )
    for item in WORLDCUP26_LEAGUES:
        rows.append(
            {
                "provider_family": "worldcup26-api",
                "provider_competition_id": item["id"],
                "sport": "football",
                "competition_name": item["name"],
                "country": item["country"],
                "season": "2026",
                "coverage_type": "fixtures/scoreboard/standings",
            }
        )
    for item in SPORTSRC_LEAGUES:
        rows.append(
            {
                "provider_family": "sportsrc",
                "provider_competition_id": item["id"],
                "sport": "football",
                "competition_name": item["name"],
                "country": item["country"],
                "season": "",
                "coverage_type": "scores/tables",
            }
        )
    for item in SPORTING_EVENTS_DATASETS:
        rows.append(
            {
                "provider_family": "sporting-events",
                "provider_competition_id": item["id"],
                "sport": item["sport"],
                "competition_name": item["name"],
                "country": item.get("country") or "",
                "season": "2026",
                "coverage_type": item["coverage"],
            }
        )
    return rows


def match_catalog(canonical_id: str) -> List[Dict[str, Any]]:
    identity = all_competitions().get(canonical_id) or {}
    sport = identity.get("sport_id") or ""
    country = (identity.get("country_id") or identity.get("region_id") or "").lower()
    names = {
        _norm(canonical_id),
        _norm(identity.get("name") or ""),
        _norm(identity.get("official_name") or ""),
        *(_norm(alias) for alias in (identity.get("aliases") or [])),
    }
    names.discard("")
    hits = []
    for row in catalog_rows():
        if row.get("canonical_hint") == canonical_id:
            hits.append({**row, "match": "exact-hint"})
            continue
        if row["sport"] and sport and row["sport"] != sport:
            continue
        row_country = _norm(row.get("country") or "")
        if country and row_country and row_country not in {"world", "europe"}:
            aliases = COUNTRY_ALIASES.get(country, {country})
            if row_country not in {_norm(item) for item in aliases} and country not in row_country:
                continue
        row_name = _norm(row.get("competition_name") or "")
        if any(row_name and (row_name in name or name in row_name) for name in names if len(name) > 4):
            hits.append({**row, "match": "name+sport+country"})
    return hits


def write_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    rows = catalog_rows()
    payload = {"providers": rows, "count": len(rows)}
    out = path or (ROOT / "provider_competition_catalog.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
