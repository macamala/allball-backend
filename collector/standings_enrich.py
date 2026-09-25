"""On-demand competition standings. Never called from the score list path."""

from __future__ import annotations

from datetime import datetime, timedelta
from collections import OrderedDict
import time
import threading
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters_fotmob import FOTMOB_LEAGUES, parse_fotmob_table
from collector.canonical_standings import unwrap_standings
from collector.http import fetch_url
from collector.models import SportsCompetition, SportsEvent, SportsSourceCompetition, SportsStandingSnapshot
from collector.util import dump_json, load_json
from collector.verified_coverage import OPENLIGADB_LEAGUES

TTL_SECONDS = 1800
_NEGATIVE_TABLES = OrderedDict()
_TABLE_LOCK = threading.RLock()
_TABLE_INFLIGHT = set()
FOTMOB_LEAGUE = "https://www.fotmob.com/api/data/leagues?id={league_id}"
OPENLIGA_TABLE = "https://api.openligadb.de/getbltable/{shortcut}/{year}"
NHL_STANDINGS = "https://api-web.nhle.com/v1/standings/now"
MLB_STANDINGS = "https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season={season}&standingsTypes=regularSeason"
SQUIGGLE_STANDINGS = "https://api.squiggle.com.au/?q=standings&year={year}"
EUROLEAGUE_STANDINGS = "https://api-live.euroleague.net/v1/standings?seasonCode={season}"
PLUSLIGA_STANDINGS = "https://www.plusliga.pl/table/tour/52/nocookies/1.html"
SUPERLEGA_HOME = "https://www.legavolley.it/superlega/"
JOLPICA_DRIVERS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"
SOFA_DYNAMIC_STANDINGS = "https://www.sofascore.com/api/v1/unique-tournament/{tournament_id}/season/{season_id}/standings/total"

def parse_sofa_dynamic_standings(payload: Any, *, sport_id: Optional[str] = None) -> List[Dict[str, Any]]:
    blocks = payload.get("standings") if isinstance(payload, dict) else []
    if not isinstance(blocks, list):
        return []
    out: List[Dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        group = block.get("name") or block.get("groupName") or block.get("description")
        rows = block.get("rows") or []
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            team = item.get("team") or {}
            name = team.get("name") if isinstance(team, dict) else team
            if not name:
                continue
            scores_for = item.get("scoresFor")
            scores_against = item.get("scoresAgainst")
            team_id = str(team.get("id") or "").strip() if isinstance(team, dict) else ""
            team_country = team.get("country") if isinstance(team, dict) else None
            if isinstance(team_country, dict):
                team_country = (
                    team_country.get("alpha2")
                    or team_country.get("alpha3")
                    or team_country.get("code")
                    or team_country.get("name")
                )
            row = {
                "position": item.get("position") or item.get("rank"),
                "team": name,
                "team_id": team_id or None,
                "logo": f"https://img.sofascore.com/api/v1/team/{team_id}/image" if team_id else None,
                "country_id": team_country or None,
                "played": item.get("matches") or item.get("played") or item.get("gamesPlayed"),
                "wins": item.get("wins"),
                "draws": item.get("draws"),
                "losses": item.get("losses"),
                "points": item.get("points"),
                "form": item.get("form"),
                "group": group,
                "goals_for": scores_for,
                "goals_against": scores_against,
                "goal_difference": item.get("scoreDiff") or item.get("goalDifference"),
                "points_for": scores_for,
                "points_against": scores_against,
                "sets_for": item.get("setsFor"),
                "sets_against": item.get("setsAgainst"),
                "ot_losses": item.get("overtimeLosses") or item.get("otLosses"),
                "pct": item.get("percentage"),
                "win_pct": item.get("winPercentage"),
            }
            out.append({key: value for key, value in row.items() if value not in (None, "", [])})
    return out


def fotmob_standings_context(db: Session, competition_key: Optional[str]) -> Optional[Dict[str, str]]:
    if not competition_key:
        return None
    competition = db.get(SportsCompetition, competition_key)
    if competition is None or competition.sport_id != "football" or str(competition.event_model or "") != "team_match":
        return None
    mappings = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_key, enabled=True)
        .order_by(SportsSourceCompetition.priority.asc())
        .all()
    )
    for mapping in mappings:
        if str(mapping.upstream_family or "") != "fotmob":
            continue
        config = load_json(mapping.source_config_json, {}) or {}
        league_id = str(config.get("fotmob_league_id") or mapping.source_competition_id or "").strip()
        if not league_id:
            continue
        return {
            "league_id": league_id,
            "league_name": str(config.get("fotmob_league_name") or competition.name or "").strip(),
            "sport_id": "football",
        }
    return None


