"""Final-18 public transports: PGA GraphQL POST, click-TT Remix, AltiusRT HTML, Champion Data, GBGB meeting JSON."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from collector.adapters import FetchRequest, FetchResult
from collector.http import USER_AGENT, fetch_url
from collector.adapters_official import parse_gbgb

PGA_GQL = "https://orchestrator.pgatour.com/graphql"
PGA_WEB_KEY = "da2-gsrx5bibzbb4njvhl7t37wqyl4"
PGA_TOURS = {
    "pga-tour": "R",
    "korn-ferry-tour": "S",
}

CLICK_TT_TABELLE = (
    "https://www.mytischtennis.de/click-tt/DTTB/25--26/ligen/Tischtennis_Bundesliga/gruppe/493079/tabelle/gesamt"
    "?_data=" + quote("routes/click-tt+/$association+/$season+/$type+/$groupname.gruppe.$urlid+/tabelle.$filter")
)
CLICK_TT_LIVE = "https://www.mytischtennis.de/api/meeting/{meeting_id}/live"

ALTIUSRT_MATCHES = [
    "https://fih.altiusrt.com/competitions/1779/matches",
    "https://eurohockey.altiusrt.com/",
]

CD_COMPS = "https://mc.championdata.com/data/competitions.json"
CD_FIXTURE = "https://mc.championdata.com/data/{comp_id}/fixture.json"

GBGB_RESULTS = "https://api.gbgb.org.uk/api/results?page={page}&itemsPerPage=50&date={date}"
GBGB_MEETING = "https://api.gbgb.org.uk/api/results/meeting/{meeting_id}?meeting={meeting_id}"

SCORELINE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")
MATCH_ROW = re.compile(
    r"<tr[^>]*>.*?</tr>",
    re.I | re.S,
)


def post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 25) -> FetchResult:
    body = json.dumps(payload).encode("utf-8")
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = getattr(resp, "status", 200) or 200
    except urllib.error.HTTPError as exc:
        raw = (exc.read() or b"").decode("utf-8", "replace")
        status = int(exc.code or 0)
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else None
        except json.JSONDecodeError:
            parsed = None
        return FetchResult(ok=False, http_status=status, payload=parsed, error=f"http {status}")
    except Exception as exc:  # noqa: BLE001
        return FetchResult(ok=False, http_status=0, error=str(exc)[:180])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    return FetchResult(ok=True, http_status=status, payload=parsed)


class PgaGraphqlAdapter:
    """pgatour.com orchestrator GraphQL used by the public site (POST + public x-api-key)."""

    adapter_key = "pga-graphql"
    source_id = "pga-graphql"

    def __init__(self, source_id: str = "pga-graphql", poster=None, getter=fetch_url):
        self.source_id = source_id
        self._post = poster or (
            lambda body: post_json(
                PGA_GQL,
                body,
                {
                    "x-api-key": PGA_WEB_KEY,
                    "x-pgat-platform": "web",
                    "origin": "https://www.pgatour.com",
                    "referer": "https://www.pgatour.com/",
                },
            )
        )
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        tour = PGA_TOURS.get(request.competition_id or "", "R")
        upcoming = self._post(
            {
                "query": (
                    'query { upcomingSchedule(tourCode: "%s") { tournaments { id tournamentName '
                    "tournamentStatus startDate endDate } } }"
                )
                % tour
            }
        )
        complete = self._post(
            {
                "query": (
                    'query { completeSchedule(tourCode: "%s") { tournaments { id tournamentName '
                    "tournamentStatus startDate endDate } } }"
                )
                % tour
            }
        )
        if not upcoming.ok and not complete.ok:
            return upcoming if not upcoming.ok else complete
        tournaments = []
        for payload in (upcoming.payload, complete.payload):
            if not isinstance(payload, dict):
                continue
            data = payload.get("data") or {}
            block = data.get("upcomingSchedule") or data.get("completeSchedule") or {}
            tournaments.extend(block.get("tournaments") or [])
        events = [self._tournament(row, request.competition_id or "pga-tour") for row in tournaments if isinstance(row, dict)]
        events = [row for row in events if row]
        current = next(
            (
                row
                for row in tournaments
                if str(row.get("tournamentStatus") or "").upper() in {"IN_PROGRESS", "INPROGRESS", "LIVE", "PLAYING"}
            ),
            None,
        )
        if current and current.get("id"):
            board = self._leaderboard(str(current["id"]), request.competition_id or "pga-tour")
            if board:
                events = board + events
        status = upcoming.http_status if upcoming.ok else complete.http_status
        return FetchResult(ok=True, http_status=status or 200, events=events)

    def _leaderboard(self, tournament_id: str, competition_id: str) -> List[Dict[str, Any]]:
        result = self._post(
            {
                "query": (
                    "query { leaderboardV3(id: \"%s\") { id tournamentId tournamentStatus players { "
                    "player { displayName id } scoringData { position total today thru currentRound "
                    "projectedCut roundScores { roundNumber strokes } } } } }"
                )
                % tournament_id
            }
        )
        if not result.ok or not isinstance(result.payload, dict):
            return []
        data = result.payload.get("data") or {}
        board = data.get("leaderboardV3") or data.get("leaderboard") or {}
        players = board.get("players") or []
        events: List[Dict[str, Any]] = []
        event_name = board.get("tournamentName") or board.get("tournamentId") or tournament_id
        for row in players[:80]:
            player = row.get("player") or {}
            scoring = row.get("scoringData") or {}
            name = player.get("displayName")
            if not name:
                continue
            thru = scoring.get("thru")
            status = "live" if thru not in (None, "", "F", "CUT", "WD") else "finished" if thru in {"F"} else "scheduled"
            if status == "scheduled" and scoring.get("position"):
                status = "finished" if scoring.get("total") not in (None, "") else "scheduled"
            score = {
                "home": scoring.get("total") if status != "scheduled" else None,
                "away": None,
                "position": scoring.get("position"),
            }
            if thru not in (None, ""):
                score["thru"] = thru
            if scoring.get("currentRound") not in (None, ""):
                score["round"] = scoring.get("currentRound")
            if scoring.get("today") not in (None, ""):
                score["today"] = scoring.get("today")
            rounds = scoring.get("roundScores") or []
            if rounds:
                extra_rounds = [
                    {"label": item.get("roundNumber"), "home": item.get("strokes"), "away": None}
                    for item in rounds
                    if isinstance(item, dict)
                ]
            else:
                extra_rounds = []
            events.append(
                {
                    "id": f"pga:{tournament_id}:{player.get('id') or name}",
                    "home": {"id": str(player.get("id") or ""), "name": name},
                    "away": {"id": "field", "name": event_name},
                    "status": status,
                    "score": score,
                    "sport": "golf",
                    "competition": event_name,
                    "competition_key": competition_id,
                    "event_family": "leaderboard",
                    "source_family": "pga-graphql",
                    "source_competition_id": tournament_id,
                    "source_event_id": str(tournament_id),
                    "source_event_ids": {"pga-graphql": str(tournament_id)},
                    "periods": extra_rounds or None,
                    "extra": {
                        "source_family": "pga-graphql",
                        "source_event_id": str(tournament_id),
                        "source_event_ids": {"pga-graphql": str(tournament_id)},
                        "source_status": status,
                        "status_inferred": False,
                        "position": scoring.get("position"),
                        "thru": thru,
                        "round": scoring.get("currentRound"),
                        "today": scoring.get("today"),
                        "cut": scoring.get("projectedCut"),
                    },
                }
            )
        return events

    def _tournament(self, row: Dict[str, Any], competition_id: str) -> Optional[Dict[str, Any]]:
        name = row.get("tournamentName")
        if not name:
            return None
        raw = str(row.get("tournamentStatus") or "").upper()
        if raw in {"IN_PROGRESS", "INPROGRESS", "LIVE", "PLAYING"}:
            status = "live"
        elif raw in {"COMPLETE", "COMPLETED", "OFFICIAL", "FINISHED"}:
            status = "finished"
        else:
            status = "scheduled"
        return {
            "id": f"pga:{row.get('id') or name}",
            "home": {"id": str(row.get("id") or ""), "name": name},
            "away": {"id": "field", "name": "Field"},
            "status": status,
            "score": {"home": None, "away": None},
            "start_time": row.get("startDate"),
            "sport": "golf",
            "competition": name,
            "competition_key": competition_id,
            "event_family": "leaderboard",
            "source_family": "pga-graphql",
            "source_competition_id": row.get("id"),
            "source_event_id": str(row.get("id") or ""),
            "source_event_ids": {"pga-graphql": str(row.get("id") or "")},
            "extra": {
                "source_family": "pga-graphql",
                "source_event_id": str(row.get("id") or ""),
                "source_event_ids": {"pga-graphql": str(row.get("id") or "")},
                "source_status": status,
                "status_inferred": False,
                "tournament_status": raw,
            },
        }


def _clicktt_start(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in text and fmt.startswith("%Y-%m-%d %H") else text, fmt).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except ValueError:
            continue
    return text


class ClickTtRemixAdapter:
    """myTischtennis.de public Remix JSON + meeting live endpoint."""

    adapter_key = "click-tt-remix"
    source_id = "click-tt-remix"

    def __init__(self, source_id: str = "click-tt-remix", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        table = self._get(CLICK_TT_TABELLE)
        if not table.ok:
            return table
        payload = table.payload if isinstance(table.payload, dict) else {}
        meetings = ((((payload.get("data") or {}).get("meetings_excerpt") or {}).get("meetings")) or [])
        events = []
        for row in meetings:
            event = self._meeting(row)
            if event:
                events.append(event)
        live_ids = [row.get("meeting_id") for row in meetings if row.get("live")]
        finished_ids = [
            row.get("meeting_id")
            for row in meetings
            if not row.get("live")
            and (
                str(row.get("state") or "").lower() in {"done", "complete", "finished"}
                or row.get("is_meeting_complete")
            )
        ]
        for meeting_id in (live_ids + finished_ids)[:8]:
            live = self._get(CLICK_TT_LIVE.format(meeting_id=meeting_id))
            if live.ok and isinstance(live.payload, dict):
                from collector.detail_families import parse_clicktt_live

                event = self._live(live.payload.get("data") or live.payload, meeting_id)
                parsed = parse_clicktt_live(live.payload)
                if event and parsed:
                    event["periods"] = parsed.get("periods")
                    extra = event.get("extra") if isinstance(event.get("extra"), dict) else {}
                    extra["sport_detail"] = {**(extra.get("sport_detail") or {}), **(parsed.get("sport_detail") or {})}
                    event["extra"] = extra
                    event["sport_detail"] = extra.get("sport_detail")
                if event:
                    events = [event if e.get("id") == event["id"] else e for e in events]
                    if event["id"] not in {e.get("id") for e in events}:
                        events.append(event)
        cap = request.capability
        if cap == "live_scores":
            events = [e for e in events if e.get("status") == "live"]
        elif cap == "results":
            events = [e for e in events if e.get("status") == "finished"]
        elif cap == "fixtures":
            events = [e for e in events if e.get("status") == "scheduled"]
        return FetchResult(ok=True, http_status=table.http_status, events=events)

    def _meeting(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        home = row.get("team_home")
        away = row.get("team_away")
        if isinstance(home, dict):
            home = home.get("name") or home.get("club") or home.get("label")
        if isinstance(away, dict):
            away = away.get("name") or away.get("club") or away.get("label")
        if not home or not away:
            return None
        state = str(row.get("state") or "").lower()
        if row.get("live"):
            status = "live"
        elif state in {"done", "complete", "finished"} or row.get("is_meeting_complete"):
            status = "finished"
        else:
            status = "scheduled"
        home_score = row.get("matches_won")
        away_score = row.get("matches_lost")
        try:
            home_score = int(home_score) if home_score not in (None, "") else None
            away_score = int(away_score) if away_score not in (None, "") else None
        except (TypeError, ValueError):
            home_score = away_score = None
        return {
            "id": f"clicktt:{row.get('meeting_id')}",
            "home": {"id": str(row.get("team_home_id") or ""), "name": home},
            "away": {"id": str(row.get("team_away_id") or ""), "name": away},
            "status": status,
            "score": {
                "home": home_score if status != "scheduled" else None,
                "away": away_score if status != "scheduled" else None,
            },
            "start_time": _clicktt_start(row.get("date") or row.get("scheduled") or row.get("datetime")),
            "sport": "table-tennis",
            "competition": row.get("league_name") or "click-TT",
            "competition_key": "germany-click-tt",
            "source_competition_name": "germany-click-tt",
            "event_family": "team_match",
            "source_family": "click-tt-remix",
            "source_event_id": str(row.get("meeting_id") or ""),
            "source_event_ids": {"click-tt-remix": str(row.get("meeting_id") or "")},
            "source_competition_id": row.get("league_id") or "493079",
            "extra": {
                "source_family": "click-tt-remix",
                "source_event_id": str(row.get("meeting_id") or ""),
                "source_event_ids": {"click-tt-remix": str(row.get("meeting_id") or "")},
                "source_status": status,
                "status_inferred": False,
                "live_flag": bool(row.get("live")),
                "source_competition_name": "germany-click-tt",
            },
        }

    def _live(self, data: Dict[str, Any], meeting_id: Any) -> Optional[Dict[str, Any]]:
        home = data.get("team_home")
        away = data.get("team_guest") or data.get("team_away")
        if not home or not away:
            return None
        if data.get("live"):
            status = "live"
        elif data.get("is_completed"):
            status = "finished"
        else:
            status = "scheduled"
        return {
            "id": f"clicktt:{meeting_id}",
            "home": {"id": "", "name": home},
            "away": {"id": "", "name": away},
            "status": status,
            "score": {
                "home": data.get("matches_home") if status != "scheduled" else None,
                "away": data.get("matches_guest") if status != "scheduled" else None,
            },
            "start_time": data.get("scheduled"),
            "sport": "table-tennis",
            "competition": "click-TT",
            "competition_key": "germany-click-tt",
            "event_family": "team_match",
            "source_family": "click-tt-remix",
            "source_event_id": str(meeting_id or ""),
            "source_event_ids": {"click-tt-remix": str(meeting_id or "")},
            "extra": {
                "source_family": "click-tt-remix",
                "source_event_id": str(meeting_id or ""),
                "source_event_ids": {"click-tt-remix": str(meeting_id or "")},
                "source_status": status,
                "status_inferred": False,
                "live_flag": bool(data.get("live")),
            },
        }


class AltiusRtHtmlAdapter:
    """Public AltiusRT match-listing HTML (REST API is credentialed; HTML scoreboard is not)."""

    adapter_key = "altiusrt-html"
    source_id = "altiusrt-html"

    def __init__(self, source_id: str = "altiusrt-html", getter=None):
        from collector.http import fetch_text

        self.source_id = source_id
        self._get = getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        events: List[Dict[str, Any]] = []
        last = None
        for url in ALTIUSRT_MATCHES:
            last = self._get(url)
            html = last.payload if last.ok and isinstance(last.payload, str) else ""
            events.extend(parse_altiusrt_matches(html, request.competition_id or "fih-eurohockey"))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=events,
        )


def parse_altiusrt_matches(html: str, competition_id: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for row in MATCH_ROW.findall(html or ""):
        text = re.sub(r"<[^>]+>", " ", row)
        text = re.sub(r"\s+", " ", text).strip()
        vs = re.search(r"([A-Z]{3})\s+v(?:s\.?)?\s+([A-Z]{3})", text)
        score = SCORELINE.search(text)
        if not vs:
            continue
        if re.search(r"\bLive\b|\bIn Progress\b", text, re.I):
            status = "live"
        elif re.search(r"\bUpcoming\b", text, re.I):
            status = "scheduled"
        elif re.search(r"\bOfficial\b", text, re.I) or score:
            status = "finished"
        else:
            status = "scheduled"
        home_score = int(score.group(1)) if score and status != "scheduled" else None
        away_score = int(score.group(2)) if score and status != "scheduled" else None
        events.append(
            {
                "id": f"altiusrt:{vs.group(1)}-{vs.group(2)}-{text[:24]}",
                "home": {"id": vs.group(1), "name": vs.group(1)},
                "away": {"id": vs.group(2), "name": vs.group(2)},
                "status": status,
                "score": {"home": home_score, "away": away_score},
                "sport": "field-hockey",
                "competition": "EuroHockey / FIH AltiusRT",
                "competition_key": competition_id,
                "event_family": "team_match",
                "source_family": "altiusrt-html",
            }
        )
    return events[:80]


class ChampionDataNetballAdapter:
    """Champion Data iStats public fixture JSON for Super Netball."""

    adapter_key = "championdata-netball"
    source_id = "championdata-netball"

    def __init__(self, source_id: str = "championdata-netball", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        comps = self._get(CD_COMPS)
        if not comps.ok:
            return comps
        payload = comps.payload if isinstance(comps.payload, dict) else {}
        rows = ((payload.get("competitionDetails") or {}).get("competition") or [])
        hits = [
            row
            for row in rows
            if isinstance(row, dict) and re.search(r"super netball", str(row.get("name") or ""), re.I)
        ]
        regular = [row for row in hits if "final" not in str(row.get("name") or "").lower()]
        pool = regular or hits
        if not hits:
            return FetchResult(ok=True, http_status=comps.http_status, events=[])
        current = sorted(pool, key=lambda row: int(row.get("id") or 0), reverse=True)[:3]
        events: List[Dict[str, Any]] = []
        last = fixture = None
        for comp in current:
            fixture = self._get(CD_FIXTURE.format(comp_id=comp["id"]))
            last = fixture
            if not fixture.ok:
                continue
            matches = ((fixture.payload or {}).get("fixture") or {}).get("match") or []
            if isinstance(matches, dict):
                matches = [matches]
            batch = [self._match(row, str(comp["id"])) for row in matches if isinstance(row, dict)]
            events.extend(row for row in batch if row)
            if any(row.get("status") == "finished" for row in events):
                break
        if last is not None and not last.ok and not events:
            return last
        return FetchResult(ok=True, http_status=(last.http_status if last else comps.http_status), events=events)

    def _match(self, row: Dict[str, Any], comp_id: str) -> Optional[Dict[str, Any]]:
        home = row.get("homeSquadName") or row.get("home") or row.get("squadNameHome")
        away = row.get("awaySquadName") or row.get("away") or row.get("squadNameAway")
        if not home or not away:
            return None
        raw = str(row.get("matchStatus") or row.get("status") or "").lower()
        if raw in {"playing", "inprogress", "in_progress", "live"}:
            status = "live"
        elif raw in {"complete", "completed", "final", "finished"}:
            status = "finished"
        else:
            status = "scheduled"
        home_score = row.get("homeSquadScore") or row.get("homeScore")
        away_score = row.get("awaySquadScore") or row.get("awayScore")
        score = {
            "home": home_score if status != "scheduled" else None,
            "away": away_score if status != "scheduled" else None,
        }
        period = row.get("period") or row.get("currentPeriod")
        clock = row.get("periodSeconds") or row.get("clock")
        if period not in (None, "") and status == "live":
            score["period"] = period
        if clock not in (None, "") and status == "live":
            score["clock"] = clock
        periods = []
        for index in range(1, 5):
            home_q = row.get(f"homeSquadScoreQ{index}") or row.get(f"homePeriod{index}")
            away_q = row.get(f"awaySquadScoreQ{index}") or row.get(f"awayPeriod{index}")
            if home_q is not None or away_q is not None:
                periods.append({"label": index, "home": home_q, "away": away_q})
        return {
            "id": f"championdata:{row.get('matchId') or row.get('id') or home}-{away}",
            "home": {"id": str(row.get("homeSquadId") or ""), "name": str(home)},
            "away": {"id": str(row.get("awaySquadId") or ""), "name": str(away)},
            "status": status,
            "score": score,
            "periods": periods or None,
            "start_time": row.get("utcStartTime") or row.get("localStartTime"),
            "sport": "netball",
            "competition": "Super Netball",
            "competition_key": "ssn-australia",
            "event_family": "team_match",
            "source_family": "championdata-netball",
            "source_event_id": f"{comp_id}:{row.get('matchId') or row.get('id') or ''}",
            "source_event_ids": {"championdata-netball": f"{comp_id}:{row.get('matchId') or row.get('id') or ''}"},
            "source_competition_id": comp_id,
            "extra": {
                "source_family": "championdata-netball",
                "source_event_id": f"{comp_id}:{row.get('matchId') or row.get('id') or ''}",
                "source_event_ids": {"championdata-netball": f"{comp_id}:{row.get('matchId') or row.get('id') or ''}"},
                "source_status": status,
                "status_inferred": False,
                "period": period,
            },
        }


class GbgbMeetingJsonAdapter:
    """GBGB public results JSON by date + meeting. Rapid official finish, not in-running odds."""

    adapter_key = "gbgb-meeting-json"
    source_id = "gbgb-meeting-json"

    def __init__(self, source_id: str = "gbgb-meeting-json", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot", "live"}:
            return FetchResult(ok=True, http_status=200, events=[])
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=delta)).isoformat() for delta in (0, 1, 2, 3)]
        last = None
        events: List[Dict[str, Any]] = []
        seen_meetings = []
        for day in dates:
            items = []
            for page in (1, 2, 3, 4):
                last = self._get(GBGB_RESULTS.format(page=page, date=day))
                if not last.ok or not isinstance(last.payload, dict):
                    break
                chunk = last.payload.get("items") or []
                if not chunk:
                    break
                events.extend(parse_gbgb(last.payload))
                items.extend(row for row in chunk if isinstance(row, dict))
                if len(chunk) < 50:
                    break
            if not items:
                continue
            meeting_ids = []
            for row in items:
                if row.get("meetingId") and row["meetingId"] not in meeting_ids:
                    meeting_ids.append(row["meetingId"])
            for meeting_id in meeting_ids:
                if meeting_id in seen_meetings:
                    continue
                seen_meetings.append(meeting_id)
                meet = self._get(GBGB_MEETING.format(meeting_id=meeting_id))
                payload = meet.payload
                if isinstance(payload, dict) and payload.get("items"):
                    events.extend(parse_gbgb(payload))
                    continue
                if isinstance(payload, list) and payload and isinstance(payload[0], dict) and (
                    payload[0].get("resultPosition") is not None or payload[0].get("raceId")
                ):
                    events.extend(parse_gbgb({"items": payload}))
                    continue
                rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
                for block in rows:
                    if not isinstance(block, dict):
                        continue
                    events.extend(self._races(block, day))
        return FetchResult(ok=True, http_status=(last.http_status if last else 200) or 200, events=events)

    def _races(self, block: Dict[str, Any], day: str) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        track = block.get("trackName") or block.get("track") or "GBGB"
        races = block.get("races") or []
        if not races and block.get("raceId"):
            races = [block]
        for race in races:
            if not isinstance(race, dict):
                continue
            traps = race.get("traps") or race.get("runners") or []
            winner = None
            runners = []
            for trap in traps:
                if not isinstance(trap, dict):
                    continue
                name = (
                    trap.get("dogName")
                    or trap.get("greyhoundName")
                    or trap.get("name")
                    or trap.get("winnerName")
                    or trap.get("officialName")
                )
                pos = trap.get("resultPosition") or trap.get("position")
                try:
                    pos_i = int(pos) if pos not in (None, "") else None
                except (TypeError, ValueError):
                    pos_i = None
                if name:
                    runners.append({"name": name, "position": pos_i, "trap": trap.get("trapNumber")})
                if pos_i == 1:
                    winner = name
            race_no = race.get("raceNumber") or race.get("raceNo") or ""
            status = "finished" if winner else "scheduled"
            events.append(
                {
                    "id": f"gbgb:{block.get('meetingId') or ''}:{race.get('raceId') or race_no}",
                    "home": {"id": str(race_no), "name": f"Race {race_no}"},
                    "away": {"id": str(block.get("meetingId") or ""), "name": str(track)},
                    "status": status,
                    "score": {"home": None, "away": None, "winner": winner} if winner else {"home": None, "away": None},
                    "start_time": f"{day}T{str(race.get('raceTime') or '00:00:00')[:8]}Z",
                    "sport": "greyhound-racing",
                    "competition": "GBGB meetings",
                    "competition_key": "gbgb-meetings",
                    "event_family": "racing",
                    "source_family": "gbgb-meeting-json",
                    "extra": {"winner": winner, "runners": runners or None, "meeting_id": block.get("meetingId"), "race_number": race_no},
                }
            )
        return events
