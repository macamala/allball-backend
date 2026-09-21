"""On-demand rich-detail fetch. Never used by the score list path.

Score freshness stays on the collector cycle. This module fills timeline,
statistics, lineups, and sport_detail for a single event when a public
source id is already stored on the canonical row.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.adapters import FetchResult
from collector.http import fetch_url
from collector.models import SportsEvent, SportsEventDetail
from collector.util import dump_json, load_json

FOTMOB_DETAILS = "https://www.fotmob.com/api/data/matchDetails?matchId={match_id}"
SOFA_INCIDENTS = "https://www.sofascore.com/api/v1/event/{event_id}/incidents"
SOFA_STATS = "https://www.sofascore.com/api/v1/event/{event_id}/statistics"
SOFA_LINEUPS = "https://www.sofascore.com/api/v1/event/{event_id}/lineups"
MLB_FEED = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
NHL_LANDING = "https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"

TTL_LIVE = 45
TTL_SCHEDULED = 1800
TTL_FINISHED = 7 * 24 * 3600


def _ttl(status: str) -> int:
    value = (status or "").lower()
    if value in {"live", "inprogress"}:
        return TTL_LIVE
    if value in {"finished", "complete"}:
        return TTL_FINISHED
    return TTL_SCHEDULED


def _source_id(extra: Dict[str, Any], family: str) -> Optional[str]:
    ids = extra.get("source_event_ids") or []
    if isinstance(ids, list):
        for item in ids:
            text = str(item or "").strip()
            if text:
                return text.split(":")[-1]
    sid = str(extra.get("source_event_id") or "").strip()
    if sid:
        return sid.split(":")[-1]
    return None


def _fresh(extra: Dict[str, Any], status: str) -> bool:
    stamp = extra.get("detail_fetched_at")
    if not stamp:
        return False
    try:
        at = datetime.fromisoformat(str(stamp).replace("Z", ""))
    except ValueError:
        return False
    age = (datetime.utcnow() - at.replace(tzinfo=None)).total_seconds()
    return age < _ttl(status)


def parse_fotmob_details(payload: Any) -> Dict[str, Any]:
    content = payload.get("content") if isinstance(payload, dict) else {}
    if not isinstance(content, dict):
        content = payload if isinstance(payload, dict) else {}
    out: Dict[str, Any] = {}
    events = content.get("matchFacts") or content.get("events") or {}
    if isinstance(events, dict):
        rows = events.get("events") or events.get("list") or []
    else:
        rows = events if isinstance(events, list) else []
    timeline = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or item.get("eventType") or item.get("key") or "").lower()
        player = item.get("name") or item.get("player") or (item.get("playerObj") or {}).get("name")
        if isinstance(player, dict):
            player = player.get("name")
        minute = item.get("time") or item.get("minute")
        assist = item.get("assistStr") or item.get("assist")
        if isinstance(assist, dict):
            assist = assist.get("name")
        timeline.append(
            {
                "type": kind or "event",
                "minute": minute,
                "player": player,
                "assist": assist,
                "side": "home" if item.get("isHome") else "away" if item.get("isHome") is False else None,
                "score_after": {"home": item.get("homeScore"), "away": item.get("awayScore")}
                if item.get("homeScore") is not None or item.get("awayScore") is not None
                else None,
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
    lineup = content.get("lineup") or content.get("lineups") or {}
    sides = lineup.get("lineup") if isinstance(lineup, dict) else None
    if isinstance(sides, list) and len(sides) >= 2:
        def pack(side: Dict[str, Any]) -> Dict[str, Any]:
            players = []
            bench = []
            for group in side.get("players") or []:
                rows = group if isinstance(group, list) else [group]
                for player in rows:
                    if not isinstance(player, dict):
                        continue
                    name = ((player.get("name") or {}) if isinstance(player.get("name"), dict) else {"fullName": player.get("name")}).get("fullName") or player.get("name")
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
    linescore = game.get("linescore") or live.get("liveData", {}).get("linescore") or {}
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
            }
        )
    if innings:
        out["periods"] = innings
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
    mapping = (
        ("runs", "Runs"),
        ("hits", "Hits"),
        ("errors", "Errors"),
    )
    home_team = (teams.get("home") or {}).get("teamStats") or {}
    away_team = (teams.get("away") or {}).get("teamStats") or {}
    batting_h = home_team.get("batting") or {}
    batting_a = away_team.get("batting") or {}
    for key, label in mapping:
        if batting_h.get(key) is not None or batting_a.get(key) is not None:
            stats.append({"label": label, "home": batting_h.get(key), "away": batting_a.get(key)})
    if stats:
        out["statistics"] = stats
    players = []
    for side_name, side in (("home", teams.get("home") or {}), ("away", teams.get("away") or {})):
        for pid, player in (side.get("players") or {}).items():
            person = player.get("person") or {}
            name = person.get("fullName")
            if not name:
                continue
            bat = player.get("stats") or {}
            batting = bat.get("batting") or {}
            players.append(
                {
                    "name": name,
                    "side": side_name,
                    "hits": batting.get("hits"),
                    "at_bats": batting.get("atBats"),
                    "rbi": batting.get("rbi"),
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
    for period in scoring:
        for goal in period.get("goals") or []:
            if not isinstance(goal, dict):
                continue
            name = (goal.get("name") or {}).get("default") if isinstance(goal.get("name"), dict) else goal.get("name")
            timeline.append(
                {
                    "type": "goal",
                    "period": period.get("periodDescriptor", {}).get("number") if isinstance(period.get("periodDescriptor"), dict) else period.get("period"),
                    "player": name,
                    "minute": goal.get("timeInPeriod"),
                    "side": "home" if goal.get("homeScore") is not None else None,
                    "score_after": {"home": goal.get("homeScore"), "away": goal.get("awayScore")},
                }
            )
    if timeline:
        out["incidents"] = timeline
    team_stats = []
    home = payload.get("homeTeam") or {}
    away = payload.get("awayTeam") or {}
    if home.get("sog") is not None or away.get("sog") is not None:
        team_stats.append({"label": "Shots", "home": home.get("sog"), "away": away.get("sog")})
    if team_stats:
        out["statistics"] = team_stats
    return out


def _get(getter, url: str) -> FetchResult:
    try:
        return getter(url)
    except TypeError:
        return getter(url)


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
        inc = _get(getter, SOFA_INCIDENTS.format(event_id=source_event_id))
        if inc.ok and isinstance(inc.payload, dict):
            rows = parse_sofa_incidents(inc.payload)
            if rows:
                out["incidents"] = rows
        stats = _get(getter, SOFA_STATS.format(event_id=source_event_id))
        if stats.ok and isinstance(stats.payload, dict):
            rows = parse_sofa_statistics(stats.payload)
            if rows:
                out["statistics"] = rows
        line = _get(getter, SOFA_LINEUPS.format(event_id=source_event_id))
        if line.ok and isinstance(line.payload, dict):
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
        result = _get(getter, NHL_LANDING.format(game_id=source_event_id.replace("nhl:", "")))
        if result.ok and isinstance(result.payload, dict):
            out.update(parse_nhl_landing(result.payload))
        return out
    return out


def enrich_event_row(db: Session, row: SportsEvent, getter=None) -> None:
    extra = load_json(row.extra_json, {}) or {}
    family = str(extra.get("source_family") or "")
    if not family or _fresh(extra, row.status or ""):
        return
    source_id = _source_id(extra, family)
    if not source_id:
        return
    started = time.perf_counter()
    if time.perf_counter() - started > 12:
        return
    detail = fetch_family_detail(family, source_id, getter=getter)
    if not detail:
        extra["detail_fetched_at"] = datetime.utcnow().isoformat()
        extra["detail_empty"] = True
        row.extra_json = dump_json(extra)
        return
    record = db.get(SportsEventDetail, row.event_id)
    if record is None:
        record = SportsEventDetail(event_id=row.event_id)
        db.add(record)
    if detail.get("incidents") and not load_json(record.incidents_json):
        record.incidents_json = dump_json(detail["incidents"])
        extra["incidents"] = extra.get("incidents") or detail["incidents"]
    if detail.get("statistics") and not load_json(record.statistics_json):
        record.statistics_json = dump_json(detail["statistics"])
        extra["statistics"] = extra.get("statistics") or detail["statistics"]
    if detail.get("lineups") and not load_json(record.lineups_json):
        record.lineups_json = dump_json(detail["lineups"])
        extra["lineups"] = extra.get("lineups") or detail["lineups"]
    if detail.get("periods") and not extra.get("periods"):
        extra["periods"] = detail["periods"]
    if detail.get("player_statistics"):
        extra["player_statistics"] = extra.get("player_statistics") or detail["player_statistics"]
    extra["detail_fetched_at"] = datetime.utcnow().isoformat()
    extra["detail_empty"] = False
    row.extra_json = dump_json(extra)
    record.updated_at = datetime.utcnow()
