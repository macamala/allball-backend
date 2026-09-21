"""Shared DataProject Web Competition / LiveScore family.

One adapter for SuperLega, PlusLiga, CEV Competition Area, and any other
host that serves the same WCM HTML/JSON. Competition identity is the page URL
plus optional competition-area ID — not a per-league scraper.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from collector.adapters import FetchRequest, FetchResult
from collector.adapters_cev_competition_area import parse_cev_competition_area
from collector.event_quality import TEAM_MATCH, event_is_valid
from collector.html_parse import _dedupe, _event, _text, parse_html, parse_jsonld
from collector.http import fetch_text
from collector.live_state import guard_future_status

HOST_URLS: Dict[str, str] = {
    "italy-superlega": "https://www.legavolley.it/calendario",
    "plusliga": "https://plusliga.pl/games",
    "cev-eurovolley-men": "https://www-old.cev.eu/Competition-Area/CompetitionView.aspx?ID=1572",
}

SET_SCORE = re.compile(r"^\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*$")
MID_RE = re.compile(r"(?:mID|matchId|gameId|id_game)=(\d+)", re.I)
LIVE_RE = re.compile(r"\b(live|in corso|trwa|in progress|playing)\b", re.I)
DATE_RE = re.compile(
    r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})(?:\s+(\d{1,2}:\d{2}))?"
)

_PAGE: Dict[str, FetchResult] = {}


def _get(getter, url: str, timeout: int = 25) -> FetchResult:
    cached = _PAGE.get(url)
    if cached is not None:
        return cached
    try:
        result = getter(url, timeout=timeout)
    except TypeError:
        result = getter(url)
    _PAGE[url] = result
    return result


def _status(home_score: Optional[int], away_score: Optional[int], blob: str, start: Optional[str]) -> str:
    live = bool(LIVE_RE.search(blob or ""))
    if live:
        return guard_future_status("live", start, inferred=False, sport_id="volleyball")
    if home_score is not None and away_score is not None:
        return guard_future_status("finished", start, inferred=True, sport_id="volleyball")
    return "scheduled"


def _ok(event: Optional[Dict[str, Any]], competition_id: str) -> Optional[Dict[str, Any]]:
    if not event:
        return None
    event["source_family"] = "dataproject-web"
    extra = event.get("extra")
    if not isinstance(extra, dict):
        extra = {}
        event["extra"] = extra
    extra["source_family"] = "dataproject-web"
    extra.setdefault("event_type", TEAM_MATCH)
    sid = extra.get("source_event_id") or event.get("source_event_id") or event.get("id")
    token = str(sid or "").split(":")[-1] if sid else ""
    if token:
        event["source_event_id"] = token
        event["source_event_ids"] = {"dataproject-web": token}
        extra["source_event_id"] = token
        extra["source_event_ids"] = {"dataproject-web": token}
    if event_is_valid(event, sport_id="volleyball", competition_id=competition_id):
        return event
    return None


def parse_dataproject_html(html: str, *, competition_id: str = "", source_url: str = "") -> List[Dict[str, Any]]:
    """Family parser: CEV span layout, then JSON-LD, then generic tables."""
    events: List[Dict[str, Any]] = []
    if "div_match" in (html or "") or "LB_SetCasa" in (html or "") or "Competition-Area" in (html or ""):
        events.extend(parse_cev_competition_area(html, competition_id=competition_id))
    if not events:
        for row in parse_jsonld(html):
            ev = _ok(row, competition_id)
            if ev:
                events.append(ev)
    if not events:
        for row in parse_html(html, source_url or ""):
            ev = _ok(row, competition_id)
            if ev:
                events.append(ev)
    scored_rows = _parse_score_rows(html, competition_id=competition_id)
    if scored_rows:
        events = scored_rows + [row for row in events if row not in scored_rows]
    out = []
    for event in _dedupe(events):
        if "source_family" not in event:
            event["source_family"] = "dataproject-web"
        extra = event.get("extra")
        if isinstance(extra, dict):
            extra.setdefault("source_family", "dataproject-web")
            extra.setdefault("event_type", TEAM_MATCH)
        home_score = (event.get("score") or {}).get("home")
        away_score = (event.get("score") or {}).get("away")
        blob = f"{event.get('home')} {event.get('away')} {event.get('status')}"
        event["status"] = _status(home_score, away_score, blob, event.get("start_time"))
        if home_score is None:
            event.setdefault("score", {})
            if isinstance(event["score"], dict) and "home" not in event["score"]:
                event["score"]["home"] = None
                event["score"]["away"] = None
        ok = _ok(event, competition_id)
        if ok:
            out.append(ok)
    return _dedupe(out)


def _parse_score_rows(html: str, *, competition_id: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = _text(html or "")
    row_re = re.compile(
        r"([A-ZÁČĎÉĚÍĹĽŇÓÔŔŘŠŤÚŮÝŽ][\w .'\-]{2,40})\s+(?:vs\.?|v|-|–)\s+"
        r"([A-ZÁČĎÉĚÍĹĽŇÓÔŔŘŠŤÚŮÝŽ][\w .'\-]{2,40})\s+(\d{1,2}\s*[-–:]\s*\d{1,2})",
        re.U,
    )
    for match in row_re.finditer(text):
        home, away, score = match.group(1).strip(), match.group(2).strip(), match.group(3)
        parsed = SET_SCORE.match(score)
        if not parsed:
            continue
        home_score, away_score = int(parsed.group(1)), int(parsed.group(2))
        date_m = DATE_RE.search(text[max(0, match.start() - 80) : match.end() + 80])
        start = None
        if date_m:
            start = f"{date_m.group(3)}-{int(date_m.group(2)):02d}-{int(date_m.group(1)):02d}"
            if date_m.group(4):
                start += f"T{date_m.group(4)}:00"
        mid = MID_RE.search(html[max(0, match.start()) : match.end() + 200])
        event = _event(
            home=home,
            away=away,
            start=start,
            status=_status(home_score, away_score, match.group(0), start),
            home_score=home_score,
            away_score=away_score,
            source_id=mid.group(1) if mid else f"{home}-{away}-{start}",
            extra={"competition": competition_id, "event_type": TEAM_MATCH, "source_family": "dataproject-web"},
        )
        if event:
            events.append(event)
    return events


class DataProjectWebAdapter:
    adapter_key = "dataproject-web"

    def __init__(self, source_id: str = "dataproject-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        cfg = request.source_config or {}
        url = (cfg.get("url") or HOST_URLS.get(competition_id) or "").strip()
        extra_id = str(cfg.get("competition_area_id") or "").strip()
        if extra_id and "CompetitionView.aspx" not in url:
            url = urljoin(
                "https://www-old.cev.eu/Competition-Area/",
                f"CompetitionView.aspx?ID={extra_id}",
            )
        if not url:
            return FetchResult(
                ok=False,
                http_status=0,
                config_missing=True,
                parse_status="empty",
                empty_reason="CONFIG_MISSING",
                error="dataproject-web host URL missing",
            )
        last = _get(self._get_text, url)
        events: List[Dict[str, Any]] = []
        if last.ok and isinstance(last.payload, str):
            events = parse_dataproject_html(
                last.payload, competition_id=competition_id, source_url=url
            )
        latency = int((time.perf_counter() - started) * 1000)
        if not last.ok and not events:
            last.latency_ms = latency
            last.request_count = 1
            return last
        return FetchResult(
            ok=True,
            http_status=last.http_status or 200,
            events=events,
            latency_ms=latency,
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="dataproject-web WCM/LiveScore family",
            request_count=1,
            restricted=bool(getattr(last, "restricted", False)),
        )
