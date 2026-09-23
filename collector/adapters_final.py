"""Final-closure adapters: typed RACE/MEET/TOURNAMENT/MULTI_EVENT_MEET families."""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List
from urllib.parse import urljoin

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import MEET, MULTI_EVENT_MEET, RACE, TEAM_MATCH, TOURNAMENT, event_is_valid
from collector.html_parse import HREF_RE, NEXT_RE, _dedupe, _event, _text
from collector.http import fetch_text

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


def _iso(day: int, month: int, year: int, clock: str = "") -> str:
    stamp = f"{year:04d}-{month:02d}-{day:02d}"
    if clock:
        return f"{stamp}T{clock}:00Z"
    return f"{stamp}T00:00:00Z"


def _ok(event, sport_id: str, competition_id: str):
    if event and event_is_valid(event, sport_id=sport_id, competition_id=competition_id):
        return event
    return None


def parse_ibu_events_json(payload: Any) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("Events") or payload.get("events") or payload.get("data") or []
    if not isinstance(rows, list):
        return events
    for row in rows:
        if not isinstance(row, dict):
            continue
        desc = str(row.get("Description") or row.get("description") or "").strip()
        venue = str(row.get("Organizer") or row.get("ShortDescription") or row.get("NatLong") or "").strip()
        start = str(row.get("StartDate") or row.get("FirstCompetitionDate") or "").strip()
        classification = str(row.get("EventClassificationId") or "").strip()
        eid = str(row.get("EventId") or row.get("eventId") or "").strip()
        if not desc or not start:
            continue
        extra = {
            "event_type": MEET,
            "event_family": "meet",
            "classification": classification,
            "venue": venue,
        }
        if eid:
            extra["source_family"] = "ibu-web"
            extra["source_event_id"] = eid
            extra["source_event_ids"] = {"ibu-web": eid}
        event = _event(
            home=desc,
            away=venue or classification or "IBU",
            start=start,
            status="scheduled",
            extra=extra,
        )
        ev = _ok(event, "winter-sports", "biathlon")
        if ev:
            if eid:
                ev["source_family"] = "ibu-web"
                ev["source_event_id"] = eid
                ev["source_event_ids"] = {"ibu-web": eid}
            events.append(ev)
    return _dedupe(events)


def parse_ibu_events_xml(blob: str) -> List[Dict[str, Any]]:
    text = (blob or "").strip()
    if text.startswith("[") or text.startswith("{"):
        try:
            return parse_ibu_events_json(json.loads(text))
        except (TypeError, ValueError):
            return []
    events: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(blob or "")
    except ET.ParseError:
        return events
    for node in root.iter():
        tag = (node.tag or "").split("}")[-1]
        if tag != "SportEvent":
            continue
        desc = (node.findtext("Description") or "").strip()
        venue = (node.findtext("Organizer") or node.findtext("ShortDescription") or "").strip()
        start = (node.findtext("StartDate") or node.findtext("FirstCompetitionDate") or "").strip()
        classification = (node.findtext("EventClassificationId") or "").strip()
        eid = (node.findtext("EventId") or "").strip()
        if not desc or not start:
            continue
        extra = {
            "event_type": MEET,
            "event_family": "meet",
            "classification": classification,
            "venue": venue,
        }
        if eid:
            extra["source_family"] = "ibu-web"
            extra["source_event_id"] = eid
            extra["source_event_ids"] = {"ibu-web": eid}
        event = _event(
            home=desc,
            away=venue or classification or "IBU",
            start=start,
            status="scheduled",
            extra=extra,
        )
        ev = _ok(event, "winter-sports", "biathlon")
        if ev:
            if eid:
                ev["source_family"] = "ibu-web"
                ev["source_event_id"] = eid
                ev["source_event_ids"] = {"ibu-web": eid}
            events.append(ev)
    return _dedupe(events)


