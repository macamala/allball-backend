"""worldcup26.ir free football JSON API. No key. ESPN-style league slugs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.http import fetch_url
from collector.provider_catalog import WORLDCUP26_LEAGUES

BASE = "https://worldcup26.ir"
SLUG_BY_COMP = {
    "england-premier-league": "eng.1",
    "england-championship": "eng.2",
    "england-league-one": "eng.3",
    "england-league-two": "eng.4",
    "fa-cup": "eng.fa",
    "spain-la-liga": "esp.1",
    "germany-bundesliga": "ger.1",
    "italy-serie-a": "ita.1",
    "france-ligue-1": "fra.1",
    "netherlands-eredivisie": "ned.1",
    "scotland-premiership": "sco.1",
    "portugal-primeira-liga": "por.1",
    "belgium-pro-league": "bel.1",
    "austria-bundesliga": "aut.1",
    "turkey-super-lig": "tur.1",
    "mls": "usa.1",
    "mexico-liga-mx": "mex.1",
    "argentina-primera": "arg.1",
    "brazil-serie-a": "bra.1",
    "japan-j1": "jpn.1",
}
_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _events(payload: Any, competition_id: str, sport_id: str) -> List[Dict[str, Any]]:
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("events") or payload.get("fixtures") or payload.get("matches") or []
        if not rows and isinstance(payload.get("scoreboard"), dict):
            rows = payload["scoreboard"].get("events") or []
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        competitions = row.get("competitions") or [row]
        for comp in competitions:
            teams = comp.get("competitors") or []
            home = next((item for item in teams if item.get("homeAway") == "home"), teams[0] if teams else None)
            away = next((item for item in teams if item.get("homeAway") == "away"), teams[1] if len(teams) > 1 else None)
            if not isinstance(home, dict) or not isinstance(away, dict):
                continue
            home_name = ((home.get("team") or {}).get("displayName") if isinstance(home.get("team"), dict) else "") or home.get("name")
            away_name = ((away.get("team") or {}).get("displayName") if isinstance(away.get("team"), dict) else "") or away.get("name")
            event = {
                "id": str(row.get("id") or ""),
                "home": {"name": home_name or ""},
                "away": {"name": away_name or ""},
                "status": "scheduled",
                "score": {"home": None, "away": None},
                "start_time": row.get("date"),
                "competition": competition_id,
            }
            if event_is_valid(event, sport_id=sport_id, competition_id=competition_id):
                events.append(event)
    return events


class Worldcup26ApiAdapter:
    adapter_key = "worldcup26-api"

    def __init__(self, source_id: str = "worldcup26-api", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def fetch(self, request: FetchRequest) -> FetchResult:
        slug = (request.source_config or {}).get("league_slug") or SLUG_BY_COMP.get(request.competition_id or "")
        if not slug or slug not in {row["id"] for row in WORLDCUP26_LEAGUES}:
            return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
        if slug not in _CACHE or self._get is not fetch_url:
            result = self._get(f"{BASE}/get/soccer/{slug}/fixtures?status=all")
            if not result.ok:
                return result
            events = _events(result.payload, request.competition_id or "", request.sport_id or "football")
            if self._get is fetch_url:
                _CACHE[slug] = events
        else:
            events = _CACHE[slug]
        return FetchResult(ok=True, http_status=200, events=events, empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS")
