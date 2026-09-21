"""Squiggle AFL API. Volunteer feed; commercial use allowed if we fetch server-side."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

GAMES_URL = f"https://api.squiggle.com.au/?q=games;year={datetime.now(timezone.utc).year}"
COMPETITION_ID = "australia-afl"


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
        "competition": COMPETITION_ID,
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
        result = self._get(GAMES_URL)
        if not result.ok:
            return result
        payload = result.payload if isinstance(result.payload, dict) else {}
        games: List[Dict[str, Any]] = payload.get("games") or []
        events = [_to_event(row) for row in games if row.get("hteam") and row.get("ateam")]
        if request.capability == "live_scores":
            events = [row for row in events if row["status"] == "live"]
        elif request.capability == "results":
            events = [row for row in events if row["status"] == "finished"]
        elif request.capability == "fixtures":
            events = [row for row in events if row["status"] == "scheduled"]
        return FetchResult(ok=True, http_status=result.http_status, payload=payload, events=events)
