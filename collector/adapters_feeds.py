"""Public unauthenticated JSON feeds used by official/public sites.

Reuse risk is recorded on the source row. Technical collectability is independent.
Does not bypass 401/403/CAPTCHA/Cloudflare.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.http import fetch_text, fetch_url
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

def _asset_url(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    for key in (
        "logo", "Logo", "image", "Image", "badge", "Badge", "crest", "Crest",
        "picture", "Picture", "pictureUrl", "PictureUrl", "imageUrl", "ImageUrl",
        "logoUrl", "LogoUrl", "teamLogo", "TeamLogo", "darkLogo",
    ):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("url") or value.get("href") or value.get("src") or value.get("default")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def _feed_team(node: Any, fallback_name: str = "") -> Dict[str, Any]:
    row = node if isinstance(node, dict) else {}
    country = (
        row.get("country_id")
        or row.get("countryCode")
        or row.get("CountryCode")
        or row.get("nationality")
        or row.get("Nationality")
        or row.get("IdAssociation")
        or row.get("IdCountry")
    )
    if isinstance(country, dict):
        country = country.get("alpha2") or country.get("alpha3") or country.get("code") or country.get("name")
    name = (
        row.get("name")
        or row.get("title")
        or row.get("abbrev")
        or row.get("displayName")
        or fallback_name
        or ""
    )
    payload = {
        "id": str(row.get("id") or row.get("IdTeam") or row.get("teamId") or ""),
        "name": str(name or ""),
        "logo": _asset_url(row),
        "country_id": str(country or ""),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


FIFA_COMPETITION_NEEDLES: Dict[str, List[str]] = {
    "africa-cup-of-nations": ["africa cup of nations", "african cup of nations", "afcon", "caf africa cup"],
    "uefa-champions-league": ["uefa champions league"],
    "uefa-nations-league": ["uefa nations league"],
}

FIFA_RESULT_TYPE = {1: "FT", 2: "PSO", 3: "AET"}
FIFA_WORLD_CUP_WINDOW = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?from=2026-07-01&to=2026-07-20&count=100&language=en&idCompetition=17"
)
FIFA_WORLD_CUP_KNOCKOUT = (
    "https://api.fifa.com/api/v3/calendar/matches"
    "?from=2026-07-14&to=2026-07-20&count=50&language=en&idCompetition=17"
)


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
        world_cup = None
        knockout = None
        if request.competition_id == "fifa-connected-competitions":
            world_cup = self._get(FIFA_WORLD_CUP_WINDOW)
            knockout = self._get(FIFA_WORLD_CUP_KNOCKOUT)
        if not live.ok and not calendar.ok and not (world_cup and world_cup.ok) and not (knockout and knockout.ok):
            return live if not live.ok else calendar
        events = []
        seen = set()
        payloads = [live.payload, calendar.payload]
        for extra in (world_cup, knockout):
            if extra and extra.ok:
                payloads.append(extra.payload)
        for payload in payloads:
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
        # The global FIFA calendar contains many competitions with generic
        # names. Never infer a canonical mapping from slug tokens like
        # "premier", "league" or "nations": that contaminates unrelated
        # competitions (e.g. Ghana EPL / CONCACAF UEFA Nations League).
        if not needles:
            return []
        return [
            event
            for event in events
            if any(needle in str(event.get("competition") or "").lower() for needle in needles)
        ]

    def _event(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        home = row.get("HomeTeam") or row.get("Home") or {}
        away = row.get("AwayTeam") or row.get("Away") or {}
        if not isinstance(home, dict) or not isinstance(away, dict):
            return None
        home_name = loc(home.get("TeamName"))
        away_name = loc(away.get("TeamName"))
        if not home_name or not away_name:
            return None
        competition = loc(row.get("CompetitionName")) or "FIFA competition"
        source_competition_id = str(row.get("IdCompetition") or "")
        home_country = str(home.get("IdAssociation") or home.get("IdCountry") or "").strip().upper()
        away_country = str(away.get("IdAssociation") or away.get("IdCountry") or "").strip().upper()
        domestic_country = home_country if home_country and home_country == away_country else ""
        native_slug = slugify(competition)
        competition_key = (
            f"football-{domestic_country.lower()}-{native_slug}"
            if domestic_country
            else f"football-{native_slug}"
        )
        home_score = home.get("Score")
        if home_score is None:
            home_score = row.get("HomeTeamScore")
        away_score = away.get("Score")
        if away_score is None:
            away_score = row.get("AwayTeamScore")
        status_code = row.get("MatchStatus")
        if status_code in {0, 10} or (home_score is not None and row.get("Winner")):
            status = "finished"
        elif status_code in {3, 4, 7, 8, 12}:
            status = "live"
        else:
            status = "scheduled"
        stadium = row.get("Stadium") if isinstance(row.get("Stadium"), dict) else {}
        match_id = str(row.get("IdMatch") or "")
        result_code = row.get("ResultType")
        result_type = FIFA_RESULT_TYPE.get(result_code) if isinstance(result_code, int) else None
        home_pens = row.get("HomeTeamPenaltyScore")
        away_pens = row.get("AwayTeamPenaltyScore")
        if home_pens is not None or away_pens is not None:
            result_type = "PSO"
        score: Dict[str, Any] = {"home": home_score, "away": away_score}
        if result_type:
            score["result_type"] = result_type
        if home_pens is not None or away_pens is not None:
            score["home_penalties"] = home_pens
            score["away_penalties"] = away_pens
        return {
            "id": f"fifa:{match_id}",
            "home": {**_feed_team(home, home_name), "name": home_name, "country_id": home_country or _feed_team(home, home_name).get("country_id", "")},
            "away": {**_feed_team(away, away_name), "name": away_name, "country_id": away_country or _feed_team(away, away_name).get("country_id", "")},
            "status": status,
            "score": score,
            "start_time": row.get("Date"),
            "venue": loc(stadium.get("Name")),
            "sport": "football",
            "competition": competition,
            "competition_key": competition_key,
            "country_id": domestic_country or None,
            "event_family": "team_match",
            "source_family": "fifa-digital",
            "source_competition_id": source_competition_id or None,
            "source_competition_name": competition,
            "source_event_id": match_id,
            "source_event_ids": {"fifa-digital": match_id},
            "result_type": result_type,
            "round": str(row.get("MatchNumber") or "") or None,
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
        events: List[Dict[str, Any]] = []
        last = None
        if request.capability in {"live_scores", "snapshot"}:
            last = self._get("https://api-web.nhle.com/v1/score/now")
            if last.ok and isinstance(last.payload, dict):
                for row in last.payload.get("games") or []:
                    events.append(self._event(row))
        if request.capability != "live_scores" or not events:
            sched = self._get("https://api-web.nhle.com/v1/schedule/now")
            last = sched if last is None or not events else last
            if not sched.ok and not events:
                return sched
            seen = {event.get("id") for event in events}
            for day in (sched.payload or {}).get("gameWeek") or []:
                for row in day.get("games") or []:
                    event = self._event(row)
                    if event.get("id") not in seen:
                        events.append(event)
        return FetchResult(
            ok=True,
            http_status=(last.http_status if last else 200) or 200,
            payload=last.payload if last else None,
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
        score: Dict[str, Any] = {
            "home": home.get("score") if status != "scheduled" else None,
            "away": away.get("score") if status != "scheduled" else None,
        }
        period = (row.get("periodDescriptor") or {}).get("number") if isinstance(row.get("periodDescriptor"), dict) else row.get("period")
        clock = row.get("clock")
        if isinstance(clock, dict):
            clock = clock.get("timeRemaining") or clock.get("display")
        if period is not None:
            score["period"] = period
        if clock:
            score["clock"] = clock
        periods = None
        home_sog = home.get("sog")
        if isinstance(row.get("homeTeam"), dict) and row.get("awayTeam"):
            lines = row.get("periodScores") or row.get("linescore")
            if isinstance(lines, list) and lines:
                periods = []
                for index, item in enumerate(lines):
                    if not isinstance(item, dict):
                        continue
                    periods.append(
                        {
                            "period": item.get("period") or index + 1,
                            "home": item.get("home") or item.get("homeScore"),
                            "away": item.get("away") or item.get("awayScore"),
                        }
                    )
        event = {
            "id": f"nhl:{row.get('id')}",
            "home": _feed_team(home, home.get("abbrev") or place.get("default") or ""),
            "away": _feed_team(away, away.get("abbrev") or away_place.get("default") or ""),
            "status": status,
            "source_status": state or status,
            "score": score,
            "start_time": row.get("startTimeUTC"),
            "venue": venue.get("default"),
            "competition": "nhl",
            "sport": "ice-hockey",
            "source_family": "nhl-web",
            "source_event_id": str(row.get("id") or ""),
            "extra": {
                "source_family": "nhl-web",
                "source_event_ids": {"nhl-web": str(row.get("id") or "")},
                "source_event_id": str(row.get("id") or ""),
            },
        }
        if periods:
            event["periods"] = periods
        if home_sog is not None:
            event.setdefault("extra", {})["shots"] = {"home": home_sog, "away": away.get("sog")}
        return event


class MlbAdapter:
    adapter_key = "mlb-statsapi"
    source_id = "mlb-statsapi"

    def __init__(self, source_id: str = "mlb-statsapi", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        end = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        result = self._get(
            "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
            f"&hydrate=linescore,team&startDate={start}&endDate={end}"
        )
        if not result.ok:
            return result
        events = []
        for day in (result.payload or {}).get("dates") or []:
            for row in day.get("games") or []:
                events.append(self._event(row))
        if request.capability == "live_scores":
            events = [row for row in events if row.get("status") == "live"]
        elif request.capability == "results":
            events = [row for row in events if row.get("status") == "finished"]
        elif request.capability == "fixtures":
            # Official schedule includes in-progress games; dropping them here
            # prevents live_scores jobs from ever attaching after UTC midnight.
            events = [row for row in events if row.get("status") in {"scheduled", "live"}]
        return FetchResult(
            ok=True,
            http_status=result.http_status,
            payload=result.payload,
            events=events,
        )

    def _event(self, row: Dict[str, Any]) -> Dict[str, Any]:
        teams = row.get("teams") or {}
        home = (teams.get("home") or {}).get("team") or {}
        away = (teams.get("away") or {}).get("team") or {}
        status_block = row.get("status") or {}
        abstract = (status_block.get("abstractGameState") or "").lower()
        detailed = (status_block.get("detailedState") or "").lower()
        if abstract == "final" or "final" in detailed:
            status = "finished"
        elif abstract == "live" or "in progress" in detailed or "innings" in detailed:
            status = "live"
        else:
            status = "scheduled"
        home_score = (teams.get("home") or {}).get("score")
        away_score = (teams.get("away") or {}).get("score")
        if status == "scheduled":
            home_score = None
            away_score = None
        linescore = row.get("linescore") if isinstance(row.get("linescore"), dict) else {}
        score: Dict[str, Any] = {"home": home_score, "away": away_score}
        inning = linescore.get("currentInning")
        half = linescore.get("inningState") or linescore.get("inningHalf")
        if inning is not None and status != "scheduled":
            score["inning"] = inning
        if half and status == "live":
            score["inning_half"] = str(half).lower()
        if linescore.get("outs") is not None and status == "live":
            score["outs"] = linescore.get("outs")
        periods = []
        for item in linescore.get("innings") or []:
            if not isinstance(item, dict):
                continue
            periods.append(
                {
                    "period": item.get("num"),
                    "home": (item.get("home") or {}).get("runs"),
                    "away": (item.get("away") or {}).get("runs"),
                }
            )
        event = {
            "id": f"mlb:{row.get('gamePk')}",
            "home": {"id": str(home.get("id") or ""), "name": home.get("name") or ""},
            "away": {"id": str(away.get("id") or ""), "name": away.get("name") or ""},
            "status": status,
            "source_status": status_block.get("detailedState") or abstract or status,
            "score": score,
            "start_time": row.get("gameDate"),
            "venue": (row.get("venue") or {}).get("name"),
            "competition": "mlb",
            "sport": "baseball",
            "source_family": "mlb-statsapi",
            "source_event_id": str(row.get("gamePk") or ""),
            "extra": {
                "source_family": "mlb-statsapi",
                "source_event_ids": {"mlb-statsapi": str(row.get("gamePk") or "")},
                "source_event_id": str(row.get("gamePk") or ""),
            },
        }
        if periods:
            event["periods"] = periods
        return event


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
        score: Dict[str, Any] = {
            "home": home.get("score") if status != "scheduled" else None,
            "away": away.get("score") if status != "scheduled" else None,
        }
        period = row.get("period") or row.get("current_period") or row.get("period_id")
        clock = row.get("game_time") or row.get("time") or row.get("clock")
        if period not in (None, ""):
            score["period"] = period
        if clock not in (None, ""):
            score["clock"] = clock
        return {
            "id": f"khl:{row.get('id') or row.get('khl_id')}",
            "home": _feed_team(home, home.get("name") or home.get("title") or ""),
            "away": _feed_team(away, away.get("name") or away.get("title") or ""),
            "status": status,
            "score": score,
            "start_time": row.get("start_at") or row.get("start_at_iso"),
            "venue": location.get("name"),
            "competition": "khl",
        }


PULSELIVE_COMP_TOKENS: Dict[str, List[str]] = {
    "super-rugby": ["super rugby"],
    "premiership-rugby": ["premiership"],
    "france-top-14": ["top 14"],
    "france-pro-d2": ["pro d2", "prod2"],
    "nz-npc": ["npc", "bunnings"],
    "internationals-rwc": ["pacific nations cup"],
}


class WorldRugbyAdapter:
    adapter_key = "world-rugby-rims"
    source_id = "world-rugby"

    def __init__(self, source_id: str = "world-rugby", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=21)).isoformat()
        end = (today + timedelta(days=28)).isoformat()
        result = self._get(
            "https://api.wr-rims-prod.pulselive.com/rugby/v3/match"
            f"?pageSize=100&sport=mru&startDate={start}&endDate={end}"
        )
        rows = list((result.payload or {}).get("content") or []) if result.ok else []
        if request.competition_id == "internationals-rwc":
            bounded = self._get(
                "https://api.wr-rims-prod.pulselive.com/rugby/v3/match"
                "?pageSize=50&sport=mru&startDate=2026-09-18&endDate=2026-09-20"
            )
            if bounded.ok:
                rows.extend((bounded.payload or {}).get("content") or [])
                result = bounded if not result.ok else result
        if not result.ok and not rows:
            return result
        events = []
        seen = set()
        for row in rows:
            event = self._event(row, request.competition_id)
            if event and event["id"] not in seen:
                seen.add(event["id"])
                events.append(event)
        tokens = PULSELIVE_COMP_TOKENS.get(request.competition_id or "")
        if tokens:
            events = [
                event
                for event in events
                if any(tok in str(event.get("competition") or "").lower() for tok in tokens)
            ]
        return FetchResult(ok=True, http_status=result.http_status, events=_filter(events, request.capability))

    def _event(self, row: Dict[str, Any], competition_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
        millis = (row.get("time") or {}).get("millis")
        if millis not in (None, ""):
            try:
                start = datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (TypeError, ValueError, OSError):
                pass
        if start and "T" not in str(start):
            start = f"{start}T00:00:00Z"
        score: Dict[str, Any] = {
            "home": scores[0] if len(scores) > 0 and status != "scheduled" else None,
            "away": scores[1] if len(scores) > 1 and status != "scheduled" else None,
        }
        clock = row.get("clock") or (row.get("time") or {}).get("millis")
        period = row.get("period") or row.get("minute")
        if clock not in (None, "") and status == "live":
            score["clock"] = clock
        if period not in (None, "") and status == "live":
            score["period"] = period
        return {
            "id": f"worldrugby:{row.get('matchId')}",
            "home": _feed_team(teams[0], teams[0].get("name") or ""),
            "away": _feed_team(teams[1], teams[1].get("name") or ""),
            "status": status,
            "score": score,
            "start_time": start,
            "venue": (row.get("venue") or {}).get("name"),
            "sport": "rugby",
            "competition": name,
            "competition_key": competition_id or f"rugby-{slugify(name)}",
            "competition_logo": _asset_url(competition) if isinstance(competition, dict) else "",
            "event_family": "team_match",
            "source_family": "pulselive",
            "source_event_id": str(row.get("matchId") or ""),
            "source_event_ids": {"pulselive": str(row.get("matchId") or "")},
            "round": row.get("eventPhase") or "",
            "stage": row.get("eventPhase") or "",
            "extra": {
                "source_family": "pulselive",
                "source_event_id": str(row.get("matchId") or ""),
                "source_event_ids": {"pulselive": str(row.get("matchId") or "")},
                "source_status": status,
                "status_inferred": False,
            },
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
            "sport": "motorsport",
            "competition": "formula-1",
            "competition_key": "formula-1",
            "event_family": "motorsport_race",
            "series_id": "formula-1",
            "source_family": "jolpica-f1",
            "source_event_id": f"{row.get('season')}:{row.get('round')}",
            "source_event_ids": {"jolpica-f1": f"{row.get('season')}:{row.get('round')}"},
            "extra": {
                "source_family": "jolpica-f1",
                "source_event_id": f"{row.get('season')}:{row.get('round')}",
                "source_event_ids": {"jolpica-f1": f"{row.get('season')}:{row.get('round')}"},
                "classification": [
                    {
                        "position": item.get("position"),
                        "name": " ".join(
                            part
                            for part in (
                                (item.get("Driver") or {}).get("givenName"),
                                (item.get("Driver") or {}).get("familyName"),
                            )
                            if part
                        ),
                        "status": item.get("status"),
                    }
                    for item in results
                    if isinstance(item, dict)
                ],
            },
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
        primary = f"E{now.year}" if now.month >= 9 else f"E{now.year - 1}"
        seasons = [primary]
        prior = f"E{int(primary[1:]) - 1}"
        if prior not in seasons:
            seasons.append(prior)
        last = None
        events: List[Dict[str, Any]] = []
        for season in seasons:
            last = self._get(f"https://api-live.euroleague.net/v1/games?seasonCode={season}")
            for row in self._game_rows(last.payload if last.ok else None):
                event = self._from_catalog(row, season)
                if event:
                    events.append(event)
            xml = fetch_text(f"https://api-live.euroleague.net/v1/results?seasonCode={season}")
            if xml.ok and isinstance(xml.payload, str):
                events.extend(self._from_results_xml(xml.payload, season))
                last = xml
        if not events:
            last = self._get(f"https://live.euroleague.net/api/Header?gamecode=1&seasoncode={primary}")
            if not last.ok:
                last = self._get(f"https://live.euroleague.net/api/Header?gamecode=1&seasoncode={prior}")
            if last.ok and isinstance(last.payload, dict):
                events.append(self._from_header(last.payload, primary, last.payload.get("GameCode") or 1))
        if not last.ok and not events:
            return last
        return FetchResult(
            ok=True,
            http_status=last.http_status if last else 200,
            events=_filter(events, request.capability),
        )

    def _game_rows(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("data", "games", "items", "value"):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
        return []

    def _from_results_xml(self, text: str, season: str) -> List[Dict[str, Any]]:
        import re

        events: List[Dict[str, Any]] = []
        blocks = re.findall(r"<game\b[^>]*>.*?</game>", text or "", flags=re.I | re.S)
        for block in blocks:
            def tag(name: str) -> str:
                found = re.search(rf"<{name}[^>]*>([^<]*)</{name}>", block, re.I)
                return (found.group(1) or "").strip() if found else ""

            number = tag("gamenumber") or tag("gamecode")
            if "_" in number:
                number = number.split("_")[-1]
            home = tag("hometeam") or tag("localteam")
            away = tag("awayteam") or tag("roadteam")
            if not number or not home or not away:
                continue
            score_a = tag("homescore") or tag("localscore")
            score_b = tag("awayscore") or tag("roadscore")
            played = tag("played").lower() in {"true", "1", "yes"}
            status = "finished" if played or (score_a and score_b) else "scheduled"
            date = tag("date")
            clock = tag("time")
            start = None
            if date:
                try:
                    stamp = f"{date} {clock}".strip()
                    parsed = datetime.strptime(stamp, "%b %d, %Y %H:%M") if clock else datetime.strptime(date, "%b %d, %Y")
                    start = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    start = date
            events.append(
                {
                    "id": f"euroleague:{season}:{number}",
                    "home": {"name": home, "id": tag("homecode")},
                    "away": {"name": away, "id": tag("awaycode")},
                    "status": status,
                    "score": {
                        "home": int(score_a) if str(score_a).isdigit() else (score_a or None),
                        "away": int(score_b) if str(score_b).isdigit() else (score_b or None),
                    },
                    "start_time": start,
                    "round": tag("round") or tag("group"),
                    "sport": "basketball",
                    "competition": "euroleague",
                    "competition_key": "euroleague",
                    "event_family": "team_match",
                    "source_family": "euroleague-live",
                    "source_event_id": f"{season}:{number}",
                    "source_event_ids": {"euroleague-live": f"{season}:{number}"},
                    "extra": {
                        "source_family": "euroleague-live",
                        "source_event_id": f"{season}:{number}",
                        "source_event_ids": {"euroleague-live": f"{season}:{number}"},
                    },
                }
            )
        return events

    def _from_catalog(self, row: Dict[str, Any], season: str) -> Optional[Dict[str, Any]]:
        code = row.get("gamecode") or row.get("gameCode") or row.get("code") or row.get("id")
        home = row.get("local") or row.get("home") or row.get("TeamA") or {}
        away = row.get("road") or row.get("away") or row.get("TeamB") or {}
        home_name = home.get("name") if isinstance(home, dict) else row.get("TeamA")
        away_name = away.get("name") if isinstance(away, dict) else row.get("TeamB")
        if not home_name or not away_name:
            return None
        live_flag = row.get("Live") or row.get("live") or str(row.get("status") or "").lower() in {"live", "inprogress"}
        status = "live" if live_flag else "scheduled"
        if row.get("played") or str(row.get("status") or "").lower() in {"finished", "final", "closed"}:
            status = "finished"
        score = {
            "home": (home.get("score") if isinstance(home, dict) else None) or row.get("ScoreA"),
            "away": (away.get("score") if isinstance(away, dict) else None) or row.get("ScoreB"),
        }
        quarter = row.get("Quarter") or row.get("quarter") or row.get("period")
        clock = row.get("Remaining") or row.get("clock") or row.get("time")
        if quarter not in (None, ""):
            score["quarter"] = quarter
            score["period"] = quarter
        if clock not in (None, ""):
            score["clock"] = clock
        return {
            "id": f"euroleague:{season}:{code}",
            "home": {"name": home_name},
            "away": {"name": away_name},
            "status": status,
            "score": score,
            "start_time": row.get("utc") or row.get("date") or row.get("startDate"),
            "venue": row.get("Stadium") or row.get("venue"),
            "sport": "basketball",
            "competition": "euroleague",
            "competition_key": "euroleague",
            "event_family": "team_match",
            "source_family": "euroleague-live",
            "source_event_id": f"{season}:{code}",
            "source_event_ids": {"euroleague-live": f"{season}:{code}"},
            "extra": {
                "source_family": "euroleague-live",
                "source_event_id": f"{season}:{code}",
                "source_event_ids": {"euroleague-live": f"{season}:{code}"},
            },
        }

    def _from_header(self, row: Dict[str, Any], season: str, gamecode: Any) -> Dict[str, Any]:
        live_flag = row.get("Live")
        status = "live" if live_flag else "scheduled"
        if row.get("ScoreA") is not None and row.get("ScoreB") is not None and not live_flag:
            status = "finished"
        score: Dict[str, Any] = {"home": row.get("ScoreA"), "away": row.get("ScoreB")}
        if row.get("Quarter") is not None:
            score["quarter"] = row.get("Quarter")
            score["period"] = row.get("Quarter")
        if row.get("Remaining"):
            score["clock"] = row.get("Remaining")
        return {
            "id": f"euroleague:{season}:{gamecode}",
            "home": {"name": row.get("TeamA") or ""},
            "away": {"name": row.get("TeamB") or ""},
            "status": status,
            "score": score,
            "start_time": None,
            "venue": row.get("Stadium"),
            "competition": "euroleague",
            "competition_key": "euroleague",
            "sport": "basketball",
            "event_family": "team_match",
            "source_family": "euroleague-live",
            "source_event_id": f"{season}:{gamecode}",
            "source_event_ids": {"euroleague-live": f"{season}:{gamecode}"},
            "extra": {
                "source_family": "euroleague-live",
                "source_event_id": f"{season}:{gamecode}",
                "source_event_ids": {"euroleague-live": f"{season}:{gamecode}"},
            },
        }
