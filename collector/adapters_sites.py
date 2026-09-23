"""Host-family parsers for mapped official sites that generic HTML misses.

Each parser is keyed by hostname, not competition. Output is the canonical
event dict used by normalize/merge.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from collector.html_parse import (
    _event,
    parse_html,
    parse_initial_data,
    parse_next_data,
    parse_tables,
    walk_json_events,
)

Q_DATA = re.compile(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.I | re.S)
NUXT = re.compile(r"window\.__NUXT__\s*=", re.I)
JSON_ASSIGN = re.compile(r"window\.([A-Z_]+)\s*=\s*(\{.*?\});", re.S)


def events_for_host(html: str, url: str) -> List[Dict[str, Any]]:
    host = urlparse(url).netloc.lower().replace("www.", "")
    if "nrl.com" in host:
        return parse_nrl(html)
    if "wnba.com" in host:
        return parse_wnba(html)
    if "cyclingnews.com" in host or "uci.org" in host or "letour.fr" in host:
        return parse_cycling(html)
    if any(token in host for token in ("sportinglife.com", "gbgb.org.uk", "hrnsw.com.au", "letrot.com", "equidia.fr")):
        return parse_racing(html)
    if "abc.net.au" in host:
        return parse_abc(html)
    if "tournamentsoftware.com" in host or "bwfbadminton.com" in host:
        from collector.source_family_closeout import bwf_tournament_links, parse_tournamentsoftware_matches

        tournament_id = ""
        match = re.search(r"/tournament/(\d+)|/(\d{3,5})$", url)
        if match:
            tournament_id = match.group(1) or match.group(2) or ""
        if not tournament_id:
            links = bwf_tournament_links(html)
            tournament_id = links[0]["tournament_id"] if links else ""
        parsed = parse_tournamentsoftware_matches(html, tournament_id=tournament_id, federation="bwf" if "bwf" in host else host)
        if parsed:
            return parsed
    if "grireland.ie" in host and "view-results" in url:
        from collector.source_family_closeout import parse_gri_race_card

        query = parse_qs(urlparse(url).query)
        track = (query.get("track") or [""])[0]
        date_token = (query.get("date") or [""])[0]
        parsed = parse_gri_race_card(html, track=track, date_token=date_token)
        if parsed:
            return parsed
    if "futsalplanet.com" in host or "lnfoficial.com.br" in host or "lnf.com.br" in host:
        return parse_html(html, url)
    if "mytischtennis.de" in host or "tischtennislive.de" in host:
        return parse_html(html, url)
    if "lnr.fr" in host or "super.rugby" in host:
        return parse_html(html, url)
    if "superliga.rs" in host:
        return parse_superliga(html)
    if host.endswith("fss.rs") or host == "fss.rs":
        return parse_fss(html)
    if "sportnet.sme.sk" in host or "futbalnet" in host:
        sportnet = parse_sportnet(html)
        if sportnet:
            return sportnet
        return parse_html(html, url)
    if any(
        token in host
        for token in (
            "conmebol.com",
            "superliga.dk",
            "tophaandbold.dk",
            "handball-bundesliga.de",
            "acb.com",
            "allsvenskan.se",
            "nwslsoccer.com",
            "uslsoccer.com",
            "uslchampionship.com",
            "netball.com.au",
            "biathlonworld.com",
            "ekstraklasa.org",
        )
    ):
        return parse_html(html, url)
    return []


def parse_nrl(html: str) -> List[Dict[str, Any]]:
    events = parse_next_data(html) or parse_initial_data(html)
    if events:
        return events
    events = walk_json_events(_embedded_objects(html))
    if events:
        return events
    return parse_tables(html)


def parse_wnba(html: str) -> List[Dict[str, Any]]:
    events = parse_next_data(html) or parse_initial_data(html)
    if events:
        return events
    return walk_json_events(_embedded_objects(html)) or parse_html(html)


def parse_cycling(html: str) -> List[Dict[str, Any]]:
    events = parse_next_data(html) or parse_initial_data(html)
    if events:
        for event in events:
            event.setdefault("event_family", "stage_race")
        return events
    table = parse_tables(html)
    if table:
        for event in table:
            event.setdefault("event_family", "stage_race")
        return table
    found = []
    for match in re.finditer(
        r"(Stage\s+\d+[^<]{0,40}|Prologue)[^\n]{0,80}(20\d{2}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+20\d{2})",
        html,
        re.I,
    ):
        event = _event(home=match.group(1).strip(), away="", start=match.group(2), extra={"event_family": "stage_race"})
        if event:
            found.append(event)
        if len(found) >= 30:
            break
    if found:
        return found
    for match in re.finditer(
        r'href=["\']([^"\']+/(?:race|races|event)[^"\']*)["\'][^>]*>([^<]{8,90})',
        html or "",
        re.I,
    ):
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        lowered = title.lower()
        if any(token in lowered for token in ("cookie", "login", "subscribe", "privacy", "newsletter", "sign in", "advert")):
            continue
        if len(title) < 10:
            continue
        event = _event(home=title, away="race", extra={"event_family": "stage_race"})
        if event:
            found.append(event)
        if len(found) >= 25:
            break
    return found or parse_html(html)


def parse_racing(html: str) -> List[Dict[str, Any]]:
    events = parse_next_data(html) or parse_initial_data(html) or walk_json_events(_embedded_objects(html))
    if events:
        for event in events:
            event.setdefault("event_family", "racing")
        return events
    found = []
    for match in re.finditer(
        r"((?:Race|R)\s*\d+)[^\n]{0,40}?([A-Z][A-Za-z]{2,}(?:\s[A-Z][A-Za-z]+){0,3})",
        html[:50000],
    ):
        event = _event(home=match.group(1), away=match.group(2), extra={"event_family": "racing"})
        if event:
            found.append(event)
        if len(found) >= 25:
            break
    return found or parse_tables(html)


def parse_abc(html: str) -> List[Dict[str, Any]]:
    events = parse_next_data(html) or parse_initial_data(html) or walk_json_events(_embedded_objects(html))
    return events or parse_html(html)


WIDGET_RE = re.compile(
    r'class="widget-single-match[^"]*"(.*?)</a>',
    re.I | re.S,
)
HOME_RE = re.compile(r'class="match-home[^"]*"[^>]*>(.*?)</div>', re.I | re.S)
AWAY_RE = re.compile(r'class="match-away[^"]*"[^>]*>(.*?)</div>', re.I | re.S)
RESULT_RE = re.compile(r'class="match-result[^"]*"[^>]*>(.*?)</div>', re.I | re.S)
DATE_RE = re.compile(r'class="match-date[^"]*"[^>]*>\s*(\d{1,2}\.\d{1,2}\.20\d{2})', re.I)
SCORE_PAIR = re.compile(r"^\s*(\d{1,3})\s*[:\-]\s*(\d{1,3})\s*$")
FSS_FIXTURE = re.compile(
    r"([A-ZČĆŠŽĐ0-9][A-ZČĆŠŽĐa-zčćšžđ0-9 .]{1,40})\s+[-–]\s+"
    r"([A-ZČĆŠŽĐ0-9][A-ZČĆŠŽĐa-zčćšžđ0-9 .]{1,40})\s+"
    r"(\d{2}\.\d{2}\.20\d{2})(?:\s+(\d{1,2}:\d{2}))?"
)
SPORTNET_MATCH = re.compile(
    r'feqZwg">([^<]{3,80})</p>.*?'
    r'feqZwg">([^<]{3,80})</p>.*?'
    r'inmneS">(\d{1,2})</p>.*?'
    r'inmneS">(\d{1,2})</p>.*?'
    r'izDkez">(\d{1,2}\.\d{2}\.\s+\d{1,2}:\d{2})</p>',
    re.I | re.S,
)


def parse_superliga(html: str) -> List[Dict[str, Any]]:
    from collector.html_parse import _text

    events: List[Dict[str, Any]] = []
    blocks = WIDGET_RE.findall(html or "")
    sources = blocks if blocks else [html or ""]
    for block in sources:
        home_m = HOME_RE.search(block)
        away_m = AWAY_RE.search(block)
        if not home_m or not away_m:
            continue
        home = _text(home_m.group(1))
        away = _text(away_m.group(1))
        result_m = RESULT_RE.search(block)
        home_score = away_score = None
        status = "scheduled"
        if result_m:
            score_m = SCORE_PAIR.match(_text(result_m.group(1)))
            if score_m:
                home_score = int(score_m.group(1))
                away_score = int(score_m.group(2))
                status = "finished"
        date_m = DATE_RE.search(block)
        start = date_m.group(1) if date_m else None
        event = _event(
            home=home,
            away=away,
            start=start,
            status=status,
            home_score=home_score,
            away_score=away_score,
        )
        if event:
            events.append(event)
        if len(events) >= 80:
            break
    return events


def parse_fss(html: str) -> List[Dict[str, Any]]:
    from collector.html_parse import TAG_RE, WS_RE

    text = WS_RE.sub(" ", TAG_RE.sub(" ", html or ""))
    events: List[Dict[str, Any]] = []
    for match in FSS_FIXTURE.finditer(text):
        home, away, day, clock = match.group(1).strip(), match.group(2).strip(), match.group(3), match.group(4)
        lowered = f"{home} {away}".lower()
        if any(token in lowered for token in ("sudija", "delegat", "kontrolor", "var:", "pomoćni")):
            continue
        start = f"{day} {clock}" if clock else day
        event = _event(home=home, away=away, start=start)
        if event:
            events.append(event)
        if len(events) >= 80:
            break
    return events


def parse_sportnet(html: str) -> List[Dict[str, Any]]:
    year = "2026"
    title = re.search(r"\((20\d{2})\s*/\s*20\d{2}\)", html or "")
    if title:
        year = title.group(1)
    events: List[Dict[str, Any]] = []
    seen = set()
    for match in SPORTNET_MATCH.finditer(html or ""):
        home, away = match.group(1).strip(), match.group(2).strip()
        if "slovan" in f"{home} {away}".lower() and "liberec" in f"{home} {away}".lower():
            continue
        day_raw = match.group(5).strip()
        day_m = re.match(r"(\d{1,2})\.(\d{2})\.", day_raw)
        clock_m = re.search(r"(\d{1,2}:\d{2})", day_raw)
        start = None
        if day_m:
            start = f"{int(day_m.group(1)):02d}.{day_m.group(2)}.{year}"
            if clock_m:
                start = f"{start} {clock_m.group(1)}"
        key = (home.lower(), away.lower(), start)
        if key in seen:
            continue
        seen.add(key)
        event = _event(
            home=home,
            away=away,
            start=start,
            status="finished",
            home_score=int(match.group(3)),
            away_score=int(match.group(4)),
        )
        if event:
            events.append(event)
        if len(events) >= 80:
            break
    return events


def _embedded_objects(html: str) -> Any:
    blobs = []
    for match in re.finditer(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', html or "", re.I | re.S):
        blob = match.group(1).strip()
        if len(blob) < 40:
            continue
        try:
            blobs.append(json.loads(blob))
        except (TypeError, ValueError):
            continue
    if len(blobs) == 1:
        return blobs[0]
    return blobs
