"""openfootball/football.json adapter. CC0 public-domain club fixtures/results."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url
from collector.verified_coverage import OPENFOOTBALL_FILES

RAW_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master/"


def _status_for(match: Dict[str, Any]) -> str:
    score = match.get("score") or {}
    if isinstance(score, dict) and score.get("ft"):
        return "finished"
    return "scheduled"


def _score(match: Dict[str, Any]) -> Dict[str, Any]:
    score = match.get("score") or {}
    ft = score.get("ft") if isinstance(score, dict) else None
    if isinstance(ft, list) and len(ft) >= 2:
        return {"home": ft[0], "away": ft[1], "period": "ft"}
    return {"home": None, "away": None}


def _start(match: Dict[str, Any]) -> Optional[str]:
    date = match.get("date")
    time_value = match.get("time")
    if not date:
        return None
    if not time_value or str(time_value) in {"00:00", "00:00:00"}:
        return str(date)
    time_value = str(time_value)
    if len(time_value) == 5:
        time_value = f"{time_value}:00"
    return f"{date}T{time_value}Z"


def _to_event(match: Dict[str, Any], competition_id: str, sport_id: str) -> Dict[str, Any]:
    home = match.get("team1") or ""
    away = match.get("team2") or ""
    return {
        "id": f"openfootball:{competition_id}:{match.get('date')}:{home}:{away}",
        "home": {"name": home},
        "away": {"name": away},
        "status": _status_for(match),
        "score": _score(match),
        "start_time": _start(match),
        "round": match.get("round"),
        "competition": competition_id,
    }


class OpenFootballAdapter:
    adapter_key = "openfootball-json"
    source_id = "openfootball"

    def __init__(self, source_id: str = "openfootball", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        spec = next(
            (row for row in OPENFOOTBALL_FILES if row["competition_id"] == request.competition_id),
            None,
        )
        if spec is None:
            return FetchResult(ok=True, http_status=200, events=[])
        payload = None
        last = FetchResult(ok=False, http_status=0, error="no path")
        for rel in spec["paths"]:
            last = self._get(RAW_BASE + rel)
            if last.ok and isinstance(last.payload, dict):
                payload = last.payload
                break
            if last.http_status == 404:
                continue
            if last.restricted or not last.ok:
                return last
        if not isinstance(payload, dict):
            return last
        matches = payload.get("matches") or []
        events: List[Dict[str, Any]] = []
        today = datetime.utcnow().date().isoformat()
        for match in matches:
            event = _to_event(match, spec["competition_id"], spec["sport_id"])
            status = event["status"]
            if request.capability == "snapshot":
                events.append(event)
                continue
            if request.capability == "results" and status != "finished":
                continue
            if request.capability == "fixtures" and status == "finished":
                continue
            if request.capability == "live_scores":
                continue
            if request.capability == "results" and (event.get("start_time") or "")[:10] > today:
                continue
            events.append(event)
        return FetchResult(ok=True, http_status=200, payload=payload, events=events)