def sofa_standings_context(db: Session, competition_key: Optional[str]) -> Optional[Dict[str, str]]:
    if not competition_key:
        return None
    competition = db.get(SportsCompetition, competition_key)
    if competition is not None and str(competition.event_model or "") != "team_match":
        return None
    rows = (
        db.query(SportsEvent)
        .filter_by(competition_id=competition_key)
        .order_by(SportsEvent.start_time.desc())
        .limit(40)
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        tournament_id = str(extra.get("sofascore_tournament_id") or "").strip()
        season_id = str(extra.get("sofascore_season_id") or extra.get("source_season_id") or "").strip()
        if not tournament_id or not season_id:
            continue
        return {
            "tournament_id": tournament_id,
            "season_id": season_id,
            "season_name": str(extra.get("source_season_name") or row.season or "").strip(),
            "sport_id": str(row.sport_id or "").strip(),
        }
    return None


def dynamic_standings_supported(db: Session, competition_key: Optional[str]) -> bool:
    return (
        fotmob_standings_context(db, competition_key) is not None
        or sofa_standings_context(db, competition_key) is not None
    )


def _fetch_fotmob_dynamic_standings(db: Session, competition_key: str, *, getter=None) -> Dict[str, Any]:
    context = fotmob_standings_context(db, competition_key)
    if not context:
        return {}
    fetch = getter or fetch_url
    from collector.football_table_identity import resolve_context, scoped_table
    context = resolve_context(db, competition_key, context, fetch)
    if not context:
        return {}
    result = fetch(FOTMOB_LEAGUE.format(league_id=context["parent_id"]))
    if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), dict):
        return {}
    scoped = scoped_table(result.payload, context)
    rows = parse_fotmob_table(scoped) if scoped else []
    # Team membership strengthens group identity and prevents an old season's
    # table from silently substituting for the current match's group.
    teams = {str(r.get("team_id")) for r in rows}
    expected = {str(t) for t in context.get("teams", []) if t}
    if not rows or (expected and not expected.issubset(teams)):
        return {}
    fetched = wrap_standings(
        rows, competition=competition_key,
        season=str((result.payload.get("details") or {}).get("selectedSeason") or "") or None,
        sport="football", source="fotmob",
    )
    fetched["source_parent_id"] = context["parent_id"]
    fetched["source_leaf_id"] = context["leaf_id"]
    fetched["identity_revision"] = 1
    return fetched


def _fetch_sofa_dynamic_standings(db: Session, competition_key: str, *, getter=None) -> Dict[str, Any]:
    context = sofa_standings_context(db, competition_key)
    if not context:
        return {}
    from collector.adapters_sofascore import sofa_fetch_url

    fetch = getter or sofa_fetch_url
    url = SOFA_DYNAMIC_STANDINGS.format(
        tournament_id=context["tournament_id"],
        season_id=context["season_id"],
    )
    result = fetch(url)
    if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), dict):
        return {}
    rows = parse_sofa_dynamic_standings(result.payload, sport_id=context.get("sport_id"))
    if not rows:
        return {}
    return wrap_standings(
        rows,
        competition=competition_key,
        season=context.get("season_name") or context.get("season_id"),
        stage="total",
        sport=context.get("sport_id"),
        source="sofascore-web",
    )


