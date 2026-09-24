"""Detail-only enrichment for the researched closure families.

Never imported by the score list. Finished results are cached by the caller.
Public throttling stays on collector.http.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from collector.http import fetch_text, fetch_url

CARGO = "https://lol.fandom.com/api.php?action=cargoquery&format=json&limit={limit}&tables={table}&fields={fields}&where={where}"
F2_ROOT = "https://www.fia.com/events/formula-2-championship/season-{year}"
F3_ROOT = "https://www.fia.com/events/fia-formula-3-championship/season-{year}"
F2_INDEX = F2_ROOT + "/formula-2"
F3_INDEX = F3_ROOT + "/fia-formula-3"
F2_STANDINGS = F2_ROOT + "/standings"
F3_STANDINGS = F3_ROOT + "/2026-standings"
FE_INDEX = "https://www.fiaformulae.com/en/results-and-standings"
FE_RACE = "https://www.fiaformulae.com/en/results-and-standings?season={season}&round={round}&session=race"
FE_DRIVERS = "https://www.fiaformulae.com/en/results-and-standings?tab=drivers&season={season}"
WEC_SEASON = "https://www.fiawec.com/en/season/{year}"
WEC_RACE = "https://www.fiawec.com{path}"
WEC_SUMMARY = "https://www.fiawec.com/en/race/summary/{summary_id}"
IBU = "https://www.biathlonresults.com/modules/sportapi/api/{path}"
WA_COMPS = "https://api.worldaquatics.com/fina/competitions?pageSize=40&page={page}"
WA_EVENTS = "https://api.worldaquatics.com/fina/competitions/{comp_id}/events"
WA_DISCIPLINE = "https://api.worldaquatics.com/fina/events/{discipline_id}"
ALTIUS_HOMES = (
    "https://fih.altiusrt.com/",
    "https://eurohockey.altiusrt.com/",
)

GAME_FIELDS = (
    "OverviewPage,Team1,Team2,WinTeam,LossTeam,Team1Score,Team2Score,Winner,"
    "Gamelength,Gamelength_Number,GameId,MatchId,Team1Side,Team2Side,"
    "Team1Picks,Team2Picks,Team1Bans,Team2Bans"
)
GAME_FIELDS_CORE = (
    "OverviewPage,Team1,Team2,WinTeam,LossTeam,Team1Score,Team2Score,Winner,"
    "Gamelength,Gamelength_Number,GameId,MatchId"
)
PLAYER_FIELDS = "Link,Champion,Kills,Deaths,Assists,Gold,CS,VisionScore,DamageToChampions,PlayerWin,GameId,MatchId,Team,Side,Role"

_MEMO: Dict[str, Any] = {}
_HEADER = {
    "Pos": "position",
    "Nr": "car",
    "No": "car",
    "No.": "car",
    "Driver": "name",
    "Drivers": "name",
    "Team": "team",
    "Competitors": "name",
    "Team / Drivers": "name",
    "Points": "points",
    "Pts": "points",
    "Time": "time",
    "Gap previous": "gap",
    "Gap": "gap",
    "Gap first": "interval",
    "Interval": "interval",
    "Laps": "laps",
    "Best lap time": "fastest_lap",
    "Best lap": "fastest_lap",
    "Best lap lap": "status",
    "Best lap number": "status",
    "Speed trap": "speed_trap",
    "Grid": "grid",
    "Kph": "speed",
    "Class": "category",
    "Category": "category",
}


def _memo(key: str, ttl: int, loader):
    hit = _MEMO.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = loader()
    _MEMO[key] = (now, value)
    return value


def _text(url: str) -> str:
    result = fetch_text(url, timeout=25)
    if result.ok and isinstance(result.payload, str):
        return result.payload
    return ""


def _json(url: str) -> Any:
    result = fetch_url(url, timeout=25)
    if result.ok and isinstance(result.payload, (dict, list)):
        return result.payload
    return None


def _norm(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("ü", "u").replace("ö", "o").replace("ä", "a").replace("é", "e")
    return re.sub(r"[^a-z0-9]+", "", text)


def _names_match(left: Any, right: Any) -> bool:
    a, b = _norm(left), _norm(right)
    if len(a) < 3 or len(b) < 3:
        return bool(a and a == b)
    return a in b or b in a


def _plain(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def _rows(html: str) -> List[List[str]]:
    out = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_plain(td) for td in re.findall(r"<t[dh][\s\S]*?</t[dh]>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        if cells:
            out.append(cells)
    return out


def _driver_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"\b[A-Z]{3}\b", "", text).strip()
    text = re.sub(r"\s{2,}", " ", text)
    return text


def _intish(value: Any) -> Any:
    text = str(value or "").strip()
    match = re.match(r"-?\d+", text)
    return int(match.group(0)) if match else value


def _duration_seconds(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = re.match(r"(\d+):(\d{2})(?::(\d{2}))?", text)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    hours = int(match.group(3) or 0)
    if match.group(3):
        return hours * 3600 + minutes * 60 + seconds
    return minutes * 60 + seconds


def _cargo_rows(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("error"):
        return []
    rows = payload.get("cargoquery") or []
    out = []
    for item in rows:
        title = item.get("title") if isinstance(item, dict) else None
        if isinstance(title, dict):
            out.append(title)
    return out


def _cargo(table: str, fields: str, where: str, limit: int = 50) -> List[Dict[str, Any]]:
    url = CARGO.format(limit=limit, table=table, fields=quote(fields, safe=","), where=quote(where, safe=""))
    payload = _memo(url, 6 * 3600, lambda: _json(url))
    if isinstance(payload, dict) and (payload.get("error") or {}).get("code") == "ratelimited":
        _MEMO.pop(url, None)
        _MEMO[url] = (time.time() - (6 * 3600 - 900), payload)
        return []
    return _cargo_rows(payload)


def parse_leaguepedia_games(payload: Any) -> List[Dict[str, Any]]:
    games = []
    for index, row in enumerate(_cargo_rows(payload) or (payload if isinstance(payload, list) else [])):
        if not isinstance(row, dict):
            continue
        blue_name = row.get("Team1")
        red_name = row.get("Team2")
        side1 = str(row.get("Team1Side") or "").lower()
        side2 = str(row.get("Team2Side") or "").lower()
        if side1 == "red" or side2 == "blue":
            blue_name, red_name = red_name, blue_name
        duration = _duration_seconds(row.get("Gamelength_Number") or row.get("Gamelength"))
        game = {
            "game_number": index + 1,
            "name": f"Game {index + 1}",
            "winner": row.get("WinTeam") or row.get("Winner"),
            "duration": duration,
            "blue": {"name": blue_name, "side": "blue"},
            "red": {"name": red_name, "side": "red"},
        }
        picks = [part for part in (row.get("Team1Picks"), row.get("Team2Picks")) if part]
        bans = [part for part in (row.get("Team1Bans"), row.get("Team2Bans")) if part]
        if picks:
            game["picks"] = " · ".join(str(part) for part in picks)
        if bans:
            game["bans"] = " · ".join(str(part) for part in bans)
        games.append({key: value for key, value in game.items() if value not in (None, "", {})})
    return games


def parse_leaguepedia_players(payload: Any) -> List[Dict[str, Any]]:
    players = []
    for row in _cargo_rows(payload) or (payload if isinstance(payload, list) else []):
        if not isinstance(row, dict):
            continue
        name = row.get("Link") or row.get("Team")
        if not name or not row.get("Champion"):
            continue
        item = {
            "name": str(name).split("/")[-1].replace("_", " "),
            "team": row.get("Team"),
            "hero": row.get("Champion"),
            "kills": _intish(row.get("Kills")) if row.get("Kills") not in (None, "") else None,
            "deaths": _intish(row.get("Deaths")) if row.get("Deaths") not in (None, "") else None,
            "assists": _intish(row.get("Assists")) if row.get("Assists") not in (None, "") else None,
            "cs": row.get("CS"),
            "gold": row.get("Gold"),
            "damage": row.get("DamageToChampions"),
            "vision": row.get("VisionScore"),
            "side": str(row.get("Side") or "").lower() or None,
        }
        players.append({key: value for key, value in item.items() if value not in (None, "")})
    return players


def fetch_lol_finished(home: str, away: str, on_date: str) -> Dict[str, Any]:
    """Finished series enrichment only. One Cargo query, then one player query."""
    if not home or not away:
        return {}
    where = (
        f'(Team1 HOLDS "{home}" AND Team2 HOLDS "{away}") OR '
        f'(Team1 HOLDS "{away}" AND Team2 HOLDS "{home}")'
    )
    games_raw = _cargo("ScoreboardGames", GAME_FIELDS, where, limit=8)
    if not games_raw:
        games_raw = _cargo("ScoreboardGames", GAME_FIELDS_CORE, where, limit=8)
    if on_date:
        dated = [row for row in games_raw if on_date in str(row.get("DateTime_UTC") or row.get("OverviewPage") or "")]
        if dated:
            games_raw = dated
    games = parse_leaguepedia_games({"cargoquery": [{"title": row} for row in games_raw]})
    if not games:
        return {}
    ids = [str(row.get("GameId")) for row in games_raw if row.get("GameId")]
    players: List[Dict[str, Any]] = []
    if ids:
        quoted = " OR ".join(f'GameId="{gid}"' for gid in ids[:8])
        player_raw = _cargo("ScoreboardPlayers", PLAYER_FIELDS, quoted, limit=80)
        players = parse_leaguepedia_players({"cargoquery": [{"title": row} for row in player_raw]})
    detail = {"best_of": len(games), "games": games}
    out: Dict[str, Any] = {"sport_detail": detail}
    if players:
        out["player_statistics"] = players
    return out


def _table_cells(html: str) -> List[List[str]]:
    out = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_plain(td) for td in re.findall(r"<t[dh][\s\S]*?</t[dh]>", tr, re.I)]
        if cells:
            out.append(cells)
    return out


def parse_fia_classification(html: str) -> Dict[str, Any]:
    rows = _table_cells(html)
    header_index = next((i for i, cells in enumerate(rows) if "Driver" in cells and "Pos" in cells), -1)
    if header_index < 0:
        return {}
    header = rows[header_index]
    mapped = [_HEADER.get(cell, "") for cell in header]
    classification = []
    for cells in rows[header_index + 1 :]:
        if not cells or not re.match(r"\d", cells[0]):
            continue
        item: Dict[str, Any] = {}
        for index, cell in enumerate(cells):
            key = mapped[index] if index < len(mapped) else ""
            if not key or not cell:
                continue
            if key == "name":
                cell = _driver_name(cell)
            if key == "status" and cell.isdigit():
                item["status"] = f"lap {cell}"
                continue
            if key == "fastest_lap" and not re.search(r"\d:\d{2}\.\d", cell):
                continue
            item[key] = cell
        if item.get("name"):
            classification.append(item)
        if len(classification) >= 30:
            break
    if not classification:
        return {}
    return {"classification": classification}


def parse_fia_standings(html: str) -> List[Dict[str, Any]]:
    rows = _rows(html)
    out = []
    group = "Drivers"
    for cells in rows:
        blob = " ".join(cells).lower()
        if "team" in blob and "driver" not in blob and len(cells) <= 4:
            group = "Teams"
        if not cells or not re.match(r"\d+$", cells[0]):
            continue
        name = ""
        points = None
        for cell in cells[1:]:
            if re.search(r"[A-Za-z]{3,}", cell) and not name:
                name = _driver_name(cell)
            if re.search(r"\d+\s*pts", cell, re.I):
                points = re.search(r"\d+", cell).group(0)
        if not name:
            continue
        if points is None:
            tail = cells[-1]
            if re.fullmatch(r"\d+", tail):
                points = tail
        if points is None:
            continue
        out.append({"position": int(cells[0]), "team": name, "points": int(points), "group": group})
    deduped = []
    seen = set()
    for row in out:
        key = (row["group"], _norm(row["team"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:40]


def _session_kind(text: str) -> str:
    folded = text.lower()
    if "sprint" in folded:
        return "sprint"
    if "feature" in folded:
        return "feature"
    if "qualifying" in folded or "quali" in folded:
        return "qualifying"
    if "practice" in folded:
        return "practice"
    return ""


def _fia_links(series: str, year: int) -> List[str]:
    index = (F2_INDEX if series == "f2" else F3_INDEX).format(year=year)
    html = _memo(index, 3600, lambda: _text(index))
    return sorted(set(re.findall(r'href="([^"]+classification[^"]*)"', html or "")))


def match_fia_session(series: str, text: str, on_date: str, links: List[str]) -> str:
    """The season index often links only the feature classification.

    Sprint, qualifying, and practice pages use the same event slug.
    """
    year = int(on_date[:4]) if on_date and on_date[:4].isdigit() else datetime.utcnow().year
    kind = _session_kind(text)
    if not kind:
        return ""
    folded = text.lower()
    for href in links:
        parts = [part for part in href.strip("/").split("/") if part]
        slug = parts[-2] if len(parts) >= 2 else ""
        words = slug.replace("-", " ")
        if words and words in folded:
            return f"{series}:{year}:{slug}:{kind}"
    return ""


def resolve_fia_session(series: str, text: str, on_date: str) -> str:
    year = int(on_date[:4]) if on_date and on_date[:4].isdigit() else datetime.utcnow().year
    return match_fia_session(series, text, on_date, _fia_links(series, year))


def fetch_fia_classification(source_id: str) -> Dict[str, Any]:
    parts = str(source_id or "").split(":")
    if len(parts) != 4:
        return {}
    series, year, slug, kind = parts
    root = F2_ROOT if series == "f2" else F3_ROOT
    leaf = {
        "sprint": "sprint-race-classification",
        "feature": "feature-race-classification",
        "qualifying": "session-classifications",
        "practice": "session-classifications",
    }.get(kind)
    if not leaf:
        return {}
    url = root.format(year=year) + f"/{slug}/{leaf}"
    return parse_fia_classification(_memo(url, 6 * 3600, lambda: _text(url)))


def fetch_fia_standings(series: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
    year = year or datetime.utcnow().year
    url = (F2_STANDINGS if series == "f2" else F3_STANDINGS).format(year=year)
    html = _memo(url, 1800, lambda: _text(url))
    return parse_fia_standings(html)


def parse_formula_e_race(html: str) -> Dict[str, Any]:
    classification = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        if "results-row-result" not in tr and "resultsRow" not in tr:
            continue
        name_match = re.search(r'href="/en/drivers/[^"]+">([^<]+)', tr)
        cells = [_plain(td) for td in re.findall(r"<t[dh][\s\S]*?</t[dh]>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        if not name_match or len(cells) < 4:
            continue
        position = _intish(cells[0])
        team = cells[2] if len(cells) > 2 else ""
        grid = cells[3] if len(cells) > 3 and re.match(r"\d", cells[3]) else ""
        clock = cells[4] if len(cells) > 4 else ""
        points = cells[5] if len(cells) > 5 and re.match(r"\d", cells[5]) else ""
        item = {
            "position": position,
            "name": name_match.group(1).strip(),
            "team": team,
            "grid": grid or None,
            "points": points or None,
        }
        if str(clock).startswith("+"):
            item["gap"] = clock
        elif ":" in str(clock):
            item["time"] = clock
        elif clock:
            item["status"] = clock
        classification.append({key: value for key, value in item.items() if value not in (None, "")})
    if not classification:
        return {}
    return {"classification": classification}


def parse_formula_e_standings(html: str) -> List[Dict[str, Any]]:
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        name_match = re.search(r'href="/en/drivers/[^"]+">([^<]+)', tr)
        if not name_match:
            continue
        cells = [_plain(td) for td in re.findall(r"<t[dh][\s\S]*?</t[dh]>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        points = next((cell for cell in reversed(cells) if re.fullmatch(r"\d+", cell)), "")
        position = _intish(cells[0]) if cells and re.match(r"\d", cells[0]) else len(rows) + 1
        if not points:
            continue
        team = ""
        driver = name_match.group(1).strip()
        for cell in cells:
            if cell == driver or cell.startswith(driver) or re.match(r"\d", cell):
                continue
            if re.search(r"[A-Za-z]{3}", cell):
                team = cell
                break
        rows.append(
            {
                "position": position,
                "team": name_match.group(1).strip(),
                "points": int(points),
                "group": team or "Drivers",
            }
        )
    return rows[:30]


_FE_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def formula_e_rounds(html: str) -> List[Dict[str, str]]:
    found = []
    seen = set()
    for match in re.finditer(r"season=(\d+)(?:&amp;|&)round=([a-z0-9-]+)", html or ""):
        key = (match.group(1), match.group(2))
        if key in seen:
            continue
        seen.add(key)
        window = html[match.end() : match.end() + 800]
        date = ""
        stamp = re.search(
            r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
            window,
            re.I,
        )
        if stamp:
            month = _FE_MONTHS[stamp.group(2)[:3].lower()]
            date = f"{int(stamp.group(3)):04d}-{month:02d}-{int(stamp.group(1)):02d}"
        else:
            iso = re.search(r"(20\d{2}-\d{2}-\d{2})", window)
            if iso:
                date = iso.group(1)
        found.append({"season": key[0], "round": key[1], "date": date})
    return found


def resolve_formula_e(text: str, on_date: str, home: str, away: str) -> str:
    html = _memo(FE_INDEX, 1800, lambda: _text(FE_INDEX))
    rounds = formula_e_rounds(html)
    folded = _norm(text)
    for row in rounds:
        city = row["round"].split("-", 1)[-1].replace("-", "")
        if city and city in folded:
            return f"{row['season']}:{row['round']}"
        if on_date and row.get("date") == on_date:
            return f"{row['season']}:{row['round']}"
    if home and away and on_date:
        for row in rounds:
            if row.get("date") != on_date:
                continue
            url = FE_RACE.format(season=row["season"], round=row["round"])
            race = parse_formula_e_race(_memo(url, 6 * 3600, lambda url=url: _text(url)))
            names = " ".join(item.get("name") or "" for item in race.get("classification") or [])
            if _names_match(home, names) and _names_match(away, names):
                return f"{row['season']}:{row['round']}"
    return ""


def fetch_formula_e(source_id: str) -> Dict[str, Any]:
    season, _, rnd = str(source_id or "").partition(":")
    if not season or not rnd:
        return {}
    url = FE_RACE.format(season=season, round=rnd)
    return parse_formula_e_race(_memo(url, 6 * 3600, lambda: _text(url)))


def fetch_formula_e_standings(season: str = "12") -> List[Dict[str, Any]]:
    html = _memo(FE_DRIVERS.format(season=season), 1800, lambda: _text(FE_DRIVERS.format(season=season)))
    return parse_formula_e_standings(html)


def parse_wec_season_races(html: str) -> List[Dict[str, str]]:
    races = []
    for href in re.findall(r'href="(/en/race/[^"]+)"', html or ""):
        if "summary" in href:
            continue
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug in {row["slug"] for row in races}:
            continue
        races.append({"slug": slug, "href": href})
    return races


def parse_wec_summary_id(html: str, slug: str) -> str:
    """Use the summary linked from this race page, not the site-wide replay strip."""
    slug_key = slug.replace("-2026", "").replace("-2025", "").lower()
    for match in re.finditer(r"/en/race/summary/(\d+)", html or ""):
        window = html[max(0, match.start() - 500) : match.end() + 80].lower()
        if slug_key and slug_key in window:
            return match.group(1)
    return ""


def wec_component_props(html: str) -> Dict[str, Any]:
    match = re.search(
        r'data-live-name-value="Editorial:CMS:RaceComponent"[^>]*data-live-props-value="([^"]+)"',
        html or "",
    )
    if not match:
        return {}
    try:
        props = json.loads(unescape(match.group(1)))
    except json.JSONDecodeError:
        return {}
    return props if isinstance(props, dict) else {}


def post_wec_results_modal(props: Dict[str, Any], modal_id: str) -> str:
    """Same public form post the Results control sends to the RaceComponent."""
    if not props or not str(modal_id).isdigit():
        return ""
    payload = json.dumps({"props": props, "updated": {}, "args": {"id": int(modal_id)}}).encode()
    boundary = "----ninkowec"
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b'Content-Disposition: form-data; name="data"\r\n\r\n'
        + payload
        + b"\r\n--" + boundary.encode() + b"--\r\n"
    )
    request = urllib.request.Request(
        "https://www.fiawec.com/en/_components/Editorial:CMS:RaceComponent/openModal",
        data=body,
        headers={
            "User-Agent": "NinkoSportsCollector/2.5 (+https://ninkosports.com; sports-data collection)",
            "Accept": "application/vnd.live-component+html",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Requested-With": "XMLHttpRequest",
            "X-Live-Url": "/en/race/official-prologue-imola-2026",
            "Referer": WEC_PROLOGUE,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:
        return ""


def parse_wec_session_results(html: str) -> Dict[str, Any]:
    if not html or "results available soon" in html.lower():
        return {}
    classification = []
    for row in _rows(html):
        if not row or not re.match(r"\d", row[0]):
            continue
        item = {"position": _intish(row[0])}
        if len(row) > 1:
            item["name"] = row[1]
        if len(row) > 2:
            item["team"] = row[2]
        clocks = [cell for cell in row if re.search(r"\d+:\d{2}\.\d+", cell)]
        if clocks:
            item["time"] = clocks[0]
        if item.get("name"):
            classification.append(item)
        if len(classification) >= 60:
            break
    if not classification:
        return {}
    return {"classification": classification}


def fetch_wec_prologue(source_id: str) -> Dict[str, Any]:
    session = str(source_id or "").split(":", 1)[-1]
    if session not in {"morning", "afternoon"}:
        return {}
    page = _memo(WEC_PROLOGUE, 1800, lambda: _text(WEC_PROLOGUE))
    sessions = wec_prologue_sessions(page)
    modal_id = sessions.get(session) or ""
    parsed: Dict[str, Any] = {}
    if modal_id and modal_id != sessions.get("afternoon" if session == "morning" else "morning"):
        props = wec_component_props(page)
        html = post_wec_results_modal(props, modal_id)
        if modal_id in html:
            parsed = parse_wec_session_results(html) or {}
    from collector.source_family_closeout import parse_wec_fastest_article

    articles = {
        "morning": ("13197", "https://www.fiawec.com/en/news/fastest-times-am-session/13197"),
        "afternoon": ("13198", "https://www.fiawec.com/en/news/fuoco-to-the-fore-as-ferrari-finishes-on-top/13198"),
    }
    article_id, article_url = articles[session]
    article = _memo(article_url, 6 * 3600, lambda: _text(article_url))
    article_parsed = parse_wec_fastest_article(article, session=session, article_id=article_id)
    if article_parsed:
        article_parsed["article_url"] = article_url
        article_parsed["article_id"] = article_id
        if not parsed or len(parsed.get("classification") or []) < len(article_parsed.get("classification") or []):
            parsed = article_parsed
    if parsed:
        parsed["sport_detail"] = {
            "session": session,
            "session_id": modal_id,
            "coverage": parsed.get("coverage") or "official_top_10_summary",
        }
    return parsed or {}


def resolve_wec(text: str, on_date: str) -> str:
    folded = _norm(text)
    if "prologue" in folded and "imola" in folded:
        if "afternoon" in folded:
            return "prologue:afternoon"
        if "morning" in folded:
            return "prologue:morning"
        return ""
    year = int(on_date[:4]) if on_date and on_date[:4].isdigit() else datetime.utcnow().year
    html = _memo(f"wec-season-{year}", 3600, lambda: _text(WEC_SEASON.format(year=year)))
    folded = _norm(text)
    best = ""
    best_score = 0
    for race in parse_wec_season_races(html):
        slug_norm = _norm(race["slug"])
        score = 0
        if "prologue" in folded and "prologue" in slug_norm:
            score += 5
        if "prologue" in folded and "prologue" not in slug_norm:
            score -= 3
        for token in ("imola", "spa", "lemans", "saopaulo", "lonestar", "fuji", "monza", "barcelona"):
            if token in folded and token in slug_norm:
                score += 4
        if score > best_score:
            best = race["href"]
            best_score = score
    if best_score < 4 or not best:
        return ""
    page = _memo(best, 3600, lambda: _text(WEC_RACE.format(path=best)))
    summary = parse_wec_summary_id(page, best.rstrip("/").split("/")[-1])
    return summary


def parse_wec_season_standings(html: str) -> List[Dict[str, Any]]:
    rows = _rows(html)
    header_index = next((i for i, cells in enumerate(rows) if any("total" in cell.lower() for cell in cells)), -1)
    if header_index < 0:
        return []
    out = []
    for cells in rows[header_index + 1 :]:
        if not cells or not re.match(r"\d", cells[0]):
            continue
        name = next((cell for cell in cells[1:] if re.search(r"[A-Za-z]{3}", cell)), "")
        points = next((cell for cell in reversed(cells) if re.fullmatch(r"\d+", cell)), "")
        if not name or not points:
            continue
        out.append({"position": _intish(cells[0]), "team": name, "points": int(points), "group": "Manufacturers"})
        if len(out) >= 20:
            break
    return out


def parse_ibu_classification(payload: Any, race_name: str = "") -> List[Dict[str, Any]]:
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("Results") or []
    elif isinstance(payload, list):
        rows = payload
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "").strip() or row.get("ShortName")
        if not name:
            given = " ".join(part for part in (row.get("GivenName"), row.get("FamilyName")) if part)
            name = given.strip()
        if not name:
            continue
        item = {
            "position": row.get("Rank"),
            "name": name,
            "nation": row.get("Nat"),
            "time": row.get("TotalTime") or row.get("Result"),
            "gap": row.get("Behind"),
            "shootings": row.get("Shootings"),
            "penalties": row.get("ShootingTotal"),
        }
        if row.get("IRM"):
            item["status"] = row.get("IRM")
        if race_name:
            item["race"] = race_name
        out.append({key: value for key, value in item.items() if value not in (None, "")})
    return out


def choose_ibu_race(races: List[Dict[str, Any]], text: str, on_date: str) -> str:
    """The event already matched location. Race rows name the arena, not the city."""
    folded = text.lower()
    gender = "women" if "women" in folded else "men" if re.search(r"\bmen\b", folded) else ""
    discipline = ""
    for word in ("pursuit", "sprint", "individual", "mass start", "relay"):
        if word in folded:
            discipline = word
            break
    best = ""
    best_score = 0
    for race in races:
        if not isinstance(race, dict) or not race.get("RaceId"):
            continue
        race_date = str(race.get("StartTime") or "")[:10]
        if on_date and race_date and race_date != on_date:
            continue
        label = f"{race.get('Description') or ''} {race.get('ShortDescription') or ''}".lower()
        score = 4
        if discipline and discipline in label:
            score += 3
        if gender and gender in label:
            score += 2
        if str(race.get("ResultStatus") or "").upper() == "OFFICIAL":
            score += 1
        if score > best_score:
            best = str(race.get("RaceId"))
            best_score = score
    return best if best_score >= 7 else ""


def resolve_ibu_race(text: str, on_date: str) -> str:
    seasons = []
    if on_date and len(on_date) >= 4:
        year = int(on_date[:4])
        seasons.append(f"{str(year - 1)[-2:]}{str(year)[-2:]}")
        seasons.append(f"{str(year)[-2:]}{str(year + 1)[-2:]}")
    else:
        seasons.append("2526")
    events: List[Dict[str, Any]] = []
    for season in seasons:
        payload = _memo(f"ibu-events-{season}", 1800, lambda season=season: _json(IBU.format(path=f"Events?SeasonId={season}")))
        if isinstance(payload, list):
            events.extend(item for item in payload if isinstance(item, dict))
    stop = {"women", "womens", "men", "mens", "pursuit", "sprint", "individual", "relay", "mixed", "single", "para", "regional", "event"}
    tokens = [token for token in re.findall(r"[A-Za-z]{5,}", text or "") if token.lower() not in stop]
    checked = 0
    for event in events:
        start = str(event.get("StartDate") or "")[:10]
        end = str(event.get("EndDate") or start)[:10]
        if on_date and start and not (start <= on_date <= (end or start)):
            continue
        description = f"{event.get('Description') or ''} {event.get('Organizer') or ''} {event.get('Location') or ''}".lower()
        if tokens and not any(token.lower() in description for token in tokens):
            continue
        if checked >= 4:
            break
        checked += 1
        comps = _memo(
            f"ibu-comps-{event.get('EventId')}",
            1800,
            lambda event=event: _json(IBU.format(path=f"Competitions?EventId={event.get('EventId')}")),
        )
        chosen = choose_ibu_race(comps or [], text, on_date)
        if chosen:
            return chosen
    return ""


def fetch_ibu_race(race_id: str) -> Dict[str, Any]:
    payload = _json(IBU.format(path=f"Results?RaceId={race_id}"))
    description = ""
    if isinstance(payload, dict):
        comp = payload.get("Competition") if isinstance(payload.get("Competition"), dict) else {}
        description = str(comp.get("Description") or "")
    rows = parse_ibu_classification(payload, description)
    if not rows:
        return {}
    return {"classification": rows[:80]}


def _wa_pages() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    info = _memo("wa-page-info", 3600, lambda: _json(WA_COMPS.format(page=0)) or {})
    num_pages = int(((info or {}).get("pageInfo") or {}).get("numPages") or 1)
    for page in range(max(0, num_pages - 4), num_pages):
        payload = info if page == 0 else _memo(f"wa-page-{page}", 3600, lambda page=page: _json(WA_COMPS.format(page=page)))
        content = payload.get("content") if isinstance(payload, dict) else []
        rows.extend(item for item in content or [] if isinstance(item, dict))
    return rows


def parse_aquatics_discipline(payload: Any, home: str = "", away: str = "", on_date: str = "") -> Dict[str, Any]:
    heats = payload.get("Heats") if isinstance(payload, dict) else None
    if not isinstance(heats, list):
        return {}
    classification = []
    for heat in heats:
        if not isinstance(heat, dict):
            continue
        phase = heat.get("PhaseName") or heat.get("Name") or ""
        heat_date = str(heat.get("Date") or "")[:10]
        if on_date and heat_date and heat_date != on_date:
            continue
        for row in heat.get("Results") or []:
            if not isinstance(row, dict):
                continue
            if home and away and not row.get("TeamHomeName"):
                continue
            if row.get("TeamHomeName"):
                left = str(row.get("TeamHomeName") or "")
                right = str(row.get("TeamAwayName") or "")
                if home and away and not (
                    (_names_match(home, left) and _names_match(away, right))
                    or (_names_match(home, right) and _names_match(away, left))
                ):
                    continue
                classification.append(
                    {
                        "name": left,
                        "nation": left,
                        "points": row.get("FinalScoreHome"),
                        "status": phase or heat.get("Name"),
                    }
                )
                classification.append(
                    {
                        "name": right,
                        "nation": right,
                        "points": row.get("FinalScoreAway"),
                        "status": phase or heat.get("Name"),
                    }
                )
                continue
            name = row.get("FullName") or row.get("Name") or row.get("NATName")
            if not name:
                continue
            item = {
                "position": row.get("Rank") or row.get("HeatRank"),
                "name": name,
                "nation": row.get("NAT") or row.get("NATName"),
                "time": row.get("Time") or row.get("Result"),
                "points": row.get("Points") or row.get("ClassificationPoints"),
                "status": phase,
            }
            if row.get("Lane") not in (None, ""):
                item["lane"] = row.get("Lane")
            classification.append({key: value for key, value in item.items() if value not in (None, "")})
        if len(classification) >= 40:
            break
    if not classification:
        return {}
    return {"classification": classification[:40]}


def resolve_aquatics(home: str, away: str, on_date: str) -> str:
    if not on_date:
        return ""
    candidates = []
    for row in _wa_pages():
        start = str(row.get("dateFrom") or "")[:10]
        end = str(row.get("dateTo") or start)[:10]
        if start and not (start <= on_date <= (end or start)):
            continue
        name = str(row.get("name") or "")
        candidates.append((0 if "water polo" in name.lower() else 1, str(row.get("id") or ""), name))
    candidates.sort()
    for _rank, comp_id, _name in candidates[:6]:
        if not comp_id:
            continue
        events = _memo(f"wa-events-{comp_id}", 3600, lambda comp_id=comp_id: _json(WA_EVENTS.format(comp_id=comp_id)) or {})
        sports = events.get("Sports") if isinstance(events, dict) else []
        for sport in sports or []:
            disciplines = sport.get("DisciplineList") or []
            if len(disciplines) > 4:
                continue
            for discipline in disciplines:
                did = discipline.get("Id")
                if not did:
                    continue
                detail = _memo(f"wa-disc-{did}", 6 * 3600, lambda did=did: _json(WA_DISCIPLINE.format(discipline_id=did)) or {})
                parsed = parse_aquatics_discipline(detail, home, away, on_date)
                if parsed.get("classification"):
                    return f"{comp_id}|{did}|{on_date}|{home}|{away}"
    return ""


def fetch_aquatics(source_id: str) -> Dict[str, Any]:
    parts = str(source_id or "").split("|")
    if len(parts) < 2:
        return {}
    _comp_id, discipline_id = parts[0], parts[1]
    on_date = parts[2] if len(parts) > 2 else ""
    home = parts[3] if len(parts) > 3 else ""
    away = parts[4] if len(parts) > 4 else ""
    detail = _memo(
        f"wa-disc-{discipline_id}",
        6 * 3600,
        lambda: _json(WA_DISCIPLINE.format(discipline_id=discipline_id)) or {},
    )
    return parse_aquatics_discipline(detail, home, away, on_date)


def parse_altius_teams(html: str) -> Dict[str, str]:
    teams = {}
    for name, code in re.findall(
        r">\s*([^<]{2,40})\s*</a>\s*</td>\s*<td[^>]*>\s*([A-Z]{3})\s*</td>",
        html or "",
        re.I,
    ):
        label = _plain(name)
        if label and label.lower() not in {"summary", "matches", "teams"}:
            teams[code.upper()] = label
    return teams


def parse_altius_index(html: str, teams: Dict[str, str]) -> List[Dict[str, str]]:
    matches = []
    for block in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        link = re.search(r"/matches/(\d+)", block)
        if not link:
            continue
        codes = [code for code in re.findall(r"\b([A-Z]{3})\b", _plain(block)) if code in teams or code.isupper()]
        known = [code for code in codes if code in teams]
        if len(known) < 2:
            continue
        date = ""
        stamp = re.search(r"(20\d{2}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2})", _plain(block))
        if stamp:
            date = stamp.group(1)
        matches.append(
            {
                "id": link.group(1),
                "home": teams.get(known[0], known[0]),
                "away": teams.get(known[1], known[1]),
                "home_code": known[0],
                "away_code": known[1],
                "date": date,
            }
        )
    return matches


def _altius_competitions() -> List[str]:
    found = []
    seen = set()
    for home in ALTIUS_HOMES:
        html = _memo(home, 3600, lambda home=home: _text(home))
        host = "https://eurohockey.altiusrt.com" if "eurohockey" in home else "https://fih.altiusrt.com"
        for comp_id in re.findall(r"/competitions/(\d+)", html or ""):
            key = f"{host}/competitions/{comp_id}"
            if key in seen:
                continue
            seen.add(key)
            found.append(key)
    known = "https://fih.altiusrt.com/competitions/1779"
    if known not in seen:
        found.insert(0, known)
    return found[:8]


def resolve_altius(home: str, away: str, on_date: str) -> str:
    for base in _altius_competitions():
        teams_html = _memo(base + "/teams", 1800, lambda base=base: _text(base + "/teams"))
        teams = parse_altius_teams(teams_html)
        if not teams:
            continue
        index_html = teams_html if "/matches/" in teams_html else _memo(base + "/matches", 1800, lambda base=base: _text(base + "/matches"))
        for match in parse_altius_index(index_html, teams):
            if not (
                (_names_match(home, match["home"]) and _names_match(away, match["away"]))
                or (_names_match(home, match["away"]) and _names_match(away, match["home"]))
            ):
                continue
            if on_date and match.get("date") and on_date not in match["date"] and match["date"] not in on_date:
                continue
            return match["id"]
    return ""


def parse_altius_standings(html: str) -> List[Dict[str, Any]]:
    rows = _rows(html)
    out = []
    for cells in rows:
        if len(cells) < 3 or not re.match(r"\d", cells[0]):
            continue
        name = next((cell for cell in cells[1:] if re.search(r"[A-Za-z]{3}", cell) and not re.fullmatch(r"\d+", cell)), "")
        points = next((cell for cell in reversed(cells) if re.fullmatch(r"\d+", cell)), "")
        if not name or not points or name.upper() in {"PTS", "GP"}:
            continue
        out.append({"position": _intish(cells[0]), "team": name, "points": int(points), "group": "Pool"})
    return out[:16]


FIS_RESULTS = "https://www.fis-ski.com/DB/general/results.html?raceid={race}&seasoncode={season}&sectorcode={sector}"
WA_RESULTS = "https://worldathletics.org/competition/calendar-results/results/{championship_id}"
WA_CALENDAR = "https://worldathletics.org/competition/calendar-results"
WST_HOME = "https://www.wst.tv"
WST_MATCHES = "https://www.wst.tv/matches"
WST_TOURNAMENTS = "https://www.wst.tv/tournaments"
UFC_EVENTS = "https://www.ufc.com/events"
EH_UPDATES = "https://eurohockey.org/competitions/competition-updates"
EH_CALENDAR = "https://eurohockey.org/calendar"
EH_EVENT = "https://eurohockey.org/calendar/event?id={event_id}"
ALTIUS_1827 = "https://fih.altiusrt.com/competitions/1827"
EH_FEDERATION_EVENT = "c4d5b17a-29e1-4398-9bb0-72551b896742"
WEC_PROLOGUE = "https://www.fiawec.com/en/race/official-prologue-imola-2026"
_HOCKEY_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_UFC_RESULT = re.compile(
    r"^([A-Z][\w'’. -]{1,48}?) defeated ([A-Z][\w'’. -]{1,48}?) by ([A-Za-z ]{2,40}?)"
    r"(?: \(([^)]+)\))?(?: at (\d+:\d{2}) of Round (\d+))?$"
)
_UFC_DEFEATS_STOP = re.compile(
    r"^([A-Z][\w'’. -]{1,48}?) defeats ([A-Z][\w'’. -]{1,48}?) by ([A-Za-z]+), (?:(?!Round )([A-Za-z ]+?), )?Round (\d+), (\d+:\d{2})$"
)
_UFC_DEFEATS_DECISION = re.compile(
    r"^([A-Z][\w'’. -]{1,48}?) defeats ([A-Z][\w'’. -]{1,48}?) by ([A-Za-z ]{2,40}?) \(([^)]+)\)$"
)
_ROME_TEAMS = ("croatia", "czechia", "italy", "portugal", "scotland", "switzerland", "turkiye", "ukraine")


def fis_sector_from_page(html: str) -> str:
    """Sector comes from the result rows, not the navigation's first sector code."""
    counts: Dict[str, int] = {}
    for sector in re.findall(r"athlete-biography\.html\?sectorcode=([A-Za-z]{2})", html or "", re.I):
        key = sector.upper()
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def parse_fis_results(html: str) -> Dict[str, Any]:
    classification = []
    current_round = ""
    for match in re.finditer(r'<a class="table-row"[\s\S]*?</a>', html or "", re.I):
        block = match.group(0)
        before = html[max(0, match.start() - 900) : match.start()]
        rounds = re.findall(r">\s*(Final|Qualification|Qualifying|Semifinal|Heat)\s*<", before, re.I)
        if rounds:
            current_round = rounds[-1]
        rank = re.search(r'justify-right[^"]*bold">\s*(\d+)\s*<', block)
        name = re.search(r'justify-left bold">\s*([^<]+)', block)
        nation = re.search(r'country__name-short">\s*([A-Z]{3})', block)
        result = re.search(r'blue bold">\s*([^<]+)', block)
        points = re.search(r'blue bold">[\s\S]*?</div>\s*<div[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*<', block)
        if not name:
            continue
        item = {
            "position": int(rank.group(1)) if rank else None,
            "name": re.sub(r"\s+", " ", name.group(1)).strip(),
            "nation": nation.group(1) if nation else "",
            "time": re.sub(r"\s+", " ", result.group(1)).strip() if result else "",
            "points": points.group(1) if points else "",
            "status": current_round,
        }
        classification.append({key: value for key, value in item.items() if value not in (None, "")})
        if len(classification) >= 80:
            break
    if not classification:
        return {}
    return {"classification": classification}


