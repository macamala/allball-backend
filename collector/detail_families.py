"""On-demand detail parsers for reusable families outside FotMob/MLB/NHL."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector.adapters import FetchResult
from collector.http import fetch_url

RUGBY_STATS = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}/stats"
RUGBY_MATCH = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}"
RUGBY_SUMMARY = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}/summary"
CFL_ROUNDS = "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"
LOL_EVENT = "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={event_id}"
LOL_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
JOLPICA_RESULTS = "https://api.jolpi.ca/ergast/f1/{season}/{round}/results.json"
OPENDOTA_MATCH = "https://api.opendota.com/api/matches/{match_id}"
SQUIGGLE_GAME = "https://api.squiggle.com.au/?q=games;game={game_id}"
EUROLEAGUE_BOX = "https://live.euroleague.net/api/Boxscore?gamecode={code}&seasoncode={season}"
EUROLEAGUE_HEADER = "https://live.euroleague.net/api/Header?gamecode={code}&seasoncode={season}"
OPENLIGA_MATCH = "https://api.openligadb.de/getmatchbyid/{match_id}"
CD_MATCH = "https://mc.championdata.com/data/{comp_id}/{match_id}.json"
CLICK_TT_LIVE = "https://www.mytischtennis.de/api/meeting/{meeting_id}/live"


def _get(getter, url: str, headers: Optional[Dict[str, str]] = None) -> FetchResult:
    try:
        if headers:
            return getter(url, headers=headers)
        return getter(url)
    except TypeError:
        return getter(url)


def parse_rugby_detail(match: Dict[str, Any], stats: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    venue = ((match.get("venue") or {}) if isinstance(match.get("venue"), dict) else {})
    if venue.get("name"):
        out["venue"] = venue.get("name")
    if match.get("attendance") not in (None, ""):
        out["attendance"] = match.get("attendance")
    officials = summary.get("officials") if isinstance(summary, dict) else []
    names = []
    for item in officials or []:
        off = (item or {}).get("official") if isinstance(item, dict) else {}
        name = ((off.get("name") or {}).get("display") if isinstance(off.get("name"), dict) else None)
        if name:
            names.append(name)
    if names:
        out["referee"] = names[0]
    team_stats = stats.get("teamStats") if isinstance(stats, dict) else []
    if isinstance(team_stats, list) and len(team_stats) >= 2:
        home_s = (team_stats[0] or {}).get("stats") if isinstance(team_stats[0], dict) else {}
        away_s = (team_stats[1] or {}).get("stats") if isinstance(team_stats[1], dict) else {}
        rows = []
        keys = sorted(set(home_s or {}) | set(away_s or {}))
        for key in keys:
            rows.append({"label": key, "home": (home_s or {}).get(key), "away": (away_s or {}).get(key)})
        if rows:
            out["statistics"] = rows
        players = []
        for side_name, blob in (("home", team_stats[0]), ("away", team_stats[1])):
            for item in (blob or {}).get("playerStats") or []:
                player = (item or {}).get("player") if isinstance(item, dict) else {}
                name = ((player.get("name") or {}).get("display") if isinstance(player.get("name"), dict) else None)
                if not name:
                    continue
                ps = (item or {}).get("stats") if isinstance((item or {}).get("stats"), dict) else {}
                players.append({"name": name, "side": side_name, "tries": ps.get("Tries"), "points": ps.get("Points")})
        if players:
            out["player_statistics"] = players
            out["lineups"] = {
                "home": {"start": [p for p in players if p["side"] == "home"], "bench": [], "formation": None, "coach": None},
                "away": {"start": [p for p in players if p["side"] == "away"], "bench": [], "formation": None, "coach": None},
            }
    teams = summary.get("teams") if isinstance(summary, dict) else []
    timeline = []
    if isinstance(teams, list):
        for index, team in enumerate(teams):
            side = "home" if index == 0 else "away"
            scoring = team.get("scoring") if isinstance(team, dict) else {}
            for try_row in (scoring.get("tries") if isinstance(scoring, dict) else []) or []:
                if not isinstance(try_row, dict):
                    continue
                player = ((try_row.get("player") or {}).get("name") or {})
                name = player.get("display") if isinstance(player, dict) else None
                timeline.append({"type": "try", "player": name, "minute": try_row.get("time"), "side": side})
            for card in (team.get("disciplinary") or []) if isinstance(team, dict) else []:
                if not isinstance(card, dict):
                    continue
                player = ((card.get("player") or {}).get("name") or {})
                name = player.get("display") if isinstance(player, dict) else None
                timeline.append({"type": str(card.get("type") or "card").lower(), "player": name, "minute": card.get("time"), "side": side})
    if timeline:
        out["incidents"] = timeline
    if isinstance(team_stats, list) and len(team_stats) >= 2:
        home_s = (team_stats[0] or {}).get("stats") if isinstance(team_stats[0], dict) else {}
        away_s = (team_stats[1] or {}).get("stats") if isinstance(team_stats[1], dict) else {}
        if (home_s or {}).get("Tries") is not None or (away_s or {}).get("Tries") is not None:
            out["sport_detail"] = {
                "tries": {"home": (home_s or {}).get("Tries"), "away": (away_s or {}).get("Tries")},
                "conversions": {"home": (home_s or {}).get("Conversions"), "away": (away_s or {}).get("Conversions")},
            }
    return out


def parse_jolpica_results(payload: Any) -> Dict[str, Any]:
    races = (((payload or {}).get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if not races:
        return {}
    race = races[0]
    results = race.get("Results") or []
    board = []
    for row in results:
        driver = row.get("Driver") or {}
        name = " ".join(part for part in (driver.get("givenName"), driver.get("familyName")) if part)
        board.append(
            {
                "position": row.get("position"),
                "name": name,
                "status": row.get("status"),
                "gap": (row.get("Time") or {}).get("time"),
                "fastest_lap": ((row.get("FastestLap") or {}).get("Time") or {}).get("time"),
                "grid": row.get("grid"),
                "points": row.get("points"),
            }
        )
    out: Dict[str, Any] = {}
    if board:
        out["classification"] = board
        out["sport_detail"] = {"session": "race", "circuit": ((race.get("Circuit") or {}).get("circuitName"))}
        out["venue"] = ((race.get("Circuit") or {}).get("circuitName"))
    return out


def parse_squiggle_game(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if row.get("hgoals") is not None or row.get("agoals") is not None:
        out["periods"] = [
            {"label": "G", "home": row.get("hgoals"), "away": row.get("agoals")},
            {"label": "B", "home": row.get("hbehinds"), "away": row.get("abehinds")},
        ]
        out["statistics"] = [
            {"label": "Goals", "home": row.get("hgoals"), "away": row.get("agoals")},
            {"label": "Behinds", "home": row.get("hbehinds"), "away": row.get("abehinds")},
            {"label": "Score", "home": row.get("hscore"), "away": row.get("ascore")},
        ]
        out["sport_detail"] = {"goals": {"home": row.get("hgoals"), "away": row.get("agoals")}, "behinds": {"home": row.get("hbehinds"), "away": row.get("abehinds")}}
    if row.get("venue"):
        out["venue"] = row.get("venue")
    return out


def parse_opendota_match(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    players = []
    for item in payload.get("players") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("personaname") or item.get("name") or str(item.get("account_id") or "")
        players.append(
            {
                "name": name,
                "side": "home" if item.get("isRadiant") else "away",
                "kills": item.get("kills"),
                "deaths": item.get("deaths"),
                "assists": item.get("assists"),
                "hero": item.get("hero_id"),
            }
        )
    if players:
        out["player_statistics"] = players
        out["lineups"] = {
            "home": {"start": [p for p in players if p["side"] == "home"], "bench": [], "formation": None, "coach": None},
            "away": {"start": [p for p in players if p["side"] == "away"], "bench": [], "formation": None, "coach": None},
        }
    duration = payload.get("duration")
    if duration:
        out["sport_detail"] = {"duration": duration, "radiant_win": payload.get("radiant_win")}
    return out


def parse_euroleague_box(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    stats = []
    home = payload.get("HomeTeam") or payload.get("home") or {}
    away = payload.get("AwayTeam") or payload.get("away") or {}
    for key, label in (("Score", "Points"), ("FieldGoalsMade", "FG made"), ("ThreePointersMade", "3PT"), ("FreeThrowsMade", "FT"), ("TotalRebounds", "Rebounds"), ("Assistances", "Assists"), ("Turnovers", "Turnovers"), ("Steals", "Steals"), ("Blocks", "Blocks"), ("FoulsCommited", "Fouls")):
        hv = home.get(key) if isinstance(home, dict) else None
        av = away.get(key) if isinstance(away, dict) else None
        if hv is not None or av is not None:
            stats.append({"label": label, "home": hv, "away": av})
    if stats:
        out["statistics"] = stats
    players = []
    for side_name, blob in (("home", home), ("away", away)):
        for item in (blob.get("Players") if isinstance(blob, dict) else []) or []:
            if not isinstance(item, dict):
                continue
            name = item.get("Player") or item.get("name")
            if not name:
                continue
            players.append({"name": name, "side": side_name, "points": item.get("Points") or item.get("points"), "rebounds": item.get("TotalRebounds"), "assists": item.get("Assistances")})
    if players:
        out["player_statistics"] = players
        out["lineups"] = {
            "home": {"start": [p for p in players if p["side"] == "home"], "bench": [], "formation": None, "coach": None},
            "away": {"start": [p for p in players if p["side"] == "away"], "bench": [], "formation": None, "coach": None},
        }
    return out


def parse_lol_event(payload: Any) -> Dict[str, Any]:
    data = (payload or {}).get("data") if isinstance(payload, dict) else {}
    event = (data or {}).get("event") or {}
    match = event.get("match") or {}
    games = match.get("games") or []
    maps = []
    for index, game in enumerate(games):
        if not isinstance(game, dict):
            continue
        teams = game.get("teams") or []
        home = teams[0] if teams else {}
        away = teams[1] if len(teams) > 1 else {}
        maps.append(
            {
                "name": game.get("number") or index + 1,
                "home": (home.get("result") or {}).get("gameWins") if isinstance(home, dict) else None,
                "away": (away.get("result") or {}).get("gameWins") if isinstance(away, dict) else None,
                "map": (game.get("vod") or {}).get("parameter") if isinstance(game.get("vod"), dict) else None,
            }
        )
    out: Dict[str, Any] = {}
    if maps:
        out["maps"] = maps
        out["sport_detail"] = {"best_of": match.get("strategy", {}).get("count") if isinstance(match.get("strategy"), dict) else None}
    return out


def parse_cfl_game(game: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    periods = []
    for key in ("quarters", "periods", "scoresByQuarter"):
        raw = game.get(key)
        if isinstance(raw, list):
            for index, item in enumerate(raw):
                if isinstance(item, dict):
                    periods.append({"label": item.get("number") or index + 1, "home": item.get("home") or item.get("homeScore"), "away": item.get("away") or item.get("awayScore")})
                elif isinstance(item, (int, float)):
                    periods.append({"label": index + 1, "home": item, "away": None})
    if periods:
        out["periods"] = periods
    home = game.get("homeSquad") or game.get("home") or {}
    away = game.get("awaySquad") or game.get("away") or {}
    stats = []
    for label, hk, ak in (("Yards", "yards", "yards"), ("Pass yards", "passYards", "passYards"), ("Rush yards", "rushYards", "rushYards")):
        hv = home.get(hk) if isinstance(home, dict) else None
        av = away.get(ak) if isinstance(away, dict) else None
        if hv is not None or av is not None:
            stats.append({"label": label, "home": hv, "away": av})
    if stats:
        out["statistics"] = stats
    return out


def parse_openliga_match(match: Dict[str, Any]) -> Dict[str, Any]:
    from collector.enrichment import incidents_from_openliga_goals, periods_from_openliga_results

    if not isinstance(match, dict):
        return {}
    out: Dict[str, Any] = {}
    incidents = incidents_from_openliga_goals(match)
    if incidents:
        out["incidents"] = incidents
    periods = periods_from_openliga_results(match)
    if periods:
        out["periods"] = periods
    loc = match.get("location") if isinstance(match.get("location"), dict) else {}
    if loc.get("locationStadium"):
        out["venue"] = loc.get("locationStadium")
    if match.get("numberOfViewers") not in (None, ""):
        out["attendance"] = match.get("numberOfViewers")
    return out


def parse_championdata_match(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    match = row.get("match") if isinstance(row.get("match"), dict) else row
    out: Dict[str, Any] = {}
    periods = []
    for index in range(1, 5):
        home_q = match.get(f"homeSquadScoreQ{index}") or match.get(f"homePeriod{index}")
        away_q = match.get(f"awaySquadScoreQ{index}") or match.get(f"awayPeriod{index}")
        if home_q is not None or away_q is not None:
            periods.append({"label": index, "home": home_q, "away": away_q})
    blob = match.get("periodScores") or match.get("scoresByPeriod")
    if not periods and isinstance(blob, list):
        for index, item in enumerate(blob):
            if isinstance(item, dict):
                periods.append({"label": item.get("period") or index + 1, "home": item.get("home"), "away": item.get("away")})
    if periods:
        out["periods"] = periods
    stats = []
    for label, key in (("Goals", "goals"), ("Goal attempts", "goalAttempts"), ("Turnovers", "turnovers"), ("Intercepts", "intercepts")):
        home_v = match.get(f"homeSquad{key[0].upper()}{key[1:]}") or match.get(f"home{key}")
        away_v = match.get(f"awaySquad{key[0].upper()}{key[1:]}") or match.get(f"away{key}")
        if home_v is not None or away_v is not None:
            stats.append({"label": label, "home": home_v, "away": away_v})
    if stats:
        out["statistics"] = stats
    players = []
    for item in match.get("player") or match.get("players") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("displayName") or item.get("firstname") or item.get("name")
        if not name:
            continue
        players.append({"name": name, "side": "home" if str(item.get("squadId") or "") == str(match.get("homeSquadId") or "") else "away", "points": item.get("goals") or item.get("points")})
    if players:
        out["player_statistics"] = players
    return out


def parse_clicktt_live(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {}
    rows = data.get("matches") or data.get("einzel") or data.get("games") or []
    periods = []
    if isinstance(rows, list):
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            home = item.get("sets_home") or item.get("matches_home") or item.get("home")
            away = item.get("sets_guest") or item.get("matches_guest") or item.get("away")
            if home is None and away is None:
                continue
            periods.append({"label": index + 1, "home": home, "away": away})
    if periods:
        out["periods"] = periods
        out["sport_detail"] = {"current_set": data.get("current_match") or data.get("current")}
    return out


def fetch_extra_family_detail(family: str, source_event_id: str, getter=None) -> Dict[str, Any]:
    getter = getter or fetch_url
    family = (family or "").lower()
    sid = str(source_event_id or "").replace("worldrugby:", "").replace("cfl:", "").replace("lolesports:", "").replace("jolpica:", "").replace("squiggle:", "").replace("euroleague:", "").replace("pga:", "")
    if family in {"pulselive", "pulselive-family", "world-rugby-rims"}:
        match = _get(getter, RUGBY_MATCH.format(match_id=sid))
        stats = _get(getter, RUGBY_STATS.format(match_id=sid))
        summary = _get(getter, RUGBY_SUMMARY.format(match_id=sid))
        return parse_rugby_detail(
            match.payload if match.ok and isinstance(match.payload, dict) else {},
            stats.payload if stats.ok and isinstance(stats.payload, dict) else {},
            summary.payload if summary.ok and isinstance(summary.payload, dict) else {},
        )
    if family in {"cfl-scoreboard-json", "cfl"}:
        result = _get(getter, CFL_ROUNDS)
        payload = result.payload if result.ok else None
        rows = payload.get("rounds") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            for round_row in rows:
                games = (round_row or {}).get("tournaments") or (round_row or {}).get("games") or []
                for game in games:
                    if not isinstance(game, dict):
                        continue
                    gid = str(game.get("id") or game.get("gameId") or "")
                    if gid == sid:
                        return parse_cfl_game(game)
        return {}
    if family in {"lolesports-json", "lolesports"}:
        result = _get(getter, LOL_EVENT.format(event_id=sid), headers={"x-api-key": LOL_KEY})
        if result.ok and isinstance(result.payload, dict):
            return parse_lol_event(result.payload)
        return {}
    if family in {"jolpica-f1", "jolpica"}:
        parts = sid.split(":")
        season = parts[0] if parts else ""
        rnd = parts[1] if len(parts) > 1 else parts[0]
        result = _get(getter, JOLPICA_RESULTS.format(season=season, round=rnd))
        if result.ok and isinstance(result.payload, dict):
            return parse_jolpica_results(result.payload)
        return {}
    if family in {"squiggle-afl", "squiggle"}:
        result = _get(getter, SQUIGGLE_GAME.format(game_id=sid))
        games = (result.payload or {}).get("games") if result.ok and isinstance(result.payload, dict) else []
        if games:
            return parse_squiggle_game(games[0] if isinstance(games[0], dict) else {})
        return {}
    if family in {"opendota"}:
        result = _get(getter, OPENDOTA_MATCH.format(match_id=sid))
        if result.ok and isinstance(result.payload, dict):
            return parse_opendota_match(result.payload)
        return {}
    if family in {"euroleague-live", "euroleague"}:
        parts = sid.split(":")
        season = parts[0] if len(parts) > 1 else "E2025"
        code = parts[-1]
        box = _get(getter, EUROLEAGUE_BOX.format(code=code, season=season))
        if box.ok and isinstance(box.payload, dict):
            return parse_euroleague_box(box.payload)
        header = _get(getter, EUROLEAGUE_HEADER.format(code=code, season=season))
        if header.ok and isinstance(header.payload, dict):
            return parse_euroleague_box(header.payload)
        return {}
    if family in {"openligadb"}:
        result = _get(getter, OPENLIGA_MATCH.format(match_id=sid.split(":")[-1]))
        payload = result.payload if result.ok else None
        if isinstance(payload, dict):
            return parse_openliga_match(payload)
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return parse_openliga_match(payload[0])
        return {}
    if family in {"championdata-netball", "championdata"}:
        parts = sid.split(":")
        comp_id = parts[0] if len(parts) > 1 else ""
        match_id = parts[-1]
        if not comp_id or not match_id:
            return {}
        result = _get(getter, CD_MATCH.format(comp_id=comp_id, match_id=match_id))
        if result.ok and isinstance(result.payload, dict):
            return parse_championdata_match(result.payload)
        return {}
    if family in {"click-tt-remix", "click-tt"}:
        result = _get(getter, CLICK_TT_LIVE.format(meeting_id=sid.split(":")[-1]))
        if result.ok and isinstance(result.payload, dict):
            return parse_clicktt_live(result.payload)
        return {}
    return {}
