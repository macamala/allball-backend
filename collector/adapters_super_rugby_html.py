"""Super Rugby public Match Centre HTML family.

Parses competition-specific match-pack HTML under super.rugby/superrugby/.
Does not call Opta/widget/private APIs.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import HREF_RE, _dedupe, _event, _text
from collector.http import fetch_text

BASE = "https://super.rugby"
MATCH_CENTRE = "https://super.rugby/superrugby/match-centre/"
PACK_INDEX = "https://super.rugby/superrugby/match-centre/match-packs/"
SEED_ROUNDS = [
    "https://super.rugby/superrugby/match-centre/match-packs/2026-srp-rd1/",
    "https://super.rugby/superrugby/match-centre/?competition=205&season=2026",
]

NAMED = re.compile(
    r"(Highlanders|Crusaders|NSW Waratahs|Waratahs|Queensland Reds|Fijian Drua|"
    r"Moana Pasifika|Blues|Chiefs|Western Force|ACT Brumbies|Brumbies|Hurricanes)"
    r"\s*(\d{1,3})\s*[-–]\s*(\d{1,3})\s*"
    r"(Highlanders|Crusaders|NSW Waratahs|Waratahs|Queensland Reds|Fijian Drua|"
    r"Moana Pasifika|Blues|Chiefs|Western Force|ACT Brumbies|Brumbies|Hurricanes)",
    re.I,
)
LISTING_VS = re.compile(
    r"(Highlanders|Crusaders|NSW Waratahs|Waratahs|Queensland Reds|Fijian Drua|"
    r"Moana Pasifika|Blues|Chiefs|Western Force|ACT Brumbies|Brumbies|Hurricanes)"
    r"\s+v(?:s\.?)?\s+"
    r"(Highlanders|Crusaders|NSW Waratahs|Waratahs|Queensland Reds|Fijian Drua|"
    r"Moana Pasifika|Blues|Chiefs|Western Force|ACT Brumbies|Brumbies|Hurricanes)",
    re.I,
)
DATE_DMY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
DATE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
DATE_TEXT = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b",
    re.I,
)
PACK_HREF = re.compile(r"/superrugby/match-centre/match-packs/[^\"'#?]+", re.I)
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


def _normalize_team(name: str) -> str:
    text = _text(name)
    lowered = text.lower()
    aliases = {
        "reds": "Queensland Reds",
        "queensland reds": "Queensland Reds",
        "waratahs": "Waratahs",
        "nsw waratahs": "Waratahs",
        "brumbies": "ACT Brumbies",
        "act brumbies": "ACT Brumbies",
        "force": "Western Force",
        "western force": "Western Force",
        "drua": "Fijian Drua",
        "fijian drua": "Fijian Drua",
    }
    if lowered in aliases:
        return aliases[lowered]
    return text


def _payload_text(html: str) -> str:
    text = html or ""
    if text.lstrip().startswith("%PDF") or "\x00" in text[:2000]:
        return text.replace("\x00", "")
    return text


def _date_from_text(html: str) -> Optional[str]:
    best = None
    for dmy in DATE_DMY.finditer(html or ""):
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        stamp = f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
        if year == 2026:
            return stamp
        best = best or stamp
    for iso in DATE_ISO.finditer(html or ""):
        year = int(iso.group(1))
        stamp = f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}T00:00:00Z"
        if year == 2026:
            return stamp
        best = best or stamp
    for named in DATE_TEXT.finditer(html or ""):
        day, month, year = int(named.group(1)), MONTHS[named.group(2)[:3].lower()], int(named.group(3))
        stamp = f"{year:04d}-{month:02d}-{day:02d}T00:00:00Z"
        if year == 2026:
            return stamp
        best = best or stamp
    return best


def parse_super_rugby_pack(html: str, url: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = _payload_text(html or "")
    date = _date_from_text(html or "") or _date_from_text(text)
    for match in NAMED.finditer(text):
        home = _normalize_team(match.group(1))
        away = _normalize_team(match.group(4))
        if home.lower() == away.lower():
            continue
        event = _event(
            home=home,
            away=away,
            start=date,
            status="finished",
            home_score=int(match.group(2)),
            away_score=int(match.group(3)),
            source_id=urlparse(url).path.rstrip("/") or f"{home}-{away}-{date}",
            extra={"competition": "Super Rugby"},
        )
        if event and event_is_valid(event, sport_id="rugby", competition_id="super-rugby"):
            start = str(event.get("start_time") or "")
            if "2026" in (url or "") and start and not start.startswith("2026"):
                continue
            events.append(event)
            break
    if not events:
        vs = LISTING_VS.search(_text(html or "") or text)
        if vs:
            home = _normalize_team(vs.group(1))
            away = _normalize_team(vs.group(2))
            event = _event(
                home=home,
                away=away,
                start=date,
                status="scheduled" if date else "scheduled",
                source_id=urlparse(url).path.rstrip("/") or f"{home}-{away}-{date}",
                extra={"competition": "Super Rugby"},
            )
            if event and event_is_valid(event, sport_id="rugby", competition_id="super-rugby"):
                start = str(event.get("start_time") or "")
                if not start.startswith("2026"):
                    event = None
                else:
                    events.append(event)
    return _dedupe(events)


def pack_urls(html: str, base: str) -> List[str]:
    found: List[str] = []
    seen: Set[str] = set()
    for href in list(HREF_RE.findall(html or "")) + PACK_HREF.findall(html or ""):
        if "match-packs" not in href.lower():
            continue
        if any(skip in href.lower() for skip in ("opta", "widget", "api.", "/cdn-cgi/")):
            continue
        absolute = urljoin(base, href.split("#")[0])
        if "super.rugby" not in urlparse(absolute).netloc.lower():
            continue
        path = urlparse(absolute).path.rstrip("/")
        if path in seen:
            continue
        seen.add(path)
        found.append(absolute)
    return found


class SuperRugbyHtmlAdapter:
    adapter_key = "super-rugby-html"

    def __init__(self, source_id: str = "super-rugby-html", text_getter=None):
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
        events: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        seeds = [
            (request.source_config or {}).get("url") or MATCH_CENTRE,
            PACK_INDEX,
            *SEED_ROUNDS,
        ]
        for n in range(1, 20):
            seeds.append(f"https://super.rugby/superrugby/match-centre/match-packs/2026-srp-rd{n}/")
        queue: List[str] = []
        seen: Set[str] = set()
        for seed in seeds:
            if not seed or seed in seen:
                continue
            seen.add(seed)
            if any(skip in seed.lower() for skip in ("opta", "widget", "/api/")):
                continue
            last = self._get(seed)
            if not last.ok or not isinstance(last.payload, str):
                continue
            events.extend(parse_super_rugby_pack(last.payload, seed))
            for pack in pack_urls(last.payload, seed):
                if pack not in seen:
                    queue.append(pack)
        for url in queue[:15]:
            if url in seen:
                continue
            seen.add(url)
            last = self._get(url)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_super_rugby_pack(last.payload, url))
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
            parse_reason="super.rugby match-centre HTML match-packs",
        )
