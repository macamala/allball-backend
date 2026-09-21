"""Squiggle AFL API. Volunteer feed; commercial use allowed if we fetch server-side."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

COMPETITION_ID = "australia-afl"


def _games_url(year: int) -> str:
    return f"https://api.squiggle.com.au/?q=games&year={year}"


def _status(row: Dict[str, Any]) -> str:
    complete = row.get("complete")
    try:
        value = float(complete)
    except (TypeError, ValueError):
        value = 0
    if value >= 100:
        return "finished"
    if value > 0:
        return "live"
    return "scheduled"


def _start(row: Dict[str, Any]) -> str | None:
    date = row.get("date") or row.get("localtime")
    if not date:
        return None
    text = str(date).replace(" ", "T")
    if len(text) == 16:
        text = f"{text}:00"
    if not text.endswith("Z") and "+" not in text:
        text = f"{text}Z"
    return text


def _to_event(row: Dict[str, Any]) -> Dict[str, Any]:
    gid = str(row.get("id") or "")
    payload = {
        "id": f"squiggle:{gid}",
        "home": {"id": str(row.get("hteamid") or ""), "name": row.get("hteam") or ""},
        "away": {"id": str(row.get("ateamid") or ""), "name": row.get("ateam") or ""},
        "status": _status(row),
        "score": {"home": row.get("hscore"), "away": row.get("ascore")},
        "start_time": _start(row),
        "venue": row.get("venue"),
        "round": row.get("roundname") or row.get("round"),
        "sport": "australian-rules",
        "competition": COMPETITION_ID,
        "competition_key": COMPETITION_ID,
        "source_family": "squiggle-afl",
        "source_event_id": gid,
        "source_event_ids": {"squiggle-afl": gid},
        "extra": {
            "source_family": "squiggle-afl",
            "source_event_id": gid,
            "source_event_ids": {"squiggle-afl": gid},
        },
    }
    if row.get("hgoals") is not None or row.get("agoals") is not None:
        payload["periods"] = [
            {"label": "G", "home": row.get("hgoals"), "away": row.get("agoals")},
            {"label": "B", "home": row.get("hbehinds"), "away": row.get("abehinds")},
        ]
        payload["extra"]["sport_detail"] = {
            "goals": {"home": row.get("hgoals"), "away": row.get("agoals")},
            "behinds": {"home": row.get("hbehinds"), "away": row.get("abehinds")},
        }
    return payload


class SquiggleAflAdapter:
    adapter_key = "squiggle-afl"
    source_id = "squiggle"

    def __init__(self, source_id: str = "squiggle", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        year = datetime.now(timezone.utc).year
        payload: Dict[str, Any] = {}
        games: List[Dict[str, Any]] = []
        last = None
        for season in (year, year - 1):
            last = self._get(_games_url(season))
            if not last.ok or not isinstance(last.payload, dict) or not (last.payload.get("games") or []):
                last = self._get(f"https://api.squiggle.com.au/?q=games;year={season}")
            if not last.ok:
                continue
            payload = last.payload if isinstance(last.payload, dict) else {}
            batch = payload.get("games") or []
            games.extend(batch)
        if last is not None and not last.ok and not games:
            return last
        events = [_to_event(row) for row in games if row.get("hteam") and row.get("ateam")]
        if request.capability == "live_scores":
            events = [row for row in events if row["status"] == "live"]
        elif request.capability == "results":
            events = [row for row in events if row["status"] == "finished"]
        elif request.capability == "fixtures":
            events = [row for row in events if row["status"] == "scheduled"]
        return FetchResult(ok=True, http_status=(last.http_status if last else 200), payload=payload, events=events)
