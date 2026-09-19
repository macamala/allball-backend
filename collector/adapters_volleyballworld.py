"""Volleyball World public competition family.

Follows Full Schedule / match pages on en.volleyballworld.com.
Does not request plusliga.pl.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import HREF_RE, NEXT_RE, _dedupe, _event, _text, parse_html, walk_json_events
from collector.http import fetch_text

BASE = "https://en.volleyballworld.com"

SLUGS: Dict[str, Dict[str, Any]] = {
    "plusliga": {"slug": "plusliga", "tokens": ("plusliga",)},
    "italy-superlega": {"slug": "superlega", "tokens": ("superlega",)},
    "fivb-competitions": {"slug": "volleyball-nations-league", "tokens": ("nations league", "vnl")},
}

SCHEDULE_ID = re.compile(r"/volleyball/competitions/([^/]+)/schedule/(\d+)/?", re.I)
TEAM_SCHED = re.compile(r"/volleyball/competitions/([^/]+)/teams/(\d+)/schedule/?", re.I)
VS_TITLE = re.compile(r"(.+?)\s+(?:vs\.?|v)\s+(.+?)(?:\s+[-|].*)?$", re.I)
SET_SCORE = re.compile(r"\b([0-3])\s*[-–:]\s*([0-3])\b")
ISO_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?")
LOC_DATE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
    re.I,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_PAGE_CACHE: Dict[str, FetchResult] = {}


def _iso_from_text(text: str) -> Optional[str]:
    iso = ISO_DATE.search(text or "")
    if iso:
        clock = iso.group(2) or "00:00"
        return f"{iso.group(1)}T{clock}:00Z" if len(clock) == 5 else f"{iso.group(1)}T00:00:00Z"
    loc = LOC_DATE.search(text or "")
    if loc:
        day, month, year = int(loc.group(1)), MONTHS[loc.group(2)[:3].lower()], int(loc.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
    return None


def parse_vw_match_page(html: str, url: str, tokens: tuple) -> List[Dict[str, Any]]:
    title = _text(re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S).group(1) if re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S) else "")
    og = re.search(r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', html or "", re.I)
    heading = _text(og.group(1) if og else title)
    vs = VS_TITLE.search(heading.replace("\u2013", "-"))
    if not vs:
        hyphen = re.search(
            r"(Sir Susa Scai Perugia|Cucine Lube Civitanova|Itas Trentino|Rana Verona|Gas Sales[^|]{0,20}|Allianz Milano)"
            r"\s*[-–]\s*"
            r"(Sir Susa Scai Perugia|Cucine Lube Civitanova|Itas Trentino|Rana Verona|Gas Sales[^|]{0,40}|Allianz Milano)",
            heading,
            re.I,
        )
        if hyphen:
            home, away = hyphen.group(1).strip(), hyphen.group(2).strip()
        else:
            return []
    else:
        home, away = vs.group(1).strip(" -|"), vs.group(2).strip(" -|")
    for junk in ("Volleyball World", "PlusLiga", "Schedule", "Match"):
        away = re.sub(rf"\s*[-|]\s*{re.escape(junk)}.*$", "", away, flags=re.I).strip()
    if home.lower() == away.lower() or len(home) < 4 or len(away) < 4:
        return []
    home_score = away_score = None
    status = "scheduled"
    score = SET_SCORE.search(_text(html or ""))
    if score:
        home_score, away_score = int(score.group(1)), int(score.group(2))
        from collector.live_state import guard_future_status

        start = _iso_from_text(html or "") or _iso_from_text(_text(html or ""))
        status = guard_future_status("finished", start, inferred=True, sport_id="volleyball")
    else:
        start = _iso_from_text(html or "") or _iso_from_text(_text(html or ""))
        status = "scheduled"
    event = _event(
        home=home,
        away=away,
        start=start,
        status=status,
        home_score=home_score,
        away_score=away_score,
        source_id=urlparse(url).path.rstrip("/"),
        extra={"competition": " ".join(tokens), "status_inferred": home_score is not None},
    )
    if event and event_is_valid(event, sport_id="volleyball"):
        return [event]
    return []


def schedule_urls(html: str, slug: str) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for href in HREF_RE.findall(html or ""):
        match = SCHEDULE_ID.search(href)
        if not match:
            continue
        if match.group(1).lower() != slug.lower():
            continue
        absolute = urljoin(BASE, href.split("#")[0])
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    for match in SCHEDULE_ID.finditer(html or ""):
        if match.group(1).lower() != slug.lower():
            continue
        absolute = f"{BASE}/volleyball/competitions/{slug}/schedule/{match.group(2)}/"
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def team_schedule_urls(html: str, slug: str) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for href in HREF_RE.findall(html or ""):
        match = TEAM_SCHED.search(href)
        if not match or match.group(1).lower() != slug.lower():
            continue
        absolute = urljoin(BASE, href.split("#")[0])
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def parse_vw_embedded(html: str, slug: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    match = NEXT_RE.search(html or "")
    payload = None
    if match:
        try:
            payload = json.loads(match.group(1))
        except (TypeError, ValueError):
            payload = None
    if payload is not None:
        events.extend(walk_json_events(payload))
    valid = []
    for event in events:
        home = ((event.get("home") or {}).get("name") or "")
        away = ((event.get("away") or {}).get("name") or "")
        if home.lower() == away.lower():
            continue
        if event_is_valid(event, sport_id="volleyball"):
            valid.append(event)
    return _dedupe(valid)


class VolleyballWorldAdapter:
    adapter_key = "volleyballworld"

    def __init__(self, source_id: str = "volleyballworld", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def _get(self, url: str, timeout: int = 20) -> FetchResult:
        cached = _PAGE_CACHE.get(url)
        if cached is not None:
            return cached
        try:
            result = self._get_text(url, timeout=timeout)
        except TypeError:
            result = self._get_text(url)
        _PAGE_CACHE[url] = result
        return result

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        spec = SLUGS.get(competition_id) or {}
        slug = spec.get("slug") or ""
        tokens = tuple(spec.get("tokens") or (slug,))
        events: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        if not slug:
            url = ((request.source_config or {}).get("url") or BASE).strip()
            last = self._get(url)
            if last.ok and isinstance(last.payload, str):
                events = [row for row in parse_html(last.payload, url) if event_is_valid(row, sport_id="volleyball")]
            return FetchResult(
                ok=True,
                http_status=(last.http_status if last is not None else 200) or 200,
                events=_dedupe(events),
                latency_ms=int((time.perf_counter() - started) * 1000),
                parse_status="ok" if events else "empty",
                empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
                parse_reason="volleyballworld generic HTML",
            )
        pages = [
            f"{BASE}/volleyball/competitions/{slug}/",
            f"{BASE}/volleyball/competitions/{slug}/schedule/",
            f"{BASE}/volleyball/competitions/{slug}/matches/",
            f"{BASE}/volleyball/competitions/{slug}/results/",
        ]
        if slug == "superlega":
            pages.insert(0, f"{BASE}/volleyball/competitions/superlega/schedule/27232/")
        configured = ((request.source_config or {}).get("url") or "").strip()
        if configured:
            pages.insert(0, configured)
        match_pages: List[str] = []
        seen: Set[str] = set()
        for url in pages:
            last = self._get(url)
            if not last.ok or not isinstance(last.payload, str):
                continue
            events.extend(parse_vw_embedded(last.payload, slug))
            for href in schedule_urls(last.payload, slug) + team_schedule_urls(last.payload, slug):
                if href not in seen:
                    seen.add(href)
                    match_pages.append(href)
        if not match_pages:
            sitemap = self._get(f"{BASE}/sitemap.xml")
            last = sitemap or last
            if sitemap.ok and isinstance(sitemap.payload, str):
                for href in re.findall(rf"https://en\.volleyballworld\.com/volleyball/competitions/{slug}/schedule/\d+/?", sitemap.payload):
                    if href not in seen:
                        seen.add(href)
                        match_pages.append(href)
        for url in match_pages[:50]:
            last = self._get(url)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_vw_match_page(last.payload, url, tokens))
            if len(events) >= 40:
                break
        events = _dedupe(events)
        latency = int((time.perf_counter() - started) * 1000)
        if last is not None and not last.ok and not events:
            last.latency_ms = latency
            return last
        return FetchResult(
            ok=True,
            http_status=(last.http_status if last is not None else 200) or 200,
            events=events,
            latency_ms=latency,
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason=f"volleyballworld {slug}",
        )