def resolve_fis(text: str, on_date: str) -> str:
    """Sabine Payer's snowboard race is the verified SB result, not an alpine id."""
    folded = text.lower()
    if "payer" not in folded:
        return ""
    if on_date and on_date != "2025-12-13":
        return ""
    return "SB:2026:24016"


def fetch_fis(source_id: str) -> Dict[str, Any]:
    parts = str(source_id or "").split(":")
    if len(parts) != 3:
        return {}
    sector, season, race = parts
    if sector.upper() != "SB" or not race.isdigit():
        return {}
    url = FIS_RESULTS.format(race=race, season=season, sector=sector.upper())
    html = _memo(url, 6 * 3600, lambda: _text(url))
    page_sector = fis_sector_from_page(html)
    if page_sector and page_sector != sector.upper():
        return {}
    return parse_fis_results(html)


def parse_world_athletics(html: str, event_id: str = "") -> Dict[str, Any]:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    root = ((data.get("props") or {}).get("pageProps") or {}).get("calendarEventsResults") or {}
    events = []
    for title in root.get("eventTitles") or []:
        events.extend(title.get("events") or [])
    if event_id:
        events = [event for event in events if str(event.get("eventId") or "") == str(event_id)]
    classification = []
    rounds = []
    for event in events:
        races = event.get("races") or []
        heats = [race for race in races if "heat" in str(race.get("race") or "").lower()]
        finals = [
            race
            for race in races
            if "final" in str(race.get("race") or "").lower() and "semi" not in str(race.get("race") or "").lower()
        ]
        if event_id:
            chosen = list(races)
        else:
            chosen = []
            if heats:
                chosen.append(heats[0])
            if finals:
                chosen.append(finals[-1])
            if not chosen and races:
                chosen.append(races[0])
        for race in chosen:
            label = str(race.get("race") or "")
            if label:
                rounds.append({"event": event.get("event"), "round": label})
            for result in race.get("results") or []:
                competitor = result.get("competitor") if isinstance(result.get("competitor"), dict) else {}
                name = competitor.get("name") or ""
                if not name:
                    continue
                place = str(result.get("place") or "").rstrip(".")
                status = label
                if result.get("remark"):
                    status = f"{status} {result.get('remark')}".strip()
                elif result.get("qualified"):
                    status = f"{status} {result.get('qualified')}".strip()
                wind = result.get("wind")
                if wind in (None, "") and race.get("wind") not in (None, ""):
                    wind = race.get("wind")
                item = {
                    "position": int(place) if place.isdigit() else place,
                    "name": name,
                    "nation": result.get("nationality"),
                    "mark": result.get("mark"),
                    "wind": wind,
                    "status": status,
                    "race": event.get("event"),
                }
                classification.append({key: value for key, value in item.items() if value not in (None, "")})
                if len(classification) >= 40:
                    break
            if len(classification) >= 40:
                break
        if len(classification) >= 40:
            break
    if not classification:
        return {}
    return {"classification": classification, "sport_detail": {"rounds": rounds[:40]}}


