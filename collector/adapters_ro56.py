"""Reusable $0 collectors proven or structured from Railway public transports.

Not wired into source_matrix_final.json. Live status is only taken from source fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

LOL_API = "https://esports-api.lolesports.com/persisted/gw"
# Public website key used by lolesports.com (not a private credential).
LOL_WEB_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"

LOL_LEAGUE_SLUGS: Dict[str, str] = {
    "lol-world-championship": "worlds",
}

CFL_ROUNDS = "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"
CFL_SQUADS = "https://cflscoreboard.cfl.ca/json/scoreboard/squads.json"

F1_INDEX = "https://livetiming.formula1.com/static/{year}/Index.json"
F1_STREAM = "https://livetiming.formula1.com/static/StreamStatus.json"

WA_COMPETITIONS = "https://api.worldaquatics.com/fina/competitions?pageSize=40"


def _asset_url(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    for key in ("logo", "logoUrl", "image", "imageUrl", "badge", "crest", "teamLogo", "icon"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            href = value.get("url") or value.get("href") or value.get("src")
            if isinstance(href, str) and href.strip():
                return href.strip()
    for key in ("logos", "images", "assets"):
        rows = node.get(key)
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, dict):
                    href = item.get("url") or item.get("href") or item.get("src")
                    if isinstance(href, str) and href.strip():
                        return href.strip()
    return ""


def _cfl_squad_assets(payload: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            logo = _asset_url(node)
            keys = [
                node.get("id"), node.get("squadId"), node.get("teamId"),
                node.get("abbreviation"), node.get("abbr"), node.get("shortName"),
                node.get("name"),
            ]
            if logo:
                for value in keys:
                    text = str(value or "").strip().lower()
                    if text:
                        out[text] = logo
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def _filter(events: List[Dict[str, Any]], capability: str) -> List[Dict[str, Any]]:
    if capability in {"snapshot", "event", "live"}:
        return events
    if capability == "live_scores":
        return [row for row in events if row.get("status") == "live"]
    if capability == "results":
        return [row for row in events if row.get("status") == "finished"]
    if capability == "fixtures":
        return [row for row in events if row.get("status") == "scheduled"]
    return events


class CflScoreboardAdapter:
    """Official CFL scoreboard JSON (cflscoreboard.cfl.ca), not ESPN."""

    adapter_key = "cfl-scoreboard-json"
    source_id = "cfl-scoreboard"

    def __init__(self, source_id: str = "cfl-scoreboard", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        rounds = self._get(CFL_ROUNDS)
        if not rounds.ok:
            return rounds
        payload = rounds.payload
        squad_assets: Dict[str, str] = {}
        squads = self._get(CFL_SQUADS)
        if squads.ok:
            squad_assets = _cfl_squad_assets(squads.payload)
        events = self._events(payload, squad_assets=squad_assets)
        return FetchResult(ok=True, http_status=rounds.http_status, events=_filter(events, request.capability))

    def _events(self, payload: Any, squad_assets: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        rows = payload
        if isinstance(payload, dict):
            rows = payload.get("rounds") or payload.get("games") or payload.get("data") or []
        if not isinstance(rows, list):
            rows = []
        for round_row in rows:
            if not isinstance(round_row, dict):
                continue
            games = round_row.get("tournaments") or round_row.get("games") or round_row.get("matches") or []
            for game in games:
                event = self._game(game, squad_assets=squad_assets)
                if event:
                    events.append(event)
        return events

    def _game(self, game: Dict[str, Any], squad_assets: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        home = game.get("homeSquad") or game.get("home") or game.get("team1") or game.get("homeTeam") or {}
        away = game.get("awaySquad") or game.get("away") or game.get("team2") or game.get("awayTeam") or {}
        if not isinstance(home, dict):
            home = {"name": str(home)}
        if not isinstance(away, dict):
            away = {"name": str(away)}
        home_name = home.get("name") or home.get("shortName") or home.get("abbreviation") or ""
        away_name = away.get("name") or away.get("shortName") or away.get("abbreviation") or ""
        if not home_name or not away_name:
            return None
        raw = str(game.get("status") or game.get("gameStatus") or game.get("state") or "").lower()
        if raw in {"live", "inprogress", "in_progress", "in-progress"}:
            status = "live"
        elif raw in {"final", "complete", "completed", "finished"}:
            status = "finished"
        else:
            status = "scheduled"
        score = {
            "home": home.get("score") if status != "scheduled" else None,
            "away": away.get("score") if status != "scheduled" else None,
        }
        clock = game.get("clock") or game.get("timeRemaining") or game.get("displayClock")
        period = game.get("activePeriod") or game.get("quarter") or game.get("period")
        if game.get("possession") not in (None, "", "None"):
            score["possession"] = game.get("possession")
        if clock not in (None, ""):
            score["clock"] = clock
        if period not in (None, ""):
            score["period"] = period
        assets = squad_assets or {}
        def squad_logo(side: Dict[str, Any], name: str) -> str:
            direct = _asset_url(side)
            if direct:
                return direct
            for value in (
                side.get("id"), side.get("squadId"), side.get("teamId"),
                side.get("abbreviation"), side.get("abbr"), side.get("shortName"), name,
            ):
                key = str(value or "").strip().lower()
                if key and assets.get(key):
                    return assets[key]
            return ""

        return {
            "id": f"cfl:{game.get('id') or game.get('gameId') or home_name}-{away_name}",
            "home": {"id": str(home.get("id") or ""), "name": str(home_name), "logo": squad_logo(home, str(home_name))},
            "away": {"id": str(away.get("id") or ""), "name": str(away_name), "logo": squad_logo(away, str(away_name))},
            "status": status,
            "score": score,
            "start_time": game.get("startTime") or game.get("date") or game.get("kickoff"),
            "sport": "canadian-football",
            "competition": "CFL",
            "competition_key": "cfl",
            "event_family": "team_match",
            "source_family": "cfl-scoreboard-json",
            "source_event_id": str(game.get("id") or game.get("gameId") or game.get("cflId") or ""),
            "source_event_ids": {
                "cfl-scoreboard-json": str(game.get("id") or game.get("gameId") or game.get("cflId") or "")
            },
            "extra": {
                "source_family": "cfl-scoreboard-json",
                "source_event_id": str(game.get("id") or game.get("gameId") or game.get("cflId") or ""),
                "source_event_ids": {
                    "cfl-scoreboard-json": str(game.get("id") or game.get("gameId") or game.get("cflId") or "")
                },
            },
        }


class LolEsportsAdapter:
    """lolesports.com persisted Graph/REST used by the public site."""

    adapter_key = "lolesports-json"
    source_id = "lolesports"

    def __init__(self, source_id: str = "lolesports", getter=None):
        self.source_id = source_id
        self._get = getter or (lambda url: fetch_url(url, headers={"x-api-key": LOL_WEB_KEY}))

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        slug = LOL_LEAGUE_SLUGS.get(request.competition_id or "", "worlds")
        leagues = self._get(f"{LOL_API}/getLeagues?hl=en-US")
        if not leagues.ok:
            return leagues
        league_id = self._league_id(leagues.payload, slug)
        if not league_id:
            return FetchResult(ok=True, http_status=leagues.http_status, events=[])
        schedule = self._get(f"{LOL_API}/getSchedule?hl=en-US&leagueId={league_id}")
        if not schedule.ok:
            return schedule
        events = []
        rows = (((schedule.payload or {}).get("data") or {}).get("schedule") or {}).get("events") or []
        for row in rows:
            event = self._event(row)
            if event:
                events.append(event)
        return FetchResult(ok=True, http_status=schedule.http_status, events=_filter(events, request.capability))

    def _league_id(self, payload: Any, slug: str) -> str:
        leagues = (((payload or {}).get("data") or {}).get("leagues") or [])
        for row in leagues:
            if str(row.get("slug") or "").lower() == slug:
                return str(row.get("id") or "")
        return ""

    def _event(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        match = row.get("match") or {}
        teams = match.get("teams") or []
        if len(teams) < 2:
            return None
        state = str(row.get("state") or "").lower()
        if state in {"inprogress", "in_progress", "live"}:
            status = "live"
        elif state in {"completed", "finished"}:
            status = "finished"
        else:
            status = "scheduled"
        home, away = teams[0], teams[1]
        home_wins = (home.get("result") or {}).get("gameWins")
        away_wins = (away.get("result") or {}).get("gameWins")
        score = {
            "home": home_wins if status != "scheduled" else None,
            "away": away_wins if status != "scheduled" else None,
        }
        return {
            "id": f"lolesports:{match.get('id') or row.get('startTime')}",
            "home": {"id": str(home.get("code") or ""), "name": home.get("name") or home.get("code") or ""},
            "away": {"id": str(away.get("code") or ""), "name": away.get("name") or away.get("code") or ""},
            "status": status,
            "score": score,
            "start_time": row.get("startTime"),
            "sport": "esports-lol",
            "competition": (row.get("league") or {}).get("name") or "Worlds",
            "competition_key": "lol-world-championship",
            "event_family": "team_match",
            "source_family": "lolesports-json",
            "source_event_id": str(match.get("id") or row.get("startTime") or ""),
            "source_event_ids": {"lolesports-json": str(match.get("id") or "")},
            "extra": {
                "source_family": "lolesports-json",
                "source_event_id": str(match.get("id") or ""),
                "source_event_ids": {"lolesports-json": str(match.get("id") or "")},
            },
        }


class F1LiveTimingIndexAdapter:
    """Official livetiming.formula1.com year Index (schedule/session discovery)."""

    adapter_key = "f1-livetiming-index"
    source_id = "f1-livetiming"

    def __init__(self, source_id: str = "f1-livetiming", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        year = datetime.now(timezone.utc).year
        index = self._get(F1_INDEX.format(year=year))
        if not index.ok:
            return index
        events = []
        for meeting in (index.payload or {}).get("Meetings") or []:
            event = self._meeting(meeting)
            if event:
                events.append(event)
        return FetchResult(ok=True, http_status=index.http_status, events=_filter(events, request.capability))

    def _meeting(self, meeting: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name = meeting.get("Name") or meeting.get("MeetingName") or "Formula 1"
        sessions = meeting.get("Sessions") or []
        race = next((s for s in sessions if str(s.get("Type") or "").lower() == "race"), sessions[-1] if sessions else {})
        start = race.get("StartDate") or meeting.get("StartDate")
        if start and "T" in str(start) and "Z" not in str(start) and "+" not in str(start):
            start = f"{start}Z"
        now = datetime.now(timezone.utc)
        status = "scheduled"
        try:
            if start:
                when = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
                end = race.get("EndDate")
                if end:
                    until = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=timezone.utc)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if when <= now <= until:
                        status = "scheduled"
        except ValueError:
            status = "scheduled"
        return {
            "id": f"f1:{meeting.get('Key') or name}",
            "home": {"id": "field", "name": name},
            "away": {"id": "grid", "name": "Grid"},
            "status": status,
            "score": {"home": None, "away": None},
            "start_time": start,
            "sport": "motorsport",
            "competition": "Formula 1",
            "competition_key": "formula-1",
            "event_family": "motorsport_race",
            "source_family": "f1-livetiming-index",
        }


class WorldAquaticsApiAdapter:
    """api.worldaquatics.com /fina/competitions public catalog."""

    adapter_key = "world-aquatics-api"
    source_id = "world-aquatics-api"

    def __init__(self, source_id: str = "world-aquatics-api", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        from collector.source_family_closeout import parse_world_aquatics_discipline

        discipline = self._get("https://api.worldaquatics.com/fina/events/a76c06d2-2982-4fb1-8bee-b48b44d6cbc2")
        if discipline.ok:
            parsed = parse_world_aquatics_discipline(discipline.payload, competition_id="5135")
            if parsed.get("events"):
                return FetchResult(
                    ok=True,
                    http_status=discipline.http_status or 200,
                    events=parsed["events"],
                    standings=parsed.get("standings") or [],
                    parse_status="ok",
                    parse_reason="api.worldaquatics.com competition 5135 discipline results",
                )
        result = self._get(WA_COMPETITIONS)
        if not result.ok:
            return result
        payload = result.payload
        rows = payload
        if isinstance(payload, dict):
            rows = payload.get("content") or payload.get("competitions") or payload.get("data") or []
        events: List[Dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            name = row.get("name") or row.get("Name") or row.get("title") or ""
            if not name:
                continue
            cid = request.competition_id or ""
            if cid == "nordic-water-polo-league" and "water polo" not in str(name).lower() and "nordic" not in str(name).lower():
                continue
            start = row.get("startDate") or row.get("StartDate") or row.get("dateFrom")
            events.append(
                {
                    "id": f"wa:{row.get('id') or row.get('Id') or name}",
                    "home": {"id": "field", "name": str(name)},
                    "away": {"id": "program", "name": "Program"},
                    "status": "scheduled",
                    "score": {"home": None, "away": None},
                    "start_time": start,
                    "sport": "aquatics",
                    "competition": name,
                    "competition_key": cid or "world-aquatics-events",
                    "event_family": "meet",
                    "source_family": "world-aquatics-api",
                    "source_event_ids": {"world-aquatics-api": str(row.get("id") or row.get("Id") or "")},
                }
            )
        return FetchResult(ok=True, http_status=result.http_status, events=_filter(events, request.capability))
