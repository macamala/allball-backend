"""OpenDota professional match feed. Free tier, no key, 60 req/min.

Creates competitions from real pro-league names present in the feed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url
from collector.util import slugify

API = "https://api.opendota.com/api/proMatches"


def _event(row: Dict[str, Any]) -> Dict[str, Any]:
    league = row.get("league_name") or "Dota 2 professional"
    start = row.get("start_time")
    iso = None
    if start:
        iso = datetime.fromtimestamp(int(start), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    finished = bool(row.get("duration"))
    return {
        "id": str(row.get("match_id") or ""),
        "home": {"id": str(row.get("radiant_team_id") or ""), "name": row.get("radiant_name") or "Radiant"},
        "away": {"id": str(row.get("dire_team_id") or ""), "name": row.get("dire_name") or "Dire"},
        "status": "finished" if finished else "live",
        "score": {"home": row.get("radiant_score"), "away": row.get("dire_score")},
        "start_time": iso,
        "game_id": "dota-2",
        "sport": "dota-2",
        "competition": league,
        "competition_key": f"dota-2-{slugify(league)}",
        "event_family": "esports_match",
        "series_id": str(row.get("series_id") or "") or None,
        "best_of": {0: 1, 1: 3, 2: 5}.get(row.get("series_type")),
        "winner": row.get("radiant_name")
        if row.get("radiant_win")
        else (row.get("dire_name") if row.get("radiant_win") is False else None),
        "source_family": "opendota",
        "source_event_id": str(row.get("match_id") or ""),
        "source_event_ids": {"opendota": str(row.get("match_id") or "")},
        "extra": {
            "source_family": "opendota",
            "source_event_id": str(row.get("match_id") or ""),
            "source_event_ids": {"opendota": str(row.get("match_id") or "")},
        },
    }


class OpenDotaAdapter:
    adapter_key = "opendota"
    source_id = "opendota"

    def __init__(self, source_id: str = "opendota", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get(API)
        if not result.ok:
            return result
        rows = result.payload if isinstance(result.payload, list) else []
        events = [_event(row) for row in rows if row.get("radiant_name") or row.get("dire_name")]
        if request.capability == "results":
            events = [row for row in events if row["status"] == "finished"]
        elif request.capability == "live_scores":
            events = [row for row in events if row["status"] == "live"]
        elif request.capability == "fixtures":
            events = [row for row in events if row["status"] != "live"]
        return FetchResult(ok=True, http_status=result.http_status, payload=result.payload, events=events)