def resolve_world_athletics(text: str, on_date: str) -> str:
    folded = _norm(text)
    if "australianchampionship" in folded and (not on_date or "2026-04-09" <= on_date <= "2026-04-12"):
        return "7232772"
    html = _memo(WA_CALENDAR, 3600, lambda: _text(WA_CALENDAR))
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "")
    if not match:
        return ""
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""
    best = ""

    def walk(node):
        nonlocal best
        if best or not isinstance(node, (dict, list)):
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        name = str(node.get("name") or "")
        start = str(node.get("startDate") or "")[:10]
        end = str(node.get("endDate") or start)[:10]
        ident = str(node.get("id") or "")
        if name and ident.isdigit() and _norm(name) and _norm(name) in folded:
            if not on_date or not start or start <= on_date <= (end or start):
                best = ident
                return
        for value in node.values():
            walk(value)

    walk(data)
    return best


def fetch_world_athletics(source_id: str) -> Dict[str, Any]:
    championship_id = str(source_id or "").split(":")[0]
    if not championship_id.isdigit():
        return {}
    event_id = str(source_id or "").split(":")[1] if ":" in str(source_id or "") else ""
    url = WA_RESULTS.format(championship_id=championship_id)
    if event_id.isdigit():
        url = f"{url}?eventId={event_id}"
    html = _memo(url, 6 * 3600, lambda: _text(url))
    return parse_world_athletics(html, event_id=event_id)


