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
MAX_MATCH_FETCHES = 6
LIVE_SCORE_MATCH_FETCHES = 1
WINDOW_PAST_DAYS = 14
WINDOW_FUTURE_DAYS = 21

_MATCH_CACHE: Dict[str, Dict[str, Any]] = {}
_CALENDAR_CACHE: Dict[str, Any] = {"at": 0.0, "rows": []}


def reset_wta_caches() -> None:
    _MATCH_CACHE.clear()
    _CALENDAR_CACHE["at"] = 0.0
    _CALENDAR_CACHE["rows"] = []


def match_to_event(row: Dict[str, Any], competition_id: str, tournament: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
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
    payload = {
        "id": oriented["source_event_id"] or f"wta:{row.get('EventID')}:{home}:{away}",
        "home": {"name": home, "side": "home"},
        "away": {"name": away, "side": "away"},
        "participant_a": {"name": home, "side": "a"},
        "participant_b": {"name": away, "side": "b"},
        "status": oriented["status"],
        "score": oriented["score"],
        "start_time": row.get("MatchTimeStamp"),
        "venue": venue.get("name") or extra_meta.get("location"),
        "competition": competition_id,
        "round": row.get("DrawLevelType"),
        "periods": oriented["periods"],
        "source_family": "wta-json",
        "source_event_id": oriented["source_event_id"],
        "walkover": True if oriented["result_type"] == "walkover" else None,
        "result_type": oriented["result_type"],
        **extra_meta,
    }
    if oriented["orientation_conflict"]:
        payload["orientation_conflict"] = True
    return payload


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
        max_fetches = LIVE_SCORE_MATCH_FETCHES if live_scores else MAX_MATCH_FETCHES
        events: List[Dict[str, Any]] = []
        fetches = 0
        for group_id, year, meta in tournaments:
            if fetches >= max_fetches:
                break
            key = f"{group_id}:{year}"
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
                event = match_to_event(row, request.competition_id or "wta-tour", meta)
                if event:
                    events.append(event)
        STATS["wta_tournaments_selected"] = min(len(tournaments), max_fetches)
        STATS["wta_match_fetches"] = fetches
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(ok=True, http_status=200, events=events, empty_reason=empty_reason)
