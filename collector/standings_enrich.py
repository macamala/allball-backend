"""On-demand competition standings. Never called from the score list path."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_fotmob import FOTMOB_LEAGUES, parse_fotmob_table
from collector.canonical_standings import unwrap_standings
from collector.http import fetch_url
from collector.models import SportsEvent, SportsStandingSnapshot
from collector.util import dump_json, load_json
from collector.verified_coverage import OPENLIGADB_LEAGUES

TTL_SECONDS = 1800
FOTMOB_LEAGUE = "https://www.fotmob.com/api/data/leagues?id={league_id}"
OPENLIGA_TABLE = "https://api.openligadb.de/getbltable/{shortcut}/{year}"
NHL_STANDINGS = "https://api-web.nhle.com/v1/standings/now"
MLB_STANDINGS = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason"
SQUIGGLE_STANDINGS = "https://api.squiggle.com.au/?q=standings;year={year}"
JOLPICA_DRIVERS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"

def standings_supported(competition_id: Optional[str]) -> bool:
    if not competition_id:
        return False
    if competition_id in FOTMOB_LEAGUES:
        return True
    if competition_id in {"nhl", "mlb", "australia-afl", "formula-1"}:
        return True
    return _openliga_shortcut(competition_id) is not None


def parse_nhl_standings(payload: Any) -> List[Dict[str, Any]]:
    rows = payload.get("standings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get("teamName") or item.get("teamCommonName") or {}
        if isinstance(name, dict):
            name = name.get("default") or name.get("name")
        if not name:
            continue
        gf = item.get("goalFor")
        ga = item.get("goalAgainst")
        gd = None
        if gf is not None and ga is not None:
            try:
                gd = int(gf) - int(ga)
            except (TypeError, ValueError):
                gd = None
        out.append(
            {
                "position": item.get("leagueSequence") or item.get("wildcardSequence"),
                "team": name,
                "played": item.get("gamesPlayed"),
                "wins": item.get("wins"),
                "losses": item.get("losses"),
                "ot_losses": item.get("otLosses"),
                "points": item.get("points"),
                "goals_for": gf,
                "goals_against": ga,
                "goal_difference": gd,
                "group": (item.get("conferenceName") or "") + ((" / " + item.get("divisionName")) if item.get("divisionName") else ""),
            }
        )
    return out


def parse_mlb_standings(payload: Any) -> List[Dict[str, Any]]:
    records = payload.get("records") if isinstance(payload, dict) else []
    out = []
    for block in records or []:
        group = ((block.get("division") or {}).get("name")) if isinstance(block, dict) else None
        for item in (block or {}).get("teamRecords") or []:
            if not isinstance(item, dict):
                continue
            team = (item.get("team") or {}).get("name")
            if not team:
                continue
            league = item.get("leagueRecord") or {}
            out.append(
                {
                    "position": item.get("divisionRank") or item.get("leagueRank"),
                    "team": team,
                    "played": item.get("gamesPlayed"),
                    "wins": league.get("wins") or item.get("wins"),
                    "losses": league.get("losses") or item.get("losses"),
                    "pct": league.get("pct") or item.get("winningPercentage"),
                    "group": group,
                }
            )
    return out


def parse_squiggle_standings(payload: Any) -> List[Dict[str, Any]]:
    rows = payload.get("standings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("team")
        if not name:
            continue
        out.append(
            {
                "position": item.get("rank") or item.get("position"),
                "team": name,
                "played": item.get("played") or item.get("games"),
                "wins": item.get("wins"),
                "losses": item.get("losses"),
                "draws": item.get("draws"),
                "points": item.get("pts") or item.get("points"),
                "goals_for": item.get("for") or item.get("pf"),
                "goals_against": item.get("against") or item.get("pa"),
                "percentage": item.get("percentage"),
            }
        )
    return out


def parse_jolpica_standings(payload: Any) -> List[Dict[str, Any]]:
    lists = (((payload or {}).get("MRData") or {}).get("StandingsTable") or {}).get("StandingsLists") or []
    if not lists:
        return []
    drivers = (lists[0] or {}).get("DriverStandings") or []
    out = []
    for item in drivers:
        if not isinstance(item, dict):
            continue
        driver = item.get("Driver") or {}
        name = " ".join(part for part in (driver.get("givenName"), driver.get("familyName")) if part)
        if not name:
            continue
        constructor = ((item.get("Constructors") or [{}])[0] or {}).get("name")
        out.append(
            {
                "position": item.get("position"),
                "team": name,
                "points": item.get("points"),
                "wins": item.get("wins"),
                "group": constructor,
            }
        )
    return out


def _fresh(row: Optional[SportsStandingSnapshot]) -> bool:
    if row is None or not row.captured_at:
        return False
    age = datetime.utcnow() - row.captured_at.replace(tzinfo=None)
    return age < timedelta(seconds=TTL_SECONDS) and bool(unwrap_standings(load_json(row.rows_json, [])))


def _openliga_shortcut(competition_id: str) -> Optional[str]:
    for spec in OPENLIGADB_LEAGUES:
        if spec.get("competition_id") == competition_id:
            return str(spec.get("shortcut") or "")
    return None


def fetch_competition_standings(competition_id: str, getter=None) -> Dict[str, Any]:
    getter = getter or fetch_url
    spec = FOTMOB_LEAGUES.get(competition_id) or {}
    if spec.get("id"):
        result = getter(FOTMOB_LEAGUE.format(league_id=spec["id"]))
        if result.ok and isinstance(result.payload, dict):
            rows = parse_fotmob_table(result.payload)
            if rows:
                return wrap_standings(rows, competition=competition_id, source="fotmob")
    shortcut = _openliga_shortcut(competition_id)
    if shortcut:
        year = datetime.utcnow().year
        result = getter(OPENLIGA_TABLE.format(shortcut=shortcut, year=year))
        payload = result.payload if result.ok else None
        if isinstance(payload, list) and payload:
            from collector.adapters_openligadb import _standings

            return wrap_standings(_standings(payload), competition=competition_id, season=str(year), source="openligadb")
    if competition_id == "nhl":
        result = getter(NHL_STANDINGS)
        if result.ok:
            rows = parse_nhl_standings(result.payload)
            if rows:
                return wrap_standings(rows, competition=competition_id, sport="ice-hockey", source="nhl-web")
    if competition_id == "mlb":
        result = getter(MLB_STANDINGS.format(season=datetime.utcnow().year))
        if result.ok:
            rows = parse_mlb_standings(result.payload)
            if rows:
                return wrap_standings(rows, competition=competition_id, sport="baseball", source="mlb-statsapi")
    if competition_id == "australia-afl":
        from collector.adapters_squiggle import SQUIGGLE_HEADERS, parse_squiggle_payload

        year = datetime.utcnow().year
        urls = []
        for season in (year, year - 1):
            urls.append(SQUIGGLE_STANDINGS.format(year=season))
            urls.append(f"https://api.squiggle.com.au/?q=standings&year={season}")
        urls.append("https://api.squiggle.com.au/?q=standings")
        for url in urls:
            try:
                result = getter(url, headers=SQUIGGLE_HEADERS)
            except TypeError:
                result = getter(url)
            payload = result.payload if result is not None else None
            rows_raw, _meta = parse_squiggle_payload(payload, "standings")
            rows = parse_squiggle_standings({"standings": rows_raw} if rows_raw else payload)
            if rows:
                season = None
                if "year=" in url:
                    season = url.rsplit("year=", 1)[-1]
                return wrap_standings(
                    rows,
                    competition=competition_id,
                    season=str(season or year),
                    sport="australian-rules",
                    source="squiggle-afl",
                )
    if competition_id == "formula-1":
        result = getter(JOLPICA_DRIVERS)
        if result.ok:
            rows = parse_jolpica_standings(result.payload)
            if rows:
                return wrap_standings(rows, competition=competition_id, sport="motorsport", source="jolpica-f1")
    return {}


def wrap_standings(rows, *, competition, season=None, stage=None, group=None, sport=None, source=None):
    from collector.canonical_standings import wrap_standings as _wrap

    payload = _wrap(rows, competition=competition, season=season, stage=stage, group=group, sport=sport)
    if source:
        payload["source"] = source
    return payload


def load_standings(db: Session, competition_key: Optional[str], getter=None) -> List[Dict[str, Any]]:
    if not competition_key:
        return []
    query = db.query(SportsStandingSnapshot).filter_by(competition_id=competition_key)
    row = query.order_by(SportsStandingSnapshot.captured_at.desc()).first()
    if _fresh(row):
        return unwrap_standings(load_json(row.rows_json, []))
    fetched = {}
    has_events = (
        db.query(SportsEvent.event_id)
        .filter_by(competition_id=competition_key)
        .limit(1)
        .first()
    )
    if has_events:
        fetched = fetch_competition_standings(competition_key, getter=getter)
    rows = unwrap_standings(fetched) if fetched else []
    if rows:
        db.add(
            SportsStandingSnapshot(
                competition_id=competition_key,
                sport_id=fetched.get("sport"),
                season=fetched.get("season"),
                source_id=fetched.get("source"),
                rows_json=dump_json(fetched),
                captured_at=datetime.utcnow(),
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
        return rows
    if row:
        return unwrap_standings(load_json(row.rows_json, []))
    return []
