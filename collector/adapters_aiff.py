"""AIFF public competition pages (the-aiff.com).

The HTML page declares tournament_type and loads same-origin
/api/competition/fixtures/{type}. That JSON is the Fixtures & Results
block on the public competition page, not a private authenticated API.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import _dedupe, _event
from collector.http import fetch_text, fetch_url

COMPETITION_PAGES = {
    "india-super-league": {
        "url": "https://www.the-aiff.com/competitions/isl",
        "slug": "isl",
        "name_tokens": ("indian super league", "isl"),
    },
}

TYPE_RE = re.compile(r"var\s+tournament_type\s*=\s*(\d+)", re.I)
BASE = "https://www.the-aiff.com"


def parse_aiff_fixtures(payload: Any, *, competition_id: str = "", slug: str = "") -> List[Dict[str, Any]]:
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("fixtures") or payload.get("results") or []
    elif isinstance(payload, list):
        rows = payload
    events: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tournament = str(row.get("tournament_name") or row.get("slug") or "").lower()
        row_slug = str(row.get("slug") or "").lower()
        if slug and row_slug and row_slug != slug and slug not in tournament:
            continue
        if competition_id == "india-super-league":
            if row_slug not in {"", "isl"} and "indian super league" not in tournament:
                continue
        home = str(row.get("team1_name") or "").strip()
        away = str(row.get("team2_name") or "").strip()
        if not home or not away:
            continue
        start = row.get("match_date") or row.get("timestamp")
        if isinstance(start, (int, float)):
            from collector.html_parse import datetime_from_unix

            start = datetime_from_unix(start)
        elif start and row.get("time"):
            start = f"{start}T{row.get('time')}:00Z"
        home_score = row.get("team1_score")
        away_score = row.get("team2_score")
        status = "finished" if row.get("ft") or row.get("over") else "scheduled"
        if row.get("ms") and not row.get("ft"):
            status = "live"
        event = _event(
            home=home,
            away=away,
            start=start,
            status=status,
            home_score=home_score,
            away_score=away_score,
            venue=row.get("venue"),
            source_id=str(row.get("id") or row.get("match_id") or f"{home}-{away}-{start}"),
            extra={"competition": row.get("tournament_name") or competition_id},
        )
        if event and event_is_valid(event, sport_id="football", competition_id=competition_id):
            events.append(event)
    return _dedupe(events)[:80]


class AiffWebAdapter:
    adapter_key = "aiff-web"

    def __init__(self, source_id: str = "aiff-web", getter=None, text_getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        spec = COMPETITION_PAGES.get(competition_id) or {}
        url = ((request.source_config or {}).get("url") or spec.get("url") or "").strip()
        if not url:
            return FetchResult(
                ok=False,
                http_status=0,
                error="no AIFF competition page configured",
                classification="CONFIG_MISSING",
                config_missing=True,
                parse_status="skipped",
            )
        page = self._get_text(url)
        latency = int((time.perf_counter() - started) * 1000)
        if not page.ok:
            page.latency_ms = latency
            return page
        html = page.payload if isinstance(page.payload, str) else ""
        match = TYPE_RE.search(html)
        tournament_type = match.group(1) if match else "2"
        fixtures_url = f"{BASE}/api/competition/fixtures/{tournament_type}"
        payload_result = self._get(fixtures_url)
        payload: Any = payload_result.payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                payload = {}
        events = parse_aiff_fixtures(
            payload,
            competition_id=competition_id,
            slug=str(spec.get("slug") or ""),
        )
        latency = int((time.perf_counter() - started) * 1000)
        return FetchResult(
            ok=True,
            http_status=payload_result.http_status or page.http_status or 200,
            events=events,
            latency_ms=latency,
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
        )