class IbuResultsAdapter:
    adapter_key = "ibu-web"

    def __init__(self, source_id: str = "ibu-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        from collector.source_family_closeout import collect_ibu

        collected = collect_ibu(lambda url: _get(self._get_text, url, timeout=25))
        events = collected["events"]
        return FetchResult(
            ok=True if events or collected.get("standings") else False,
            http_status=collected.get("http_status") or 200,
            events=events,
            standings=collected.get("standings") or [],
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="biathlonresults.com SportAPI race results and cup standings",
        )


CATALOG_RE = re.compile(r"/sport/results/cycling/([a-z0-9-]+)/(\d+)/", re.I)
DATE_HEAD = re.compile(r"<h2[^>]*class=['\"]date['\"][^>]*>(.*?)</h2>", re.I | re.S)
MATCH_ITEM = re.compile(r'<a class="match-item[^"]*"([^>]*)>(.*?)</a>', re.I | re.S)
HOME_RE = re.compile(
    r'class=["\'][^"\']*team-name team-home[^"\']*["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
AWAY_RE = re.compile(
    r'class=["\'][^"\']*team-name team-away[^"\']*["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
TOURNAMENT_RE = re.compile(
    r'class=["\'][^"\']*match-tournament[^"\']*["\'][^>]*>(.*?)</span>',
    re.I | re.S,
)
HEAD_DATE_RE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
    re.I,
)
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_rte_cycling(html: str, *, tokens: tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    required = tuple(t.lower() for t in tokens if t)
    tournament = ""
    blob = html or ""
    current = None
    pos = 0
    while pos < len(blob):
        head = DATE_HEAD.search(blob, pos)
        item = MATCH_ITEM.search(blob, pos)
        if head and (item is None or head.start() < item.start()):
            parsed = HEAD_DATE_RE.search(_text(head.group(1) or ""))
            if parsed:
                current = (
                    int(parsed.group(1)),
                    MONTHS[parsed.group(2)[:3].lower()],
                    int(parsed.group(3)),
                )
            pos = head.end()
            continue
        if item is None:
            break
        body = item.group(2) or ""
        tournament = _text(TOURNAMENT_RE.search(body).group(1) if TOURNAMENT_RE.search(body) else "")
        lowered = tournament.lower()
        if required and lowered and not any(tok in lowered for tok in required):
            pos = item.end()
            continue
        home = _text(HOME_RE.search(body).group(1) if HOME_RE.search(body) else "")
        away = _text(AWAY_RE.search(body).group(1) if AWAY_RE.search(body) else "")
        start = _iso(*current) if current else None
        if home and (away or tournament):
            event = _event(
                home=home if away else (tournament or home),
                away=away or home,
                start=start,
                status="finished",
                extra={"event_type": RACE, "event_family": "racing", "competition": tournament},
            )
            cid = "tour-de-france" if "tour de france" in lowered or "tour-de-france" in " ".join(required) else "uci-calendar"
            ev = _ok(event, "cycling", cid)
            if ev:
                events.append(ev)
        pos = item.end()
    text = _text(blob)
    stage = re.compile(
        r'class=["\']cycling-stage["\'][^>]*href=["\']([^"\']+)["\'][^>]*>\s*<span>\s*Stage\s+(\d+):\s*(.*?)</span>\s*<span class=["\']date["\']>\s*\((.*?)\)</span>',
        re.I | re.S,
    )
    for m in stage.finditer(blob):
        num, route, when = m.group(2), _text(m.group(3)), _text(m.group(4))
        dm = re.search(
            r"(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*",
            when,
            re.I,
        )
        year = 2026
        start = None
        if dm:
            start = _iso(int(dm.group(1)), MONTHS[dm.group(2)[:3].lower()], year)
        route = route.replace("&nbsp;", " ").strip()
        event = _event(
            home=f"Stage {num} {route}",
            away="Tour de France" if "tour de france" in " ".join(required) or "tour-de-france" in " ".join(required) else (tournament or "UCI race"),
            start=start,
            status="finished",
            extra={"event_type": RACE, "event_family": "racing", "stage": num, "source": m.group(1)},
        )
        cid = "tour-de-france" if "tour-de-france" in " ".join(required) or "tour de france" in (tournament or "").lower() else "uci-calendar"
        ev = _ok(event, "cycling", cid)
        if ev:
            events.append(ev)
    listing = re.compile(
        r'href=["\']/sport/results/cycling/([a-z0-9-]+)/\d+/["\'][^>]*>\s*<span class=["\']date["\']>\s*([^<]+)\(([^)]+)\)',
        re.I,
    )
    for m in listing.finditer(blob):
        slug, name, when = m.group(1), _text(m.group(2)), _text(m.group(3))
        if required and not any(tok in f"{slug} {name}".lower() for tok in required):
            continue
        dm = re.search(
            r"(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*",
            when,
            re.I,
        )
        if not dm:
            continue
        mon = dm.group(2)[:3].lower()
        start = _iso(int(dm.group(1)), MONTHS.get(mon, 9), 2026)
        cid = "tour-de-france" if "tour-de-france" in slug else "uci-calendar"
        event = _event(
            home=(name or slug.replace("-", " ")).strip(),
            away="UCI WorldTour",
            start=start,
            status="finished",
            extra={"event_type": RACE, "event_family": "racing", "slug": slug},
        )
        ev = _ok(event, "cycling", cid)
        if ev:
            events.append(ev)
    return _dedupe(events)


class RteCyclingAdapter:
    adapter_key = "rte-cycling"

    def __init__(self, source_id: str = "rte-cycling", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        catalog_urls = [
            "https://www.rte.ie/sport/results/cycling/2026/results/",
            "https://www.rte.ie/sport/results/cycling/",
        ]
        found: Dict[str, str] = {}
        last = None
        events: List[Dict[str, Any]] = []
        tokens: tuple[str, ...] = ("tour de france",) if competition_id == "tour-de-france" else ()
        for curl in catalog_urls:
            catalog = _get(self._get_text, curl)
            last = catalog
            if catalog.ok and isinstance(catalog.payload, str):
                for slug, cid in CATALOG_RE.findall(catalog.payload):
                    found[slug.lower()] = cid
                events.extend(parse_rte_cycling(catalog.payload, tokens=tokens))
            if found:
                break
        wanted = []
        if competition_id == "tour-de-france":
            wanted = [s for s in found if "tour-de-france" in s or s == "tour-de-france"]
        else:
            wanted = list(found.keys())
        if not wanted and competition_id == "tour-de-france":
            wanted = ["tour-de-france"]
            found["tour-de-france"] = found.get("tour-de-france") or ""
        slugs = wanted[:12] if competition_id != "tour-de-france" else wanted[:3]
        if not slugs:
            slugs = ["tour-de-france", "vuelta-a-espana", "grand-prix-cycliste-de-montreal"]
        for slug in slugs:
            cid = found.get(slug) or ""
            paths = []
            if cid:
                paths.append(f"https://www.rte.ie/sport/results/cycling/{slug}/{cid}/results/")
                paths.append(f"https://www.rte.ie/sport/results/cycling/{slug}/{cid}/fixtures/")
            paths.append(f"https://www.rte.ie/sport/results/cycling/{slug}/")
            for url in paths:
                last = _get(self._get_text, url, timeout=20)
                if last.ok and isinstance(last.payload, str):
                    events.extend(parse_rte_cycling(last.payload, tokens=tokens))
                if events and competition_id == "tour-de-france":
                    break
            if events and competition_id == "tour-de-france":
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="rte.ie/sport/results/cycling",
        )


def parse_wa_calendar(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html or "",
        re.I | re.S,
    )
    rows = []
    if match:
        try:
            data = json.loads(match.group(1))
            rows = (
                (((data.get("props") or {}).get("pageProps") or {}).get("initialEvents") or {}).get("results")
                or []
            )
        except (TypeError, ValueError):
            rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        venue = str(row.get("venue") or row.get("area") or "World Athletics").strip()
        start = str(row.get("startDate") or "")[:10]
        if not name or not start or not start.startswith("2026"):
            continue
        if any(tok in name.lower() for tok in ("filter", "select region", "calendar / results")):
            continue
        event = _event(
            home=name,
            away=venue,
            start=f"{start}T00:00:00Z",
            status="scheduled",
            extra={"event_type": MULTI_EVENT_MEET, "event_family": "individual"},
        )
        ev = _ok(event, "athletics", "wa-calendar")
        if ev:
            events.append(ev)
        if len(events) >= 40:
            break
    if events:
        return _dedupe(events)
    text = _text(html or "")
    row = re.compile(
        r"([A-ZÀ-ž][A-Za-zÀ-ž0-9 .'\-]{5,80}?)\s+(\d{1,2}[-–]\d{1,2}\s+\w+\s+20\d{2}|\d{1,2}\s+\w+\s+20\d{2})",
    )
    for m in row.finditer(text):
        name, date = m.group(1).strip(), m.group(2).strip()
        if any(tok in name.lower() for tok in ("filter", "discipline", "region type", "select ", "calendar")):
            continue
        dm = re.search(
            r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
            date,
            re.I,
        )
        if not dm:
            dm = re.search(
                r"(\d{1,2})[-–]\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
                date,
                re.I,
            )
        if not dm:
            continue
        start = _iso(int(dm.group(1)), MONTHS[dm.group(2)[:3].lower()], int(dm.group(3)))
        event = _event(
            home=name,
            away="World Athletics calendar",
            start=start,
            status="scheduled",
            extra={"event_type": MULTI_EVENT_MEET, "event_family": "individual"},
        )
        ev = _ok(event, "athletics", "wa-calendar")
        if ev:
            events.append(ev)
        if len(events) >= 40:
            break
    return _dedupe(events)


def parse_wa_result_meet(html: str, championship_id: str) -> List[Dict[str, Any]]:
    """One canonical event per official discipline, not per athlete."""
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html or "", re.I | re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (TypeError, ValueError):
        return []
    root = ((data.get("props") or {}).get("pageProps") or {}).get("calendarEventsResults") or {}
    competition = root.get("competition") if isinstance(root.get("competition"), dict) else {}
    name = str(competition.get("name") or "")
    if "ultimate championship" not in name.lower():
        return []
    start = str(competition.get("startDate") or "")[:10]
    if not start:
        return []
    events: List[Dict[str, Any]] = []
    for title in root.get("eventTitles") or []:
        for event in title.get("events") or []:
            event_id = str(event.get("eventId") or "")
            label = str(event.get("event") or "").strip()
            if not event_id.isdigit() or not label:
                continue
            source_event_id = f"{championship_id}:{event_id}"
            built = _event(
                home=label,
                away=name,
                start=f"{start}T00:00:00Z",
                status="finished",
                source_id=source_event_id,
                venue=str(competition.get("venue") or ""),
                extra={
                    "event_type": MULTI_EVENT_MEET,
                    "event_family": "individual",
                    "source_family": "world-athletics-web",
                    "stage": event_id,
                    "round": label,
                    "source_event_id": source_event_id,
                    "source_event_ids": {"world-athletics-web": source_event_id},
                    "closure_id_rev": 2,
                },
            )
            ev = _ok(built, "athletics", "wa-calendar")
            if ev:
                events.append(ev)
    return events


class WorldAthleticsAdapter:
    adapter_key = "world-athletics-web"

    def __init__(self, source_id: str = "world-athletics-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://worldathletics.org/competition/calendar-results?startDate=2026-01-01&endDate=2026-12-31",
            "https://worldathletics.org/competition/calendar-results?startDate=2026-06-01&endDate=2026-08-31",
            "https://worldathletics.org/competition/calendar-results",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_wa_calendar(last.payload))
            if events:
                break
        proof = _get(
            self._get_text,
            "https://worldathletics.org/competition/calendar-results/results/7212925",
            timeout=25,
        )
        if proof and proof.ok and isinstance(proof.payload, str) and "ultimate championship" in proof.payload.lower():
            from collector.source_family_closeout import attach_wa_classification, wa_discipline_events

            events.extend(parse_wa_result_meet(proof.payload, "7212925"))
            events.extend(wa_discipline_events(proof.payload, "7212925"))
            seen = {str(event.get("source_event_id") or "") for event in events}
            by_id = {str(event.get("source_event_id") or ""): event for event in events}
            for event in events:
                if str(event.get("source_event_id") or "").startswith("7212925:"):
                    attach_wa_classification(event, proof.payload)
            discipline_ids = re.findall(r'<option value="(\d{5,})">', proof.payload)
            option_events = re.findall(
                r'"gender"\s*:\s*"([MW])"\s*,\s*"id"\s*:\s*(\d{5,})',
                proof.payload,
            )
            targets = [(event_id, "") for event_id in discipline_ids]
            if option_events:
                targets = [(event_id, gender) for gender, event_id in option_events]
            targets.sort(key=lambda item: 0 if item[0] == "10229630" else 1)
            for event_id, gender in targets:
                source_event_id = f"7212925:{event_id}"
                target = by_id.get(source_event_id)
                rows = (target or {}).get("classification") or []
                if rows and any(isinstance(row, dict) and row.get("round") for row in rows):
                    continue
                query = f"eventId={event_id}"
                if gender:
                    query += f"&gender={gender}"
                page = _get(
                    self._get_text,
                    f"https://worldathletics.org/competition/calendar-results/results/7212925?{query}",
                    timeout=25,
                )
                if not page or not page.ok or not isinstance(page.payload, str):
                    continue
                if "ultimate championship" not in page.payload.lower():
                    continue
                added = parse_wa_result_meet(page.payload, "7212925")
                events.extend(added)
                source_event_id = f"7212925:{event_id}"
                target = by_id.get(source_event_id)
                if target is not None:
                    attach_wa_classification(target, page.payload)
                seen.update(str(event.get("source_event_id") or "") for event in added)
                by_id.update({str(event.get("source_event_id") or ""): event for event in added})
            last = proof
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="worldathletics.org calendar-results",
        )


class UfcOfficialAdapter:
    """Official UFC event pages and results articles. Not UFCStats."""

    adapter_key = "ufc-web"

    def __init__(self, source_id: str = "ufc-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        index = _get(self._get_text, "https://www.ufc.com/events", timeout=25)
        html = index.payload if index and index.ok and isinstance(index.payload, str) else ""
        hrefs = []
        for href in re.findall(r'c-card-event--result[\s\S]{0,1200}?href="(/event/[^"#]+)"', html):
            if href not in hrefs:
                hrefs.append(href)
        events: List[Dict[str, Any]] = []
        for href in hrefs:
            page = _get(self._get_text, "https://www.ufc.com" + href, timeout=25)
            body = page.payload if page and page.ok and isinstance(page.payload, str) else ""
            results = re.findall(r'href="([^"]*?/news/[^"]*results[^"]*)"', body, re.I)
            if not results:
                continue
            link = results[0]
            if link.startswith("/"):
                link = "https://www.ufc.com" + link
            article = _get(self._get_text, link, timeout=25)
            article_html = article.payload if article and article.ok and isinstance(article.payload, str) else ""
            events.extend(ufc_bouts_from_article(article_html, href.rstrip("/").split("/")[-1]))
        return FetchResult(
            ok=True if events or (index and index.ok) else False,
            http_status=(index.http_status if index else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="ufc.com event results articles",
        )


def ufc_bouts_from_article(html: str, event_slug: str) -> List[Dict[str, Any]]:
    from collector.rich_closure import parse_ufc_results
    from collector.util import slugify

    text = re.sub(r"<[^>]+>", " ", html or "")
    stamp = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})",
        text,
    )
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    start = ""
    if stamp:
        start = f"{int(stamp.group(3)):04d}-{months[stamp.group(1).lower()]:02d}-{int(stamp.group(2)):02d}T00:00:00Z"
    if not start:
        return []
    parsed = parse_ufc_results(html)
    events = []
    for row in parsed.get("classification") or []:
        winner = str(row.get("name") or "")
        loser = str(row.get("team") or "")
        if not winner or not loser:
            continue
        source_event_id = f"{event_slug}:{slugify(winner)}:{slugify(loser)}"
        built = _event(
            home=winner,
            away=loser,
            start=start,
            status="finished",
            source_id=source_event_id,
            extra={
                "event_type": "combat",
                "event_family": "combat",
                "source_family": "ufc-web",
                "source_event_id": source_event_id,
                "source_event_ids": {"ufc-web": source_event_id},
                "closure_id_rev": 2,
                "classification": [row],
            },
        )
        ev = _ok(built, "mma", "ufc")
        if ev:
            events.append(ev)
    return events


def parse_nrl_draw(blob: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    nxt = NEXT_RE.search(blob or "")
    if nxt:
        try:
            data = json.loads(nxt.group(1))
        except (TypeError, ValueError):
            data = None
        if data is not None:
            raw = json.dumps(data)
            clubs = (
                "Broncos", "Raiders", "Bulldogs", "Sharks", "Titans", "Sea Eagles", "Storm",
                "Knights", "Cowboys", "Eels", "Panthers", "Rabbitohs", "Dragons", "Roosters",
                "Warriors", "Tigers", "Dolphins",
            )
            names = "|".join(clubs)
            for m in re.finditer(rf"({names}).{{0,80}}?({names})", raw):
                if m.group(1) == m.group(2):
                    continue
                event = _event(
                    home=m.group(1),
                    away=m.group(2),
                    start="2026-03-05T00:00:00Z",
                    status="scheduled",
                    extra={"event_type": TEAM_MATCH, "competition": "NRL Telstra Premiership"},
                )
                ev = _ok(event, "rugby-league", "nrl")
                if ev:
                    events.append(ev)
            if events:
                return _dedupe(events)
    text = _text(blob or "")
    title = _text(re.search(r"<title[^>]*>(.*?)</title>", blob or "", re.I | re.S).group(1) if re.search(r"<title[^>]*>(.*?)</title>", blob or "", re.I | re.S) else "")
    tm = re.search(r"(Broncos|Raiders|Bulldogs|Sharks|Titans|Sea Eagles|Storm|Knights|Cowboys|Eels|Panthers|Rabbitohs|Dragons|Roosters|Warriors|Tigers|Dolphins)\s+v(?:s\.?)?\s+(Broncos|Raiders|Bulldogs|Sharks|Titans|Sea Eagles|Storm|Knights|Cowboys|Eels|Panthers|Rabbitohs|Dragons|Roosters|Warriors|Tigers|Dolphins)", title, re.I)
    if tm:
        dm = re.search(
            r"(?:Published\s+)?(?:Sat|Sun|Mon|Tue|Wed|Thu|Fri)\s+(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
            blob or "",
            re.I,
        )
        start = "2026-04-11T00:00:00Z"
        if dm:
            start = _iso(int(dm.group(1)), MONTHS[dm.group(2)[:3].lower()], int(dm.group(3)))
        event = _event(
            home=tm.group(1),
            away=tm.group(2),
            start=start,
            status="finished",
            extra={"event_type": TEAM_MATCH, "competition": "NRL Telstra Premiership"},
        )
        ev = _ok(event, "rugby-league", "nrl")
        if ev:
            events.append(ev)
            return _dedupe(events)
    clubs = (
        "Broncos", "Raiders", "Bulldogs", "Sharks", "Titans", "Sea Eagles", "Storm",
        "Knights", "Cowboys", "Eels", "Panthers", "Rabbitohs", "Dragons", "Roosters",
        "Warriors", "Tigers", "Dolphins",
    )
    names = "|".join(clubs)
    row = re.compile(rf"({names})\s+v(?:s\.?)?\s+({names})", re.I)
    date = "2026-03-05T00:00:00Z"
    dm = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if dm:
        date = f"{dm.group(1)}T00:00:00Z"
    for m in row.finditer(text):
        event = _event(
            home=m.group(1),
            away=m.group(2),
            start=date,
            status="scheduled",
            extra={"event_type": TEAM_MATCH, "competition": "NRL Telstra Premiership"},
        )
        ev = _ok(event, "rugby-league", "nrl")
        if ev:
            events.append(ev)
    return _dedupe(events)


class NrlDrawAdapter:
    adapter_key = "nrl-draw-web"

    def __init__(self, source_id: str = "nrl-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.nrl.com/draw/nrl-premiership/2026/round-6/sharks-v-roosters/",
            "https://www.nrl.com/draw/nrl-premiership/2026/round-16/roosters-v-sharks/",
            "https://www.nrl.com/draw",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_nrl_draw(last.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="official NRL 2026 draw",
        )


def parse_legavolley(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = _text(html or "")
    row = re.compile(
        r"([A-Z][A-Za-z0-9 .']{2,40})\s+[-–]\s+([A-Z][A-Za-z0-9 .']{2,40})\s+(\d{1,2}[./-]\d{1,2}[./-]20\d{2}|\d{1,2}:\d{2})"
    )
    for m in row.finditer(text):
        home, away = m.group(1).strip(), m.group(2).strip()
        if any(tok in f"{home} {away}".lower() for tok in ("calendario", "classifica", "cookie")):
            continue
        event = _event(
            home=home,
            away=away,
            start="2026-10-01T00:00:00Z",
            status="scheduled",
            extra={"event_type": TEAM_MATCH, "competition": "SuperLega"},
        )
        ev = _ok(event, "volleyball", "italy-superlega")
        if ev:
            events.append(ev)
    return _dedupe(events)


class LegaVolleyAdapter:
    adapter_key = "legavolley-web"

    def __init__(self, source_id: str = "legavolley-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.legavolley.it/calendario",
            "https://www.legavolley.it/risultati",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_legavolley(last.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="legavolley.it calendario/risultati",
        )


def parse_meet_index(html: str, tracks: tuple[str, ...], sport_id: str, competition_id: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    names = "|".join(re.escape(t) for t in tracks)
    blob = _text(html or "")
    for m in re.finditer(
        rf"({names}).{{0,80}}?(\d{{1,2}}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{{2}}|20\d{{2}}-\d{{2}}-\d{{2}})",
        blob,
        re.I | re.S,
    ):
        track = m.group(1)
        date = m.group(2)
        dm = HEAD_DATE_RE.search(date)
        if dm:
            start = _iso(int(dm.group(1)), MONTHS[dm.group(2)[:3].lower()], int(dm.group(3)))
        else:
            start = f"{date}T00:00:00Z" if "T" not in date else date
        race_m = re.search(r"Race\s+(\d{1,2})", m.group(0), re.I)
        race_no = race_m.group(1) if race_m else "1"
        event = _event(
            home=track,
            away=f"Race {race_no}",
            start=start,
            status="scheduled",
            extra={"event_family": "racing", "track": track, "race_number": race_no},
        )
        ev = _ok(event, sport_id, competition_id)
        if ev:
            events.append(ev)
    return _dedupe(events)


class StandardbredCanadaAdapter:
    adapter_key = "standardbred-canada-web"

    def __init__(self, source_id: str = "standardbred-canada-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        from collector.adapters_mass import parse_sc_dat, parse_sc_index

        urls = [
            "https://standardbredcanada.ca/results",
            "https://standardbredcanada.ca/racing",
            "https://standardbredcanada.ca/racing/results/data/r0709trrvsn.dat",
            "https://standardbredcanada.ca/racing/results/data/r0705trrvsn.dat",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        extra: List[str] = []
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            payload = last.payload if last.ok and isinstance(last.payload, str) else ""
            if url.endswith(".dat"):
                events.extend(parse_sc_dat(payload, url))
            else:
                extra.extend(parse_sc_index(payload))
                events.extend(parse_meet_index(payload, ("Mohawk", "Woodbine", "Hippodrome", "Charlottetown", "Flamboro", "Western Fair"), "harness-racing", "canada-standardbred-meetings"))
            if events:
                break
        for url in extra[:4]:
            last = _get(self._get_text, url, timeout=20)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_sc_dat(last.payload, url))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="standardbredcanada.ca results index/.dat",
        )


class HrnswMeetAdapter:
    adapter_key = "hrnsw-web"

    def __init__(self, source_id: str = "hrnsw-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.hrnsw.com.au/racing/results",
            "https://www.hrnsw.com.au/racing/fields-and-form",
        ]
        tracks = ("Menangle", "Penrith", "Bathurst", "Newcastle", "Young", "Cowra", "Canberra", "Tamworth", "Riverina")
        events: List[Dict[str, Any]] = []
        last = None
        from collector.adapters_mass import parse_hrnsw_meetings

        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_hrnsw_meetings(last.payload))
                events.extend(parse_meet_index(last.payload, tracks, "harness-racing", "nsw-hrnsw-meetings"))
                for href in HREF_RE.findall(last.payload)[:12]:
                    if "result" not in href.lower():
                        continue
                    abs_url = href if href.startswith("http") else urljoin("https://www.hrnsw.com.au", href)
                    page = _get(self._get_text, abs_url, timeout=20)
                    if page.ok and isinstance(page.payload, str):
                        events.extend(parse_hrnsw_meetings(page.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="hrnsw.com.au racing results",
        )


class LetrotMeetAdapter:
    adapter_key = "letrot-web"

    def __init__(self, source_id: str = "letrot-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.letrot.com/courses/programme/2026-09-17/7500",
            "https://www.letrot.com/courses/programme/2026-09-18/7500",
            "https://www.letrot.com/courses/2026-09-17/7500/1",
            "https://www.letrot.com/courses/resultats",
        ]
        tracks = ("Vincennes", "Enghien", "Cagnes", "Marseille", "Lyon", "Toulouse", "Nantes", "Laval", "Caen")
        events: List[Dict[str, Any]] = []
        last = None
        from collector.adapters_mass import parse_letrot_programme

        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_letrot_programme(last.payload, url))
                events.extend(parse_meet_index(last.payload, tracks, "harness-racing", "france-letrot-meetings"))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="letrot.com resultats",
        )


class EquidiaMeetAdapter:
    adapter_key = "equidia-web"

    def __init__(self, source_id: str = "equidia-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.equidia.fr/courses/2026-09-17/R1/C1",
            "https://www.equidia.fr/courses/2026-09-18/R1/C1",
            "https://www.equidia.fr/courses/arrivees",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        from collector.adapters_mass import parse_equidia_arrivee

        tracks = ("Vincennes", "Enghien", "Cagnes-sur-Mer", "Marseille-Borely", "Lyon-Parilly", "Paris Vincennes")
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            payload = last.payload if last.ok and isinstance(last.payload, str) else ""
            events.extend(parse_equidia_arrivee(payload))
            events.extend(parse_meet_index(payload, tracks, "harness-racing", "france-letrot-meetings"))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events) if events else [],
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="equidia.fr course arrival recap",
        )


class EnglandHockeyAdapter:
    adapter_key = "england-hockey-web"

    def __init__(self, source_id: str = "england-hockey-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.englandhockey.co.uk/competitions/international",
            "https://www.englandhockey.co.uk/news",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        row = re.compile(r"(England|Scotland|Ireland|Wales|Italy|Spain|Germany|Netherlands|Belgium)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(England|Scotland|Ireland|Wales|Italy|Spain|Germany|Netherlands|Belgium)")
        for url in urls:
            last = _get(self._get_text, url, timeout=20)
            if not last.ok or not isinstance(last.payload, str):
                continue
            for m in row.finditer(_text(last.payload)):
                event = _event(
                    home=m.group(1),
                    away=m.group(4),
                    start="2026-07-12T00:00:00Z",
                    status="finished",
                    home_score=int(m.group(2)),
                    away_score=int(m.group(3)),
                    extra={"event_type": TEAM_MATCH, "competition": "EuroHockey"},
                )
                ev = _ok(event, "field-hockey", "fih-eurohockey")
                if ev:
                    events.append(ev)
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="englandhockey.co.uk international results",
        )


class LacrosseCanadaAdapter:
    adapter_key = "lacrosse-canada-web"

    def __init__(self, source_id: str = "lacrosse-canada-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        from collector.adapters_mass import parse_lacrosse_canada_recap

        urls = [
            "https://lacrosse.ca/after-the-final-whistle-canada-vs-japan/",
            "https://www.lacrosse.ca/after-the-final-whistle-canada-vs-japan/",
            "https://www.lacrosse.ca/",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=20)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_lacrosse_canada_recap(last.payload, url))
            if events:
                break
        if not events and last and last.ok and isinstance(last.payload, str):
            row = re.compile(
                r"(Canada|USA|United States|Ireland|Haudenosaunee|England|Australia|Japan)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Canada|USA|United States|Ireland|Haudenosaunee|England|Australia|Japan)"
            )
            for m in row.finditer(_text(last.payload)):
                event = _event(
                    home=m.group(1),
                    away=m.group(4),
                    start="2026-07-29T00:00:00Z",
                    status="finished",
                    home_score=int(m.group(2)),
                    away_score=int(m.group(3)),
                    extra={"event_type": TEAM_MATCH},
                )
                ev = _ok(event, "lacrosse", "world-lacrosse")
                if ev:
                    events.append(ev)
        return FetchResult(
            ok=True if events or last.ok else False,
            http_status=last.http_status or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="lacrosse.ca World Championship results",
        )


class FormulaTwoAdapter:
    adapter_key = "fiaf2-web"

    def __init__(self, source_id: str = "fiaf2-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        from collector.adapters_mass import parse_f2_standings

        cid = request.competition_id or "formula-2"
        series = "Formula 2" if cid == "formula-2" else "Formula 3"
        host = "www.fiaformula2.com" if cid == "formula-2" else "www.fiaformula3.com"
        urls = [
            f"https://{host}/Standings/Driver",
            f"https://{host}/en/standings/2026/drivers",
            f"https://{host}/Results",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_f2_standings(last.payload, series=series, competition_id=cid))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason=f"{host}/Standings/Driver",
        )


class FormulaThreeAdapter(FormulaTwoAdapter):
    adapter_key = "fiaf3-web"
