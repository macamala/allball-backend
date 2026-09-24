"""Public WTA JSON backend used by wtatennis.com.

Base: https://api.wtatennis.com/tennis/
Tournament list: GET /tournaments?page=&pageSize= (chronological, not year-filtered)
Tournament matches: /tournaments/{tournamentGroup.id}/{year}/matches

Calendar discovery reads the last few pages of /tournaments (recent/future end
of the list) and keeps a 12h cache. It does not walk the full 18k history.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from collector.adapters import FetchRequest, FetchResult
from collector.http import STATS, fetch_url
from collector.metrics import incr
from collector.wta_orientation import orient_wta_match

BASE = "https://api.wtatennis.com/tennis"
DEFAULT_TOURNAMENTS = [(901, 2026)]
CALENDAR_TTL_S = 12 * 3600
LIVE_MATCH_TTL_S = 45
PAST_MATCH_TTL_S = 12 * 3600
MAX_MATCH_FETCHES = 36
LIVE_SCORE_MATCH_FETCHES = 1
WINDOW_PAST_DAYS = 14
WINDOW_FUTURE_DAYS = 21

_MATCH_CACHE: Dict[str, Dict[str, Any]] = {}
_PLAYER_CACHE: Dict[str, Dict[str, Any]] = {}
_CALENDAR_CACHE: Dict[str, Any] = {"at": 0.0, "rows": []}


def reset_wta_caches() -> None:
    _MATCH_CACHE.clear()
    _PLAYER_CACHE.clear()
    _CALENDAR_CACHE["at"] = 0.0
    _CALENDAR_CACHE["rows"] = []


def _fold_player_name(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _player_country_map(payload: Any) -> Dict[str, str]:
    """Index WTA tournament entry-list countries by stable id and full name."""
    out: Dict[str, str] = {}
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            player = node.get("player") if isinstance(node.get("player"), dict) else node
            country = str(
                player.get("countryCode")
                or player.get("country_code")
                or player.get("nationality")
                or node.get("countryCode")
                or ""
            ).strip()
            if country:
                player_id = str(player.get("id") or node.get("playerId") or node.get("playerID") or "").strip()
                full_name = str(
                    player.get("fullName")
                    or player.get("displayName")
                    or player.get("name")
                    or ""
                ).strip()
                if not full_name:
                    full_name = " ".join(
                        part
                        for part in (
                            str(player.get("firstName") or "").strip(),
                            str(player.get("lastName") or "").strip(),
                        )
                        if part
                    )
                if player_id:
                    out[f"id:{player_id}"] = country
                if full_name:
                    out[f"name:{_fold_player_name(full_name)}"] = country
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def _countries_for_name(name: str, player_countries: Optional[Dict[str, str]]) -> List[str]:
    lookup = player_countries or {}
    countries: List[str] = []
    for part in str(name or "").split("/"):
        folded = _fold_player_name(part)
        country = lookup.get(f"name:{folded}", "")
        if country and country not in countries:
            countries.append(country)
    return countries


def _country_for_side(row: Dict[str, Any], prefix: str, name: str, player_countries: Optional[Dict[str, str]]) -> str:
    country = (
        row.get(f"CountryCode{prefix}")
        or row.get(f"Country{prefix}")
        or row.get(f"PlayerCountryCode{prefix}")
        or row.get(f"PlayerCountry{prefix}")
        or row.get(f"Nationality{prefix}")
    )
    if country not in (None, ""):
        return str(country)
    lookup = player_countries or {}
    player_id = (
        row.get(f"PlayerID{prefix}")
        or row.get(f"PlayerId{prefix}")
        or row.get(f"Player{prefix}ID")
        or row.get(f"Player{prefix}Id")
    )
    if player_id not in (None, "") and lookup.get(f"id:{player_id}"):
        return lookup[f"id:{player_id}"]
    return lookup.get(f"name:{_fold_player_name(name)}", "")


def match_to_event(
    row: Dict[str, Any],
    competition_id: str,
    tournament: Optional[Dict[str, Any]] = None,
    player_countries: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    oriented = orient_wta_match(row, tournament)
    home = oriented["home_name"]
    away = oriented["away_name"]
    if not home or not away:
        return None
    venue = row.get("Venue") if isinstance(row.get("Venue"), dict) else {}
    group = (tournament or {}).get("tournamentGroup") or {}
    extra_meta = {
        k: v
        for k, v in {
            "tournament_id": group.get("id") or (tournament or {}).get("id"),
            "tournament_name": group.get("name") or (tournament or {}).get("title"),
            "location": (tournament or {}).get("city"),
            "country": (tournament or {}).get("country"),
            "surface": (tournament or {}).get("surface"),
            "category": (tournament or {}).get("level") or group.get("level"),
            "tournament_start": (tournament or {}).get("startDate"),
            "tournament_end": (tournament or {}).get("endDate"),
        }.items()
        if v not in (None, "")
    }
    home_side = {"name": home, "side": "home"}
    away_side = {"name": away, "side": "away"}
    for side, prefix in ((home_side, "A"), (away_side, "B")):
        seed = row.get(f"Seed{prefix}") or row.get(f"PlayerSeed{prefix}") or row.get(f"SeedPlayer{prefix}")
        rank = row.get(f"Rank{prefix}") or row.get(f"PlayerRank{prefix}") or row.get(f"Ranking{prefix}")
        player_id = (
            row.get(f"PlayerID{prefix}")
            or row.get(f"PlayerId{prefix}")
            or row.get(f"Player{prefix}ID")
            or row.get(f"Player{prefix}Id")
        )
        country = _country_for_side(row, prefix, side["name"], player_countries)
        if player_id not in (None, ""):
            side["id"] = str(player_id)
        if country not in (None, ""):
            side["country_id"] = str(country)
        else:
            country_ids = _countries_for_name(side["name"], player_countries)
            if len(country_ids) == 1:
                side["country_id"] = country_ids[0]
            elif country_ids:
                side["country_ids"] = country_ids
        if seed not in (None, ""):
            side["seed"] = seed
        if rank not in (None, ""):
            side["rank"] = rank
    payload = {
        "id": oriented["source_event_id"] or f"wta:{row.get('EventID')}:{home}:{away}",
        "home": home_side,
        "away": away_side,
        "participant_a": {**home_side, "side": "a"},
        "participant_b": {**away_side, "side": "b"},
        "status": oriented["status"],
        "score": oriented["score"],
        "start_time": row.get("MatchTimeStamp"),
        "venue": venue.get("name") or extra_meta.get("location"),
        "competition": competition_id,
        "round": row.get("DrawLevelType"),
        "periods": oriented["periods"],
        "source_family": "wta-json",
        "source_event_id": oriented["source_event_id"],
        "source_event_ids": {"wta-json": oriented["source_event_id"]},
        "walkover": True if oriented["result_type"] == "walkover" else None,
        "result_type": oriented["result_type"],
        **extra_meta,
    }
    stats = wta_match_statistics(row)
    if stats:
        payload["statistics"] = stats
    if oriented["orientation_conflict"]:
        payload["orientation_conflict"] = True
    return payload


_WTA_STAT_PAIRS = (
    ("AcesA", "AcesB", "Aces"),
    ("DoubleFaultsA", "DoubleFaultsB", "Double faults"),
    ("FirstServePercentageA", "FirstServePercentageB", "First serve %"),
    ("FirstServeA", "FirstServeB", "First serve %"),
    ("FirstServePointsWonA", "FirstServePointsWonB", "First serve points won"),
    ("BreakPointsConvertedA", "BreakPointsConvertedB", "Break points converted"),
    ("BreakPointsWonA", "BreakPointsWonB", "Break points won"),
    ("WinnersA", "WinnersB", "Winners"),
    ("UnforcedErrorsA", "UnforcedErrorsB", "Unforced errors"),
)


def wta_match_statistics(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for key_a, key_b, label in _WTA_STAT_PAIRS:
        if label in seen:
            continue
        home = row.get(key_a)
        away = row.get(key_b)
        if home in (None, "") and away in (None, ""):
            continue
        seen.add(label)
        out.append({"label": label, "home": home, "away": away})
    return out


def _parse_day(value: Any) -> Optional[date]:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _in_window(row: Dict[str, Any], today: date) -> bool:
    start = _parse_day(row.get("startDate"))
    end = _parse_day(row.get("endDate")) or start
    if not start:
        return False
    return start <= today + timedelta(days=WINDOW_FUTURE_DAYS) and (end or start) >= today - timedelta(days=WINDOW_PAST_DAYS)


def _status_rank(status: str) -> int:
    value = (status or "").lower()
    if value in {"live", "inprogress"}:
        return 0
    if value in {"future", "upcoming"}:
        return 1
    if value in {"past"}:
        return 2
    return 3


def discover_current_tournaments(getter, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.utcnow()
    today = now.date() if hasattr(now, "date") else date.today()
    cached = _CALENDAR_CACHE.get("rows") or []
    if cached and (time.monotonic() - float(_CALENDAR_CACHE.get("at") or 0)) < CALENDAR_TTL_S:
        return [row for row in cached if _in_window(row, today)]
    listing = getter(f"{BASE}/tournaments?page=0&pageSize=1")
    incr("wta_calendar_http")
    if not listing.ok or not isinstance(listing.payload, dict):
        return [row for row in cached if _in_window(row, today)]
    info = listing.payload.get("pageInfo") or {}
    total = int(info.get("numEntries") or 0)
    page_size = 50
    last = max(0, (total + page_size - 1) // page_size - 1) if total else 0
    pages = sorted({last, max(0, last - 1), max(0, last - 2)})
    rows: List[Dict[str, Any]] = []
    for page in pages:
        result = getter(f"{BASE}/tournaments?page={page}&pageSize={page_size}")
        incr("wta_calendar_http")
        if not result.ok or not isinstance(result.payload, dict):
            continue
        rows.extend(item for item in (result.payload.get("content") or []) if isinstance(item, dict))
    _CALENDAR_CACHE["at"] = time.monotonic()
    _CALENDAR_CACHE["rows"] = rows
    STATS["wta_calendar_rows"] = len(rows)
    windowed = [row for row in rows if _in_window(row, today)]
    windowed.sort(key=lambda row: (_status_rank(str(row.get("status") or "")), str(row.get("startDate") or "")))
    return windowed


class WtaJsonAdapter:
    adapter_key = "wta-json"

    def __init__(self, source_id: str = "wta-json", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        config = request.source_config or {}
        discovered = discover_current_tournaments(self._get)
        tournaments: List[Tuple[int, int, Optional[Dict[str, Any]]]] = []
        for row in discovered:
            group = row.get("tournamentGroup") or {}
            try:
                tournaments.append((int(group.get("id")), int(row.get("year")), row))
            except (TypeError, ValueError):
                continue
        if not tournaments:
            configured = list(config.get("tournaments") or DEFAULT_TOURNAMENTS)
            tournaments = [(int(group_id), int(year), None) for group_id, year in configured]
        live_scores = request.capability == "live_scores"
        if live_scores:
            tournaments.sort(key=lambda row: _status_rank(str((row[2] or {}).get("status") or "")))
            live_only = [
                row
                for row in tournaments
                if str((row[2] or {}).get("status") or "").lower() in {"live", "inprogress"}
            ]
            tournaments = live_only or tournaments[:1]
        if request.capability in {"results", "fixtures"} and not live_scores:
            tournaments.sort(
                key=lambda row: (
                    0 if str((row[2] or {}).get("status") or "").lower() == "past" else 1,
                    _status_rank(str((row[2] or {}).get("status") or "")),
                )
            )
        max_fetches = LIVE_SCORE_MATCH_FETCHES if live_scores else int(
            (config or {}).get("max_match_fetches") or MAX_MATCH_FETCHES
        )
        events: List[Dict[str, Any]] = []
        fetches = 0
        for group_id, year, meta in tournaments:
            if fetches >= max_fetches:
                break
            key = f"{group_id}:{year}"
            player_countries: Dict[str, str] = {}
            player_cached = _PLAYER_CACHE.get(key) or {}
            if player_cached and (time.monotonic() - float(player_cached.get("at") or 0)) < PAST_MATCH_TTL_S:
                player_countries = dict(player_cached.get("countries") or {})
            else:
                players_result = self._get(f"{BASE}/tournaments/{group_id}/{year}/players")
                incr("wta_player_http")
                if players_result.ok:
                    player_countries = _player_country_map(players_result.payload)
                    _PLAYER_CACHE[key] = {"at": time.monotonic(), "countries": player_countries}
            cached = _MATCH_CACHE.get(key) or {}
            status = str((meta or {}).get("status") or "").lower()
            ttl = LIVE_MATCH_TTL_S if status in {"live", "inprogress"} else PAST_MATCH_TTL_S
            rows = None
            if cached and (time.monotonic() - float(cached.get("at") or 0)) < ttl:
                rows = cached.get("rows")
            else:
                result = self._get(f"{BASE}/tournaments/{group_id}/{year}/matches")
                fetches += 1
                incr("wta_match_http")
                if not result.ok or not isinstance(result.payload, dict):
                    continue
                rows = [row for row in (result.payload.get("matches") or []) if isinstance(row, dict)]
                _MATCH_CACHE[key] = {"at": time.monotonic(), "rows": rows}
            for row in rows or []:
                event = match_to_event(
                    row,
                    request.competition_id or "wta-tour",
                    meta,
                    player_countries=player_countries,
                )
                if event:
                    events.append(event)
        STATS["wta_tournaments_selected"] = min(len(tournaments), max_fetches)
        STATS["wta_match_fetches"] = fetches
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(ok=True, http_status=200, events=events, empty_reason=empty_reason)