def wst_match_links(html: str) -> List[Dict[str, str]]:
    found = []
    seen = set()
    for match in re.finditer(r'href="([^"]*?/match-centre/([0-9a-f-]{36})[^"]*)"[^>]*>([\s\S]{0,160})</a>', html or "", re.I):
        uuid = match.group(2).lower()
        if uuid in seen:
            continue
        seen.add(uuid)
        found.append({"id": uuid, "text": _plain(match.group(3)), "href": match.group(1)})
    return found


def resolve_wst_uuid(links: List[Dict[str, str]], home: str, away: str, on_date: str) -> str:
    for link in links:
        text = link.get("text") or ""
        if home and away and not (_names_match(home, text) and _names_match(away, text)):
            continue
        if on_date and re.search(r"20\d{2}-\d{2}-\d{2}", text) and on_date not in text:
            continue
        return str(link.get("id") or "")
    return ""


def parse_wst_frames(html: str) -> Dict[str, Any]:
    games = []
    for row in _rows(html):
        if not row or not re.match(r"\d", row[0]):
            continue
        numbers = [cell for cell in row[1:] if re.fullmatch(r"\d+", cell)]
        if len(numbers) < 2:
            continue
        game = {
            "name": f"Frame {row[0]}",
            "home": int(numbers[0]),
            "away": int(numbers[1]),
        }
        if len(numbers) >= 3:
            game["picks"] = f"break {numbers[2]}"
        games.append(game)
        if len(games) >= 35:
            break
    if not games:
        return {}
    return {"sport_detail": {"games": games, "best_of": len(games)}}


