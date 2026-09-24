"""Squiggle AFL API. Volunteer feed; commercial use allowed if we fetch server-side."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

COMPETITION_ID = "australia-afl"
TEAMS_URL = "https://api.squiggle.com.au/?q=teams"
SQUIGGLE_ASSET_BASE = "https://squiggle.com.au"
SQUIGGLE_HEADERS = {
    "User-Agent": "NinkoSports/2.5 (AFL collector; +https://ninkosports.com)",
    "Accept": "application/json, text/json, text/plain;q=0.9, */*;q=0.1",
}


def _games_url(year: int, *, amp: bool = True) -> str:
    if amp:
        return f"https://api.squiggle.com.au/?q=games&year={year}"
    return f"https://api.squiggle.com.au/?q=games;year={year}"


def parse_squiggle_payload(payload: Any, key: str = "games") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Accept the public Squiggle envelope, a raw list, or a JSON string."""
    meta: Dict[str, Any] = {"key": key}
    raw = payload
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
        meta["decoded_bytes"] = True
    if isinstance(raw, str):
        text = raw.strip()
        meta["shape"] = "string"
        meta["preview"] = text[:180]
        if text.lower().startswith("<!doctype") or text.lower().startswith("<html"):
            meta["content_type_guess"] = "text/html"
            return [], meta
        if text.startswith(")]}'"):
            text = text[4:].lstrip()
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            meta["parse"] = "json_error"
            return [], meta
    if isinstance(raw, list):
        rows = [row for row in raw if isinstance(row, dict)]
        meta["shape"] = "list"
        meta["count"] = len(rows)
        return rows, meta
    if isinstance(raw, dict):
        meta["shape"] = "dict"
        meta["keys"] = sorted(str(item) for item in raw.keys())[:16]
        rows = raw.get(key)
        if isinstance(rows, list):
            out = [row for row in rows if isinstance(row, dict)]
            meta["count"] = len(out)
            return out, meta
        meta["count"] = 0
        return [], meta
    meta["shape"] = type(payload).__name__
    return [], meta


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


def _team_assets(payload: Any) -> Dict[str, Dict[str, Any]]:
    rows, _meta = parse_squiggle_payload(payload, "teams")
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        team_id = str(row.get("id") or "").strip()
        if not team_id:
            continue
        logo = str(row.get("logo") or "").strip()
        if logo.startswith("/"):
            logo = f"{SQUIGGLE_ASSET_BASE}{logo}"
        out[team_id] = {
            "logo": logo,
            "name": str(row.get("name") or "").strip(),
            "abbrev": str(row.get("abbrev") or "").strip(),
        }
    return out


def _to_event(row: Dict[str, Any], team_assets: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    gid = str(row.get("id") or "")
    assets = team_assets or {}
    home_id = str(row.get("hteamid") or "")
    away_id = str(row.get("ateamid") or "")
    home_asset = assets.get(home_id) or {}
    away_asset = assets.get(away_id) or {}
    payload = {
        "id": f"squiggle:{gid}",
        "home": {
            "id": home_id,
            "name": row.get("hteam") or home_asset.get("name") or "",
            "logo": home_asset.get("logo") or "",
        },
        "away": {
            "id": away_id,
            "name": row.get("ateam") or away_asset.get("name") or "",
            "logo": away_asset.get("logo") or "",
        },
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


def _call(getter, url: str) -> FetchResult:
    try:
        return getter(url, headers=SQUIGGLE_HEADERS)
    except TypeError:
        return getter(url)


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
        team_assets: Dict[str, Dict[str, Any]] = {}
        teams_result = _call(self._get, TEAMS_URL)
        if teams_result and teams_result.ok:
            team_assets = _team_assets(teams_result.payload)
        last: Optional[FetchResult] = None
        diag: List[Dict[str, Any]] = []
        urls: List[str] = []
        for season in (year, year - 1):
            urls.extend((_games_url(season, amp=True), _games_url(season, amp=False)))
        urls.append("https://api.squiggle.com.au/?q=games")
        for url in urls:
            last = _call(self._get, url)
            body = last.payload if last is not None else None
            if body is None and last is not None and last.error:
                body = last.payload
            rows, meta = parse_squiggle_payload(body, "games")
            diag.append(
                {
                    "url": url,
                    "http_status": last.http_status if last else 0,
                    "ok": bool(last.ok) if last else False,
                    "error": last.error if last else None,
                    **meta,
                }
            )
            if rows:
                payload = body if isinstance(body, dict) else {"games": rows}
                games.extend(rows)
                break
        if last is not None and not last.ok and not games:
            last.empty_reason = json.dumps(diag[:4])[:800]
            return last
        events = [_to_event(row, team_assets) for row in games if row.get("hteam") and row.get("ateam")]
        if request.capability == "live_scores":
            events = [row for row in events if row["status"] == "live"]
        elif request.capability == "results":
            events = [row for row in events if row["status"] == "finished"]
        elif request.capability == "fixtures":
            events = [row for row in events if row["status"] == "scheduled"]
        reason = json.dumps(diag[:3])[:800] if not events else "squiggle games"
        return FetchResult(
            ok=True,
            http_status=(last.http_status if last else 200),
            payload=payload or {"games": games, "fetch_diag": diag[:4]},
            events=events,
            empty_reason=None if events else json.dumps(diag[:4])[:800],
            parse_reason=reason,
        )
