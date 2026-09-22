"""On-demand rich detail for the verified public transports.

Called from Match Centre enrichment only. Never from the score list.
Provider ids stay on source_event_ids and are stripped before the public payload.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from collector.http import fetch_text, fetch_url
from collector.source_ids import merge_family_ids
from collector.util import load_json

CD_COMPS = "https://mc.championdata.com/data/competitions.json"
CD_FIXTURE = "https://mc.championdata.com/data/{comp_id}/fixture.json"
LIIGA_GAMES = "https://liiga.fi/api/v2/games?tournament=runkosarja&season={season}"
LIIGA_STATS = "https://liiga.fi/api/v2/games/stats/{season}/{game_id}"
LIIGA_GAME = "https://liiga.fi/api/v2/games/{season}/{game_id}"
LIIGA_SHOTS = "https://liiga.fi/api/v2/shotmap/{season}/{game_id}"
IBU = "https://www.biathlonresults.com/modules/sportapi/api/{path}"
WA_COMPS = "https://api.worldaquatics.com/fina/competitions?pageSize=40"
WA_EVENTS = "https://api.worldaquatics.com/fina/competitions/{comp_id}/events"
LETOUR = "https://www.letour.fr/en/rankings/stage-{stage}"
LETOUR_WEBVIEW = "https://www.letour.fr/en/webview/rankings/stage-{stage}"
WEC_HOME = "https://www.fiawec.com/en/"
WEC_SUMMARY = "https://www.fiawec.com/en/race/summary/{race_id}"
ALTIUS_MATCHES = "https://fih.altiusrt.com/competitions/1779/matches"
ALTIUS_MATCH = "https://fih.altiusrt.com/matches/{match_id}"
GRI_INDEX = "https://www.grireland.ie/results"
GRI_MEETING = "https://www.grireland.ie/results/view-results/?date={date}&track={track}"
LETROT = "https://www.letrot.com/courses/{date}/{track}/{race}"

_MEMO: Dict[str, Any] = {}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_NRL_STATS = (
    ("tries", "Tries"),
    ("tackles", "Tackles"),
    ("lineBreaks", "Line breaks"),
    ("metresGained", "Metres"),
    ("runMetres", "Run metres"),
    ("tryAssists", "Try assists"),
)
_NETBALL_STATS = (
    ("goals", "Goals"),
    ("goalAssists", "Assists"),
    ("goalMisses", "Misses"),
    ("centrePassReceives", "Centre pass receives"),
    ("intercepts", "Intercepts"),
    ("penalties", "Penalties"),
)
_GOAL_TYPE = {"FG": "field goal", "PC": "penalty corner", "PS": "penalty stroke"}
_CARD_TYPE = {"G": "green", "Y": "yellow", "R": "red"}


def _memo(key: str, ttl: int, loader):
    hit = _MEMO.get(key)
    now = time.time()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = loader()
    _MEMO[key] = (now, value)
    return value


def _json(url: str) -> Any:
    result = fetch_url(url, timeout=20)
    if result.ok and isinstance(result.payload, (dict, list)):
        return result.payload
    return None


def _text(url: str) -> str:
    result = fetch_text(url, timeout=20)
    if result.ok and isinstance(result.payload, str):
        return result.payload
    return ""


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _names_match(left: Any, right: Any) -> bool:
    a, b = _norm(left), _norm(right)
    if len(a) < 3 or len(b) < 3:
        return bool(a and a == b)
    return a in b or b in a


def _pair_match(home: str, away: str, left: str, right: str) -> bool:
    if _names_match(home, left) and _names_match(away, right):
        return True
    return _names_match(home, right) and _names_match(away, left)


def _sides(row) -> tuple:
    participants = load_json(getattr(row, "participants_json", None), {}) or {}
    def name(side: str) -> str:
        value = participants.get(side) or {}
        if isinstance(value, dict):
            return str(value.get("name") or "")
        return str(value or "")
    return name("home"), name("away")


def _day(row) -> str:
    start = getattr(row, "start_time", None)
    if start is None:
        return ""
    try:
        return start.date().isoformat()
    except AttributeError:
        text = str(start)
        return text[:10]


def _checked(extra: Dict[str, Any]) -> bool:
    stamp = extra.get("rich_id_checked_at")
    if not stamp:
        return False
    try:
        at = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    return (datetime.utcnow() - at.replace(tzinfo=None)).total_seconds() < 900


def _mark_checked(extra: Dict[str, Any]) -> None:
    extra["rich_id_checked_at"] = datetime.utcnow().isoformat()


def _store(extra: Dict[str, Any], family: str, source_id: str) -> None:
    if not source_id:
        return
    extra["source_event_ids"] = merge_family_ids(extra.get("source_event_ids"), family=family, source_event_id=source_id)


def _rows_of(node: Any, key: str) -> List[Dict[str, Any]]:
    if isinstance(node, dict):
        inner = node.get(key)
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
        if isinstance(inner, dict):
            return [inner]
    if isinstance(node, list):
        return [item for item in node if isinstance(item, dict)]
    return []


def _stat_row(label: str, home: Any, away: Any) -> Optional[Dict[str, Any]]:
    if home in (None, "") and away in (None, ""):
        return None
    return {"label": label, "home": home, "away": away}


def parse_championdata_detail(payload: Dict[str, Any]) -> Dict[str, Any]:
    stats = payload.get("matchStats") if isinstance(payload.get("matchStats"), dict) else payload
    if not isinstance(stats, dict) or "teamStats" not in stats and "playerStats" not in stats:
        return {}
    info = stats.get("matchInfo") if isinstance(stats.get("matchInfo"), dict) else {}
    teams = _rows_of(stats.get("teamStats"), "team")
    if len(teams) < 2:
        return {}
    home_id = str(info.get("homeSquadId") or teams[0].get("squadId") or "")
    away_id = str(info.get("awaySquadId") or teams[1].get("squadId") or "")
    by_id = {str(team.get("squadId")): team for team in teams}
    home = by_id.get(home_id) or teams[0]
    away = by_id.get(away_id) or teams[1]
    rugby = home.get("tries") is not None or away.get("tries") is not None
    mapping = _NRL_STATS if rugby else _NETBALL_STATS
    statistics = []
    for key, label in mapping:
        row = _stat_row(label, home.get(key), away.get(key))
        if row:
            statistics.append(row)
    names = {}
    squads = {}
    for player in _rows_of(stats.get("playerInfo"), "player"):
        pid = str(player.get("playerId") or "")
        display = player.get("displayName") or " ".join(
            part for part in (player.get("firstname"), player.get("surname")) if part
        )
        if pid and display:
            names[pid] = str(display).strip()
            squads[pid] = str(player.get("squadId") or "")
    players = []
    for player in _rows_of(stats.get("playerStats"), "player"):
        pid = str(player.get("playerId") or "")
        name = names.get(pid)
        if not name:
            continue
        side_id = str(player.get("squadId") or squads.get(pid) or "")
        side = "home" if side_id == str(home.get("squadId")) else "away"
        item = {"name": name, "side": side}
        if rugby:
            for src, dest in (
                ("tries", "tries"),
                ("tackles", "tackles"),
                ("lineBreaks", "line_breaks"),
                ("metresGained", "metres"),
                ("runMetres", "metres"),
                ("tryAssists", "assists"),
            ):
                if player.get(src) not in (None, "") and item.get(dest) is None:
                    item[dest] = player.get(src)
        else:
            if player.get("goals") not in (None, ""):
                item["goals"] = player.get("goals")
            if player.get("goalAssists") not in (None, ""):
                item["assists"] = player.get("goalAssists")
        players.append(item)
    periods = _champion_periods(stats, str(home.get("squadId")), str(away.get("squadId")))
    lineups = {"home": {"start": []}, "away": {"start": []}}
    for pid, name in names.items():
        side = "home" if squads.get(pid) == str(home.get("squadId")) else "away"
        lineups[side]["start"].append({"name": name})
    if not lineups["home"]["start"] and not lineups["away"]["start"]:
        lineups = {}
    out: Dict[str, Any] = {}
    if statistics:
        out["statistics"] = statistics
    if players:
        out["player_statistics"] = players
    if periods:
        out["periods"] = periods
    if lineups:
        out["lineups"] = lineups
    venue = info.get("venueName") or info.get("venue")
    if venue:
        out["venue"] = venue
    detail: Dict[str, Any] = {}
    if rugby and (home.get("tries") is not None or away.get("tries") is not None):
        detail["tries"] = {"home": home.get("tries"), "away": away.get("tries")}
    if detail:
        out["sport_detail"] = detail
    return out


def _champion_periods(stats: Dict[str, Any], home_id: str, away_id: str) -> List[Dict[str, Any]]:
    rows = _rows_of(stats.get("teamPeriodStats"), "team")
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        label = row.get("period") or row.get("periodNumber") or row.get("periodNum")
        if label in (None, ""):
            continue
        key = str(label)
        bucket = grouped.setdefault(key, {"label": label})
        score = row.get("score")
        if score is None:
            score = row.get("points")
        side = "home" if str(row.get("squadId")) == home_id else "away" if str(row.get("squadId")) == away_id else ""
        if side and score is not None:
            bucket[side] = score
    ordered = [grouped[key] for key in sorted(grouped, key=lambda item: str(item))]
    return [row for row in ordered if row.get("home") is not None or row.get("away") is not None]


def parse_liiga_bundle(detail: Any, stats: Any, shots: Any) -> Dict[str, Any]:
    game = detail.get("game") if isinstance(detail, dict) else {}
    if not isinstance(game, dict):
        return {}
    periods = []
    for row in game.get("periods") or []:
        if not isinstance(row, dict):
            continue
        if row.get("homeTeamGoals") is None and row.get("awayTeamGoals") is None:
            continue
        periods.append({"label": row.get("index") or row.get("category"), "home": row.get("homeTeamGoals"), "away": row.get("awayTeamGoals")})
    home = game.get("homeTeam") if isinstance(game.get("homeTeam"), dict) else {}
    away = game.get("awayTeam") if isinstance(game.get("awayTeam"), dict) else {}
    names: Dict[str, str] = {}
    players = []
    for side, rows in (("home", detail.get("homeTeamPlayers")), ("away", detail.get("awayTeamPlayers"))):
        if not isinstance(rows, list):
            continue
        for player in rows:
            if not isinstance(player, dict):
                continue
            name = " ".join(part for part in (player.get("firstName"), player.get("lastName")) if part).strip()
            if not name:
                continue
            pid = str(player.get("id") or "")
            if pid:
                names[pid] = name
            item = {"name": name, "side": side}
            if player.get("line") not in (None, ""):
                item["line"] = player.get("line")
            role = str(player.get("role") or player.get("roleCode") or "")
            if re.search(r"goal", role, re.I):
                item["position"] = "goalie"
            players.append(item)
    incidents = []
    for side, team in (("home", home), ("away", away)):
        for goal in team.get("goalEvents") or []:
            if not isinstance(goal, dict):
                continue
            scorer = goal.get("scorerPlayer") if isinstance(goal.get("scorerPlayer"), dict) else {}
            player = " ".join(part for part in (scorer.get("firstName"), scorer.get("lastName")) if part).strip()
            assists = []
            for assist in goal.get("assistantPlayers") or []:
                if isinstance(assist, dict):
                    assists.append(" ".join(part for part in (assist.get("firstName"), assist.get("lastName")) if part).strip())
            incidents.append(
                {
                    "minute": _clock(goal.get("gameTime")),
                    "player": player or None,
                    "assist": ", ".join(a for a in assists if a) or None,
                    "family": "goal",
                    "type": "goal",
                    "side": side,
                    "score_after": {"home": goal.get("homeTeamScore"), "away": goal.get("awayTeamScore")},
                }
            )
        for penalty in team.get("penaltyEvents") or []:
            if not isinstance(penalty, dict):
                continue
            who = penalty.get("player") if isinstance(penalty.get("player"), dict) else {}
            player = " ".join(part for part in (who.get("firstName"), who.get("lastName")) if part).strip()
            if not player:
                player = str(penalty.get("committedBy") or "")
            incidents.append(
                {
                    "minute": _clock(penalty.get("gameTime") or penalty.get("time")),
                    "player": player or None,
                    "family": "penalty",
                    "type": penalty.get("penaltyType") or penalty.get("type") or "penalty",
                    "side": side,
                }
            )
    statistics = []
    shot_totals = _liiga_team_totals(stats)
    for label, key in (("Goals", "goals"), ("Shots", "shots"), ("Penalty minutes", "penaltyMinutes")):
        row = _stat_row(label, (shot_totals.get("home") or {}).get(key), (shot_totals.get("away") or {}).get(key))
        if row:
            statistics.append(row)
    if not any(item.get("label") == "Goals" for item in statistics):
        row = _stat_row("Goals", home.get("goals"), away.get("goals"))
        if row:
            statistics.append(row)
    shot_rows = []
    if isinstance(shots, list):
        for shot in shots[:40]:
            if not isinstance(shot, dict):
                continue
            shot_rows.append(
                {
                    "period": shot.get("period"),
                    "x": shot.get("shotX"),
                    "y": shot.get("shotY"),
                    "player": names.get(str(shot.get("shooterId") or "")),
                    "type": shot.get("eventType") or shot.get("type"),
                }
            )
    lines = []
    for side in ("home", "away"):
        grouped: Dict[str, List[str]] = {}
        for player in players:
            if player.get("side") != side or player.get("line") in (None, ""):
                continue
            grouped.setdefault(str(player["line"]), []).append(player["name"])
        for line, group in grouped.items():
            lines.append({"side": side, "line": line, "players": group})
    out: Dict[str, Any] = {}
    if periods:
        out["periods"] = periods
    if incidents:
        out["incidents"] = [row for row in incidents if row.get("player") or row.get("minute") is not None]
    if statistics:
        out["statistics"] = statistics
    if players:
        out["player_statistics"] = players
    detail: Dict[str, Any] = {}
    if shot_rows:
        detail["shots"] = shot_rows
    if lines:
        detail["lines"] = lines
    goalies = [player["name"] for player in players if player.get("position") == "goalie"]
    if goalies:
        detail["goalies"] = goalies
    rink = game.get("iceRink")
    if isinstance(rink, dict) and rink.get("name"):
        out["venue"] = rink.get("name")
    elif isinstance(rink, str) and rink:
        out["venue"] = rink
    if detail:
        out["sport_detail"] = detail
    return out


def _clock(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value) // 60 if value > 180 else int(value)
    text = str(value)
    match = re.search(r"(\d+):(\d+)", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        number = int(text)
        return number // 60 if number > 180 else number
    return None


def _liiga_team_totals(stats: Any) -> Dict[str, Dict[str, Any]]:
    out = {"home": {}, "away": {}}
    if not isinstance(stats, dict):
        return out
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        rows = stats.get(key)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            continue
        goals = shots = pim = 0
        seen = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("goals") is not None:
                goals += int(row.get("goals") or 0)
                seen = True
            if row.get("shots") is not None:
                shots += int(row.get("shots") or 0)
                seen = True
            if row.get("penaltyMinutes") is not None:
                pim += int(row.get("penaltyMinutes") or 0)
                seen = True
        if seen:
            out[side] = {"goals": goals, "shots": shots, "penaltyMinutes": pim}
    return out


def parse_ibu_results(payload: Any, race_name: str = "") -> List[Dict[str, Any]]:
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("Results") or []
    elif isinstance(payload, list):
        rows = payload
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("Name") or row.get("ShortName")
        if not name:
            continue
        item = {
            "position": row.get("Rank"),
            "name": name,
            "nation": row.get("Nat"),
            "time": row.get("TotalTime") or row.get("Result"),
            "gap": row.get("Behind"),
            "shootings": row.get("Shootings"),
        }
        if row.get("IRM"):
            item["status"] = row.get("IRM")
        if race_name:
            item["race"] = race_name
        out.append({key: value for key, value in item.items() if value not in (None, "")})
    return out


def parse_world_aquatics(payload: Any) -> Dict[str, Any]:
    heats: List[Dict[str, Any]] = []
    _collect_heats(payload, heats, 0)
    classification = []
    for heat in heats:
        if not isinstance(heat, dict):
            continue
        label = heat.get("Name") or heat.get("Phase") or ""
        results = heat.get("Results") if isinstance(heat.get("Results"), list) else []
        for row in results:
            if not isinstance(row, dict):
                continue
            name = row.get("FullName") or row.get("Name")
            if not name:
                continue
            item = {
                "position": row.get("Rank") or row.get("HeatRank"),
                "name": name,
                "nation": row.get("NAT") or row.get("Nation"),
                "points": row.get("TotalPoints"),
                "time": row.get("Time") or row.get("Result"),
                "status": label or row.get("ResultStatus"),
            }
            if row.get("Lane") not in (None, ""):
                item["lane"] = row.get("Lane")
            classification.append({key: value for key, value in item.items() if value not in (None, "")})
            if len(classification) >= 80:
                break
        if len(classification) >= 80:
            break
    if not classification:
        return {}
    return {"classification": classification}


def _collect_heats(node: Any, found: List[Dict[str, Any]], depth: int) -> None:
    if depth > 7 or len(found) >= 20:
        return
    if isinstance(node, dict):
        heats = node.get("Heats")
        if isinstance(heats, list):
            for heat in heats:
                if isinstance(heat, dict):
                    found.append(heat)
                    if len(found) >= 20:
                        return
        for value in node.values():
            if isinstance(value, (dict, list)):
                _collect_heats(value, found, depth + 1)
    elif isinstance(node, list):
        for item in node[:30]:
            _collect_heats(item, found, depth + 1)


def parse_letour_rankings(html: str) -> Dict[str, Any]:
    rows = []
    for tr in re.findall(r"<tr class=\"rankingTables__row[\s\S]*?</tr>", html or "", re.I):
        cells = [_cell(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        if len(cells) < 3:
            continue
        name = ""
        alt = re.search(r'alt="([^"]+)"', tr)
        if alt:
            name = alt.group(1).strip()
        position = cells[0]
        if not name:
            continue
        item = {"position": position, "name": name}
        team = next((cell for cell in cells if re.search(r"[A-Za-z]", cell) and name not in cell and cell != name), "")
        if team:
            item["team"] = team
        times = [cell for cell in cells if re.search(r"\d:\d{2}", cell) or cell in {"-", "–"} or cell.startswith("+")]
        if times:
            item["time"] = times[0]
        if len(times) > 1:
            item["gap"] = times[1]
        points = [cell for cell in cells if cell.isdigit() and cell != position]
        if points:
            item["points"] = points[-1]
        rows.append({key: value for key, value in item.items() if value not in (None, "")})
    if not rows:
        return {}
    return {"classification": rows[:80]}


def parse_wec_summary(html: str) -> Dict[str, Any]:
    table = re.search(r"<table class=\"table table-sm table-standing[\s\S]*?</table>", html or "", re.I)
    if not table:
        return {}
    body = table.group(0)
    headers = [_cell(th).lower() for th in re.findall(r"<t[dh][^>]*>[\s\S]*?</t[dh]>", re.search(r"<thead[\s\S]*?</thead>", body, re.I).group(0) if re.search(r"<thead", body, re.I) else "")]
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", body, re.I):
        if "<th" in tr.lower() and "<td" not in tr.lower():
            continue
        cells = [_cell(td) for td in re.findall(r"<t[dh][^>]*>[\s\S]*?</t[dh]>", tr, re.I)]
        if not cells or not cells[0].rstrip(".").isdigit():
            continue
        indexed = {headers[i]: cells[i] for i in range(min(len(headers), len(cells))) if headers[i]}
        item = {
            "position": indexed.get("pos.") or cells[0],
            "car": indexed.get("n°") or indexed.get("nº") or indexed.get("no."),
            "name": indexed.get("team / drivers") or indexed.get("competitors"),
            "laps": indexed.get("laps"),
            "gap": indexed.get("gap"),
            "interval": indexed.get("interval"),
            "fastest_lap": indexed.get("best lap"),
        }
        if indexed.get("best lap number"):
            item["status"] = f"lap {indexed.get('best lap number')}"
        rows.append({key: value for key, value in item.items() if value not in (None, "")})
    if not rows:
        return {}
    return {"classification": rows[:60]}


def parse_gri_results(html: str) -> Dict[str, Any]:
    text = html or ""
    races = re.split(r"<h4[^>]*>", text, flags=re.I)
    classification = []
    for block in races[1:]:
        title = _cell(re.split(r"</h4>", block, maxsplit=1, flags=re.I)[0])
        race = ""
        title_match = re.search(r"Race\s+(\d+)", title, re.I)
        if title_match:
            race = title_match.group(1)
        grade = ""
        grade_match = re.search(r"Grade\s*:\s*([A-Z0-9]+)", title, re.I)
        if grade_match:
            grade = grade_match.group(1)
        for tr in re.findall(r"<tr[\s\S]*?</tr>", block, re.I):
            cells = [_cell(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
            cells = [cell for cell in cells if cell and cell not in {"|"}]
            if len(cells) < 4:
                continue
            position = cells[0].rstrip(".")
            if not position.isdigit():
                continue
            name = next((cell for cell in cells[1:] if re.search(r"[A-Za-z]{3}", cell) and not re.search(r"^\d", cell)), "")
            if not name or name.lower() in {"pos.", "trap", "greyhound"}:
                continue
            item = {"position": position, "name": name, "race": race}
            if grade:
                item["category"] = grade
            times = [cell for cell in cells if re.search(r"^\d{2}\.\d{2}$", cell)]
            if times:
                item["time"] = times[0]
            weights = [cell for cell in cells if re.fullmatch(r"\d{2}", cell)]
            if weights:
                item["weight"] = weights[0]
            prices = [cell for cell in cells if "/" in cell and re.search(r"\d", cell)]
            if prices:
                item["points"] = prices[0]
            comments = [cell for cell in cells if re.search(r"[A-Za-z]{2}", cell) and cell != name and "grade" not in cell.lower()]
            if comments:
                item["status"] = comments[-1][:80]
            classification.append({key: value for key, value in item.items() if value not in (None, "")})
    if not classification:
        return {}
    return {"classification": classification[:80]}


def parse_letrot_race(html: str) -> Dict[str, Any]:
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_cell(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        names = [cell for cell in cells if re.search(r"[A-Za-z]{3}", cell) and cell.upper() == cell and " " in cell]
        if not names:
            names = [cell for cell in cells if re.search(r"[A-Z]{2,}\s+[A-Z]{2,}", cell)]
        if not names:
            continue
        item = {"name": names[0].title() if names[0].isupper() else names[0]}
        times = [cell for cell in cells if re.search(r"\d['′]\d{2}|\d:\d{2}", cell)]
        if times:
            item["time"] = times[0]
            placing = next((cell for cell in cells if re.fullmatch(r"[1-9]|1\d|20", cell)), "")
            if placing:
                item["position"] = placing
        rows.append(item)
    if not rows:
        return {}
    return {"classification": rows[:20], "runners": rows[:20]}


def parse_altius_match(html: str) -> Dict[str, Any]:
    text = (html or "").replace("&quot;", '"').replace("&amp;", "&")
    people = _altius_people(text)
    events = _json_array_after(text, "events")
    incidents = []
    officials = []
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = str(event.get("event") or "").lower()
        minute = None
        try:
            minute = int(float(event.get("seconds") or 0) // 60)
        except (TypeError, ValueError):
            minute = None
        player = people.get(str(event.get("player_id") or ""))
        if kind == "goal":
            incidents.append(
                {
                    "minute": minute,
                    "player": player,
                    "family": "goal",
                    "type": _GOAL_TYPE.get(str(event.get("type") or ""), str(event.get("type") or "goal")),
                }
            )
        elif kind == "card":
            incidents.append(
                {
                    "minute": minute,
                    "player": player,
                    "family": "card",
                    "type": _CARD_TYPE.get(str(event.get("type") or ""), str(event.get("type") or "card")),
                }
            )
        elif "shoot" in kind:
            incidents.append({"minute": minute, "player": player, "family": "shootout", "type": kind})
    for official in _json_array_after(text, "officials"):
        if isinstance(official, dict):
            name = official.get("name") or official.get("display_name")
            if name:
                officials.append(str(name))
        elif isinstance(official, str):
            officials.append(official)
    incidents = [row for row in incidents if row.get("player") or row.get("type")]
    if not incidents and not officials:
        return {}
    out: Dict[str, Any] = {}
    if incidents:
        out["incidents"] = incidents
    if officials:
        out["officials"] = officials
        out["referee"] = officials[0]
    return out


def _altius_people(text: str) -> Dict[str, str]:
    people = {}
    for match in re.finditer(r"\{[^{}]{0,500}shirtnumber[^{}]{0,300}\}", text, re.I):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        pid = obj.get("id") or obj.get("player_id")
        name = obj.get("name") or obj.get("display_name") or obj.get("fullname")
        if pid and name:
            people[str(pid)] = str(name)
    return people


def _json_array_after(text: str, key: str) -> list:
    token = f'"{key}":'
    start = text.find(token)
    if start < 0:
        return []
    bracket = text.find("[", start)
    if bracket < 0 or bracket - start > 40:
        return []
    depth = 0
    in_str = False
    esc = False
    for index in range(bracket, min(len(text), bracket + 400000)):
        ch = text[index]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[bracket : index + 1])
                except json.JSONDecodeError:
                    return []
                return parsed if isinstance(parsed, list) else []
    return []


def _cell(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip(" |")


def ensure_rich_source_ids(row, extra: Dict[str, Any]) -> None:
    competition = str(getattr(row, "competition_id", "") or "")
    ids = extra.get("source_event_ids") if isinstance(extra.get("source_event_ids"), dict) else {}
    wanted = _wanted_family(competition)
    if not wanted:
        return
    if ids.get(wanted):
        return
    if _checked(extra):
        return
    try:
        source_id = _resolve(competition, row, extra)
    except Exception:
        source_id = ""
    if source_id:
        _store(extra, wanted, source_id)
        extra.pop("rich_id_checked_at", None)
    else:
        _mark_checked(extra)


def _wanted_family(competition: str) -> str:
    return {
        "nrl": "championdata-netball",
        "ssn-australia": "championdata-netball",
        "finland-liiga": "liiga-web",
        "biathlon": "ibu-web",
        "tour-de-france": "letour-web",
        "wec": "fiawec-web",
        "fih-eurohockey": "altiusrt-html",
        "ireland-gri-meetings": "gri-web",
        "irish-greyhound-derby": "gri-web",
        "france-letrot-meetings": "letrot-web",
        "world-aquatics-events": "world-aquatics-api",
        "world-aquatics-meets": "world-aquatics-api",
    }.get(competition, "")


def _resolve(competition: str, row, extra: Dict[str, Any]) -> str:
    if competition in {"nrl", "ssn-australia"}:
        return _resolve_champion(competition, row)
    if competition == "finland-liiga":
        return _resolve_liiga(row)
    if competition == "biathlon":
        return str(extra.get("source_event_id") or "")
    if competition == "tour-de-france":
        return _stage_number(row, extra)
    if competition == "wec":
        return _resolve_wec(row)
    if competition == "fih-eurohockey":
        return _resolve_altius(row)
    if competition in {"ireland-gri-meetings", "irish-greyhound-derby"}:
        return _resolve_gri(row)
    if competition == "france-letrot-meetings":
        return _resolve_letrot(row, extra)
    if competition in {"world-aquatics-events", "world-aquatics-meets"}:
        return _resolve_aquatics(row)
    return ""


def _stage_number(row, extra: Dict[str, Any]) -> str:
    stage = str(extra.get("stage") or "")
    if stage.isdigit():
        return stage
    home, away = _sides(row)
    match = re.search(r"stage\s+(\d+)", f"{home} {away}", re.I)
    return match.group(1) if match else ""


def _resolve_champion(competition: str, row) -> str:
    payload = _memo("cd-comps", 1800, lambda: _json(CD_COMPS) or {})
    rows = ((payload.get("competitionDetails") or {}).get("competition") or []) if isinstance(payload, dict) else []
    pattern = r"nrl premiership" if competition == "nrl" else r"super netball"
    hits = [
        item
        for item in rows
        if isinstance(item, dict)
        and re.search(pattern, str(item.get("name") or ""), re.I)
        and not re.search(r"women|nrlw|final", str(item.get("name") or ""), re.I)
    ]
    if not hits:
        return ""
    comp = sorted(hits, key=lambda item: int(item.get("id") or 0))[-1]
    comp_id = comp.get("id")
    fixture = _memo(f"cd-fix-{comp_id}", 900, lambda: _json(CD_FIXTURE.format(comp_id=comp_id)) or {})
    matches = (((fixture.get("fixture") or {}).get("match")) if isinstance(fixture, dict) else None) or []
    home, away = _sides(row)
    day = _day(row)
    for match in matches:
        if not isinstance(match, dict):
            continue
        if not _pair_match(home, away, str(match.get("homeSquadName") or ""), str(match.get("awaySquadName") or "")):
            continue
        start = str(match.get("localStartTime") or match.get("startTime") or "")
        if day and start and day not in start[:10] and not _same_day(day, start):
            continue
        match_id = match.get("matchId") or match.get("id")
        if match_id:
            return f"{comp_id}:{match_id}"
    return ""


def _same_day(day: str, raw: str) -> bool:
    return day[:10] == raw[:10]


def _resolve_liiga(row) -> str:
    day = _day(row)
    if not day:
        return ""
    year = int(day[:4])
    month = int(day[5:7])
    season = year + 1 if month >= 7 else year
    games = _memo(f"liiga-{season}", 900, lambda: _json(LIIGA_GAMES.format(season=season)) or [])
    if not isinstance(games, list):
        return ""
    home, away = _sides(row)
    for game in games:
        if not isinstance(game, dict):
            continue
        start = str(game.get("start") or "")
        if day not in start:
            continue
        ht = (game.get("homeTeam") or {}).get("teamName")
        at = (game.get("awayTeam") or {}).get("teamName")
        if _pair_match(home, away, str(ht or ""), str(at or "")):
            return f"{season}:{game.get('id')}"
    return ""


def _resolve_wec(row) -> str:
    html = _memo("wec-home", 1800, lambda: _text(WEC_HOME))
    home, away = _sides(row)
    for match in re.finditer(r'href="(/en/race/summary/(\d+))"[^>]*>([\s\S]{0,180})</a>', html or "", re.I):
        label = _cell(match.group(3))
        if _names_match(home, label) or _names_match(away, label):
            return match.group(2)
    return ""


def _resolve_altius(row) -> str:
    html = _memo("altius-matches", 900, lambda: _text(ALTIUS_MATCHES))
    home, away = _sides(row)
    for block in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        link = re.search(r"/matches/(\d+)", block)
        codes = re.findall(r"\b([A-Z]{3})\b", _cell(block))
        if not link or len(codes) < 2:
            continue
        if _pair_match(home, away, codes[0], codes[1]):
            return link.group(1)
    return ""


def _resolve_gri(row) -> str:
    day = _day(row)
    home, _away = _sides(row)
    html = _memo("gri-index", 1800, lambda: _text(GRI_INDEX))
    stamp = _gri_stamp(day)
    for date, track in re.findall(r"view-results/\?date=([0-9]{1,2}-[A-Za-z]{3}-\d{2})&track=([A-Za-z0-9]+)", html or ""):
        window = html[max(0, html.find(date) - 200): html.find(date) + 200]
        if stamp and date.lower() == stamp.lower() and (not home or _names_match(home, window) or home.lower() in window.lower()):
            return f"{date}|{track}"
    if "shelbourne" in home.lower() and stamp:
        return f"{stamp}|SPK"
    return ""


def _gri_stamp(day: str) -> str:
    if len(day) < 10:
        return ""
    try:
        year = int(day[:4])
        month = int(day[5:7])
        date = int(day[8:10])
    except ValueError:
        return ""
    return f"{date:02d}-{_MONTHS[month - 1]}-{year % 100:02d}"


def _resolve_letrot(row, extra: Dict[str, Any]) -> str:
    home, away = _sides(row)
    if "vincennes" not in f"{home} {away}".lower():
        return ""
    day = _day(row)
    race = str(extra.get("race_number") or "")
    if not race:
        match = re.search(r"race\s+(\d+)", f"{home} {away}", re.I)
        race = match.group(1) if match else ""
    if not day or not race:
        return ""
    return f"{day}/7500/{race}"


def _resolve_aquatics(row) -> str:
    home, _away = _sides(row)
    payload = _memo("wa-comps", 1800, lambda: _json(WA_COMPS) or {})
    content = payload.get("content") if isinstance(payload, dict) else []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name and (_names_match(home, name) or _names_match(name, home)):
            return str(item.get("id") or "")
    return ""


def fetch_rich_family(family: str, source_event_id: str) -> Dict[str, Any]:
    sid = str(source_event_id or "")
    if family == "liiga-web" and ":" in sid:
        season, game_id = sid.split(":", 1)
        detail = _json(LIIGA_GAME.format(season=season, game_id=game_id)) or {}
        stats = _json(LIIGA_STATS.format(season=season, game_id=game_id)) or {}
        shots = _json(LIIGA_SHOTS.format(season=season, game_id=game_id)) or []
        return parse_liiga_bundle(detail, stats, shots)
    if family == "ibu-web" and sid:
        comps = _json(IBU.format(path=f"Competitions?EventId={sid}"))
        races = comps if isinstance(comps, list) else []
        official = [race for race in races if str(race.get("ResultStatus") or "").upper() == "OFFICIAL"]
        chosen = (official or races)[:3]
        rows = []
        for race in chosen:
            if not isinstance(race, dict) or not race.get("RaceId"):
                continue
            payload = _json(IBU.format(path=f"Results?RaceId={race.get('RaceId')}"))
            rows.extend(parse_ibu_results(payload, str(race.get("Description") or "")))
        if not rows:
            return {}
        return {"classification": rows[:80]}
    if family == "letour-web" and sid.isdigit():
        parsed = parse_letour_rankings(_text(LETOUR.format(stage=sid)))
        if parsed:
            return parsed
        return parse_letour_rankings(_text(LETOUR_WEBVIEW.format(stage=sid)))
    if family == "fiawec-web" and sid.isdigit():
        return parse_wec_summary(_text(WEC_SUMMARY.format(race_id=sid)))
    if family == "altiusrt-html" and sid.isdigit():
        return parse_altius_match(_text(ALTIUS_MATCH.format(match_id=sid)))
    if family == "gri-web" and "|" in sid:
        date, track = sid.split("|", 1)
        return parse_gri_results(_text(GRI_MEETING.format(date=date, track=track)))
    if family == "letrot-web" and sid.count("/") == 2:
        date, track, race = sid.split("/")
        return parse_letrot_race(_text(LETROT.format(date=date, track=track, race=race)))
    if family == "world-aquatics-api" and sid.isdigit():
        return parse_world_aquatics(_json(WA_EVENTS.format(comp_id=sid)) or {})
    return {}