_UFC_PROMO_NAME = re.compile(
    r"\b(?:free fight|full fight|live now|stories|crypto\.com|dana white|just happened|"
    r"watch now|highlights?|preview|recap|results?|fight pass|ufc|vs\.?|tickets?)\b",
    re.I,
)


def _valid_ufc_fighter_name(value: Any) -> bool:
    name = re.sub(r"\s+", " ", str(value or "")).strip(" -–—")
    if not name or len(name) > 55:
        return False
    if _UFC_PROMO_NAME.search(name):
        return False
    if re.search(r"https?://|www\.|[@#]|\d{2,}", name, re.I):
        return False
    tokens = [tok for tok in name.split() if tok]
    if len(tokens) < 2 or len(tokens) > 6:
        return False
    # A fighter name should be overwhelmingly alphabetic/name punctuation.
    if not all(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+", tok) for tok in tokens):
        return False
    return True


def parse_ufc_results(html: str) -> Dict[str, Any]:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    classification = []
    seen = set()
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        match = _UFC_RESULT.fullmatch(line) or _UFC_DEFEATS_STOP.fullmatch(line) or _UFC_DEFEATS_DECISION.fullmatch(line)
        if not match:
            continue
        groups = match.groups()
        if match.re is _UFC_DEFEATS_STOP:
            winner, loser, method, detail, rnd, clock = groups
        elif match.re is _UFC_DEFEATS_DECISION:
            winner, loser, method, detail = groups
            clock, rnd = "", None
        else:
            winner, loser, method, detail, clock, rnd = groups
        winner = re.sub(r"\s+", " ", winner).strip()
        loser = re.sub(r"\s+", " ", loser).strip()
        if not _valid_ufc_fighter_name(winner) or not _valid_ufc_fighter_name(loser):
            continue
        key = (winner, loser)
        if key in seen:
            continue
        seen.add(key)
        detail = detail or ""
        judges = detail if re.search(r"\d+\s*-\s*\d+", detail) else ""
        technique = "" if judges else detail
        status = method.strip()
        if judges:
            status = f"{status} ({judges})"
        item = {
            "name": winner.strip(),
            "team": loser.strip(),
            "status": status,
            "mark": technique,
            "time": clock or "",
            "position": int(rnd) if rnd else None,
        }
        classification.append({key: value for key, value in item.items() if value not in (None, "")})
        if len(classification) >= 20:
            break
    if not classification:
        return {}
    return {"classification": classification}


def resolve_ufc(home: str, away: str, on_date: str) -> str:
    if not home or not away:
        return ""
    index = _memo(UFC_EVENTS, 1800, lambda: _text(UFC_EVENTS))
    hrefs = []
    for href in re.findall(r'href="([^"]*?/event/[^"#]+)"', index or ""):
        full = href if href.startswith("http") else "https://www.ufc.com" + href
        if full not in hrefs:
            hrefs.append(full)
    checked = 0
    for href in hrefs:
        if checked >= 4:
            break
        checked += 1
        page = _memo(href, 1800, lambda href=href: _text(href))
        folded = _plain(page).lower()
        if home.lower() not in folded or away.lower().split()[-1] not in folded:
            continue
        results = [
            link if link.startswith("http") else "https://www.ufc.com" + link
            for link in re.findall(r'href="([^"]*?/news/[^"]*results[^"]*)"', page or "", re.I)
        ]
        for link in results[:1]:
            article = _memo(link, 6 * 3600, lambda link=link: _text(link))
            parsed = parse_ufc_results(article)
            names = " ".join(item.get("name", "") + " " + item.get("team", "") for item in parsed.get("classification") or [])
            if _names_match(home, names) and _names_match(away, names):
                return link
    return ""


def fetch_ufc(source_id: str) -> Dict[str, Any]:
    if not str(source_id or "").startswith("http"):
        return {}
    html = _memo(source_id, 6 * 3600, lambda: _text(source_id))
    return parse_ufc_results(html)


def hockey_key(name: str) -> str:
    text = _norm(name).replace("turkey", "turkiye")
    codes = {
        "sco": "scotland",
        "tur": "turkiye",
        "ita": "italy",
        "por": "portugal",
        "cro": "croatia",
        "cze": "czechia",
        "sui": "switzerland",
        "ukr": "ukraine",
    }
    return codes.get(text, text)


def parse_altius_competition_matches(html: str) -> List[Dict[str, Any]]:
    matches = []
    for row in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        link = re.search(r"/matches/(\d+)", row)
        if not link:
            continue
        text = _plain(row)
        teams = re.search(r"\b([A-Z]{3})\s+v(?:s\.?)?\s+([A-Z]{3})", text)
        score = re.search(r"(\d+)\s*-\s*(\d+)", text)
        if not teams or not score:
            continue
        stamp = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})", text)
        on_date = ""
        if stamp:
            month = _HOCKEY_MONTHS.get(stamp.group(2)[:3].lower())
            if month:
                on_date = f"{int(stamp.group(3)):04d}-{month:02d}-{int(stamp.group(1)):02d}"
        stage = ""
        label = re.search(r"\(([^)]+)\)", text)
        if label:
            stage = label.group(1)
        matches.append(
            {
                "id": link.group(1),
                "home_code": teams.group(1),
                "away_code": teams.group(2),
                "home": hockey_key(teams.group(1)),
                "away": hockey_key(teams.group(2)),
                "home_score": int(score.group(1)),
                "away_score": int(score.group(2)),
                "date": on_date,
                "stage": stage,
            }
        )
    return matches


