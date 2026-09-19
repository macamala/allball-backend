"""CEV Competition Area (www-old.cev.eu) public HTML family.

Parses CompetitionView.aspx match rows (teams, sets, local time, venue, match ID).
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin

from datetime import datetime, timedelta, timezone

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import _dedupe, _event, _text
from collector.http import fetch_text

BASE = "https://www-old.cev.eu/Competition-Area/"

COMPETITION_IDS: Dict[str, List[str]] = {
    "cev-eurovolley-men": ["1572"],
}

PLACEHOLDER = re.compile(r"\bwinner of\b|\bloser of\b|\bme[fs]-\d+\b", re.I)
SPAN_RE = re.compile(
    r'<span[^>]*id=["\'][^"\']*(Label2|Label4|LB_SetCasa|LB_SetOspiti|LB_DataOra|LB_Palasport|LB_Codice)["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
DIV_MATCH = re.compile(r'<div[^>]*id=["\'][^"\']*div_match["\'][^>]*>', re.I)
MID_RE = re.compile(r"MatchPage\.aspx\?[^\"']*mID=(\d+)", re.I)
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})(?:\s+(\d{1,2}:\d{2}))?")
PHASE_ID = re.compile(r"CompetitionView\.aspx\?ID=(\d+)", re.I)
LEGEND_RE = re.compile(r"<legend[^>]*>(.*?)</legend>", re.I | re.S)

_PAGE_CACHE: Dict[str, FetchResult] = {}


def _iso(day: int, month: int, year: int, clock: str = "") -> str:
    stamp = f"{year:04d}-{month:02d}-{day:02d}"
    if clock:
        return f"{stamp}T{clock}:00"
    return stamp


def _span_map(block: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, inner in SPAN_RE.findall(block or ""):
        out[key] = _text(inner)
    return out


def parse_cev_competition_area(html: str, *, competition_id: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    stage = ""
    for legend in LEGEND_RE.findall(html or ""):
        text = _text(legend)
        if text:
            stage = text.split("(")[0].strip()
            break
    starts = [match.start() for match in DIV_MATCH.finditer(html or "")]
    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(html or "")
        blocks.append((html or "")[start:end])
    for block in blocks:
        fields = _span_map(block)
        home = fields.get("Label2") or ""
        away = fields.get("Label4") or ""
        if PLACEHOLDER.search(f"{home} {away}"):
            continue
        home_score = away_score = None
        if fields.get("LB_SetCasa", "").isdigit() and fields.get("LB_SetOspiti", "").isdigit():
            home_score = int(fields["LB_SetCasa"])
            away_score = int(fields["LB_SetOspiti"])
        when = fields.get("LB_DataOra") or ""
        parsed = DATE_RE.search(when)
        start = None
        if parsed:
            start = _iso(int(parsed.group(1)), int(parsed.group(2)), int(parsed.group(3)), parsed.group(4) or "")
        mid = MID_RE.search(block)
        status = "scheduled"
        if home_score is not None:
            event_probe = {
                "start_time": start,
                "status": "finished",
                "status_inferred": True,
            }
            from collector.live_state import guard_future_status

            status = guard_future_status("finished", start, inferred=True, sport_id="volleyball")
        event = _event(
            home=home,
            away=away,
            start=start,
            status=status,
            home_score=home_score,
            away_score=away_score,
            venue=fields.get("LB_Palasport") or None,
            source_id=mid.group(1) if mid else f"{home}-{away}-{start}",
            extra={
                "competition": competition_id,
                "stage": stage,
                "match_code": fields.get("LB_Codice") or "",
                "status_inferred": home_score is not None,
            },
        )
        if event and event_is_valid(event, sport_id="volleyball", competition_id=competition_id):
            events.append(event)
    return _dedupe(events)


def phase_ids(html: str) -> List[str]:
    return list(dict.fromkeys(PHASE_ID.findall(html or "")))


class CevCompetitionAreaAdapter:
    adapter_key = "cev-competition-area"

    def __init__(self, source_id: str = "cev-competition-area", text_getter=None):
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
        ids = list(COMPETITION_IDS.get(competition_id) or [])
        configured = ((request.source_config or {}).get("url") or "").strip()
        if configured and "CompetitionView.aspx" in configured:
            match = re.search(r"ID=(\d+)", configured)
            if match and match.group(1) not in ids:
                ids.insert(0, match.group(1))
        extra_id = ((request.source_config or {}).get("competition_area_id") or "").strip()
        if extra_id and extra_id not in ids:
            ids.insert(0, extra_id)
        events: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        seen: Set[str] = set()
        queue = list(ids)
        while queue:
            cid = queue.pop(0)
            if cid in seen:
                continue
            seen.add(cid)
            url = urljoin(BASE, f"CompetitionView.aspx?ID={cid}")
            last = self._get(url)
            if not last.ok or not isinstance(last.payload, str):
                continue
            events.extend(parse_cev_competition_area(last.payload, competition_id=competition_id))
            if len(seen) == 1:
                for extra in phase_ids(last.payload):
                    if extra not in seen and len(queue) + len(seen) < 8:
                        queue.append(extra)
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
            parse_reason=f"cev competition-area {','.join(seen)}",
        )
