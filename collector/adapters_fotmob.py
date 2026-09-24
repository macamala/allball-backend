"""FotMob public JSON family. One date-board fetch is reused across leagues."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

# Railway-proven FotMob league IDs (www.fotmob.com/api/data/allLeagues, 2026-09-20).
FOTMOB_LEAGUES: Dict[str, Dict[str, Any]] = {
    "albania-superliga": {"id": 260, "name": "Kategoria Superiore", "ccode": "alb"},
    "australia-a-league-women": {"id": 9495, "name": "A-League Women", "ccode": "aus"},
    "bosnia-premier-liga": {"id": 267, "name": "Premier League", "ccode": "bih"},
    "bulgaria-first-league": {"id": 270, "name": "First Professional League", "ccode": "bul"},
    "china-super-league": {"id": 120, "name": "Super League", "ccode": "chn"},
    "colombia-primera-a": {"id": 274, "name": "Primera A", "ccode": "col"},
    "copa-sudamericana": {"id": 299, "name": "Copa Sudamericana", "ccode": "int"},
    "costa-rica-liga-fpd": {"id": 121, "name": "Primera Division", "ccode": "crc"},
    "croatia-hnl": {"id": 252, "name": "HNL", "ccode": "cro"},
    "czech-first-league": {"id": 122, "name": "1. Liga", "ccode": "cze"},
    "ecuador-serie-a": {"id": 246, "name": "Serie A", "ccode": "ecu"},
    "egypt-premier-league": {"id": 519, "name": "Premier League", "ccode": "egy"},
    "finland-veikkausliiga": {"id": 51, "name": "Veikkausliiga", "ccode": "fin"},
    "france-ligue-1": {"id": 53, "name": "Ligue 1", "ccode": "fra"},
    "hungary-nb-i": {"id": 212, "name": "Nemzeti Bajnokság I", "ccode": "hun"},
    "iceland-urvalsdeild": {"id": 215, "name": "Besta deildin", "ccode": "isl"},
    "indonesia-liga-1": {"id": 8983, "name": "Super League", "ccode": "idn"},
    "italy-serie-a": {"id": 55, "name": "Serie A", "ccode": "ita"},
    "korea-k-league-1": {"id": 9080, "name": "K League 1", "ccode": "kor"},
    "malaysia-super-league": {"id": 8985, "name": "Liga Super", "ccode": "mas"},
    "morocco-botola": {"id": 530, "name": "Botola Pro", "ccode": "mar"},
    "netherlands-eredivisie": {"id": 57, "name": "Eredivisie", "ccode": "ned"},
    "norway-eliteserien": {"id": 59, "name": "Eliteserien", "ccode": "nor"},
    "paraguay-primera": {"id": 199, "name": "Division Profesional", "ccode": "par"},
    "poland-ekstraklasa": {"id": 196, "name": "Ekstraklasa", "ccode": "pol"},
    "portugal-primeira-liga": {"id": 61, "name": "Liga Portugal", "ccode": "por"},
    "romania-superliga": {"id": 189, "name": "Liga I", "ccode": "rou"},
    "saudi-pro-league": {"id": 536, "name": "Saudi Pro League", "ccode": "ksa"},
    "serbia-superliga": {"id": 182, "name": "Super Liga", "ccode": "srb"},
    "slovakia-super-liga": {"id": 176, "name": "1. liga", "ccode": "svk"},
    "slovenia-1-snl": {"id": 173, "name": "Prva Liga", "ccode": "svn"},
    "tunisia-ligue-1": {"id": 544, "name": "Ligue I", "ccode": "tun"},
    "uruguay-primera": {"id": 161, "name": "Liga AUF Uruguaya", "ccode": "uru"},
    "vietnam-v-league-1": {"id": 9088, "name": "V-League", "ccode": "vie"},
    "england-premier-league": {"id": 47, "name": "Premier League", "ccode": "eng"},
    "spain-la-liga": {"id": 87, "name": "LaLiga", "ccode": "esp"},
    "germany-bundesliga": {"id": 54, "name": "Bundesliga", "ccode": "ger"},
    "belgium-pro-league": {"id": 40, "name": "Pro League", "ccode": "bel"},
    "uefa-nations-league": {"ids": [9806, 9807, 9808, 9809], "name": "UEFA Nations League", "ccode": "int"},
}

def _league_ids(spec: Dict[str, Any], source_config: Optional[Dict[str, Any]] = None) -> List[str]:
    source_config = source_config or {}
    raw = spec.get("ids")
    if not raw:
        raw = source_config.get("fotmob_league_ids")
    if raw:
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        return [str(value) for value in values if value not in (None, "")]
    value = spec.get("id")
    if value in (None, ""):
        value = source_config.get("fotmob_league_id")
    return [str(value)] if value not in (None, "") else []


MATCHES_URL = "https://www.fotmob.com/api/data/matches?date={date}"
SCORE_URL = "https://www.fotmob.com/api/data/match-score?matchId={match_id}"

_BOARD: Dict[str, List[Dict[str, Any]]] = {}


def board_dates(*, past_days: int = 3, future_days: int = 1) -> List[str]:
    now = datetime.now(timezone.utc).date()
    days: List[str] = []
    cursor = now - timedelta(days=past_days)
    end = now + timedelta(days=future_days)
    while cursor <= end:
        days.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    return days


def _dates() -> List[str]:
    """Live poll window. Do not widen; date-board backfill uses board_dates(past_days=7)."""
    return board_dates(past_days=3, future_days=1)


def _extract_matches(payload: Any) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []

    def walk(node: Any, league: Optional[Dict[str, Any]] = None) -> None:
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, league)
            return
        if not isinstance(node, dict):
            return
        if node.get("matches") or node.get("Matches"):
            lg = {
                "id": node.get("id") or node.get("primaryId"),
                "name": node.get("name") or node.get("ccode"),
                "ccode": node.get("ccode"),
            }
            for row in node.get("matches") or node.get("Matches") or []:
                if isinstance(row, dict):
                    row = dict(row)
                    row["_league"] = lg
                    matches.append(row)
            return
        if node.get("id") and (node.get("home") or node.get("homeTeam")) and node.get("status") is not None:
            row = dict(node)
            row["_league"] = league
            matches.append(row)
            return
        next_league = league
        if node.get("name") and node.get("id"):
            next_league = {"id": node.get("id"), "name": node.get("name"), "ccode": node.get("ccode")}
        for key, value in node.items():
            if key in {"home", "away", "status", "homeTeam", "awayTeam"}:
                continue
            walk(value, next_league)

    walk(payload)
    return matches


def _int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(str(value).split("-")[0].split(":")[0])
    except (TypeError, ValueError):
        return None


def _team_logo(team: Dict[str, Any]) -> str:
    team_id = str((team or {}).get("id") or (team or {}).get("teamId") or "").strip()
    return f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png" if team_id else ""


def _league_logo(league: Dict[str, Any]) -> str:
    league_id = str((league or {}).get("id") or "").strip()
    return f"https://images.fotmob.com/image_resources/logo/leaguelogo/{league_id}.png" if league_id else ""


def _scores(status: Dict[str, Any], match: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    raw = status.get("scoreStr") or match.get("score")
    if isinstance(raw, str) and "-" in raw:
        left, right = raw.split("-", 1)
        return _int_or_none(left.strip()), _int_or_none(right.strip())
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    return _int_or_none(home.get("score")), _int_or_none(away.get("score"))


def match_to_event(match: Dict[str, Any], competition_id: str) -> Optional[Dict[str, Any]]:
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    home_name = (home.get("name") or home.get("shortName") or "").strip()
    away_name = (away.get("name") or away.get("shortName") or "").strip()
    if not home_name or not away_name:
        return None
    status_obj = match.get("status") if isinstance(match.get("status"), dict) else {}
    started = bool(status_obj.get("started"))
    finished = bool(status_obj.get("finished"))
    if finished:
        status = "finished"
    elif started:
        status = "live"
    else:
        status = "scheduled"
    home_score, away_score = _scores(status_obj, match)
    if status == "scheduled":
        home_score = None
        away_score = None
    live_time = status_obj.get("liveTime") if isinstance(status_obj.get("liveTime"), dict) else {}
    minute = live_time.get("short") or live_time.get("long") or None
    score: Dict[str, Any] = {"home": home_score, "away": away_score}
    if minute not in (None, ""):
        score["minute"] = minute
    league = match.get("_league") or {}
    start = None
    ts = match.get("status", {}).get("utcTime") if isinstance(match.get("status"), dict) else None
    start = ts or match.get("time") or match.get("utcTime")
    return {
        "id": str(match.get("id") or match.get("matchId") or f"{home_name}-{away_name}-{start}"),
        "home": {
            "id": str(home.get("id") or home.get("teamId") or ""),
            "name": home_name,
            "logo": _team_logo(home),
        },
        "away": {
            "id": str(away.get("id") or away.get("teamId") or ""),
            "name": away_name,
            "logo": _team_logo(away),
        },
        "status": status,
        "score": score,
        "start_time": start,
        "source_family": "fotmob",
        "source_event_id": str(match.get("id") or ""),
        "source_competition_id": str(league.get("id") or ""),
        "source_competition_name": str(league.get("name") or ""),
        "competition_logo": _league_logo(league),
        "extra": {
            "source_family": "fotmob",
            "source_status": status_obj.get("reason", {}).get("short") if isinstance(status_obj.get("reason"), dict) else status,
            "status_inferred": False,
            "source_event_ids": {"fotmob": str(match.get("id") or "")},
            "source_event_id": str(match.get("id") or ""),
            "source_competition_id": str(league.get("id") or ""),
            "source_competition_name": str(league.get("name") or ""),
        },
    }


def _load_boards(getter, dates: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    days = list(dates or _dates())
    cache_key = "d:" + ",".join(days)
    cached = _BOARD.get(cache_key)
    if cached is not None:
        return cached
    if dates is None and _BOARD.get("all") is not None:
        return _BOARD["all"]
    rows: List[Dict[str, Any]] = []
    for day in days:
        url = MATCHES_URL.format(date=day)
        result = getter(url) if getter else fetch_url(url)
        payload = result.payload if isinstance(getattr(result, "payload", None), (dict, list)) else None
        if payload is None and isinstance(getattr(result, "payload", None), str):
            import json

            try:
                payload = json.loads(result.payload)
            except (TypeError, ValueError):
                payload = None
        if payload is not None:
            for match in _extract_matches(payload):
                match["_board_date"] = day
                rows.append(match)
    _BOARD[cache_key] = rows
    if dates is None:
        _BOARD["all"] = rows
    return rows


def parse_fotmob_table(payload: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []

    def take_rows(rows: Any, stage: Optional[str] = None, group: Optional[str] = None) -> None:
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            team_node = item.get("team") if isinstance(item.get("team"), dict) else {}
            team = item.get("name") or item.get("shortName") or team_node
            if isinstance(team, dict):
                team = team.get("name") or team.get("shortName")
            team_id = str(
                item.get("id")
                or item.get("teamId")
                or team_node.get("id")
                or team_node.get("teamId")
                or ""
            ).strip()
            pts = item.get("pts") if item.get("pts") is not None else item.get("points")
            played = item.get("played") or item.get("matchesPlayed")
            if not team or (pts is None and played is None):
                continue
            scores = str(item.get("scoresStr") or "")
            gf = ga = None
            if "-" in scores:
                left, right = scores.split("-", 1)
                gf, ga = left.strip(), right.strip()
            found.append(
                {
                    "position": item.get("idx") or item.get("position"),
                    "team": team,
                    "team_id": team_id or None,
                    "logo": f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png" if team_id else None,
                    "played": played,
                    "wins": item.get("wins"),
                    "draws": item.get("draws"),
                    "losses": item.get("losses"),
                    "goals_for": item.get("scoresFor") or gf,
                    "goals_against": item.get("scoresAgainst") or ga,
                    "goal_difference": item.get("goalConDiff") or item.get("gd"),
                    "points": pts,
                    "form": "".join(str(x) for x in (item.get("form") or []) if x) if isinstance(item.get("form"), list) else item.get("form"),
                    "stage": stage,
                    "group": group,
                }
            )

    def walk(node: Any, stage: Optional[str] = None) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, stage)
            return
        if not isinstance(node, dict):
            return
        label = node.get("leagueName") or node.get("groupName") or node.get("name")
        table = node.get("table")
        if isinstance(table, list) and table and isinstance(table[0], dict) and (
            table[0].get("pts") is not None or table[0].get("played") is not None or table[0].get("name")
        ):
            take_rows(table, stage=stage, group=label if label else None)
            return
        data = node.get("data")
        if isinstance(data, dict) and isinstance(data.get("table"), dict):
            inner = data["table"]
            take_rows(inner.get("all") or inner.get("home") or inner.get("away") or [], stage=stage, group=label)
        all_rows = node.get("all")
        if isinstance(all_rows, list):
            take_rows(all_rows, stage=stage, group=label)
        for key, value in node.items():
            if key in {"home", "away", "team", "stats"}:
                continue
            walk(value, stage or (label if key in {"table", "tables", "leagueTable", "standings"} else stage))

    walk(payload)
    # unique teams keep first
    seen = set()
    out = []
    for row in found:
        key = str(row.get("team") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


LEAGUE_URL = "https://www.fotmob.com/api/data/leagues?id={league_id}"


class FotMobAdapter:
    adapter_key = "fotmob"

    def __init__(self, source_id: str = "fotmob", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        spec = FOTMOB_LEAGUES.get(competition_id) or {}
        league_ids = _league_ids(spec, request.source_config)
        if not league_ids:
            return FetchResult(
                ok=False,
                http_status=0,
                config_missing=True,
                parse_status="empty",
                empty_reason="CONFIG_MISSING",
                error="fotmob league id missing",
            )
        if request.capability == "standings":
            rows: List[Dict[str, Any]] = []
            payloads: List[Any] = []
            statuses: List[int] = []
            for league_id in league_ids:
                result = self._get(LEAGUE_URL.format(league_id=league_id))
                statuses.append(result.http_status or 0)
                payload = result.payload if result.ok else None
                if payload is not None:
                    payloads.append(payload)
                if isinstance(payload, dict):
                    rows.extend(parse_fotmob_table(payload))
            unique_rows: List[Dict[str, Any]] = []
            seen = set()
            for row in rows:
                key = (str(row.get("team") or ""), str(row.get("group") or ""), str(row.get("stage") or ""))
                if key in seen:
                    continue
                seen.add(key)
                unique_rows.append(row)
            ok = bool(payloads)
            return FetchResult(
                ok=ok,
                http_status=next((status for status in statuses if status), 200 if ok else 0),
                payload=payloads[0] if len(payloads) == 1 else payloads,
                standings=unique_rows,
                parse_status="ok" if unique_rows else "empty",
                request_count=len(league_ids),
            )
        matches = _load_boards(self._get)
        allowed = set(league_ids)
        events: List[Dict[str, Any]] = []
        for match in matches:
            lid = (match.get("_league") or {}).get("id")
            if str(lid) not in allowed:
                continue
            event = match_to_event(match, competition_id)
            if event:
                events.append(event)
        return FetchResult(
            ok=True,
            http_status=200,
            events=events,
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="fotmob date board + league id(s)",
            request_count=0 if _BOARD.get("all") is not None else len(_dates()),
        )