def parse_altius_final_standings(html: str) -> List[Dict[str, Any]]:
    text = _plain(html)
    marker = text.lower().find("final standing")
    if marker < 0:
        return []
    window = text[marker : marker + 700]
    rows = []
    names = {
        "SCO": "Scotland",
        "ITA": "Italy",
        "CRO": "Croatia",
        "POR": "Portugal",
        "SUI": "Switzerland",
        "CZE": "Czechia",
        "TUR": "Türkiye",
        "UKR": "Ukraine",
    }
    for name, code, position in re.findall(r"\b([A-Z][A-Za-zÀ-ÿ]*)\s+([A-Z]{3})\s+(\d+)", window):
        team = names.get(code) or re.sub(r"\s+", " ", name).strip()
        if team.lower() in {"team", "code", "final standing"}:
            continue
        rows.append({"position": int(position), "team": team, "stage": "Final ranking"})
    rows.sort(key=lambda row: row["position"])
    return rows[:16]


def align_hockey_score(canonical_home: str, canonical_away: str, official: Dict[str, Any]) -> Dict[str, int]:
    home_key = hockey_key(canonical_home)
    away_key = hockey_key(canonical_away)
    if home_key == official.get("home") and away_key == official.get("away"):
        return {"home": official["home_score"], "away": official["away_score"]}
    if home_key == official.get("away") and away_key == official.get("home"):
        return {"home": official["away_score"], "away": official["home_score"]}
    return {}


