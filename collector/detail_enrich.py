"""On-demand rich-detail fetch. Never used by the score list path.

Score freshness stays on the collector cycle. This module fills timeline,
statistics, lineups, and sport_detail for a single event when a public
source id is already stored on the canonical row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters import FetchResult
from collector.http import fetch_url
from collector.models import SportsEvent, SportsEventDetail
from collector.source_ids import families_with_ids, id_for_family, merge_family_ids
from collector.util import dump_json, load_json

FOTMOB_DETAILS = "https://www.fotmob.com/api/data/matchDetails?matchId={match_id}"
SOFA_INCIDENTS = "https://www.sofascore.com/api/v1/event/{event_id}/incidents"
SOFA_STATS = "https://www.sofascore.com/api/v1/event/{event_id}/statistics"
SOFA_LINEUPS = "https://www.sofascore.com/api/v1/event/{event_id}/lineups"
MLB_FEED = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
NHL_LANDING = "https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"
NHL_BOXSCORE = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"

TTL_LIVE = 45
TTL_SCHEDULED = 1800
TTL_FINISHED = 7 * 24 * 3600
TTL_NEGATIVE = 900
PARSER_REV = 5

DETAIL_FAMILIES = (
    "fotmob",
    "sofascore-web",
    "mlb-statsapi",
    "nhl-web",
    "pulselive",
    "pulselive-family",
    "world-rugby-rims",
    "cfl-scoreboard-json",
    "lolesports-json",
    "jolpica-f1",
    "squiggle-afl",
    "squiggle",
    "euroleague-live",
    "opendota",
    "pga-graphql",
    "openligadb",
    "championdata-netball",
    "click-tt-remix",
    "dataproject-web",
    "cricsheet",
)


def _ttl(status: str, *, empty: bool) -> int:
    if empty:
        return TTL_NEGATIVE
    value = (status or "").lower()
    if value in {"live", "inprogress"}:
        return TTL_LIVE
    if value in {"finished", "complete"}:
        return TTL_FINISHED
    return TTL_SCHEDULED


def _source_id(extra: Dict[str, Any], family: str) -> Optional[str]:
    return id_for_family(extra, family)


def _fresh(extra: Dict[str, Any], status: str) -> bool:
    if extra.get("parser_rev") != PARSER_REV:
        return False
    stamp = extra.get("detail_fetched_at")
    if not stamp:
        return False
    try:
        at = datetime.fromisoformat(str(stamp).replace("Z", ""))
    except ValueError:
        return False
    age = (datetime.utcnow() - at.replace(tzinfo=None)).total_seconds()
    empty = bool(extra.get("detail_empty") or extra.get("detail_negative"))
    return age < _ttl(status, empty=empty)


def _player_name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        inner = value.get("name")
        if isinstance(inner, dict):
            return inner.get("fullName") or inner.get("lastName")
        return value.get("fullName") or inner or value.get("lastName")
    if value not in (None, ""):
        return str(value)
    return None


def parse_fotmob_details(payload: Any) -> Dict[str, Any]:
    root = payload if isinstance(payload, dict) else {}
    content = root.get("content") if isinstance(root.get("content"), dict) else root
    out: Dict[str, Any] = {}
    general = root.get("general") if isinstance(root.get("general"), dict) else {}
    if not general and isinstance(content.get("general"), dict):
        general = content.get("general") or {}
    facts = content.get("matchFacts") if isinstance(content.get("matchFacts"), dict) else {}
    info = facts.get("infoBox") if isinstance(facts.get("infoBox"), dict) else {}
    stadium = info.get("Stadium") if isinstance(info.get("Stadium"), dict) else {}
    venue = stadium.get("name") or general.get("venueName")
    if isinstance(general.get("venue"), dict):
        venue = venue or general["venue"].get("name")
    if venue:
        out["venue"] = venue
    referee_blob = info.get("Referee")
    referee = None
    if isinstance(referee_blob, dict):
        referee = referee_blob.get("text") or referee_blob.get("name")
    elif referee_blob:
        referee = referee_blob
    if not referee:
        raw_ref = general.get("referee")
        if isinstance(raw_ref, dict):
            referee = raw_ref.get("name") or raw_ref.get("text")
        else:
            referee = raw_ref
    if referee:
        out["referee"] = referee
    attendance = info.get("Attendance")
    if isinstance(attendance, dict):
        attendance = attendance.get("value") or attendance.get("text")
    if attendance in (None, ""):
        attendance = general.get("attendance") or general.get("spectators")
    if attendance not in (None, ""):
        out["attendance"] = attendance
    events = facts.get("events") if isinstance(facts, dict) else {}
    if isinstance(events, dict):
        rows = events.get("events") or events.get("list") or []
    else:
        rows = events if isinstance(events, list) else []
    timeline = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("eventType") or item.get("key") or "").lower()
        if kind in {"half", "addedtime", "added time"}:
            continue
        player = _player_name(item.get("name") or item.get("player") or item.get("playerObj"))
        minute = item.get("time") or item.get("minute")
        assist = item.get("assistStr") or item.get("assist")
        if isinstance(assist, dict):
            assist = assist.get("name")
        card = item.get("card") or item.get("cardType")
        if card:
            kind = f"{str(card).lower()} card"
        if item.get("varReason") or "var" in kind:
            kind = kind if "var" in kind else "var"
        player_in = _player_name(item.get("playerIn") or item.get("inPlayer"))
        player_out = _player_name(item.get("playerOut") or item.get("outPlayer"))
        if kind in {"substitution", "subst", "sub"}:
            kind = "substitution"
            player_in = player_in or player
        timeline.append(
            {
                "type": kind or "event",
                "minute": minute,
                "player": player,
                "assist": assist,
                "player_in": player_in,
                "player_out": player_out,
                "side": "home" if item.get("isHome") else "away" if item.get("isHome") is False else None,
                "score_after": {"home": item.get("homeScore"), "away": item.get("awayScore")}
                if item.get("homeScore") is not None or item.get("awayScore") is not None
                else None,
                "description": item.get("str") or item.get("text") or item.get("varReason"),
            }
        )
    if timeline:
        out["incidents"] = timeline
    stats_block = content.get("stats") or content.get("statistics") or {}
    periods = stats_block.get("Periods") if isinstance(stats_block, dict) else {}
    all_stats = (periods.get("All") or {}).get("stats") if isinstance(periods, dict) else None
    if isinstance(all_stats, list):
        rows = []
        for group in all_stats:
            for item in (group.get("stats") if isinstance(group, dict) else []) or []:
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or item.get("key")
                values = item.get("stats") or item.get("values") or []
                if title and isinstance(values, list) and len(values) >= 2:
                    rows.append({"label": title, "home": values[0], "away": values[1]})
        if rows:
            out["statistics"] = rows
    period_rows = []
    for key, label in (("FirstHalf", "1"), ("SecondHalf", "2")):
        blob = periods.get(key) if isinstance(periods, dict) else None
        if not isinstance(blob, dict):
            continue
        scoreline = blob.get("score") or blob.get("Score")
        if isinstance(scoreline, str) and "-" in scoreline:
            left, right = scoreline.split("-", 1)
            period_rows.append({"label": label, "home": left.strip(), "away": right.strip()})
    if period_rows:
        out["periods"] = period_rows
    lineup = content.get("lineup") or content.get("lineups") or {}
    sides = lineup.get("lineup") if isinstance(lineup, dict) else None
    home_id = str((general.get("homeTeam") or {}).get("id") or "") if isinstance(general.get("homeTeam"), dict) else ""

    def _players_from_side(side: Dict[str, Any], *, substitutes: bool) -> List[Dict[str, Any]]:
        key = "subs" if substitutes else "starters"
        alt = "substitutes" if substitutes else "startXI"
        players = []
        for player in side.get(key) or side.get(alt) or []:
            if not isinstance(player, dict):
                continue
            name = player.get("name") or player.get("lastName")
            if not name:
                continue
            rating = (player.get("performance") or {}).get("rating") if isinstance(player.get("performance"), dict) else None
            players.append({"name": name, "number": player.get("shirtNumber") or player.get("number"), "rating": rating})
        return players

    if isinstance(lineup, dict) and lineup.get("homeTeam") and lineup.get("awayTeam"):
        def pack_team(side: Dict[str, Any]) -> Dict[str, Any]:
            coach = side.get("coach") or {}
            if isinstance(coach, list) and coach:
                coach = coach[0]
            return {
                "formation": side.get("formation"),
                "coach": (coach.get("name") if isinstance(coach, dict) else None) or side.get("coachName"),
                "start": _players_from_side(side, substitutes=False),
                "bench": _players_from_side(side, substitutes=True),
            }

        packed = {
            "home": pack_team(lineup.get("homeTeam") if isinstance(lineup.get("homeTeam"), dict) else {}),
            "away": pack_team(lineup.get("awayTeam") if isinstance(lineup.get("awayTeam"), dict) else {}),
        }
        if packed["home"]["start"] or packed["away"]["start"]:
            out["lineups"] = packed
    elif isinstance(sides, list) and len(sides) >= 2:
        def pack(side: Dict[str, Any]) -> Dict[str, Any]:
            players = []
            bench = []
            for group in side.get("players") or []:
                rows = group if isinstance(group, list) else [group]
                for player in rows:
                    if not isinstance(player, dict):
                        continue
                    name_blob = player.get("name")
                    if isinstance(name_blob, dict):
                        name = name_blob.get("fullName") or name_blob.get("lastName")
                    else:
                        name = name_blob
                    row = {"name": name, "number": player.get("shirtNumber") or player.get("number")}
                    if player.get("substitute") or player.get("isSubstitute"):
                        bench.append(row)
                    else:
                        players.append(row)
            coach = side.get("coach") or {}
            if isinstance(coach, list) and coach:
                coach = coach[0]
            return {
                "formation": side.get("formation"),
                "coach": (coach.get("name") if isinstance(coach, dict) else None) or side.get("coachName"),
                "start": players,
                "bench": bench,
            }

        packed = {"home": pack(sides[0] if isinstance(sides[0], dict) else {}), "away": pack(sides[1] if isinstance(sides[1], dict) else {})}
        if packed["home"]["start"] or packed["away"]["start"]:
            out["lineups"] = packed
    player_stats_blob = content.get("playerStats") if isinstance(content.get("playerStats"), dict) else {}
    players_out = []
    for item in player_stats_blob.values():
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        groups = item.get("stats") if isinstance(item.get("stats"), list) else []
        values: Dict[str, Any] = {}
        for group in groups:
            stats = (group or {}).get("stats") if isinstance(group, dict) else None
            if not isinstance(stats, dict):
                continue
            for label, blob in stats.items():
                stat = blob.get("stat") if isinstance(blob, dict) else None
                if isinstance(stat, dict) and "value" in stat:
                    values[label] = stat.get("value")
        team_id = str(item.get("teamId") or "")
        side = "home" if home_id and team_id == home_id else "away" if home_id else None
        players_out.append(
            {
                "name": name,
                "number": item.get("shirtNumber"),
                "side": side,
                "rating": values.get("FotMob rating"),
                "minutes": values.get("Minutes played"),
                "goals": values.get("Goals"),
                "assists": values.get("Assists"),
                "xg": values.get("Expected goals (xG)") or values.get("xG"),
                "xa": values.get("Expected assists (xA)"),
            }
        )
    if players_out:
        out["player_statistics"] = players_out
    shots = ((content.get("shotmap") or {}).get("shots") if isinstance(content.get("shotmap"), dict) else None) or []
    if isinstance(shots, list) and shots:
        out["sport_detail"] = {
            **(out.get("sport_detail") or {}),
            "shots": len(shots),
            "shots_on_target": sum(1 for shot in shots if isinstance(shot, dict) and shot.get("isOnTarget")),
        }
    return out


def parse_sofa_incidents(payload: Any) -> List[Dict[str, Any]]:
    rows = payload.get("incidents") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("incidentType") or item.get("type") or "").lower()
        player = item.get("player") or {}
        assist = item.get("assist1") or item.get("assist") or {}
        out.append(
            {
                "type": kind or "event",
                "minute": item.get("time") or item.get("minute"),
                "player": player.get("name") if isinstance(player, dict) else player,
                "assist": assist.get("name") if isinstance(assist, dict) else assist,
                "side": "home" if item.get("isHome") else "away" if item.get("isHome") is False else None,
                "score_after": {"home": item.get("homeScore"), "away": item.get("awayScore")}
                if item.get("homeScore") is not None
                else None,
            }
        )
    return out


def parse_sofa_statistics(payload: Any) -> List[Dict[str, Any]]:
    groups = []
    if isinstance(payload, dict):
        for period in payload.get("statistics") or []:
            groups.extend(period.get("groups") or [])
    out = []
    for group in groups:
        for item in (group or {}).get("statisticsItems") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("key")
            if not name:
                continue
            out.append({"label": name, "home": item.get("home"), "away": item.get("away")})
    return out


def parse_sofa_lineups(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    def pack(side: Any) -> Dict[str, Any]:
        blob = side if isinstance(side, dict) else {}
        start = []
        bench = []
        for player in blob.get("players") or []:
            info = player.get("player") if isinstance(player, dict) else {}
            row = {
                "name": (info or {}).get("name") or player.get("name"),
                "number": player.get("jerseyNumber") or (info or {}).get("jerseyNumber"),
                "position": player.get("position"),
            }
            if player.get("substitute"):
                bench.append(row)
            else:
                start.append(row)
        return {
            "formation": blob.get("formation"),
            "coach": (blob.get("coach") or {}).get("name") if isinstance(blob.get("coach"), dict) else blob.get("coach"),
            "start": start,
            "bench": bench,
        }

    home = pack(payload.get("home"))
    away = pack(payload.get("away"))
    if not home["start"] and not away["start"]:
        return None
    return {"home": home, "away": away}


def parse_mlb_live(payload: Any) -> Dict[str, Any]:
    live = payload if isinstance(payload, dict) else {}
    game = live.get("liveData") or {}
    box = game.get("boxscore") or {}
    plays = game.get("plays") or {}
    linescore = game.get("linescore") or {}
    out: Dict[str, Any] = {}
    innings = []
    for item in linescore.get("innings") or []:
        if not isinstance(item, dict):
            continue
        innings.append(
            {
                "label": item.get("num") or item.get("ordinalNum"),
                "home": (item.get("home") or {}).get("runs"),
                "away": (item.get("away") or {}).get("runs"),
                "hits_home": (item.get("home") or {}).get("hits"),
                "hits_away": (item.get("away") or {}).get("hits"),
                "errors_home": (item.get("home") or {}).get("errors"),
                "errors_away": (item.get("away") or {}).get("errors"),
            }
        )
    if innings:
        out["periods"] = innings
    if linescore:
        out["sport_detail"] = {
            "inning": linescore.get("currentInning"),
            "inning_half": linescore.get("inningHalf") or linescore.get("inningState"),
            "outs": linescore.get("outs"),
            "balls": (linescore.get("balls")),
            "strikes": linescore.get("strikes"),
        }
        pitcher = ((linescore.get("defense") or {}).get("pitcher") or {}).get("fullName")
        batter = ((linescore.get("offense") or {}).get("batter") or {}).get("fullName")
        if pitcher or batter:
            out["sport_detail"]["pitcher"] = pitcher
            out["sport_detail"]["batter"] = batter
    all_plays = plays.get("allPlays") or []
    timeline = []
    for item in all_plays[-80:]:
        result = item.get("result") or {}
        about = item.get("about") or {}
        desc = result.get("description") or about.get("description")
        if not desc:
            continue
        timeline.append(
            {
                "type": result.get("eventType") or result.get("event") or "play",
                "period": about.get("inning"),
                "player": None,
                "minute": None,
                "description": desc,
            }
        )
    if timeline:
        out["incidents"] = timeline
    teams = box.get("teams") or {}
    stats = []
    home_team = (teams.get("home") or {}).get("teamStats") or {}
    away_team = (teams.get("away") or {}).get("teamStats") or {}
    batting_h = home_team.get("batting") or {}
    batting_a = away_team.get("batting") or {}
    for key, label in (("runs", "Runs"), ("hits", "Hits"), ("errors", "Errors")):
        if batting_h.get(key) is not None or batting_a.get(key) is not None:
            stats.append({"label": label, "home": batting_h.get(key), "away": batting_a.get(key)})
    if stats:
        out["statistics"] = stats
    players = []
    for side_name, side in (("home", teams.get("home") or {}), ("away", teams.get("away") or {})):
        for _pid, player in (side.get("players") or {}).items():
            person = player.get("person") or {}
            name = person.get("fullName")
            if not name:
                continue
            bat = (player.get("stats") or {}).get("batting") or {}
            pit = (player.get("stats") or {}).get("pitching") or {}
            players.append(
                {
                    "name": name,
                    "side": side_name,
                    "hits": bat.get("hits"),
                    "at_bats": bat.get("atBats"),
                    "rbi": bat.get("rbi"),
                    "innings_pitched": pit.get("inningsPitched"),
                    "strikeouts": pit.get("strikeOuts"),
                }
            )
    if players:
        out["player_statistics"] = players
        out["lineups"] = {
            "home": {"start": [p for p in players if p.get("side") == "home"][:9], "bench": [], "formation": None, "coach": None},
            "away": {"start": [p for p in players if p.get("side") == "away"][:9], "bench": [], "formation": None, "coach": None},
        }
    return out


def parse_nhl_landing(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    summary = payload.get("summary") or {}
    scoring = summary.get("scoring") or []
    timeline = []
    periods = []
    for period in scoring:
        descriptor = period.get("periodDescriptor") if isinstance(period.get("periodDescriptor"), dict) else {}
        number = descriptor.get("number") or period.get("period")
        goals = period.get("goals") or []
        last = next((g for g in reversed(goals) if isinstance(g, dict) and (g.get("homeScore") is not None or g.get("awayScore") is not None)), None)
        periods.append(
            {
                "label": number,
                "home": last.get("homeScore") if last else 0,
                "away": last.get("awayScore") if last else 0,
            }
        )
        for goal in goals:
            if not isinstance(goal, dict):
                continue
            name = (goal.get("name") or {}).get("default") if isinstance(goal.get("name"), dict) else goal.get("name")
            timeline.append(
                {
                    "type": "goal",
                    "period": number,
                    "player": name,
                    "minute": goal.get("timeInPeriod"),
                    "score_after": {"home": goal.get("homeScore"), "away": goal.get("awayScore")},
                }
            )
    penalties = summary.get("penalties") or []
    for period in penalties if isinstance(penalties, list) else []:
        number = (period.get("periodDescriptor") or {}).get("number") if isinstance(period, dict) else None
        for item in (period.get("penalties") if isinstance(period, dict) else []) or []:
            if not isinstance(item, dict):
                continue
            name = (item.get("committedByPlayer") or {}).get("default") if isinstance(item.get("committedByPlayer"), dict) else item.get("committedByPlayer")
            timeline.append(
                {
                    "type": "penalty",
                    "period": number,
                    "player": name,
                    "minute": item.get("timeInPeriod"),
                    "description": item.get("descKey") or item.get("duration"),
                }
            )
    if timeline:
        out["incidents"] = timeline
    home = payload.get("homeTeam") or {}
    away = payload.get("awayTeam") or {}
    team_stats = []
    if home.get("sog") is not None or away.get("sog") is not None:
        team_stats.append({"label": "Shots", "home": home.get("sog"), "away": away.get("sog")})
    if home.get("score") is not None or away.get("score") is not None:
        team_stats.append({"label": "Goals", "home": home.get("score"), "away": away.get("score")})
    for key, label in (("powerPlayConversion", "Power play"), ("pim", "PIM")):
        if home.get(key) is not None or away.get(key) is not None:
            team_stats.append({"label": label, "home": home.get(key), "away": away.get(key)})
    if team_stats:
        out["statistics"] = team_stats
    home_periods = home.get("scoreByPeriod") or home.get("periodScores") or []
    away_periods = away.get("scoreByPeriod") or away.get("periodScores") or []
    filled = []
    count = max(len(home_periods) if isinstance(home_periods, list) else 0, len(away_periods) if isinstance(away_periods, list) else 0)
    for index in range(count):
        hv = home_periods[index] if index < len(home_periods) else None
        av = away_periods[index] if index < len(away_periods) else None
        if isinstance(hv, dict):
            hv = hv.get("goals") or hv.get("score")
        if isinstance(av, dict):
            av = av.get("goals") or av.get("score")
        if hv is None and av is None:
            continue
        filled.append({"label": index + 1, "home": hv, "away": av})
    if filled:
        out["periods"] = filled
    elif any((row.get("home") or row.get("away")) for row in periods):
        out["periods"] = periods
    return out


def parse_nhl_boxscore(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: Dict[str, Any] = {}
    blob = payload.get("playerByGameStats") or {}
    players = []
    for side_name, key in (("home", "homeTeam"), ("away", "awayTeam")):
        team = blob.get(key) or {}
        groups = []
        for group_key in ("forwards", "defense", "goalies"):
            groups.extend(team.get(group_key) or [])
        start = []
        for item in groups:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or {}).get("default") if isinstance(item.get("name"), dict) else item.get("name")
            row = {
                "name": name,
                "side": side_name,
                "goals": item.get("goals"),
                "assists": item.get("assists"),
                "shots": item.get("sog") or item.get("shots"),
                "pim": item.get("pim"),
            }
            players.append(row)
            start.append({"name": name, "number": item.get("sweaterNumber")})
        if start:
            out.setdefault("lineups", {})[side_name] = {"start": start, "bench": [], "formation": None, "coach": None}
    if players:
        out["player_statistics"] = players
    return out


def _get(getter, url: str) -> FetchResult:
    try:
        return getter(url)
    except TypeError:
        return getter(url)


def _merge_detail(base: Dict[str, Any], part: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in (part or {}).items():
        if not value:
            continue
        if not base.get(key):
            base[key] = value
    return base


def fetch_family_detail(family: str, source_event_id: str, getter=None) -> Dict[str, Any]:
    getter = getter or fetch_url
    family = (family or "").lower()
    out: Dict[str, Any] = {}
    if family == "fotmob":
        result = _get(getter, FOTMOB_DETAILS.format(match_id=source_event_id))
        payload = result.payload if result.ok else None
        if isinstance(payload, dict):
            out.update(parse_fotmob_details(payload))
        return out
    if family == "sofascore-web":
        from concurrent.futures import ThreadPoolExecutor

        urls = {
            "incidents": SOFA_INCIDENTS.format(event_id=source_event_id),
            "statistics": SOFA_STATS.format(event_id=source_event_id),
            "lineups": SOFA_LINEUPS.format(event_id=source_event_id),
        }

        def _fetch(item):
            kind, url = item
            return kind, _get(getter, url)

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = dict(pool.map(_fetch, urls.items()))
        inc = results.get("incidents")
        if inc and inc.ok and isinstance(inc.payload, dict):
            rows = parse_sofa_incidents(inc.payload)
            if rows:
                out["incidents"] = rows
        stats = results.get("statistics")
        if stats and stats.ok and isinstance(stats.payload, dict):
            rows = parse_sofa_statistics(stats.payload)
            if rows:
                out["statistics"] = rows
        line = results.get("lineups")
        if line and line.ok and isinstance(line.payload, dict):
            packed = parse_sofa_lineups(line.payload)
            if packed:
                out["lineups"] = packed
        return out
    if family == "mlb-statsapi":
        result = _get(getter, MLB_FEED.format(game_pk=source_event_id.replace("mlb:", "")))
        if result.ok and isinstance(result.payload, dict):
            out.update(parse_mlb_live(result.payload))
        return out
    if family == "nhl-web":
        gid = source_event_id.replace("nhl:", "")
        result = _get(getter, NHL_LANDING.format(game_id=gid))
        if result.ok and isinstance(result.payload, dict):
            out.update(parse_nhl_landing(result.payload))
        box = _get(getter, NHL_BOXSCORE.format(game_id=gid))
        if box.ok and isinstance(box.payload, dict):
            _merge_detail(out, parse_nhl_boxscore(box.payload))
        return out
    from collector.detail_families import fetch_extra_family_detail

    extra = fetch_extra_family_detail(family, source_event_id, getter=getter)
    if extra:
        out.update(extra)
    return out


def enrich_event_row(db: Session, row: SportsEvent, getter=None) -> None:
    extra = load_json(row.extra_json, {}) or {}
    try:
        from collector.models import SportsEventObservation

        for obs in (
            db.query(SportsEventObservation)
            .filter_by(event_id=row.event_id)
            .all()
        ):
            if obs.source_family and obs.source_event_id:
                extra["source_event_ids"] = merge_family_ids(
                    extra.get("source_event_ids"),
                    family=str(obs.source_family),
                    source_event_id=obs.source_event_id,
                )
    except Exception:
        pass
    ids = families_with_ids(extra)
    tried = set(extra.get("detail_families_tried") or [])
    click_detail = extra.get("sport_detail") if isinstance(extra.get("sport_detail"), dict) else {}
    if (ids.get("click-tt-remix") or ids.get("click-tt")) and not click_detail.get("rubbers"):
        tried.discard("click-tt-remix")
        tried.discard("click-tt")
    if str(row.competition_id or "") == "lol-world-championship":
        lol_detail = extra.get("sport_detail") if isinstance(extra.get("sport_detail"), dict) else {}
        if not lol_detail.get("games"):
            tried.discard("lolesports-json")
            tried.discard("lolesports")
        if not (ids.get("lolesports-json") or ids.get("lolesports")):
            from collector.detail_families import resolve_lol_match_id

            participants = load_json(row.participants_json, {}) or {}
            home_name = ((participants.get("home") or {}) if isinstance(participants.get("home"), dict) else {}).get("name")
            away_name = ((participants.get("away") or {}) if isinstance(participants.get("away"), dict) else {}).get("name")
            found = resolve_lol_match_id(str(home_name or ""), str(away_name or ""), getter or fetch_url)
            if found:
                extra["source_event_ids"] = merge_family_ids(
                    extra.get("source_event_ids"),
                    family="lolesports-json",
                    source_event_id=found,
                )
                ids = families_with_ids(extra)
    if str(getattr(row, "sport_id", "") or "") == "cricket" and not extra.get("innings"):
        checked = extra.get("bbc_cricket_checked_at")
        retry = True
        if checked:
            try:
                checked_at = datetime.fromisoformat(str(checked))
                retry = (datetime.utcnow() - checked_at.replace(tzinfo=None)).total_seconds() > TTL_NEGATIVE
            except ValueError:
                retry = True
        if retry:
            from collector.detail_families import fetch_bbc_cricket_match

            participants = load_json(row.participants_json, {}) or {}
            home_name = ((participants.get("home") or {}) if isinstance(participants.get("home"), dict) else {}).get("name")
            away_name = ((participants.get("away") or {}) if isinstance(participants.get("away"), dict) else {}).get("name")
            on_date = row.start_time.date().isoformat() if row.start_time else ""
            found = fetch_bbc_cricket_match(str(home_name or ""), str(away_name or ""), on_date)
            extra["bbc_cricket_checked_at"] = datetime.utcnow().isoformat()
            if found.get("innings"):
                extra["innings"] = found["innings"]
                detail = dict(extra.get("sport_detail") or {}) if isinstance(extra.get("sport_detail"), dict) else {}
                detail.update(found.get("sport_detail") or {})
                extra["sport_detail"] = detail
                if found.get("live") is True:
                    row.live = True
                    row.status = "live"
    pending = [fam for fam in DETAIL_FAMILIES if ids.get(fam) and fam not in tried]
    record = db.get(SportsEventDetail, row.event_id)
    missing_lineups = not (record and load_json(record.lineups_json)) and not extra.get("lineups_absent")
    if missing_lineups:
        tried.discard("fotmob")
        tried.discard("sofascore-web")
        pending = [fam for fam in DETAIL_FAMILIES if ids.get(fam)]
    if _fresh(extra, row.status or "") and not pending and not missing_lineups:
        row.extra_json = dump_json(extra)
        return
    if not any(fam in DETAIL_FAMILIES for fam in ids):
        row.extra_json = dump_json(extra)
        return
    jobs = [(family, source_id) for family, source_id in ids.items() if family in DETAIL_FAMILIES]
    detail: Dict[str, Any] = {}
    used = list(tried)
    def _detail_getter(url, headers=None):
        if headers:
            return fetch_url(url, headers=headers, timeout=12)
        return fetch_url(url, timeout=12)

    getter = getter or _detail_getter
    from concurrent.futures import ThreadPoolExecutor

    def _one(item):
        family, source_id = item
        return family, fetch_family_detail(family, source_id, getter=getter)

    if len(jobs) == 1:
        family, source_id = jobs[0]
        if not (family in tried and _fresh(extra, row.status or "") and extra.get("detail_empty") is False):
            _merge_detail(detail, fetch_family_detail(family, source_id, getter=getter))
            used.append(family)
    else:
        with ThreadPoolExecutor(max_workers=min(3, len(jobs))) as pool:
            for family, part in pool.map(_one, jobs):
                used.append(family)
                _merge_detail(detail, part)
    extra["detail_families_tried"] = list(dict.fromkeys(used))
    extra["detail_fetched_at"] = datetime.utcnow().isoformat()
    extra["parser_rev"] = PARSER_REV
    if not detail:
        extra["detail_empty"] = True
        extra["detail_negative"] = True
        extra["lineups_absent"] = True
        row.extra_json = dump_json(extra)
        return
    record = db.get(SportsEventDetail, row.event_id)
    if record is None:
        record = SportsEventDetail(event_id=row.event_id)
        db.add(record)
    if detail.get("incidents") and not load_json(record.incidents_json):
        record.incidents_json = dump_json(detail["incidents"])
    if detail.get("statistics") and not load_json(record.statistics_json):
        record.statistics_json = dump_json(detail["statistics"])
    if detail.get("lineups") and not load_json(record.lineups_json):
        record.lineups_json = dump_json(detail["lineups"])
    if detail.get("periods") and not extra.get("periods"):
        extra["periods"] = detail["periods"]
    for key in ("venue", "referee", "attendance"):
        if detail.get(key) and not extra.get(key):
            extra[key] = detail[key]
    if detail.get("player_statistics"):
        extra["player_statistics"] = extra.get("player_statistics") or detail["player_statistics"]
    if detail.get("sport_detail"):
        extra["sport_detail"] = extra.get("sport_detail") or detail["sport_detail"]
    if detail.get("classification"):
        extra["classification"] = extra.get("classification") or detail["classification"]
    if detail.get("maps"):
        extra["maps"] = extra.get("maps") or detail["maps"]
    if detail.get("referee"):
        extra["referee"] = extra.get("referee") or detail["referee"]
    extra["detail_empty"] = False
    extra["detail_negative"] = False
    extra["lineups_absent"] = not bool(detail.get("lineups") or load_json(record.lineups_json))
    row.extra_json = dump_json(extra)
    from collector.list_extra import store_list_extra

    store_list_extra(row, extra)
    record.updated_at = datetime.utcnow()
