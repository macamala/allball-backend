"""TheSportsDB v1 free API adapter.

Livescores are premium-only and are not called. Free responses are truncated;
mappings are still competition-specific.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url, family_host_blocked
from collector.family_health import family_rate_limited, note_family_failure, note_family_success

BASE = "https://www.thesportsdb.com/api/v1/json/123"
_RAW_CACHE: Dict[str, FetchResult] = {}
REQUEST_LOG: List[str] = []


def _status(raw: Dict[str, Any], start: Optional[str] = None) -> str:
    value = str(raw.get("strStatus") or "").upper()
    if value in {"FT", "AET", "PEN"}:
        return "finished"
    if value in {"1H", "2H", "HT", "LIVE", "IN PLAY", "INPLAY"}:
        return "live"
    if value in {"PST", "POSTPONED"}:
        return "postponed"
    if value in {"CANC", "ABD"}:
        return "cancelled"
    if raw.get("intHomeScore") not in (None, "") and value in {"", "NS"}:
        from collector.live_state import guard_future_status

        return guard_future_status("finished", start, inferred=True)
    return "scheduled"


def _event(raw: Any, competition_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    start = raw.get("strTimestamp") or None
    timezone = "UTC" if start else None
    if not start and raw.get("dateEvent"):
        clock = (raw.get("strTime") or "").strip()
        if clock and clock not in {"00:00:00", "00:00"}:
            start = f"{raw.get('dateEvent')}T{clock}"
        else:
            start = str(raw.get("dateEvent"))
    home_name = raw.get("strHomeTeam") or ""
    away_name = raw.get("strAwayTeam") or ""
    event_name = (raw.get("strEvent") or "").strip()
    if not home_name and not away_name:
        if (raw.get("strSport") or "").lower() != "golf" or not event_name:
            return None
        home_name = re.sub(r"\s+(Round\s+\d+|Final Round)\s*$", "", event_name, flags=re.I).strip() or event_name
        away_name = raw.get("strLeague") or "Golf"
        if (raw.get("dateEventLocal") or "").strip():
            start = str(raw.get("dateEventLocal"))
    inferred = str(raw.get("strStatus") or "").upper() in {"", "NS"} and raw.get("intHomeScore") not in (None, "")
    return {
        "id": str(raw.get("idEvent") or ""),
        "home": {"id": str(raw.get("idHomeTeam") or ""), "name": home_name},
        "away": {"id": str(raw.get("idAwayTeam") or ""), "name": away_name},
        "status": _status(raw, start),
        "status_inferred": inferred,
        "score": {"home": _num(raw.get("intHomeScore")), "away": _num(raw.get("intAwayScore"))},
        "start_time": start,
        "timezone": timezone,
        "source_family": "thesportsdb",
        "venue": raw.get("strVenue"),
        "season": raw.get("strSeason"),
        "round": raw.get("intRound"),
        "competition": raw.get("strLeague") or competition_id,
        "source_competition_name": raw.get("strLeague") or "",
        "source_competition_id": str(raw.get("idLeague") or "") or None,
        "country_id": raw.get("strCountry"),
    }


def _num(value: Any) -> Any:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _table_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        out.append(
            {
                "position": _num(row.get("intRank")),
                "team": row.get("strTeam"),
                "played": _num(row.get("intPlayed")),
                "wins": _num(row.get("intWin")),
                "draws": _num(row.get("intDraw")),
                "losses": _num(row.get("intLoss")),
                "goal_difference": _num(row.get("intGoalDifference")),
                "points": _num(row.get("intPoints")),
            }
        )
    return out


def reset_thesportsdb_cache() -> None:
    _RAW_CACHE.clear()
    REQUEST_LOG.clear()


class TheSportsDbAdapter:
    adapter_key = "thesportsdb"
    source_id = "thesportsdb"

    def __init__(self, source_id: str = "thesportsdb", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if family_rate_limited("thesportsdb") or family_host_blocked("thesportsdb"):
            return FetchResult(ok=False, http_status=429, error="thesportsdb family cooldown", classification="RATE_LIMITED")
        league_id = request.source_competition_id
        if league_id and not str(league_id).isdigit():
            from collector.family_catalog import TSDB_BY_COMP

            league_id = TSDB_BY_COMP.get(request.competition_id or "") or league_id
        if not league_id:
            return FetchResult(ok=True, http_status=200, events=[])
        if request.capability == "live_scores":
            return FetchResult(ok=True, http_status=200, events=[], error="livescores require TheSportsDB premium")
        if request.capability == "standings":
            result = self._get(f"{BASE}/lookuptable.php?l={league_id}")
            if not result.ok:
                return result
            table = (result.payload or {}).get("table") if isinstance(result.payload, dict) else []
            return FetchResult(
                ok=True,
                http_status=result.http_status,
                payload=result.payload,
                standings=_table_rows(table or []),
            )
        next_url = f"{BASE}/eventsnextleague.php?id={league_id}"
        past_url = f"{BASE}/eventspastleague.php?id={league_id}"
        next_result = self._cached_get(next_url)
        if next_result.restricted or (not next_result.ok and next_result.http_status in {401, 403, 429}):
            if next_result.http_status == 429 or next_result.classification == "RATE_LIMITED":
                note_family_failure("thesportsdb", http_status=429, error_type="RATE_LIMITED")
            return next_result
        if not next_result.ok and next_result.http_status == 0:
            return next_result
        past_result = FetchResult(ok=True, http_status=next_result.http_status or 200, payload={"events": []})
        if request.capability in {"results", "snapshot", "event"}:
            past_result = self._cached_get(past_url)
            if past_result.restricted or (not past_result.ok and past_result.http_status in {401, 403, 429}):
                if past_result.http_status == 429 or past_result.classification == "RATE_LIMITED":
                    note_family_failure("thesportsdb", http_status=429, error_type="RATE_LIMITED")
                    return past_result
        if not past_result.ok:
            past_result = FetchResult(ok=True, http_status=next_result.http_status or 200, payload={"events": []})
        season_result = None
        if (request.competition_id or "") == "korean-golf-tour":
            season_result = self._cached_get(f"{BASE}/eventsseason.php?id={league_id}&s=2026")
        events_raw: List[Any] = []
        blobs = [next_result.payload, past_result.payload]
        if season_result is not None:
            blobs.append(season_result.payload)
        for blob in blobs:
            if isinstance(blob, dict):
                chunk = blob.get("events")
                if isinstance(chunk, list):
                    events_raw.extend(chunk)
            elif isinstance(blob, list):
                events_raw.extend(blob)
        mapped = [row for row in (_event(item, request.competition_id or "") for item in events_raw) if row]
        if request.capability == "results":
            mapped = [row for row in mapped if row["status"] == "finished"]
        elif request.capability == "fixtures":
            mapped = [row for row in mapped if row["status"] != "finished"]
        note_family_success("thesportsdb", http_status=200, events=len(mapped), parse_ok=True)
        return FetchResult(
            ok=True,
            http_status=200,
            payload={"next": next_result.payload, "past": past_result.payload},
            events=mapped,
            empty_reason="SOURCE_HEALTHY_NO_EVENTS" if not mapped else None,
        )

    def _cached_get(self, url: str) -> FetchResult:
        REQUEST_LOG.append(url)
        cached = _RAW_CACHE.get(url)
        if cached is not None:
            return cached
        result = self._get(url)
        if result.http_status != 0:
            _RAW_CACHE[url] = result
        return result
