"""On-demand detail parsers for reusable families outside FotMob/MLB/NHL."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector.adapters import FetchResult
from collector.http import fetch_text, fetch_url

RUGBY_STATS = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}/stats"
RUGBY_MATCH = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}"
RUGBY_SUMMARY = "https://api.wr-rims-prod.pulselive.com/rugby/v3/match/{match_id}/summary"
CFL_ROUNDS = "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"
LOL_EVENT = "https://esports-api.lolesports.com/persisted/gw/getEventDetails?hl=en-US&id={event_id}"
LOL_LEAGUES = "https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US"
LOL_SCHEDULE = "https://esports-api.lolesports.com/persisted/gw/getSchedule?hl=en-US&leagueId={league_id}"
LOL_WINDOW = "https://feed.lolesports.com/livestats/v1/window/{game_id}?startingTime={starting_time}"
LOL_WINDOW_OPEN = "https://feed.lolesports.com/livestats/v1/window/{game_id}"
LOL_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"
JOLPICA_RESULTS = "https://api.jolpi.ca/ergast/f1/{season}/{round}/results.json"
OPENDOTA_MATCH = "https://api.opendota.com/api/matches/{match_id}"
OPENDOTA_HEROES = "https://api.opendota.com/api/constants/heroes"
SQUIGGLE_GAME = "https://api.squiggle.com.au/?q=games&game={game_id}"
EUROLEAGUE_BOX = "https://live.euroleague.net/api/Boxscore?gamecode={code}&seasoncode={season}"
EUROLEAGUE_HEADER = "https://live.euroleague.net/api/Header?gamecode={code}&seasoncode={season}"
OPENLIGA_MATCH = "https://api.openligadb.de/getmatchbyid/{match_id}"
CD_MATCH = "https://mc.championdata.com/data/{comp_id}/{match_id}.json"
CLICK_TT_LIVE = "https://www.mytischtennis.de/api/meeting/{meeting_id}/live"
BBC_CRICKET_DAY = "https://www.bbc.com/sport/cricket/scores-fixtures/{date}"
BBC_CRICKET_TODAY = "https://www.bbc.com/sport/cricket/scores-fixtures"

_OPENDOTA_HERO_CACHE: Dict[str, Any] = {}


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
                "penalties": {"home": (home_s or {}).get("PenaltyGoals") or (home_s or {}).get("Penalties"), "away": (away_s or {}).get("PenaltyGoals") or (away_s or {}).get("Penalties")},
            }
    scores = match.get("scores")
    if isinstance(scores, list) and scores and isinstance(scores[0], (list, tuple)):
        periods = []
        for index, pair in enumerate(scores, start=1):
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            periods.append({"label": index, "home": pair[0], "away": pair[1]})
        if periods:
            out["periods"] = periods
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
    goals = {"home": row.get("hgoals"), "away": row.get("agoals")}
    behinds = {"home": row.get("hbehinds"), "away": row.get("abehinds")}
    score = {"home": row.get("hscore"), "away": row.get("ascore")}
    if goals["home"] is not None or goals["away"] is not None:
        out["periods"] = [
            {"label": "G", "home": goals["home"], "away": goals["away"]},
            {"label": "B", "home": behinds["home"], "away": behinds["away"]},
        ]
        out["statistics"] = [
            {"label": "Goals", "home": goals["home"], "away": goals["away"]},
            {"label": "Behinds", "home": behinds["home"], "away": behinds["away"]},
            {"label": "Score", "home": score["home"], "away": score["away"]},
        ]
        detail = {"goals": goals, "behinds": behinds, "score": score}
        if row.get("venue"):
            detail["venue"] = row.get("venue")
        round_name = row.get("roundname") or row.get("round")
        if round_name and not str(round_name).isdigit():
            detail["round"] = round_name
        out["sport_detail"] = detail
    if row.get("venue"):
        out["venue"] = row.get("venue")
    if row.get("roundname"):
        out["round"] = row.get("roundname")
    return out


def _opendota_heroes(getter) -> Dict[str, Any]:
    global _OPENDOTA_HERO_CACHE
    if _OPENDOTA_HERO_CACHE:
        return _OPENDOTA_HERO_CACHE
    result = _get(getter, OPENDOTA_HEROES)
    if result.ok and isinstance(result.payload, dict):
        _OPENDOTA_HERO_CACHE = result.payload
    return _OPENDOTA_HERO_CACHE


def parse_opendota_match(payload: Any, heroes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    hero_map = heroes if isinstance(heroes, dict) else {}
    players = []
    for item in payload.get("players") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("personaname") or item.get("name") or str(item.get("account_id") or "")
        hero_id = item.get("hero_id")
        hero = hero_map.get(str(hero_id)) if hero_id not in (None, "") else None
        hero = hero if isinstance(hero, dict) else {}
        hero_name = hero.get("localized_name") or hero.get("name") or hero_id
        hero_image = hero.get("img") or hero.get("icon")
        if hero_image and str(hero_image).startswith("/"):
            hero_image = f"https://cdn.cloudflare.steamstatic.com{hero_image}"
        players.append(
            {
                "id": item.get("account_id"),
                "name": name,
                "side": "home" if item.get("isRadiant") else "away",
                "kills": item.get("kills"),
                "deaths": item.get("deaths"),
                "assists": item.get("assists"),
                "hero_id": hero_id,
                "hero": hero_name,
                "image": hero_image,
            }
        )
    if players:
        out["player_statistics"] = players
        out["lineups"] = {
            "home": {"start": [p for p in players if p["side"] == "home"], "bench": [], "formation": None, "coach": None},
            "away": {"start": [p for p in players if p["side"] == "away"], "bench": [], "formation": None, "coach": None},
        }
    duration = payload.get("duration")
    detail = {}
    if duration:
        detail["duration"] = duration
        detail["radiant_win"] = payload.get("radiant_win")
    if payload.get("radiant_score") is not None or payload.get("dire_score") is not None:
        out["statistics"] = [
            {"label": "Kills", "home": payload.get("radiant_score"), "away": payload.get("dire_score")},
        ]
        if payload.get("duration"):
            out["statistics"].append({"label": "Duration", "home": duration, "away": duration})
    if detail:
        out["sport_detail"] = detail
    return out


def parse_euroleague_box(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    by_q = payload.get("ByQuarter") or []
    if isinstance(by_q, list) and len(by_q) >= 2:
        periods = []
        home_q, away_q = by_q[0], by_q[1]
        for index, key in enumerate(("Quarter1", "Quarter2", "Quarter3", "Quarter4", "ExtraTime"), start=1):
            hv = home_q.get(key) if isinstance(home_q, dict) else None
            av = away_q.get(key) if isinstance(away_q, dict) else None
            if hv is None and av is None:
                continue
            periods.append({"label": "OT" if key == "ExtraTime" else index, "home": hv, "away": av})
        if periods:
            out["periods"] = periods
    stats_rows = payload.get("Stats") or []
    home = stats_rows[0] if isinstance(stats_rows, list) and stats_rows and isinstance(stats_rows[0], dict) else payload.get("HomeTeam") or {}
    away = stats_rows[1] if isinstance(stats_rows, list) and len(stats_rows) > 1 and isinstance(stats_rows[1], dict) else payload.get("AwayTeam") or {}
    stats = []
    for key, label in (
        ("Score", "Points"),
        ("FieldGoalsMade", "FG made"),
        ("ThreePointersMade", "3PT"),
        ("FreeThrowsMade", "FT"),
        ("TotalRebounds", "Rebounds"),
        ("Assistances", "Assists"),
        ("Turnovers", "Turnovers"),
        ("Steals", "Steals"),
        ("BlocksFavour", "Blocks"),
        ("FoulsCommited", "Fouls"),
    ):
        hv = home.get(key) if isinstance(home, dict) else None
        av = away.get(key) if isinstance(away, dict) else None
        if hv is not None or av is not None:
            stats.append({"label": label, "home": hv, "away": av})
    if stats:
        out["statistics"] = stats
    players = []
    for side_name, blob in (("home", home), ("away", away)):
        roster = []
        if isinstance(blob, dict):
            roster = blob.get("PlayersStats") or blob.get("Players") or []
        for item in roster or []:
            if not isinstance(item, dict):
                continue
            name = item.get("Player") or item.get("PlayerName") or item.get("name")
            if not name:
                continue
            players.append(
                {
                    "name": str(name).strip(),
                    "side": side_name,
                    "points": item.get("Points") or item.get("points"),
                    "rebounds": item.get("TotalRebounds"),
                    "assists": item.get("Assistances"),
                }
            )
    if players:
        out["player_statistics"] = players
        out["lineups"] = {
            "home": {"start": [p for p in players if p["side"] == "home"], "bench": [], "formation": None, "coach": None},
            "away": {"start": [p for p in players if p["side"] == "away"], "bench": [], "formation": None, "coach": None},
        }
    if payload.get("Referees"):
        out["referee"] = payload.get("Referees")
    if payload.get("Attendance"):
        out["attendance"] = payload.get("Attendance")
    return out


def _lol_side(team: Dict[str, Any]) -> str:
    return str(team.get("side") or "").lower()


def _lol_names(match: Dict[str, Any]) -> Dict[str, str]:
    names = {}
    for team in match.get("teams") or []:
        if isinstance(team, dict) and team.get("id"):
            names[str(team.get("id"))] = team.get("name") or team.get("code") or ""
    return names


def _lol_winner(teams: List[Dict[str, Any]], names: Dict[str, str]) -> Optional[str]:
    for team in teams:
        if not isinstance(team, dict):
            continue
        result = team.get("result") if isinstance(team.get("result"), dict) else {}
        outcome = str(result.get("outcome") or "").lower()
        if outcome in {"win", "winner"}:
            return names.get(str(team.get("id"))) or team.get("name") or team.get("code")
    return None


def _window_stats(window: Dict[str, Any]) -> Dict[str, Any]:
    frames = window.get("frames") if isinstance(window, dict) else []
    if not isinstance(frames, list) or not frames:
        return {}
    start = frames[0].get("rfc460Timestamp") if isinstance(frames[0], dict) else None
    last = frames[-1] if isinstance(frames[-1], dict) else {}
    meta = window.get("gameMetadata") if isinstance(window.get("gameMetadata"), dict) else {}
    finished = str(last.get("gameState") or "").lower() == "finished"
    stats: Dict[str, Any] = {"state": last.get("gameState"), "started_at": start, "ended_at": last.get("rfc460Timestamp")}
    for side, meta_key, frame_key in (
        ("blue", "blueTeamMetadata", "blueTeam"),
        ("red", "redTeamMetadata", "redTeam"),
    ):
        team_meta = meta.get(meta_key) if isinstance(meta.get(meta_key), dict) else {}
        frame = last.get(frame_key) if isinstance(last.get(frame_key), dict) else {}
        side_stats = {"team_id": team_meta.get("esportsTeamId")}
        if finished and frame.get("totalKills") is not None:
            side_stats["kills"] = frame.get("totalKills")
        stats[side] = side_stats
    if finished and start and last.get("rfc460Timestamp"):
        try:
            from datetime import datetime

            opened = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            closed = datetime.fromisoformat(str(last.get("rfc460Timestamp")).replace("Z", "+00:00"))
            seconds = int((closed - opened).total_seconds())
            if seconds > 0:
                stats["duration"] = seconds
        except ValueError:
            pass
    return stats


def parse_lol_event(payload: Any, windows: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = (payload or {}).get("data") if isinstance(payload, dict) else {}
    event = (data or {}).get("event") or {}
    match = event.get("match") or {}
    games = match.get("games") or []
    names = _lol_names(match)
    windows = windows or {}
    rows = []
    for index, game in enumerate(games):
        if not isinstance(game, dict):
            continue
        gid = str(game.get("id") or game.get("gameId") or "")
        teams = [team for team in (game.get("teams") or []) if isinstance(team, dict)]
        blue = next((team for team in teams if _lol_side(team) == "blue"), teams[0] if teams else {})
        red = next((team for team in teams if _lol_side(team) == "red"), teams[1] if len(teams) > 1 else {})
        window = _window_stats(windows.get(gid) or {})
        blue_id = str((blue or {}).get("id") or (window.get("blue") or {}).get("team_id") or "")
        red_id = str((red or {}).get("id") or (window.get("red") or {}).get("team_id") or "")
        row = {
            "id": gid or None,
            "name": game.get("number") or index + 1,
            "state": game.get("state") or window.get("state"),
            "blue": {"id": blue_id or None, "name": names.get(blue_id) or None, "side": "blue"},
            "red": {"id": red_id or None, "name": names.get(red_id) or None, "side": "red"},
            "winner": _lol_winner(teams, names),
        }
        for side in ("blue", "red"):
            kills = (window.get(side) or {}).get("kills")
            if kills is not None:
                row[side]["kills"] = kills
        if window.get("duration"):
            row["duration"] = window["duration"]
        rows.append({key: value for key, value in row.items() if value not in (None, "", {})})
    out: Dict[str, Any] = {}
    if rows and any(item.get("id") or item.get("state") not in (None, "", "unstarted") for item in rows):
        strategy = match.get("strategy") if isinstance(match.get("strategy"), dict) else {}
        league = event.get("league") if isinstance(event.get("league"), dict) else {}
        stage = league.get("name") or event.get("blockName")
        out["sport_detail"] = {
            "series_id": str(match.get("id") or event.get("id") or "") or None,
            "best_of": strategy.get("count"),
            "stage": stage if stage and not str(stage).isdigit() else None,
            "games": rows,
        }
        out["sport_detail"] = {key: value for key, value in out["sport_detail"].items() if value not in (None, "", [])}
    return out


def parse_cfl_game(game: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    home = game.get("homeSquad") or game.get("home") or {}
    away = game.get("awaySquad") or game.get("away") or {}
    if not isinstance(home, dict):
        home = {}
    if not isinstance(away, dict):
        away = {}
    if home.get("score") is not None or away.get("score") is not None:
        out["sport_detail"] = {
            "home_score": home.get("score"),
            "away_score": away.get("score"),
            "winner_id": game.get("winner"),
        }
    timeouts = game.get("timeouts") if isinstance(game.get("timeouts"), dict) else {}
    if timeouts:
        out["statistics"] = [{"label": "Timeouts", "home": timeouts.get("home"), "away": timeouts.get("away")}]
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
    if isinstance(row.get("matchStats"), dict):
        from collector.rich_public import parse_championdata_detail

        parsed = parse_championdata_detail(row)
        if parsed:
            return parsed
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
    if isinstance(data.get("data"), dict):
        data = data.get("data") or {}
    out: Dict[str, Any] = {}
    rows = data.get("matches") or data.get("match") or data.get("einzel") or data.get("games") or data.get("rubbers") or []
    rubbers = []
    periods = []
    if isinstance(rows, list):
        for index, item in enumerate(rows):
            if not isinstance(item, dict):
                continue
            home = item.get("sets_home") or item.get("matches_home") or item.get("home")
            away = item.get("sets_guest") or item.get("matches_guest") or item.get("away") or item.get("sets_away")
            def _player_name(value: Any) -> Any:
                if isinstance(value, dict):
                    named = value.get("name") or value.get("display")
                    if named:
                        return named
                    return " ".join(part for part in (value.get("firstname"), value.get("lastname")) if part) or None
                return value

            def _named_list(keys, list_key):
                names = []
                raw_list = item.get(list_key)
                if isinstance(raw_list, list):
                    for value in raw_list:
                        name = _player_name(value)
                        if name and name not in names:
                            names.append(name)
                for key in keys:
                    name = _player_name(item.get(key))
                    if name and name not in names:
                        names.append(name)
                return names

            home_names = _named_list(("player_home", "playerHome", "mm_player11", "mm_player12"), "home_players")
            away_names = _named_list(("player_guest", "playerAway", "mm_player21", "mm_player22"), "guest_players")
            home_player = home_names[0] if home_names else None
            away_player = away_names[0] if away_names else None
            games = []
            raw_games = item.get("set_scores") or item.get("sets") or item.get("games") or item.get("points") or []
            if not raw_games:
                for set_no in range(1, 8):
                    hv = item.get(f"set{set_no}_home")
                    av = item.get(f"set{set_no}_guest")
                    if hv in (None, "") and av in (None, ""):
                        continue
                    try:
                        if int(hv or 0) == 0 and int(av or 0) == 0:
                            continue
                    except (TypeError, ValueError):
                        pass
                    raw_games.append({"home": hv, "away": av})
            if isinstance(raw_games, list):
                for g_index, game in enumerate(raw_games):
                    if isinstance(game, dict):
                        games.append(
                            {
                                "label": g_index + 1,
                                "home": game.get("home") or game.get("home_points"),
                                "away": game.get("away") or game.get("guest_points") or game.get("away_points"),
                            }
                        )
                    elif isinstance(game, (list, tuple)) and len(game) >= 2:
                        games.append({"label": g_index + 1, "home": game[0], "away": game[1]})
            if home is None and away is None and not games:
                continue
            rubber = {
                "label": item.get("position") or item.get("nr") or index + 1,
                "home": home,
                "away": away,
                "home_player": home_player,
                "away_player": away_player,
                "home_players": home_names if len(home_names) > 1 else None,
                "away_players": away_names if len(away_names) > 1 else None,
                "games": games or None,
            }
            rubbers.append({key: value for key, value in rubber.items() if value not in (None, "", [])})
            periods.append({"label": f"Rubber {index + 1}", "home": home, "away": away})
    if periods:
        out["periods"] = periods
    if rubbers:
        out["sport_detail"] = {
            "meeting": True,
            "rubbers": rubbers,
            "current_set": data.get("current_match") or data.get("current"),
        }
    return out


def _lol_headers() -> Dict[str, str]:
    return {"x-api-key": LOL_KEY}


def _pair_names(home: str, away: str, labels: List[str]) -> bool:
    def hit(name: str) -> bool:
        needle = (name or "").lower().strip()
        if len(needle) < 2:
            return False
        for label in labels:
            other = label.lower().strip()
            if needle == other or (len(needle) > 2 and (needle in other or other in needle)):
                return True
        return False

    return hit(home) and hit(away)


def resolve_lol_match_id(home: str, away: str, getter) -> str:
    """Find the public Worlds match id for a series that was stored without one."""
    if not home or not away:
        return ""
    from urllib.parse import quote

    leagues = _get(getter, LOL_LEAGUES, headers=_lol_headers())
    league_id = ""
    rows = (((leagues.payload or {}).get("data") or {}).get("leagues") or []) if leagues.ok else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("slug") or "").lower() == "worlds":
            league_id = str(row.get("id") or "")
    if not league_id:
        return ""
    token = ""
    for _page in range(4):
        url = LOL_SCHEDULE.format(league_id=league_id)
        if token:
            url += "&pageToken=" + quote(token, safe="")
        page = _get(getter, url, headers=_lol_headers())
        if not page.ok or not isinstance(page.payload, dict):
            break
        schedule = ((page.payload.get("data") or {}).get("schedule") or {})
        for row in schedule.get("events") or []:
            match = (row or {}).get("match") or {}
            labels = [
                str(team.get("name") or team.get("code") or "")
                for team in (match.get("teams") or [])
                if isinstance(team, dict)
            ]
            if match.get("id") and _pair_names(home, away, labels):
                return str(match.get("id"))
        token = str(((schedule.get("pages") or {}).get("older")) or "")
        if not token:
            break
    return ""


def _lol_game_window(getter, game_id: str) -> Dict[str, Any]:
    from datetime import datetime, timedelta
    from urllib.parse import quote

    opened = _get(getter, LOL_WINDOW_OPEN.format(game_id=game_id), headers=_lol_headers())
    if not opened.ok or not isinstance(opened.payload, dict):
        return {}
    frames = opened.payload.get("frames") or []
    stamp = frames[0].get("rfc460Timestamp") if frames and isinstance(frames[0], dict) else None
    if not stamp:
        return opened.payload
    best = opened.payload
    start = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    for minutes in (20, 35, 50, 70):
        starting = quote((start + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"), safe=":-")
        page = _get(getter, LOL_WINDOW.format(game_id=game_id, starting_time=starting), headers=_lol_headers())
        if not page.ok or not isinstance(page.payload, dict):
            continue
        late = list(page.payload.get("frames") or [])
        if late and isinstance(late[0], dict):
            late[0] = {**late[0], "rfc460Timestamp": stamp}
        best = {**page.payload, "frames": late}
        last = late[-1] if late else {}
        if isinstance(last, dict) and str(last.get("gameState") or "").lower() == "finished":
            return best
    return best


def _cricket_number(value: Any) -> Any:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return int(text) if text.isdigit() else float(text) if "." in text else value
    except ValueError:
        return value


def parse_bbc_cricket_payload(payload: Any) -> List[Dict[str, Any]]:
    """Innings from the public BBC Sport scores-fixtures INITIAL_DATA payload."""
    found: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            participants = node.get("participants")
            if isinstance(participants, dict) and isinstance(participants.get("homeTeam"), dict) and node.get("id"):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload or {})
    out = []
    for node in found:
        participants = node.get("participants") or {}
        home = participants.get("homeTeam") or {}
        away = participants.get("awayTeam") or {}
        status = str(node.get("status") or "")
        innings = []
        for side, team in (("home", home), ("away", away)):
            for item in team.get("innings") or []:
                if not isinstance(item, dict):
                    continue
                innings.append(
                    {
                        "label": team.get("name"),
                        "side": side,
                        "runs": _cricket_number(item.get("runs")),
                        "wickets": _cricket_number(item.get("wickets")),
                        "overs": item.get("overs"),
                        "innings_number": _cricket_number(item.get("inningsNumber")),
                        "live": item.get("isLive") is True,
                    }
                )
        summary = node.get("matchSummary") if isinstance(node.get("matchSummary"), dict) else {}
        live = status == "InPlay"
        out.append(
            {
                "id": str(node.get("id") or ""),
                "home": home.get("name") or "",
                "away": away.get("name") or "",
                "status": "live" if live else "finished" if status == "PostEvent" else "scheduled",
                "live": live,
                "innings": [row for row in innings if row.get("runs") is not None or row.get("wickets") is not None],
                "sport_detail": {
                    key: value
                    for key, value in {
                        "result": summary.get("resultString"),
                        "winner": summary.get("winnerTeamName"),
                        "series": node.get("tournamentName"),
                        "venue": node.get("groundName"),
                        "live": live,
                        "historical": False,
                    }.items()
                    if value not in (None, "", {})
                },
            }
        )
    return out


def match_bbc_cricket(events: List[Dict[str, Any]], home: str, away: str) -> Dict[str, Any]:
    for event in events:
        labels = [str(event.get("home") or ""), str(event.get("away") or "")]
        if event.get("innings") and _pair_names(home, away, labels):
            return event
    return {}


def fetch_bbc_cricket_match(home: str, away: str, on_date: str = "", text_getter=None) -> Dict[str, Any]:
    from collector.html_parse import _quoted_window_json
    from collector.http import fetch_text

    getter = text_getter or fetch_text
    urls = []
    if on_date:
        urls.append(BBC_CRICKET_DAY.format(date=on_date))
    if BBC_CRICKET_TODAY not in urls:
        urls.append(BBC_CRICKET_TODAY)
    for url in urls:
        try:
            result = getter(url)
        except TypeError:
            result = getter(url)
        html = result.payload if getattr(result, "ok", False) and isinstance(result.payload, str) else ""
        if not html:
            continue
        payload = _quoted_window_json(html, "__INITIAL_DATA__")
        matched = match_bbc_cricket(parse_bbc_cricket_payload(payload), home, away)
        if matched:
            return matched
    return {}


def fetch_lol_event(source_event_id: str, getter) -> Dict[str, Any]:
    sid = str(source_event_id or "").replace("lolesports:", "")
    if not sid:
        return {}
    result = _get(getter, LOL_EVENT.format(event_id=sid), headers=_lol_headers())
    payload = result.payload if result.ok and isinstance(result.payload, dict) else {}
    if not payload:
        return {}
    games = ((((payload.get("data") or {}).get("event") or {}).get("match") or {}).get("games") or [])
    windows: Dict[str, Any] = {}
    for game in games:
        if not isinstance(game, dict):
            continue
        gid = str(game.get("id") or "")
        if not gid or str(game.get("state") or "").lower() not in {"completed", "finished"}:
            continue
        try:
            windows[gid] = _lol_game_window(getter, gid)
        except (TypeError, ValueError, OSError):
            continue
    return parse_lol_event(payload, windows)


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
                if not isinstance(round_row, dict):
                    continue
                games = round_row.get("tournaments") or round_row.get("games") or []
                for game in games:
                    if not isinstance(game, dict):
                        continue
                    gid = str(game.get("id") or game.get("gameId") or game.get("cflId") or "")
                    if gid == sid or str(game.get("cflId") or "") == sid:
                        return parse_cfl_game(game)
        return {}
    if family in {"lolesports-json", "lolesports"}:
        return fetch_lol_event(sid, getter)
    if family in {"jolpica-f1", "jolpica"}:
        parts = sid.split(":")
        season = parts[0] if parts else ""
        rnd = parts[1] if len(parts) > 1 else parts[0]
        result = _get(getter, JOLPICA_RESULTS.format(season=season, round=rnd))
        if result.ok and isinstance(result.payload, dict):
            return parse_jolpica_results(result.payload)
        return {}
    if family in {"squiggle-afl", "squiggle"}:
        from collector.adapters_squiggle import SQUIGGLE_HEADERS, parse_squiggle_payload

        try:
            result = getter(SQUIGGLE_GAME.format(game_id=sid), headers=SQUIGGLE_HEADERS)
        except TypeError:
            result = _get(getter, SQUIGGLE_GAME.format(game_id=sid))
        rows, _meta = parse_squiggle_payload(result.payload if result else None, "games")
        matched = [row for row in rows if str(row.get("id") or "") == str(sid)]
        if matched:
            return parse_squiggle_game(matched[0])
        if len(rows) == 1:
            return parse_squiggle_game(rows[0])
        return {}
    if family in {"opendota"}:
        result = _get(getter, OPENDOTA_MATCH.format(match_id=sid))
        if result.ok and isinstance(result.payload, dict):
            return parse_opendota_match(result.payload, _opendota_heroes(getter))
        return {}
    if family in {"euroleague-live", "euroleague"}:
        parts = sid.split(":")
        season = parts[0] if len(parts) > 1 else "E2025"
        code = parts[-1]
        box = _get(getter, EUROLEAGUE_BOX.format(code=code, season=season))
        payload = box.payload if box.ok else None
        if not isinstance(payload, dict):
            text = fetch_text(EUROLEAGUE_BOX.format(code=code, season=season))
            if text.ok and isinstance(text.payload, str) and text.payload.strip().startswith("{"):
                import json

                try:
                    payload = json.loads(text.payload)
                except json.JSONDecodeError:
                    payload = None
        if isinstance(payload, dict):
            parsed = parse_euroleague_box(payload)
            if parsed:
                return parsed
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
    if family in {"pga-graphql", "pga"}:
        from collector.adapters_final18 import PgaGraphqlAdapter

        adapter = PgaGraphqlAdapter()
        board = adapter._leaderboard(sid, "pga-tour")
        rows = []
        for item in board:
            extra = item.get("extra") if isinstance(item, dict) else {}
            name = ((item.get("home") or {}).get("name") if isinstance(item, dict) else None)
            if not name:
                continue
            rows.append(
                {
                    "position": extra.get("position") or (item.get("score") or {}).get("position"),
                    "name": name,
                    "total": (item.get("score") or {}).get("home"),
                    "today": extra.get("today"),
                    "thru": extra.get("thru"),
                    "cut": extra.get("cut"),
                }
            )
        if rows:
            return {"classification": rows, "leaderboard": rows, "sport_detail": {"field": len(rows)}}
        return {}
    from collector.rich_public import fetch_rich_family

    parsed = fetch_rich_family(family, sid)
    if parsed:
        return parsed
    return {}
