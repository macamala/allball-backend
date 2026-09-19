"""Sporting Events free CSV/JSON datasets. Attribution required."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid, split_fixture
from collector.http import fetch_url

ATTRIBUTION = {
    "required": True,
    "text": "Fixture data from Sporting Events",
    "url": "https://sporting-events.org/data/",
}

DATASETS = {
    "nrl": "https://sporting-events.org/data/nrl.json",
    "motogp": "https://sporting-events.org/data/motogp.json",
    "ufc": "https://sporting-events.org/data/ufc.json",
    "tennis": "https://sporting-events.org/data/tennis.json",
    "swimming": "https://sporting-events.org/data/swimming.json",
    "golf": "https://sporting-events.org/data/golf.json",
    "esports": "https://sporting-events.org/data/esports.json",
    "rugby-union": "https://sporting-events.org/data/rugby-union.json",
    "football": "https://sporting-events.org/data/football.json",
}

COMPETITION_DATASET = {
    "nrl": "nrl",
    "motogp": "motogp",
    "ufc": "ufc",
    "title-fights": "ufc",
    "atp-tour": "tennis",
    "wta-tour": "tennis",
    "world-aquatics-meets": "swimming",
    "korean-golf-tour": "golf",
    "vct": "esports",
    "worlds-msi-regional": "esports",
    "tier1": "esports",
}

_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def _row_event(row: Dict[str, Any], competition_id: str, sport_id: str) -> Optional[Dict[str, Any]]:
    home = (row.get("home_team") or "").strip()
    away = (row.get("away_team") or "").strip()
    if not home or not away:
        parsed = split_fixture(row.get("fixture") or "")
        if parsed:
            home, away = parsed
    event = {
        "id": row.get("url") or f"sporting-events:{competition_id}:{row.get('date_utc')}:{home}:{away}",
        "home": {"name": home},
        "away": {"name": away},
        "status": "finished" if (row.get("status") or "") in {"completed", "finished"} else "scheduled",
        "score": {"home": None, "away": None},
        "start_time": f"{row.get('date_utc') or ''}T{(row.get('time_utc') or '00:00')}:00Z",
        "venue": row.get("city"),
        "competition": row.get("competition") or competition_id,
        "extra": {"attribution": ATTRIBUTION, "source_url": row.get("url")},
    }
    if not event_is_valid(event, sport_id=sport_id, competition_id=competition_id):
        return None
    return event


class SportingEventsAdapter:
    adapter_key = "sporting-events"

    def __init__(self, source_id: str = "sporting-events", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def fetch(self, request: FetchRequest) -> FetchResult:
        dataset = (request.source_config or {}).get("dataset") or COMPETITION_DATASET.get(request.competition_id or "")
        url = DATASETS.get(dataset or "")
        if not url:
            return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
        if dataset not in _CACHE or self._get is not fetch_url:
            result = self._get(url)
            if not result.ok or not isinstance(result.payload, dict):
                return result if result and not result.ok else FetchResult(ok=True, http_status=200, events=[])
            rows = [row for row in (result.payload.get("events") or []) if isinstance(row, dict)]
            if self._get is fetch_url:
                _CACHE[dataset] = rows
        else:
            rows = _CACHE[dataset]
        events = []
        for row in rows:
            event = _row_event(row, request.competition_id or "", request.sport_id or "")
            if event:
                events.append(event)
        return FetchResult(
            ok=True,
            http_status=200,
            events=events,
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            payload={"attribution": ATTRIBUTION},
        )
