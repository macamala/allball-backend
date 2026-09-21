"""Cricsheet delayed match archive. ODC-By 1.0, commercial use with attribution."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_bytes
from collector.util import slugify

RECENT_ZIP = "https://cricsheet.org/downloads/recently_added_7_json.zip"


def _runs(innings: List[Dict[str, Any]], team: str) -> Optional[int]:
    total = 0
    found = False
    for inn in innings:
        if inn.get("team") != team:
            continue
        found = True
        for delivery in inn.get("overs") or []:
            for ball in delivery.get("deliveries") or []:
                runs = (ball.get("runs") or {}).get("total") or 0
                total += int(runs)
    return total if found else None


def _innings_cards(doc: Dict[str, Any], teams: List[str]) -> List[Dict[str, Any]]:
    cards = []
    for inn in doc.get("innings") or []:
        if not isinstance(inn, dict):
            continue
        team = inn.get("team")
        runs = wickets = 0
        overs = inn.get("overs") or []
        over_count = 0
        for over in overs:
            over_count += 1
            for ball in over.get("deliveries") or []:
                runs += int(((ball.get("runs") or {}).get("total") or 0))
                if ball.get("wickets"):
                    wickets += len(ball.get("wickets") or [])
        target = (inn.get("target") or {}).get("runs") if isinstance(inn.get("target"), dict) else None
        cards.append(
            {
                "label": team,
                "home": runs if teams and team == teams[0] else None,
                "away": runs if teams and len(teams) > 1 and team == teams[1] else None,
                "runs": runs,
                "wickets": wickets,
                "overs": over_count,
                "target": target,
            }
        )
    return cards


def _event(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    info = doc.get("info") or {}
    teams = info.get("teams") or []
    if len(teams) < 2:
        return None
    home, away = teams[0], teams[1]
    event = info.get("event") or {}
    competition = event.get("name") or info.get("match_type") or "Cricket"
    outcome = info.get("outcome") or {}
    finished = bool(outcome)
    innings = doc.get("innings") or []
    dates = info.get("dates") or []
    start = f"{dates[0]}T00:00:00Z" if dates else None
    cards = _innings_cards(doc, teams)
    winner = outcome.get("winner")
    result = outcome.get("result") or (f"{winner} won" if winner else None)
    if result == "draw":
        result = "draw"
    by_blob = outcome.get("by") if isinstance(outcome.get("by"), dict) else {}
    sport_detail = {
        "match_type": info.get("match_type"),
        "gender": info.get("gender"),
        "series": (event.get("name") if isinstance(event, dict) else None),
        "result": result,
        "winner": winner,
        "win_by": by_blob or None,
        "historical": True,
        "live": False,
    }
    sid = str(info.get("cricsheet_id") or info.get("match_id") or f"{dates[0] if dates else ''}:{home}:{away}")
    return {
        "id": f"cricsheet:{info.get('match_type')}:{dates[0] if dates else ''}:{home}:{away}",
        "home": {"name": home},
        "away": {"name": away},
        "status": "finished" if finished else "scheduled",
        "score": {"home": _runs(innings, home), "away": _runs(innings, away)},
        "start_time": start,
        "venue": info.get("venue"),
        "sport": "cricket",
        "competition": competition,
        "competition_key": f"cricket-{slugify(competition)}",
        "event_family": "team_match",
        "gender": info.get("gender"),
        "match_type": info.get("match_type"),
        "periods": cards or None,
        "innings": cards or None,
        "source_family": "cricsheet",
        "source_event_id": sid,
        "source_event_ids": {"cricsheet": sid},
        "sport_detail": {k: v for k, v in sport_detail.items() if v not in (None, "", {})},
        "extra": {
            "source_family": "cricsheet",
            "source_event_id": sid,
            "source_event_ids": {"cricsheet": sid},
            "historical": True,
            "sport_detail": {k: v for k, v in sport_detail.items() if v not in (None, "", {})},
            "periods": cards or None,
            "innings": cards or None,
        },
    }


def _from_zip(raw: bytes) -> List[Dict[str, Any]]:
    events = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            if not name.endswith(".json") or name.endswith("README.json"):
                continue
            with archive.open(name) as handle:
                try:
                    doc = json.loads(handle.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
            event = _event(doc)
            if event:
                events.append(event)
    return events


class CricsheetAdapter:
    adapter_key = "cricsheet-json"
    source_id = "cricsheet"

    def __init__(self, source_id: str = "cricsheet", getter=fetch_bytes):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        if request.capability not in {"fixtures", "results", "live_scores", "snapshot"}:
            return FetchResult(ok=True, http_status=200, events=[])
        result = self._get(RECENT_ZIP)
        if not result.ok:
            return result
        payload = result.payload
        if isinstance(payload, (bytes, bytearray)):
            events = _from_zip(bytes(payload))
        elif isinstance(payload, list):
            events = []
            for row in payload:
                event = _event(row) if "info" in row else row
                if event:
                    events.append(event)
        else:
            return FetchResult(ok=False, http_status=result.http_status, error="unexpected cricsheet payload")
        if request.competition_id:
            for event in events:
                event["competition_key"] = request.competition_id
        if request.capability == "live_scores":
            events = []
        elif request.capability == "results":
            events = [row for row in events if row.get("status") == "finished"]
        elif request.capability == "fixtures":
            events = [row for row in events if row.get("status") != "finished"]
        if request.competition_id == "t20-internationals":
            events = [
                row
                for row in events
                if "t20" in str(row.get("match_type") or "").lower()
                or "t20" in str(row.get("competition") or "").lower()
            ]
            finished = [row for row in events if row.get("status") == "finished"]
            events = finished or events
        return FetchResult(
            ok=True,
            http_status=result.http_status,
            payload={"matches": len(events)},
            events=events,
            empty_reason="SOURCE_HEALTHY_NO_EVENTS" if not events else None,
        )
