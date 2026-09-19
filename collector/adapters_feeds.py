"""Public unauthenticated JSON feeds used by official/public sites.

Reuse risk is recorded on the source row. Technical collectability is independent.
Does not bypass 401/403/CAPTCHA/Cloudflare.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.http import fetch_url
from collector.util import slugify


def loc(value: Any) -> str:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("Description") or first.get("Name") or "")
        return str(first)
    if isinstance(value, dict):
        return str(value.get("Description") or value.get("Name") or "")
    return str(value or "")


FIFA_COMPETITION_NEEDLES: Dict[str, List[str]] = {
    "africa-cup-of-nations": ["africa cup of nations", "african cup of nations", "afcon", "caf africa cup"],
    "uefa-champions-league": ["uefa champions league", "champions league"],
}


def _filter(events: List[Dict[str, Any]], capability: str) -> List[Dict[str, Any]]:
    if capability in {"snapshot", "event"}:
        return events
    if capability == "live_scores":
        return [row for row in events if row.get("status") == "live"]
    if capability == "results":
        return [row for row in events if row.get("status") == "finished"]
    if capability == "fixtures":
        return [row for row in events if row.get("status") == "scheduled"]
    return events


class FifaFootballAdapter:
    adapter_key = "fifa-json"
    source_id = "fifa"

    def __init__(self, source_id: str = "fifa", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        live = self._get("https://api.fifa.com/api/v3/live/football?language=en")
        calendar = self._get("https://api.fifa.com/api/v3/calendar/matches?count=50&language=en")
        if not live.ok and not calendar.ok:
            return live if not live.ok else calendar
        events = []
        seen = set()
        for payload in (live.payload, calendar.payload):
            rows = payload.get("Results") if isinstance(payload, dict) else None
            for row in rows or []:
                event = self._event(row)
                if event and event["id"] not in seen:
                    seen.add(event["id"])
                    events.append(event)
        if request.competition_id:
            events = self._scoped_events(events, request.competition_id)
        return FetchResult(ok=True, http_status=200, events=_filter(events, request.capability))

    def _scoped_events(self, events: List[Dict[str, Any]], competition_id: str) -> List[Dict[str, Any]]:
        cid = competition_id
        if cid in {"fifa-connected-competitions"}:
            return [event for event in events if str(event.get("sport") or "football") == "football"]
        if cid.startswith("fifa-futsal"):
            return [
                event
                for event in events
                if "futsal" in str(event.get("competition") or "").lower()
                and event_is_valid(event, sport_id="futsal", competition_id=cid)
            ]
        needles = FIFA_COMPETITION_NEEDLES.get(cid)
        if needles is None:
            needles = [part for part in cid.split("-") if len(part) > 3]
        if not needles:
            return []
        return [
            event
            for event in events
            if any(needle in str(event.get("competition") or "").lower() for needle in needles)
        ]

    def _event(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        home = row.get("HomeTeam") or {}
        away = row.get("AwayTeam") or {}
        home_name = loc(home.get("TeamName"))
        away_name = loc(away.get("TeamName"))
        if not home_name or not away_name:
            return None
        competition = loc(row.get("CompetitionName")) or "FIFA competition"
        home_score = home.get("Score")
        status_code = row.get("MatchStatus")
        if status_code in {0, 10} or (home_score is not None and row.get("Winner")):
            status = "finished"
        elif status_code in {3, 4, 7, 8, 12}:
            status = "live"
        else:
            status = "scheduled"
        stadium = row.get("Stadium") if isinstance(row.get("Stadium"), dict) else {}
        return {
            "id": f"fifa:{row.get('IdMatch')}",
            "home": {"id": str(home.get("IdTeam") or ""), "name": home_name},
            "away": {"id": str(away.get("IdTeam") or ""), "name": away_name},
            "status": status,
            "score": {"home": home_score, "away": away.get("Score")},
            "start_time": row.get("Date"),
            "venue": loc(stadium.get("Name")),
            "sport": "football",
            "competition": competition,
            "competition_key": f"football-{slugify(competition)}",
            "event_family": "team_match",
        }


class NhlAdapter:
    adapter_key = "nhl-web"
    source_id = "nhl-web"

    def __init__(self, source_id: str = "nhl-web", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get("https://api-web.nhle.com/v1/schedule/now")
        if not result.ok:
            return result
        events = []
        for day in (result.payload or {}).get("gameWeek") or []:
            for row in day.get("games") or []:
                events.append(self._event(row))
        return FetchResult(
            ok=True,
            http_status=result.http_status,
            payload=result.payload,
            events=_filter(events, request.capability),
        )

    def _event(self, row: Dict[str, Any]) -> Dict[str, Any]:
        home = row.get("homeTeam") or {}
        away = row.get("awayTeam") or {}
        place = home.get("placeName") if isinstance(home.get("placeName"), dict) else {}
        away_place = away.get("placeName") if isinstance(away.get("placeName"), dict) else {}
        state = str(row.get("gameState") or "")
        if state in {"OFF", "FINAL"}:
            status = "finished"
        elif state in {"LIVE", "CRIT"}:
            status = "live"
        else:
            status = "scheduled"
        venue = row.get("venue") if isinstance(row.get("venue"), dict) else {}
        return {
            "id": f"nhl:{row.get('id')}",
            "home": {"id": str(home.get("id") or ""), "name": home.get("abbrev") or place.get("default") or ""},
            "away": {"id": str(away.get("id") or ""), "name": away.get("abbrev") or away_place.get("default") or ""},
            "status": status,
            "score": {"home": home.get("score"), "away": away.get("score")},
            "start_time": row.get("startTimeUTC"),
            "venue": venue.get("default"),
            "competition": "nhl",
        }


class MlbAdapter:
    adapter_key = "mlb-statsapi"
    source_id = "mlb-statsapi"

    def __init__(self, source_id: str = "mlb-statsapi", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get("https://statsapi.mlb.com/api/v1/schedule?sportId=1")
        if not result.ok:
            return result
        events = []
        for day in (result.payload or {}).get("dates") or []:
            for row in day.get("games") or []:
                events.append(self._event(row))
        return FetchResult(
            ok=True,
            http_status=result.http_status,
            payload=result.payload,
            events=_filter(events, request.capability),
        )

    def _event(self, row: Dict[str, Any]) -> Dict[str, Any]:
        teams = row.get("teams") or {}
        home = (teams.get("home") or {}).get("team") or {}
        away = (teams.get("away") or {}).get("team") or {}
        abstract = ((row.get("status") or {}).get("abstractGameState") or "").lower()
        if abstract == "final":
            status = "finished"
        elif abstract == "live":
            status = "live"
        else:
            status = "scheduled"
        return {
            "id": f"mlb:{row.get('gamePk')}",
            "home": {"id": str(home.get("id") or ""), "name": home.get("name") or ""},
            "away": {"id": str(away.get("id") or ""), "name": away.get("name") or ""},
            "status": status,
            "score": {
                "home": (teams.get("home") or {}).get("score"),
                "away": (teams.get("away") or {}).get("score"),
            },
            "start_time": row.get("gameDate"),
            "venue": (row.get("venue") or {}).get("name"),
            "competition": "mlb",
        }


class KhlAdapter:
    adapter_key = "khl-mobile"
    source_id = "khl-mobile"

    def __init__(self, source_id: str = "khl-mobile", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get("https://khl.api.webcaster.pro/api/khl_mobile/events_v2.json")
        if not result.ok:
            return result
        events = []
        for wrap in result.payload if isinstance(result.payload, list) else []:
            row = wrap.get("event") if isinstance(wrap, dict) else None
            if not isinstance(row, dict):
                continue
            events.append(self._event(row))
        return FetchResult(ok=True, http_status=result.http_status, events=_filter(events, request.capability))

    def _event(self, row: Dict[str, Any]) -> Dict[str, Any]:
        home = row.get("team_a") if isinstance(row.get("team_a"), dict) else {}
        away = row.get("team_b") if isinstance(row.get("team_b"), dict) else {}
        state = str(row.get("game_state_key") or "").lower()
        if "finish" in state or state in {"over", "ended", "final"}:
            status = "finished"
        elif "live" in state or "progress" in state:
            status = "live"
        else:
            status = "scheduled"
        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        return {
            "id": f"khl:{row.get('id') or row.get('khl_id')}",
            "home": {"id": str(home.get("id") or ""), "name": home.get("name") or home.get("title") or ""},
            "away": {"id": str(away.get("id") or ""), "name": away.get("name") or away.get("title") or ""},
            "status": status,
            "score": {"home": home.get("score"), "away": away.get("score")},
            "start_time": row.get("start_at") or row.get("start_at_iso"),
            "venue": location.get("name"),
            "competition": "khl",
        }


class WorldRugbyAdapter:
    adapter_key = "world-rugby-rims"
    source_id = "world-rugby"

    def __init__(self, source_id: str = "world-rugby", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get("https://api.wr-rims-prod.pulselive.com/rugby/v3/match?pageSize=30&sport=mru")
        if not result.ok:
            return result
        events = []
        for row in (result.payload or {}).get("content") or []:
            event = self._event(row)
            if event:
                events.append(event)
        if request.competition_id == "super-rugby":
            events = [
                event
                for event in events
                if "super rugby" in str(event.get("competition") or "").lower()
            ]
        return FetchResult(ok=True, http_status=result.http_status, events=_filter(events, request.capability))

    def _event(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        teams = row.get("teams") or []
        if len(teams) < 2:
            return None
        scores = row.get("scores") or [None, None]
        state = str(row.get("status") or "")
        if state == "C":
            status = "finished"
        elif state == "L":
            status = "live"
        else:
            status = "scheduled"
        competition = row.get("competition") or {}
        name = competition.get("name") if isinstance(competition, dict) else loc(competition)
        name = name or "Rugby"
        start = (row.get("time") or {}).get("label")
        if start and "T" not in str(start):
            start = f"{start}T00:00:00Z"
        return {
            "id": f"worldrugby:{row.get('matchId')}",
            "home": {"id": str(teams[0].get("id") or ""), "name": teams[0].get("name") or ""},
            "away": {"id": str(teams[1].get("id") or ""), "name": teams[1].get("name") or ""},
            "status": status,
            "score": {
                "home": scores[0] if len(scores) > 0 else None,
                "away": scores[1] if len(scores) > 1 else None,
            },
            "start_time": start,
            "venue": (row.get("venue") or {}).get("name"),
            "sport": "rugby",
            "competition": name,
            "competition_key": f"rugby-{slugify(name)}",
            "event_family": "team_match",
        }


class JolpicaF1Adapter:
    adapter_key = "jolpica-f1"
    source_id = "jolpica"

    def __init__(self, source_id: str = "jolpica", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        if request.capability == "live_scores":
            return FetchResult(ok=True, http_status=200, events=[])
        path = "current/results.json" if request.capability == "results" else "current.json"
        result = self._get(f"https://api.jolpi.ca/ergast/f1/{path}")
        if not result.ok:
            return result
        races = (((result.payload or {}).get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
        events = [self._event(row, request.capability) for row in races]
        events = [row for row in events if row]
        return FetchResult(ok=True, http_status=result.http_status, events=events)

    def _event(self, row: Dict[str, Any], capability: str) -> Optional[Dict[str, Any]]:
        results = row.get("Results") or []
        winner = results[0] if results else {}
        driver = winner.get("Driver") or {}
        date = row.get("date")
        time_value = row.get("time") or "00:00:00Z"
        start = f"{date}T{time_value}" if date else None
        finished = bool(results)
        if capability == "results" and not finished:
            return None
        if capability == "fixtures" and finished:
            return None
        return {
            "id": f"jolpica:{row.get('season')}:{row.get('round')}",
            "home": {"name": driver.get("familyName") or row.get("raceName") or "F1"},
            "away": {"name": (row.get("Circuit") or {}).get("circuitName") or ""},
            "status": "finished" if finished else "scheduled",
            "score": {"home": winner.get("position"), "away": None},
            "start_time": start,
            "venue": (row.get("Circuit") or {}).get("circuitName"),
            "competition": "formula-1",
            "series_id": "formula-1",
        }


class EuroleagueLiveAdapter:
    adapter_key = "euroleague-live"
    source_id = "euroleague-live"

    def __init__(self, source_id: str = "euroleague-live", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        now = datetime.now(timezone.utc)
        season = f"E{now.year}" if now.month >= 9 else f"E{now.year - 1}"
        result = self._get(f"https://live.euroleague.net/api/Header?gamecode=1&seasoncode={season}")
        if not result.ok:
            result = self._get("https://live.euroleague.net/api/Header?gamecode=1&seasoncode=E2025")
        if not result.ok or not isinstance(result.payload, dict):
            return result
        row = result.payload
        live_flag = row.get("Live")
        status = "live" if live_flag else "scheduled"
        if row.get("ScoreA") is not None and row.get("ScoreB") is not None and not live_flag:
            status = "finished"
        event = {
            "id": f"euroleague:{season}:1",
            "home": {"name": row.get("TeamA") or ""},
            "away": {"name": row.get("TeamB") or ""},
            "status": status,
            "score": {"home": row.get("ScoreA"), "away": row.get("ScoreB")},
            "start_time": None,
            "venue": row.get("Stadium"),
            "competition": "euroleague",
        }
        return FetchResult(ok=True, http_status=result.http_status, events=_filter([event], request.capability))
