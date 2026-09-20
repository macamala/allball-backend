"""RTÉ Rugby public results/fixtures family.

Parses competition-specific match-item rows on rte.ie/sport/results/rugby/.
Does not use generic rugby events; tournament text must match the mapping.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import HREF_RE, _dedupe, _event, _text
from collector.http import fetch_text

BASE = "https://www.rte.ie"
CATALOG = "https://www.rte.ie/sport/results/rugby/"

COMPETITION_SPECS: Dict[str, Dict[str, Any]] = {
    "france-top-14": {
        "path": "/sport/results/rugby/top-14/43093/",
        "tokens": ("top 14",),
        "slug": "top-14",
    },
    "france-pro-d2": {
        "path": "",
        "tokens": ("pro d2", "prod2"),
        "slug": "pro-d2",
    },
    "premiership-rugby": {
        "path": "",
        "tokens": ("premiership",),
        "slug": "premiership",
    },
    "super-rugby": {
        "path": "",
        "tokens": ("super rugby",),
        "slug": "super-rugby",
    },
    "nz-npc": {
        "path": "",
        "tokens": ("npc", "bunnings"),
        "slug": "npc",
    },
}

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

DATE_HEAD = re.compile(
    r"<h2[^>]*class=[\"']date[\"'][^>]*>(.*?)</h2>",
    re.I | re.S,
)
MATCH_ITEM = re.compile(
    r'<a class="match-item[^"]*"([^>]*)>(.*?)</a>',
    re.I | re.S,
)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*["\']([^"\']*)["\']')
TOURNAMENT_RE = re.compile(
    r'class=["\'][^"\']*match-tournament[^"\']*["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
HOME_RE = re.compile(
    r'class=["\'][^"\']*team-name team-home\s+hide-for-small-only["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
AWAY_RE = re.compile(
    r'class=["\'][^"\']*team-name team-away hide-for-small-only["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
INFO_RE = re.compile(r'class=["\']match-main-info["\'][^>]*>(.*?)</p>', re.I | re.S)
FOOTER_RE = re.compile(r'class=["\'][^"\']*match-footer[^"\']*["\'][^>]*>\s*<p>(.*?)</p>', re.I | re.S)
STATUS_RE = re.compile(r"status-(finished|notstarted|live)", re.I)
CLOCK_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
SCORE_RE = re.compile(r"(\d{1,3})\s*[-–]\s*(\d{1,3})")
HEAD_DATE_RE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
    re.I,
)
CATALOG_RE = re.compile(r"/sport/results/rugby/([a-z0-9-]+)/(\d+)/", re.I)

_PAGE_CACHE: Dict[str, FetchResult] = {}


def _iso(day: int, month: int, year: int, clock: str = "") -> str:
    stamp = f"{year:04d}-{month:02d}-{day:02d}"
    if clock:
        return f"{stamp}T{clock}:00Z"
    return f"{stamp}T00:00:00Z"


def _parse_heading_date(text: str) -> Optional[Tuple[int, int, int]]:
    match = HEAD_DATE_RE.search(_text(text) or "")
    if not match:
        return None
    return int(match.group(1)), MONTHS[match.group(2)[:3].lower()], int(match.group(3))


def catalog_competitions(html: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for slug, cid in CATALOG_RE.findall(html or ""):
        found[slug.lower()] = cid
    return found


def parse_rte_rugby(html: str, *, tokens: Tuple[str, ...]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    required = tuple(token.lower() for token in tokens if token)
    current_date: Optional[Tuple[int, int, int]] = None
    pos = 0
    blob = html or ""
    while pos < len(blob):
        head = DATE_HEAD.search(blob, pos)
        item = MATCH_ITEM.search(blob, pos)
        if head and (item is None or head.start() < item.start()):
            parsed = _parse_heading_date(head.group(1))
            if parsed:
                current_date = parsed
            pos = head.end()
            continue
        if item is None:
            break
        attrs = dict(ATTR_RE.findall(item.group(1) or ""))
        body = item.group(2) or ""
        tournament = _text(TOURNAMENT_RE.search(body).group(1) if TOURNAMENT_RE.search(body) else "")
        lowered = tournament.lower()
        if required and not any(token in lowered for token in required):
            pos = item.end()
            continue
        home = _text(HOME_RE.search(body).group(1) if HOME_RE.search(body) else "")
        away = _text(AWAY_RE.search(body).group(1) if AWAY_RE.search(body) else "")
        info = _text(INFO_RE.search(body).group(1) if INFO_RE.search(body) else "")
        venue = _text(FOOTER_RE.search(body).group(1) if FOOTER_RE.search(body) else "")
        class_blob = f"{attrs.get('class') or ''} {item.group(1)}"
        status_m = STATUS_RE.search(class_blob) or STATUS_RE.search(body)
        status = "scheduled"
        if status_m:
            kind = status_m.group(1).lower()
            status = {"finished": "finished", "live": "live"}.get(kind, "scheduled")
        home_score = away_score = None
        score = SCORE_RE.search(info or "")
        clock = CLOCK_RE.search(info or "")
        if score and ":" not in (info or "").split("-")[0]:
            home_score, away_score = int(score.group(1)), int(score.group(2))
            status = "finished"
        start = None
        if current_date:
            start = _iso(*current_date, clock.group(1) if clock and home_score is None else "")
        event = _event(
            home=home,
            away=away,
            start=start,
            status=status,
            home_score=home_score,
            away_score=away_score,
            venue=venue or None,
            source_id=str(attrs.get("data-matchID") or attrs.get("data-matchid") or f"{home}-{away}-{start}"),
            extra={"competition": tournament, "stage": status},
        )
        if event and event_is_valid(event, sport_id="rugby"):
            events.append(event)
        pos = item.end()
    return _dedupe(events)


class RteRugbyAdapter:
    adapter_key = "rte-rugby"

    def __init__(self, source_id: str = "rte-rugby", text_getter=None):
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

    def _resolve_path(self, competition_id: str, config: Dict[str, Any]) -> Tuple[str, Tuple[str, ...]]:
        spec = COMPETITION_SPECS.get(competition_id) or {}
        tokens = tuple(spec.get("tokens") or ())
        path = (config.get("path") or spec.get("path") or "").strip()
        configured = (config.get("url") or "").strip()
        if configured and "rte.ie" in configured:
            parsed = urlparse(configured).path
            if "/sport/results/rugby/" in parsed:
                path = parsed if parsed.endswith("/") else parsed.rsplit("/", 1)[0] + "/"
                if not path.endswith("/"):
                    path += "/"
        if path:
            return path, tokens
        catalog = self._get(CATALOG)
        if catalog.ok and isinstance(catalog.payload, str):
            found = catalog_competitions(catalog.payload)
            slug = spec.get("slug") or ""
            cid = found.get(slug)
            if cid and slug:
                return f"/sport/results/rugby/{slug}/{cid}/", tokens
        return "", tokens

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        config = request.source_config or {}
        path, tokens = self._resolve_path(competition_id, config)
        events: List[Dict[str, Any]] = []
        last = None
        if not path:
            return FetchResult(
                ok=True,
                http_status=200,
                events=[],
                latency_ms=int((time.perf_counter() - started) * 1000),
                parse_status="empty",
                empty_reason="SOURCE_HEALTHY_NO_EVENTS",
                parse_reason="rte rugby catalog has no competition path",
            )
        pages = []
        for kind in ("results", "fixtures"):
            base = urljoin(BASE, path + kind + "/")
            pages.append(base)
            for page in range(2, 7):
                pages.append(f"{base}?page={page}")
        tried = set()
        for url in pages:
            if url in tried:
                continue
            tried.add(url)
            last = self._get(url)
            if not last.ok or not isinstance(last.payload, str):
                continue
            events.extend(parse_rte_rugby(last.payload, tokens=tokens))
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
            parse_reason=f"rte rugby {path}",
        )