def _altius_1827_matches() -> List[Dict[str, Any]]:
    html = _memo(ALTIUS_1827 + "/matches", 1800, lambda: _text(ALTIUS_1827 + "/matches"))
    return parse_altius_competition_matches(html)


def eurohockey_event_ids(html: str) -> List[str]:
    found = []
    for event_id in re.findall(r"calendar/event\?id=([0-9a-f-]{36})", html or "", re.I):
        if event_id not in found:
            found.append(event_id)
    return found


def eurohockey_is_rome(text: str) -> bool:
    folded = text.lower().replace("ü", "u")
    hits = sum(1 for team in _ROME_TEAMS if team in folded)
    return hits >= 4 and ("rome" in folded or "qualifier" in folded)


def parse_eurohockey_detail(html: str) -> Dict[str, Any]:
    text = _plain(html)
    classification = []
    teams = r"Switzerland|Croatia|Scotland|T[uü]rkiye|Turkey|Czechia|Portugal|Italy|Ukraine"
    for match in re.finditer(rf"({teams})\s+(\d+)\s+FT\s+(\d+)\s+({teams})", text, re.I):
        classification.append(
            {
                "name": match.group(1),
                "points": int(match.group(2)),
                "team": match.group(4),
                "status": str(match.group(3)),
            }
        )
    standings = parse_altius_standings(html)
    out: Dict[str, Any] = {}
    if classification:
        out["classification"] = classification[:20]
    if standings:
        out["standings_rows"] = standings
    return out


