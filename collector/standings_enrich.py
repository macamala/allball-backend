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
SQUIGGLE_STANDINGS = "https://api.squiggle.com.au/?q=standings&year={year}"
EUROLEAGUE_STANDINGS = "https://api-live.euroleague.net/v1/standings?seasonCode={season}"
PLUSLIGA_STANDINGS = "https://www.plusliga.pl/table/tour/52/nocookies/1.html"
SUPERLEGA_HOME = "https://www.legavolley.it/superlega/"
JOLPICA_DRIVERS = "https://api.jolpi.ca/ergast/f1/current/driverStandings.json"

def standings_supported(competition_id: Optional[str]) -> bool:
    if not competition_id:
        return False
    if competition_id in FOTMOB_LEAGUES:
        return True
    if competition_id in {"nhl", "mlb", "australia-afl", "formula-1", "euroleague", "plusliga", "italy-superlega", "germany-click-tt"}:
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
            urls.append(f"https://api.squiggle.com.au/?q=standings;year={season}")
        for url in urls:
            try:
                result = getter(url, headers=SQUIGGLE_HEADERS)
            except TypeError:
                result = getter(url)
            payload = result.payload if result is not None else None
            rows_raw, _meta = parse_squiggle_payload(payload, "standings")
            rows = parse_squiggle_standings({"standings": rows_raw} if rows_raw else payload)
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
    stored = (
        db.query(SportsStandingSnapshot)
        .filter_by(competition_id=competition_key)
        .order_by(SportsStandingSnapshot.captured_at.desc())
        .all()
    )
    cached = _best_snapshot(stored)
    if _fresh(cached):
        return unwrap_standings(_snapshot_payload(cached))
    fetched: Dict[str, Any] = {}
    has_events = (
        db.query(SportsEvent.event_id)
        .filter_by(competition_id=competition_key)
        .limit(1)
        .first()
    )
    if has_events:
        fetched = fetch_competition_standings(competition_key, getter=getter) or {}
    rows = unwrap_standings(fetched) if fetched else []
    if rows:
        try:
            _store_standings(db, competition_key, fetched)
            db.commit()
        except Exception:
            db.rollback()
        return rows
    if cached:
        return unwrap_standings(_snapshot_payload(cached))
    return []
