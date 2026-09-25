"""FotMob public JSON family. One date-board fetch is reused across leagues."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

# Railway-proven FotMob league IDs (www.fotmob.com/api/data/allLeagues, 2026-09-20).
FOTMOB_LEAGUES: Dict[str, Dict[str, Any]] = {
    "albania-superliga": {"id": 260, "name": "Kategoria Superiore", "ccode": "alb"},
    "australia-a-league-women": {"id": 9495, "name": "A-League Women", "ccode": "aus"},
    "argentina-primera": {"id": 112, "name": "Liga Profesional", "ccode": "arg"},
    "austria-bundesliga": {"id": 38, "name": "Bundesliga", "ccode": "aut"},
    "brazil-serie-a": {"id": 268, "name": "Serie A", "ccode": "bra"},
    "denmark-superliga": {"id": 46, "name": "Superligaen", "ccode": "den"},
    "football-friendlies-women": {"id": 293, "name": "Women's Friendlies", "ccode": "int"},
    "germany-2-bundesliga": {"id": 146, "name": "2. Bundesliga", "ccode": "ger"},
    "germany-3-liga": {"id": 208, "name": "3. Liga", "ccode": "ger"},
    "fa-cup": {"id": 132, "name": "FA Cup", "ccode": "eng"},
    "mls": {"id": 130, "name": "MLS", "ccode": "usa"},
    "spain-copa-del-rey": {"id": 138, "name": "Copa del Rey", "ccode": "esp"},
    "sweden-allsvenskan": {"id": 67, "name": "Allsvenskan", "ccode": "swe"},
    "switzerland-super-league": {"id": 69, "name": "Super League", "ccode": "sui"},
    "thai-league-1": {"id": 8984, "name": "Thai League", "ccode": "tha"},
    "ukraine-premier-league": {"id": 441, "name": "Premier League", "ccode": "ukr"},
    "uzbekistan-super-league": {"id": 540, "name": "Superliga", "ccode": "uzb"},
    "womens-super-league": {"id": 9227, "name": "Women's Super League", "ccode": "eng"},
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

# Public/canonical competition keys that are intentionally NOT enabled as
# FotMob ingestion sources. They may still reuse a verified FotMob league
# roster for identity artwork backfill. Keeping this separate from
# FOTMOB_LEAGUES prevents duplicate fixture ingestion under alias keys.
FOTMOB_ASSET_LEAGUE_ALIASES: Dict[str, List[str]] = {
    "football-tun-ligue-1": ["544"],
    "football-alg-ligue-1": ["516"],
    "football-mar-botola-pro": ["530"],
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


def asset_league_ids(
    competition_id: str,
    source_config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Verified FotMob league ids usable for artwork/identity repair only."""
    key = str(competition_id or "").strip()
    values = [
        *_league_ids(FOTMOB_LEAGUES.get(key) or {}, source_config),
        *(FOTMOB_ASSET_LEAGUE_ALIASES.get(key) or []),
    ]
    out: List[str] = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class FotMobBoardError(RuntimeError):
    def __init__(self, result: FetchResult):
        self.result = result
        super().__init__(str(result.error or "FotMob board unavailable"))


MATCHES_URL = "https://www.fotmob.com/api/data/matches?date={date}"
SCORE_URL = "https://www.fotmob.com/api/data/match-score?matchId={match_id}"

_BATCH_BOARDS: ContextVar = ContextVar("fotmob_batch_boards", default=None)


@contextmanager
def shared_board_batch():
    token = _BATCH_BOARDS.set({})
    try:
        yield
    finally:
        _BATCH_BOARDS.reset(token)


_BOARD: Dict[str, List[Dict[str, Any]]] = {}
_BOARD_AT: Dict[str, float] = {}
LIVE_BOARD_TTL_SECONDS = 5
FIXTURE_BOARD_TTL_SECONDS = 60


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


def _board_league(node: Dict[str, Any]) -> Dict[str, Any]:
    """Retain both the competition ID and its season-specific group ID."""
    return {
        "id": node.get("id") or node.get("primaryId"),
        "primaryId": node.get("primaryId"),
        "parentLeagueId": node.get("parentLeagueId"),
        "parentLeagueName": node.get("parentLeagueName"),
        "name": node.get("name") or node.get("ccode"),
        "ccode": node.get("ccode"),
        "isGroup": bool(node.get("isGroup")),
        "groupName": node.get("groupName"),
    }