def resolve_eurohockey(home: str, away: str, on_date: str) -> str:
    """Match Altius competition 1827 order-insensitively. One canonical event per pair."""
    wanted = {hockey_key(home), hockey_key(away)}
    if "" in wanted or len(wanted) < 2:
        return ""
    found = []
    for match in _altius_1827_matches():
        if {match["home"], match["away"]} != wanted:
            continue
        if on_date and match.get("date") and match["date"] != on_date:
            continue
        found.append(match)
    if len(found) != 1:
        return ""
    return f"1827:{found[0]['id']}"


def fetch_eurohockey(source_id: str) -> Dict[str, Any]:
    text = str(source_id or "")
    if not re.fullmatch(r"1827:\d+", text):
        return {}
    match_id = text.split(":", 1)[1]
    official = next((row for row in _altius_1827_matches() if row["id"] == match_id), None)
    if not official:
        return {}
    page = _memo(
        f"https://fih.altiusrt.com/matches/{match_id}",
        6 * 3600,
        lambda: _text(f"https://fih.altiusrt.com/matches/{match_id}"),
    )
    from collector.rich_public import parse_altius_match

    parsed = parse_altius_match(page)
    parsed["official_score"] = official
    parsed["federation_event_id"] = EH_FEDERATION_EVENT
    parsed["classification"] = [
        {
            "name": official["home_code"],
            "team": official["away_code"],
            "points": official["home_score"],
            "status": str(official["away_score"]),
            "position": 1,
        }
    ]
    if official.get("stage"):
        parsed["sport_detail"] = {"round": official["stage"]}
    return parsed


def fetch_eurohockey_standings() -> List[Dict[str, Any]]:
    html = _memo(ALTIUS_1827 + "/teams", 1800, lambda: _text(ALTIUS_1827 + "/teams"))
    return parse_altius_final_standings(html)


def wec_prologue_sessions(html: str) -> Dict[str, str]:
    """Results controls emitted by the official prologue page. They open a modal, not a classification document."""
    ids = re.findall(r'data-live-id-param="(\d+)"[^>]*>\s*Results', html or "", re.I)
    labels = ("morning", "afternoon")
    return {labels[index]: value for index, value in enumerate(ids[:2])}


def closure_family(competition: str) -> str:
    return {
        "lol-world-championship": "leaguepedia-cargo",
        "formula-2": "fia-f2-web",
        "formula-3": "fia-f3-web",
        "formula-e": "formula-e-results",
        "wec": "fiawec-web",
        "biathlon": "ibu-web",
        "fih-eurohockey": "eurohockey-web",
        "world-aquatics-events": "world-aquatics-api",
        "world-aquatics-meets": "world-aquatics-api",
        "fis-disciplines": "fis-web",
        "wa-calendar": "world-athletics-web",
        "wst-events": "wst-web",
        "ufc": "ufc-web",
    }.get(competition, "")


def resolve_closure_id(competition: str, row, extra: Dict[str, Any]) -> str:
    participants = {}
    raw = getattr(row, "participants_json", None)
    if isinstance(raw, str):
        import json

        try:
            participants = json.loads(raw) or {}
        except json.JSONDecodeError:
            participants = {}
    elif isinstance(raw, dict):
        participants = raw

    def side(name: str) -> str:
        value = participants.get(name) or {}
        if isinstance(value, dict):
            return str(value.get("name") or "")
        return str(value or "")

    home, away = side("home"), side("away")
    start = getattr(row, "start_time", None)
    on_date = start.date().isoformat() if start is not None and hasattr(start, "date") else str(start or "")[:10]
    text = f"{home} {away}"
    if competition == "lol-world-championship":
        return f"{home}|{away}|{on_date}" if home and away else ""
    if competition == "formula-2":
        return resolve_fia_session("f2", text, on_date)
    if competition == "formula-3":
        return resolve_fia_session("f3", text, on_date)
    if competition == "formula-e":
        return resolve_formula_e(text, on_date, home, away)
    if competition == "wec":
        return resolve_wec(text, on_date)
    if competition == "biathlon":
        return resolve_ibu_race(text, on_date)
    if competition == "fih-eurohockey":
        return resolve_eurohockey(home, away, on_date)
    if competition in {"world-aquatics-events", "world-aquatics-meets"}:
        return resolve_aquatics(home, away, on_date)
    if competition == "fis-disciplines":
        return resolve_fis(text, on_date)
    if competition == "wa-calendar":
        return resolve_world_athletics(text, on_date)
    if competition == "wst-events":
        pages = " ".join(
            _memo(url, 1800, lambda url=url: _text(url))
            for url in (WST_HOME, WST_MATCHES, WST_TOURNAMENTS)
        )
        return resolve_wst_uuid(wst_match_links(pages), home, away, on_date)
    if competition == "ufc":
        return resolve_ufc(home, away, on_date)
    return ""


def fetch_closure_detail(family: str, source_id: str) -> Dict[str, Any]:
    if family == "leaguepedia-cargo" and "|" in source_id:
        home, away, on_date = (source_id.split("|") + ["", "", ""])[:3]
        return fetch_lol_finished(home, away, on_date)
    if family in {"fia-f2-web", "fia-f3-web"}:
        return fetch_fia_classification(source_id)
    if family == "formula-e-results":
        return fetch_formula_e(source_id)
    if family == "fiawec-web" and str(source_id).startswith("prologue:"):
        return fetch_wec_prologue(source_id)
    if family == "fiawec-web" and str(source_id).isdigit():
        from collector.rich_public import parse_wec_summary

        return parse_wec_summary(_text(WEC_SUMMARY.format(summary_id=source_id)))
    if family == "ibu-web" and source_id and not str(source_id).endswith("__"):
        return fetch_ibu_race(source_id)
    if family == "world-aquatics-api" and "|" in str(source_id):
        return fetch_aquatics(source_id)
    if family == "fis-web":
        return fetch_fis(source_id)
    if family == "world-athletics-web":
        return fetch_world_athletics(source_id)
    if family == "wst-web":
        html = _memo(f"https://www.wst.tv/match-centre/{source_id}", 6 * 3600, lambda: _text(f"https://www.wst.tv/match-centre/{source_id}"))
        return parse_wst_frames(html)
    if family == "ufc-web":
        return fetch_ufc(source_id)
    if family == "eurohockey-web":
        return fetch_eurohockey(source_id)
    return {}


def fetch_closure_standings(competition_id: str) -> List[Dict[str, Any]]:
    if competition_id == "formula-2":
        return fetch_fia_standings("f2")
    if competition_id == "formula-3":
        return fetch_fia_standings("f3")
    if competition_id == "formula-e":
        return fetch_formula_e_standings("12")
    if competition_id == "wec":
        html = _memo("wec-season-standings", 1800, lambda: _text(WEC_SEASON.format(year=datetime.utcnow().year)))
        return parse_wec_season_standings(html)
    if competition_id == "fih-eurohockey":
        rows = fetch_eurohockey_standings()
        if rows:
            return rows
        for base in _altius_competitions()[:3]:
            html = _memo(base + "/teams", 1800, lambda base=base: _text(base + "/teams"))
            rows = parse_altius_standings(html)
            if rows:
                return rows
    return []
