"""Omega Timing public XML/HTML family adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_text


def _local(tag: str) -> str:
    return (tag or "").split("}")[-1].lower()


def parse_omega_xml(text: str, competition_id: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return events
    for node in root.iter():
        tag = _local(node.tag)
        if tag not in {"game", "match", "result", "heat"} and not (
            node.attrib.get("Home") or node.attrib.get("home") or node.find("Home") is not None
        ):
            continue
        home = (
            node.attrib.get("Home")
            or node.attrib.get("home")
            or (node.findtext("Home") or node.findtext("home") or "")
        )
        away = (
            node.attrib.get("Away")
            or node.attrib.get("away")
            or (node.findtext("Away") or node.findtext("away") or "")
        )
        if not home:
            continue
        home_score = node.attrib.get("HomeScore") or node.findtext("HomeScore")
        away_score = node.attrib.get("AwayScore") or node.findtext("AwayScore")
        start = node.attrib.get("Date") or node.attrib.get("Start") or node.findtext("Date")
        events.append(
            {
                "id": node.attrib.get("Id") or f"{home}-{away}-{start}",
                "home": {"name": home.strip()},
                "away": {"name": (away or "").strip()},
                "status": "finished" if home_score not in (None, "") else "scheduled",
                "score": {
                    "home": int(home_score) if str(home_score or "").isdigit() else None,
                    "away": int(away_score) if str(away_score or "").isdigit() else None,
                },
                "start_time": start,
                "competition": competition_id,
            }
        )
        if len(events) >= 40:
            break
    if events:
        return events
    for event_el in root.iter():
        if _local(event_el.tag) not in {"event", "unit", "discipline", "heat"}:
            continue
        event_name = (
            event_el.attrib.get("Name")
            or event_el.attrib.get("Title")
            or event_el.attrib.get("Description")
            or event_el.attrib.get("EventName")
            or "Omega event"
        )
        start = event_el.attrib.get("StartDate") or event_el.attrib.get("Date") or ""
        for node in event_el.iter():
            if _local(node.tag) not in {"athlete", "competitor", "swimmer", "diver"}:
                continue
            home = (
                node.attrib.get("FullName")
                or node.attrib.get("Name")
                or " ".join(
                    part
                    for part in (
                        node.attrib.get("GivenName") or node.attrib.get("FirstName"),
                        node.attrib.get("FamilyName") or node.attrib.get("LastName"),
                    )
                    if part
                )
                or (node.findtext("FullName") or node.findtext("Name") or "")
            ).strip()
            if not home:
                continue
            rank = node.attrib.get("Rank") or node.attrib.get("Place") or node.findtext("Rank")
            result_time = node.attrib.get("Time") or node.attrib.get("Result") or node.findtext("Time")
            events.append(
                {
                    "id": node.attrib.get("Id") or f"{home}-{event_name}-{rank}",
                    "home": {"name": home},
                    "away": {"name": str(event_name)},
                    "status": "finished" if rank not in (None, "") or result_time else "scheduled",
                    "score": {
                        "home": int(rank) if str(rank or "").isdigit() else None,
                        "away": None,
                    },
                    "start_time": start,
                    "competition": competition_id,
                    "extra": {"result": result_time, "rank": rank},
                }
            )
            if len(events) >= 40:
                return events
    return events


class OmegaTimingAdapter:
    adapter_key = "omega-timing"

    def __init__(self, source_id: str = "omega-timing", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        from collector.html_parse import _event, _text
        from collector.event_quality import event_is_valid
        from collector.adapters_generic import GenericHttpAdapter, classify_http
        from urllib.parse import urljoin
        import re

        sport_index = self._get_text("https://www.omegatiming.com/Sport")
        index_events: List[Dict[str, Any]] = []
        follow: List[str] = []
        if sport_index.ok and isinstance(sport_index.payload, str):
            html = sport_index.payload
            for row in re.finditer(
                r'<p class="date">(.*?)</p>\s*<h3 class="detail">\s*<a href="([^"]+)">([^<]+)</a>',
                html,
                re.I | re.S,
            ):
                date_txt = _text(row.group(1))
                href = urljoin("https://www.omegatiming.com/", row.group(2))
                name = _text(row.group(3))
                year = "2026" if "2026" in date_txt or "/2026/" in href else ""
                if request.competition_id == "world-aquatics-meets" and not any(
                    token in f"{name} {href}".lower() for token in ("swim", "diving", "high diving", "aquatic")
                ):
                    continue
                if request.competition_id == "world-aquatics-events" and "water polo" not in f"{name} {href}".lower():
                    # still allow diving/swim index rows only for meets
                    if "polo" not in f"{name} {href}".lower():
                        continue
                start = None
                dm = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}).{0,40}(20\d{2})", date_txt, re.I)
                if dm:
                    months = {
                        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
                        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
                    }
                    start = f"{dm.group(3)}-{months[dm.group(1).lower()]:02d}-{int(dm.group(2)):02d}T00:00:00Z"
                venue = date_txt.split("-")[-1].strip() if "-" in date_txt else date_txt
                event = _event(
                    home=name,
                    away=venue or "Omega",
                    start=start,
                    status="scheduled",
                    extra={"event_family": "individual"},
                )
                if event and event_is_valid(
                    event,
                    sport_id="swimming" if (request.competition_id or "").endswith("meets") else "water-polo",
                    competition_id=request.competition_id or "",
                ):
                    blob = f"{name} {venue}".lower()
                    if not any(tok in blob for tok in ("start list", "dive list", "round vs", "detailed results")):
                        index_events.append(event)
                if year == "2026" or "/2026/" in href:
                    follow.append(href)
            for href in follow[:4]:
                extra = self._get_text(href)
                if extra.ok and isinstance(extra.payload, str):
                    html_events = GenericHttpAdapter(source_id=self.source_id, text_getter=self._get_text).fetch(
                        FetchRequest(capability="snapshot", competition_id=request.competition_id, source_config={"url": href})
                    )
                    cleaned = []
                    for ev in html_events.events or []:
                        blob = f"{(ev.get('home') or {}).get('name')} {(ev.get('away') or {}).get('name')}".lower()
                        if any(tok in blob for tok in ("start list", "dive list", "detailed results", "cookie")):
                            continue
                        if event_is_valid(
                            ev,
                            sport_id="swimming" if (request.competition_id or "").endswith("meets") else "water-polo",
                            competition_id=request.competition_id or "",
                        ):
                            cleaned.append(ev)
                    if cleaned:
                        return FetchResult(ok=True, http_status=html_events.http_status or 200, events=cleaned, parse_reason="Omega event live-results HTML")
                    xml_hrefs = []
                    for match in re.finditer(r'href=["\']([^"\']+\.xml)["\']', extra.payload, re.I):
                        xml_hrefs.append(urljoin(href, match.group(1)))
                    for xml_url in xml_hrefs[:3]:
                        xml_res = self._get_text(xml_url)
                        if xml_res.ok and isinstance(xml_res.payload, str):
                            parsed = parse_omega_xml(xml_res.payload, request.competition_id or "")
                            if parsed:
                                return FetchResult(ok=True, http_status=xml_res.http_status or 200, events=parsed)
        if index_events:
            return FetchResult(ok=True, http_status=sport_index.http_status or 200, events=index_events, parse_reason="omegatiming.com/Sport index")

        config = request.source_config or {}
        url = (config.get("url") or "").strip()
        xml_urls = [item for item in (config.get("xml_urls") or []) if item]
        if url.lower().endswith(".xml") or (config.get("source_type") or "").lower().find("xml") >= 0:
            if url:
                xml_urls = [url] + [item for item in xml_urls if item != url]
        if xml_urls:
            last = None
            for xml_url in xml_urls[:3]:
                last = self._get_text(xml_url)
                if not last.ok:
                    last.classification = classify_http(last)
                    continue
                text = last.payload if isinstance(last.payload, str) else ""
                events = parse_omega_xml(text, request.competition_id or "")
                if events:
                    return FetchResult(
                        ok=True,
                        http_status=last.http_status or 200,
                        events=events,
                    )
            if last is not None and not last.ok:
                return last
            return FetchResult(
                ok=True,
                http_status=(last.http_status if last else 200) or 200,
                events=[],
                empty_reason="SOURCE_HEALTHY_NO_EVENTS",
            )
        html_result = GenericHttpAdapter(source_id=self.source_id, text_getter=self._get_text).fetch(request)
        if html_result.events:
            return html_result
        listing = self._get_text(url) if url else html_result
        text = listing.payload if listing and isinstance(listing.payload, str) else ""
        xml_hrefs = []
        for match in __import__("re").finditer(r'href=["\']([^"\']+\.xml)["\']', text or "", __import__("re").I):
            href = match.group(1)
            if href.startswith("http"):
                xml_hrefs.append(href)
            elif url:
                from urllib.parse import urljoin

                xml_hrefs.append(urljoin(url, href))
        for xml_url in xml_hrefs[:4]:
            extra = self._get_text(xml_url)
            if not extra.ok or not isinstance(extra.payload, str):
                continue
            events = parse_omega_xml(extra.payload, request.competition_id or "")
            if events:
                return FetchResult(ok=True, http_status=extra.http_status or 200, events=events)
        return html_result