def _matching_league_id(league: Dict[str, Any], allowed: set[str]) -> str:
    # A group cannot match by name, number, or another league's group. Only
    # explicit IDs from the same upstream node authorize this competition.
    for value in (league.get("id"), league.get("primaryId"), league.get("parentLeagueId")):
        if value is not None and str(value) in allowed:
            return str(value)
    return ""


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
            lg = _board_league(node)
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
            next_league = _board_league(node)
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
    league_id = str((league or {}).get("parentLeagueId") or (league or {}).get("primaryId") or (league or {}).get("id") or "").strip()
    return f"https://images.fotmob.com/image_resources/logo/leaguelogo/{league_id}.png" if league_id else ""


def _fotmob_status(status: Dict[str, Any]) -> str:
    reason = status.get("reason") if isinstance(status.get("reason"), dict) else {}
    raw_reason = str(reason.get("short") or reason.get("long") or "").strip().lower()
    normalized = "".join(ch for ch in raw_reason if ch.isalnum())

    # FotMob can keep started=false/finished=false for non-played terminal
    # states. Preserve that lifecycle instead of silently calling everything
    # scheduled.
    if "postp" in normalized or "postpon" in normalized:
        return "postponed"
    if "cancel" in normalized or "cancl" in normalized:
        return "cancelled"
    if "aband" in normalized or "abnd" in normalized:
        return "abandoned"
    if "susp" in normalized:
        return "suspended"
    if "delay" in normalized:
        return "delayed"
    if bool(status.get("finished")):
        return "finished"
    live_time = status.get("liveTime") if isinstance(status.get("liveTime"), dict) else {}
    phase = str(live_time.get("short") or live_time.get("long") or "").strip().lower().replace("-", "")
    if bool(status.get("started")) and (normalized in {"ht", "halftime", "break"} or phase in {"ht", "halftime", "break"}):
        return "break"
    if bool(status.get("started")):
        return "live"
    return "scheduled"


