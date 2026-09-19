"""SportSRC V1 no-key football scores. Reference: mcp-sports-hub sportsrc.ts."""

from __future__ import annotations

from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.http import fetch_url
from collector.provider_catalog import SPORTSRC_LEAGUES

BASE = "https://api.sportsrc.org/"
LEAGUE_BY_COMP = {
    "england-premier-league": "PL",
    "uefa-champions-league": "CL",
    "germany-bundesliga": "BL1",
    "netherlands-eredivisie": "DED",
    "brazil-serie-a": "BSA",
    "spain-la-liga": "PD",
    "france-ligue-1": "FL1",
    "england-championship": "ELC",
    "portugal-primeira-liga": "PPL",
    "italy-serie-a": "SA",
}
_CACHE: Dict[str, List[Dict[str, Any]]] = {}


class SportSrcAdapter:
    adapter_key = "sportsrc"

    def __init__(self, source_id: str = "sportsrc", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def fetch(self, request: FetchRequest) -> FetchResult:
        league = (request.source_config or {}).get("league") or LEAGUE_BY_COMP.get(request.competition_id or "")
        allowed = {row["id"] for row in SPORTSRC_LEAGUES}
        if not league or league not in allowed:
            return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
        if league not in _CACHE or self._get is not fetch_url:
            result = self._get(f"{BASE}?data=results&category=scores&league={league}")
            if not result.ok or not isinstance(result.payload, dict):
                return result if result and not result.ok else FetchResult(ok=True, http_status=200, events=[])
            rows = result.payload.get("data") or []
            events = []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                home = ((row.get("home") or {}).get("name") if isinstance(row.get("home"), dict) else row.get("home")) or row.get("homeTeam") or ""
                away = ((row.get("away") or {}).get("name") if isinstance(row.get("away"), dict) else row.get("away")) or row.get("awayTeam") or ""
                event = {
                    "id": str(row.get("id") or f"{home}-{away}"),
                    "home": {"name": str(home)},
                    "away": {"name": str(away)},
                    "status": "finished",
                    "score": {"home": None, "away": None},
                    "start_time": str(row.get("date") or row.get("utcDate") or ""),
                    "competition": request.competition_id,
                }
                if event_is_valid(event, sport_id="football", competition_id=request.competition_id or ""):
                    events.append(event)
            if self._get is fetch_url:
                _CACHE[league] = events
        else:
            events = _CACHE[league]
        return FetchResult(ok=True, http_status=200, events=events, empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS")