def standings_supported(competition_id: Optional[str]) -> bool:
    if not competition_id:
        return False
    if competition_id in FOTMOB_LEAGUES:
        return True
    if competition_id in {
        "nhl",
        "mlb",
        "australia-afl",
        "formula-1",
        "formula-2",
        "formula-3",
        "formula-e",
        "wec",
        "fih-eurohockey",
        "euroleague",
        "plusliga",
        "italy-superlega",
        "germany-click-tt",
    }:
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
        abbrev = item.get("teamAbbrev") or item.get("teamAbbreviation") or {}
        if isinstance(abbrev, dict):
            abbrev = abbrev.get("default") or abbrev.get("name")
        abbrev = str(abbrev or "").strip().upper()
        out.append(
            {
                "position": item.get("leagueSequence") or item.get("wildcardSequence"),
                "team": name,
                "team_id": abbrev or None,
                "logo": f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg" if abbrev else None,
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
            team_row = item.get("team") or {}
            team = team_row.get("name")
            if not team:
                continue
            team_id = str(team_row.get("id") or "").strip()
            league = item.get("leagueRecord") or {}
            out.append(
                {
                    "position": item.get("divisionRank") or item.get("leagueRank"),
                    "team": team,
                    "team_id": team_id or None,
                    "logo": f"https://www.mlbstatic.com/team-logos/{team_id}.svg" if team_id else None,
                    "played": item.get("gamesPlayed"),
                    "wins": league.get("wins") or item.get("wins"),
                    "losses": league.get("losses") or item.get("losses"),
                    "pct": league.get("pct") or item.get("winningPercentage"),
                    "group": group,
                }
            )
    return out


def parse_squiggle_standings(payload: Any) -> List[Dict[str, Any]]:
    """AFL ladder. Percentage and premiership points, not football goals for/against."""
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
        wins = item.get("wins")
        losses = item.get("losses")
        draws = item.get("draws")
        played = item.get("played") or item.get("games")
        if played is None and all(value is not None for value in (wins, losses)):
            try:
                played = int(wins) + int(losses) + int(draws or 0)
            except (TypeError, ValueError):
                played = None
        out.append(
            {
                "position": item.get("rank") or item.get("position"),
                "team": name,
                "team_id": str(item.get("id") or item.get("teamid") or item.get("teamId") or "").strip() or None,
                "logo": item.get("logo") or item.get("image") or None,
                "played": played,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "points": item.get("pts") or item.get("points"),
                "percentage": item.get("percentage"),
            }
        )
    return out


def parse_euroleague_standings(payload: Any) -> List[Dict[str, Any]]:
    """Euroleague api-live standings XML. No invented draws."""
    import xml.etree.ElementTree as ET

    text = payload if isinstance(payload, str) else ""
    if isinstance(payload, (bytes, bytearray)):
        text = payload.decode("utf-8", "replace")
    if not text or "<standings" not in text[:400].lower() and "<team" not in text[:800].lower():
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    groups = list(root.findall("group")) or [root]
    for group in groups:
        label = group.get("name") or group.get("round") or "Regular Season"
        bucket = grouped.setdefault(label, [])
        for team in group.findall("team"):
            name = (team.findtext("name") or "").strip()
            if not name:
                continue
            try:
                played = int(team.findtext("totalgames") or 0)
                wins = int(team.findtext("wins") or 0)
                losses = int(team.findtext("losses") or 0)
            except ValueError:
                continue
            win_pct = round(wins / played, 3) if played else None
            bucket.append(
                {
                    "position": team.findtext("ranking"),
                    "team": name,
                    "played": played,
                    "wins": wins,
                    "losses": losses,
                    "win_pct": win_pct,
                    "points_for": team.findtext("ptsfavour"),
                    "points_against": team.findtext("ptsagainst"),
                    "group": label,
                }
            )
    if not grouped:
        return []
    if "Regular Season" in grouped and grouped["Regular Season"]:
        return grouped["Regular Season"]
    return max(grouped.values(), key=len)


def parse_dataproject_standings(html: str) -> List[Dict[str, Any]]:
    """PlusLiga / DataProject rank table. Latest round rows only."""
    import re

    text = html or ""
    if "rs-standings-table" not in text and "data-teamname" not in text:
        return []
    row_re = re.compile(
        r'<tr[^>]*data-termin="([^"]+)"[^>]*data-teamname="([^"]+)"[^>]*>(.*?)</tr>',
        re.I | re.S,
    )
    parsed = []
    for termin, team, body in row_re.findall(text):
        cells = [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", body, re.I | re.S)]
        cells = [re.sub(r"\s+", " ", cell).strip() for cell in cells]
        if len(cells) < 8 or not team.strip():
            continue
        parts = termin.split("-")
        try:
            round_no = int(parts[-1])
        except ValueError:
            round_no = 0
        parsed.append((round_no, team.strip(), cells))
    if not parsed:
        return []
    latest = max(item[0] for item in parsed)
    out = []
    for round_no, team, cells in parsed:
        if round_no != latest:
            continue
        out.append(
            {
                "position": cells[0],
                "team": team,
                "points": cells[2],
                "played": cells[3],
                "wins": cells[4],
                "losses": cells[5],
                "sets_for": cells[6],
                "sets_against": cells[7],
            }
        )
    return out


def parse_clicktt_standings(payload: Any) -> List[Dict[str, Any]]:
    """Bundesliga table from the public click-TT Remix tabelle payload."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    table = data.get("league_table") or []
    if not isinstance(table, list):
        return []
    out = []
    for item in table:
        if not isinstance(item, dict) or item.get("is_excluded"):
            continue
        team = item.get("team_name") or item.get("team")
        if not team:
            continue
        row = {
            "position": item.get("table_rank"),
            "team": team,
            "played": item.get("meetings_count"),
            "wins": item.get("meetings_won"),
            "losses": item.get("meetings_lost"),
            "points": item.get("points_won"),
            "sets_for": item.get("sets_won"),
            "sets_against": item.get("sets_lost"),
        }
        if item.get("meetings_tie") not in (None, 0, "0"):
            row["draws"] = item.get("meetings_tie")
        out.append(row)
    return out


def parse_legavolley_standings(html: str) -> List[Dict[str, Any]]:
    """legavolley.it classifica table. Same public host as the SuperLega calendar."""
    import re

    text = html or ""
    start = text.find("GareGiornata")
    if start < 0:
        return []
    body = text[start:]
    out = []
    for chunk in re.split(r'class="pos">', body)[1:]:
        position = chunk.split("<", 1)[0].strip()
        team_match = re.search(r"</span>(?:&nbsp;|\s)+([^<]+)", chunk)
        if not team_match or not position.isdigit():
            continue
        values = re.findall(r">\s*([0-9]+(?:[.,][0-9]+)?|\.)\s*<", chunk[:1800])
        if len(values) < 4:
            continue
        points = None if values[0] in {".", "-"} else values[0]
        out.append(
            {
                "position": position,
                "team": re.sub(r"\s+", " ", team_match.group(1)).strip(),
                "points": points,
                "played": values[1],
                "wins": values[2],
                "losses": values[3],
                "sets_for": values[10] if len(values) > 10 else None,
                "sets_against": values[11] if len(values) > 11 else None,
            }
        )
    return [row for row in out if row.get("team")]


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
    payload = load_json(row.rows_json, [])
    rows = unwrap_standings(payload)
    if not rows:
        return False
    if row.competition_id == "uefa-nations-league":
        if not isinstance(payload, dict) or payload.get("schema_revision") != 2:
            return False
        if set(payload.get("league_ids") or []) != {"9806", "9807", "9808", "9809"}:
            return False
    sport = payload.get("sport") if isinstance(payload, dict) else ""
    if str(getattr(row, "competition_id", "") or "") == "australia-afl" or sport == "australian-rules":
        if rows[0].get("percentage") is None or rows[0].get("goals_for") is not None:
            return False
    if str(getattr(row, "competition_id", "") or "") == "italy-superlega" and _played_total(rows) <= 0:
        return False
    return age < timedelta(seconds=TTL_SECONDS)


def _openliga_shortcut(competition_id: str) -> Optional[str]:
    for spec in OPENLIGADB_LEAGUES:
        if spec.get("competition_id") == competition_id:
            return str(spec.get("shortcut") or "")
    return None


def _snapshot_payload(row: SportsStandingSnapshot) -> Any:
    return load_json(row.rows_json, {})


def _snapshot_identity(row: SportsStandingSnapshot) -> tuple:
    payload = _snapshot_payload(row)
    if not isinstance(payload, dict):
        payload = {}
    return (str(row.season or ""), str(payload.get("stage") or ""), str(payload.get("group") or ""))


def _best_snapshot(rows: List[SportsStandingSnapshot]) -> Optional[SportsStandingSnapshot]:
    valid = [row for row in rows if unwrap_standings(_snapshot_payload(row))]
    if not valid:
        return None
    return max(valid, key=lambda row: (str(row.season or ""), row.captured_at or datetime.min))


def _store_standings(db: Session, competition_key: str, fetched: Dict[str, Any]) -> None:
    """Update only the matching competition/season/stage/group row. Never delete another season."""
    identity = (str(fetched.get("season") or ""), str(fetched.get("stage") or ""), str(fetched.get("group") or ""))
    existing = (
        db.query(SportsStandingSnapshot)
        .filter_by(competition_id=competition_key)
        .order_by(SportsStandingSnapshot.captured_at.desc())
        .all()
    )
    target = next((row for row in existing if _snapshot_identity(row) == identity), None)
    if target is None:
        target = SportsStandingSnapshot(competition_id=competition_key, rows_json=dump_json(fetched))
        db.add(target)
    target.sport_id = fetched.get("sport")
    target.season = fetched.get("season")
    target.source_id = fetched.get("source")
    target.rows_json = dump_json(fetched)
    target.captured_at = datetime.utcnow()
    from collector.cache import note_list_invalidation
    note_list_invalidation(db, sport=fetched.get("sport"), competition=competition_key)


def _read_body(getter, url: str, headers: Optional[Dict[str, str]] = None):
    from collector.http import fetch_text

    reader = fetch_text if getter is fetch_url else getter
    try:
        if headers:
            return reader(url, headers=headers)
    except TypeError:
        pass
    return reader(url)


def _body_text(result) -> str:
    if result is None:
        return ""
    payload = getattr(result, "payload", None)
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode("utf-8", "replace")
    return ""


def _euroleague_standings(getter) -> Dict[str, Any]:
    now = datetime.utcnow()
    primary = f"E{now.year}" if now.month >= 9 else f"E{now.year - 1}"
    seasons = [primary, f"E{int(primary[1:]) - 1}"]
    fallback = None
    for season in seasons:
        result = _read_body(getter, EUROLEAGUE_STANDINGS.format(season=season))
        rows = parse_euroleague_standings(_body_text(result))
        if not rows:
            continue
        payload = wrap_standings(
            rows,
            competition="euroleague",
            season=season,
            stage="Regular Season",
            sport="basketball",
            source="euroleague-live",
        )
        if _played_total(rows) > 0:
            return payload
        fallback = fallback or payload
    return fallback or {}


_PLUSLIGA_MARKERS = ("Zawiercie", "Jastrz", "ZAKSA", "Resovia", "Lublin", "Skra", "Trefl")
_SUPERLEGA_MARKERS = ("Perugia", "Civitanova", "Trentino", "Monza", "Milano", "Modena", "Verona")


def _marker_hits(rows: List[Dict[str, Any]], markers) -> int:
    blob = " ".join(str(row.get("team") or "") for row in rows)
    return sum(1 for token in markers if token in blob)


def _played_total(rows: List[Dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        try:
            total += int(row.get("played") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _volleyball_standings(competition_id: str, getter) -> Dict[str, Any]:
    import re

    if competition_id == "plusliga":
        result = _read_body(getter, PLUSLIGA_STANDINGS)
        text = _body_text(result)
        rows = parse_dataproject_standings(text)
        if _marker_hits(rows, _PLUSLIGA_MARKERS) < 2:
            return {}
        season_match = re.search(r"Sezon\s+(\d{4}/\d{4})", text)
        season = season_match.group(1) if season_match else "2025/2026"
        return wrap_standings(
            rows,
            competition=competition_id,
            season=season,
            stage="regular-season",
            sport="volleyball",
            source="dataproject-web",
        )
    home = _read_body(getter, SUPERLEGA_HOME)
    home_html = _body_text(home)
    ids = []
    for campionato in re.findall(r"IdCampionato=(\d+)", home_html, re.I):
        if campionato not in ids:
            ids.append(campionato)
    best = None
    best_key = None
    best_id = None
    for campionato in ids[:12]:
        page = _read_body(getter, f"https://www.legavolley.it/classifica/?IdCampionato={campionato}")
        rows = parse_legavolley_standings(_body_text(page))
        hits = _marker_hits(rows, _SUPERLEGA_MARKERS)
        played = _played_total(rows)
        if hits < 3 or not rows or played <= 0:
            continue
        key = (played, hits, len(rows))
        if best_key is None or key > best_key:
            best = rows
            best_key = key
            best_id = campionato
    if not best:
        return {}
    return wrap_standings(
        best,
        competition=competition_id,
        season=str(best_id),
        stage="classification",
        sport="volleyball",
        source="dataproject-web",
    )


def fetch_competition_standings(competition_id: str, getter=None) -> Dict[str, Any]:
    getter = getter or fetch_url
    spec = FOTMOB_LEAGUES.get(competition_id) or {}
    from collector.adapters_fotmob import _league_ids
    league_ids = _league_ids(spec)
    if league_ids:
        combined = []
        seasons = set()
        complete = True
        for league_id in league_ids:
            result = getter(FOTMOB_LEAGUE.format(league_id=league_id))
            payload = result.payload if result.ok and isinstance(result.payload, dict) else {}
            rows = parse_fotmob_table(payload)
            if not rows:
                complete = False
            combined.extend(rows)
            season = (payload.get("details") or {}).get("selectedSeason")
            if season: seasons.add(str(season))
        if combined and complete and len(seasons) <= 1:
            result = wrap_standings(combined, competition=competition_id, sport="football",
                                    season=next(iter(seasons), None), source="fotmob")
            result["schema_revision"] = 2
            result["league_ids"] = league_ids
            return result
        if len(league_ids) > 1:
            return {}  # Never replace a complete grouped table with one division.
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
        from collector.adapters_squiggle import (
            SQUIGGLE_HEADERS,
            TEAMS_URL,
            _team_assets,
            parse_squiggle_payload,
        )

        team_assets = {}
        try:
            teams_result = getter(TEAMS_URL, headers=SQUIGGLE_HEADERS)
        except TypeError:
            teams_result = getter(TEAMS_URL)
        if teams_result is not None and getattr(teams_result, "ok", False):
            team_assets = _team_assets(teams_result.payload)

        year = datetime.utcnow().year
        urls = []
        for season in (year, year - 1):
            urls.append(SQUIGGLE_STANDINGS.format(year=season))
            urls.append(f"https://api.squiggle.com.au/?q=standings;year={season}")
        for url in urls:
            try:
                result = getter(url, headers=SQUIGGLE_HEADERS)
            except TypeError:
                result = getter(url)
            payload = result.payload if result is not None else None
            rows_raw, _meta = parse_squiggle_payload(payload, "standings")
            rows = parse_squiggle_standings({"standings": rows_raw} if rows_raw else payload)
            if rows and team_assets:
                for row in rows:
                    team_id = str(row.get("team_id") or "").strip()
                    asset = team_assets.get(team_id) if team_id else None
                    if not asset:
                        folded_name = str(row.get("team") or "").strip().casefold()
                        asset = next(
                            (
                                value
                                for value in team_assets.values()
                                if str(value.get("name") or "").strip().casefold() == folded_name
                            ),
                            None,
                        )
                    if asset and asset.get("logo") and not row.get("logo"):
                        row["logo"] = asset["logo"]
            if rows:
                season = str(year)
                if "year=" in url:
                    season = url.rsplit("year=", 1)[-1].split("&", 1)[0]
                return wrap_standings(
                    rows,
                    competition=competition_id,
                    season=season,
                    sport="australian-rules",
                    source="squiggle-afl",
                )
    if competition_id == "euroleague":
        fetched = _euroleague_standings(getter)
        if fetched:
            return fetched
    if competition_id in {"plusliga", "italy-superlega"}:
        fetched = _volleyball_standings(competition_id, getter)
        if fetched:
            return fetched
    if competition_id == "germany-click-tt":
        from collector.adapters_final18 import CLICK_TT_TABELLE

        result = getter(CLICK_TT_TABELLE)
        payload = result.payload if getattr(result, "ok", False) else None
        rows = parse_clicktt_standings(payload)
        if rows and _played_total(rows) > 0:
            return wrap_standings(
                rows,
                competition=competition_id,
                season="2025/2026",
                stage="gesamt",
                sport="table-tennis",
                source="click-tt-remix",
            )
    if competition_id in {"formula-2", "formula-3", "formula-e", "wec", "fih-eurohockey"}:
        from collector.rich_closure import fetch_closure_standings

        rows = fetch_closure_standings(competition_id)
        if rows:
            return wrap_standings(rows, competition=competition_id, sport="motorsport" if competition_id != "fih-eurohockey" else "field-hockey", source="official-html")
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


def _load_standings(db: Session, competition_key: Optional[str], getter=None) -> List[Dict[str, Any]]:
    if not competition_key:
        return []
    stored = (
        db.query(SportsStandingSnapshot)
        .filter_by(competition_id=competition_key)
        .order_by(SportsStandingSnapshot.captured_at.desc())
        .all()
    )
    cached = _best_snapshot(stored)
    live = db.query(SportsEvent.event_id).filter(
        SportsEvent.competition_id == competition_key,
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.isnot(False),
        SportsEvent.status.in_(("live", "halftime", "break")),
        SportsEvent.start_time >= datetime.utcnow()-timedelta(hours=5),
    ).first() is not None
    if _fresh(cached) and (not live or (datetime.utcnow()-cached.captured_at.replace(tzinfo=None)).total_seconds() < 60):
        return unwrap_standings(_snapshot_payload(cached))
    # Backoff only empty tables, shorter during live play. A valid cached table
    # remains visible during upstream failure. No invented zero-row tables.
    if getter is None:
        with _TABLE_LOCK:
            key = (competition_key, live)
            if _NEGATIVE_TABLES.get(key, 0) > time.monotonic():
                return unwrap_standings(_snapshot_payload(cached)) if cached else []
    fetched: Dict[str, Any] = {}
    has_events = (
        db.query(SportsEvent.event_id)
        .filter_by(competition_id=competition_key)
        .limit(1)
        .first()
    )
    if has_events:
        fetched = fetch_competition_standings(competition_key, getter=getter) or {}
        if not fetched:
            fetched = _fetch_fotmob_dynamic_standings(db, competition_key, getter=getter) or {}
        if not fetched:
            fetched = _fetch_sofa_dynamic_standings(db, competition_key, getter=getter) or {}
    rows = unwrap_standings(fetched) if fetched else []
    if rows:
        with _TABLE_LOCK:
            _NEGATIVE_TABLES.pop((competition_key, True), None)
            _NEGATIVE_TABLES.pop((competition_key, False), None)
        try:
            _store_standings(db, competition_key, fetched)
            db.commit()
        except Exception:
            db.rollback()
        return rows
    if getter is None:
        with _TABLE_LOCK:
            _NEGATIVE_TABLES[(competition_key, live)] = time.monotonic() + (60 if live else 600)
            while len(_NEGATIVE_TABLES) > 512:
                _NEGATIVE_TABLES.popitem(last=False)
    if cached:
        return unwrap_standings(_snapshot_payload(cached))
    return []


def load_standings(db: Session, competition_key: Optional[str], getter=None) -> List[Dict[str, Any]]:
    """Coalesce refreshes; a concurrent reader retains the last good table."""
    if not competition_key:
        return []
    if getter is not None:
        return _load_standings(db, competition_key, getter=getter)
    with _TABLE_LOCK:
        if competition_key in _TABLE_INFLIGHT:
            cached = _best_snapshot(db.query(SportsStandingSnapshot).filter_by(competition_id=competition_key).all())
            return unwrap_standings(_snapshot_payload(cached)) if cached else []
        _TABLE_INFLIGHT.add(competition_key)
    try:
        return _load_standings(db, competition_key)
    finally:
        with _TABLE_LOCK:
            _TABLE_INFLIGHT.discard(competition_key)


def standings_view(db: Session, competition_key: str, season: Optional[str] = None) -> Dict[str, Any]:
    """Competition-only view. An explicit old season never gets today's table."""
    competition = db.get(SportsCompetition, competition_key)
    snapshots = db.query(SportsStandingSnapshot).filter_by(competition_id=competition_key).all()
    newest = _best_snapshot(snapshots)
    if season is None or (newest and str(newest.season or '') == season):
        load_standings(db, competition_key)
        snapshots = db.query(SportsStandingSnapshot).filter_by(competition_id=competition_key).all()
    selected = _best_snapshot([s for s in snapshots if season is None or str(s.season or '') == season])
    rows = unwrap_standings(_snapshot_payload(selected)) if selected else []
    from collector.competition_presentation import attach_competition_metadata
    sample = db.query(SportsEvent).filter_by(competition_id=competition_key, canonical_event_id=None, display_eligible=True).order_by(SportsEvent.start_time.desc()).first()
    artwork = load_json(sample.extra_json, {}) if sample else {}
    meta = attach_competition_metadata({'competition_key': competition_key, 'sport': competition.sport_id if competition else 'football',
                                       'source_competition_name': competition.name if competition else '',
                                       'country_id': competition.country_id if competition else None})
    logo = (artwork or {}).get('competition_logo')
    if not logo and selected:
        source_meta = _snapshot_payload(selected)
        parent_id = source_meta.get('source_parent_id') if isinstance(source_meta, dict) else None
        if parent_id and str(parent_id).isdigit():
            logo = f'https://images.fotmob.com/image_resources/logo/leaguelogo/{parent_id}.png'

    return {
        'rows': rows,
        'competition': {'id': competition_key, 'name': (competition.name if competition else '') or meta.get('competition_name') or competition_key,
                        'sport': competition.sport_id if competition else meta.get('sport'),
                        'logo': logo, 'country_id': meta.get('country_id')},
        'season': season if season is not None else (selected.season if selected else None),
        'seasons': sorted({str(s.season) for s in snapshots if s.season and unwrap_standings(_snapshot_payload(s))}, reverse=True),
        'updated_at': selected.captured_at.isoformat()+'Z' if selected and selected.captured_at else None,
        'stale': not _fresh(selected),
        'available': bool(rows),
    }