def _scores(status: Dict[str, Any], match: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    raw = status.get("scoreStr") or match.get("score")
    if isinstance(raw, str) and "-" in raw:
        left, right = raw.split("-", 1)
        return _int_or_none(left.strip()), _int_or_none(right.strip())
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    return _int_or_none(home.get("score")), _int_or_none(away.get("score"))


def match_to_event(match: Dict[str, Any], competition_id: str, *, source_league_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    home = match.get("home") if isinstance(match.get("home"), dict) else {}
    away = match.get("away") if isinstance(match.get("away"), dict) else {}
    home_name = (home.get("name") or home.get("shortName") or "").strip()
    away_name = (away.get("name") or away.get("shortName") or "").strip()
    if not home_name or not away_name:
        return None
    status_obj = match.get("status") if isinstance(match.get("status"), dict) else {}
    started = bool(status_obj.get("started"))
    status = _fotmob_status(status_obj)
    home_score, away_score = _scores(status_obj, match)
    if not started and status != "finished":
        home_score = None
        away_score = None
    live_time = status_obj.get("liveTime") if isinstance(status_obj.get("liveTime"), dict) else {}
    minute = live_time.get("short") or live_time.get("long") or None
    score: Dict[str, Any] = {"home": home_score, "away": away_score}
    if minute not in (None, ""):
        score["minute"] = minute
    league = match.get("_league") or {}
    source_league_id = source_league_id or str(league.get("id") or "")
    group_identity = {}
    if league.get("isGroup") and league.get("id"):
        group_identity = {
            "source_group_id": str(league["id"]),
            "source_parent_competition_id": str(league.get("parentLeagueId") or league.get("primaryId") or ""),
            "group": str(league.get("name") or league.get("groupName") or ""),
            "group_name": str(league.get("groupName") or ""),
            "stage": str(league.get("parentLeagueName") or ""),
        }
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
        "sport": "football",
        "source_competition_context": dict(league),
        "source_event_id": str(match.get("id") or ""),
        "source_competition_id": source_league_id,
        "source_competition_name": str(league.get("name") or ""),
        "competition_logo": _league_logo(league),
        "source_badge_group_id": str(league.get("id") or ""),
        "source_badge_parent_id": str(league.get("parentLeagueId") or league.get("primaryId") or league.get("id") or ""),
        "source_fetch_time": match.get("_source_fetched_at"),
        "fetch_completed_at": match.get("_source_fetched_at"),
        **group_identity,
        "extra": {
            **group_identity,
            "source_family": "fotmob",
            "source_status": status_obj.get("reason", {}).get("short") if isinstance(status_obj.get("reason"), dict) else status,
            "status_inferred": False,
            "source_event_ids": {"fotmob": str(match.get("id") or "")},
            "source_event_id": str(match.get("id") or ""),
            "source_competition_id": source_league_id,
            "source_competition_name": str(league.get("name") or ""),
        },
    }


def current_batch_has_board(capability: str) -> bool:
    if capability not in {"fixtures", "results", "live_scores"}:
        return False
    batch = _BATCH_BOARDS.get()
    if batch is None:
        return False
    days = board_dates(past_days=1, future_days=0) if capability == "live_scores" else _dates()
    ttl = LIVE_BOARD_TTL_SECONDS if capability == "live_scores" else FIXTURE_BOARD_TTL_SECONDS
    return ("d:" + ",".join(days), ttl) in batch


def _load_boards(
    getter,
    dates: Optional[List[str]] = None,
    *,
    ttl_seconds: int = FIXTURE_BOARD_TTL_SECONDS,
) -> List[Dict[str, Any]]:
    days = list(dates or _dates())
    cache_key = "d:" + ",".join(days)
    batch = _BATCH_BOARDS.get()
    batch_key = (cache_key, ttl_seconds)
    if batch is not None and batch_key in batch:
        return batch[batch_key]
    now_mono = time.monotonic()
    cached = _BOARD.get(cache_key)
    cached_at = _BOARD_AT.get(cache_key, 0.0)
    if cached is not None and now_mono - cached_at < max(0, ttl_seconds):
        if batch is not None:
            batch[batch_key] = cached
        return cached
    if dates is None and _BOARD.get("all") is not None:
        all_at = _BOARD_AT.get("all", 0.0)
        if now_mono - all_at < max(0, ttl_seconds):
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
        if not getattr(result, "ok", False) or payload is None:
            # Failed reads are not a healthy empty board. Do not poison the
            # board cache or let discovery acknowledge this day as complete.
            raise FotMobBoardError(result)
        fetched_at = getattr(result, "fetched_at", None) or datetime.now(timezone.utc).isoformat()
        for match in _extract_matches(payload):
            match["_board_date"] = day
            match["_source_fetched_at"] = fetched_at
            rows.append(match)
    if batch is not None:
        batch[batch_key] = rows
    _BOARD[cache_key] = rows
    _BOARD_AT[cache_key] = time.monotonic()
    if dates is None:
        _BOARD["all"] = rows
        _BOARD_AT["all"] = _BOARD_AT[cache_key]
    return rows


def parse_fotmob_table(payload: Any) -> List[Dict[str, Any]]:
    from collector.fotmob_tables import parse_tables
    return parse_tables(payload)


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
        try:
            if request.capability == "live_scores":
                live_dates = board_dates(past_days=1, future_days=0)
                matches = _load_boards(
                    self._get,
                    dates=live_dates,
                    ttl_seconds=LIVE_BOARD_TTL_SECONDS,
                )
            else:
                matches = _load_boards(
                    self._get,
                    ttl_seconds=FIXTURE_BOARD_TTL_SECONDS,
                )
        except FotMobBoardError as exc:
            failed = exc.result
            return FetchResult(ok=False, http_status=failed.http_status,
                               restricted=failed.restricted, error=str(exc),
                               classification=failed.classification, parse_status="failed")
        allowed = set(league_ids)
        events: List[Dict[str, Any]] = []
        for match in matches:
            lid = _matching_league_id(match.get("_league") or {}, allowed)
            if not lid:
                continue
            event = match_to_event(match, competition_id, source_league_id=lid)
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
