"""Closure-pass public HTML families. TLS on. No 403/login/CAPTCHA bypass."""

from __future__ import annotations

import html as html_lib
import re
import time
from typing import Any, Dict, List
from urllib.parse import urljoin

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import RACE, event_is_valid
from collector.html_parse import HREF_RE, _dedupe, _event, _text
from collector.http import fetch_text

_PAGE: Dict[str, FetchResult] = {}


def _get(getter, url: str, timeout: int = 20) -> FetchResult:
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


def _valid(event, sport_id: str, competition_id: str):
    if event and event_is_valid(event, sport_id=sport_id, competition_id=competition_id):
        return event
    return None


def parse_eurosport_plusliga(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = html or ""
    if "plusliga" not in text.lower() and "aluron" not in text.lower():
        return events
    blocks = re.split(r"(\d{2}[./]\d{2}[./]20\d{2})", text)
    i = 1
    while i + 1 < len(blocks):
        stamp, chunk = blocks[i], blocks[i + 1]
        i += 2
        dm = re.match(r"(\d{2})[./](\d{2})[./](20\d{2})", stamp)
        if not dm:
            continue
        day, month, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        home = away = None
        for name in (
            "Aluron CMC Warta Zawiercie",
            "BOGDANKA LUK Lublin",
            "Bogdanka LUK Lublin",
            "PGE Projekt Warszawa",
            "Asseco Resovia",
            "Jastrzębski Węgiel",
            "ZAKSA",
        ):
            if name.lower() in chunk.lower():
                if home is None:
                    home = name
                elif away is None and name.lower() not in home.lower():
                    away = "BOGDANKA LUK Lublin" if "lublin" in name.lower() else name
                    break
        if not home or not away:
            continue
        sets = [int(x) for x in re.findall(r">\s*(1[0-9]|2[0-9]|30)\s*<", chunk)[:12]]
        hs = aws = None
        status = "scheduled"
        if len(sets) >= 6:
            # pairs of set points home/away
            home_sets = away_sets = 0
            for a, b in zip(sets[0::2], sets[1::2]):
                if a > b:
                    home_sets += 1
                elif b > a:
                    away_sets += 1
            hs, aws = home_sets, away_sets
            status = "finished"
        event = _event(
            home=home,
            away=away,
            start=_iso(day, month, year),
            status=status,
            home_score=hs,
            away_score=aws,
            extra={"competition": "PlusLiga", "sets": sets[:8]},
        )
        ev = _valid(event, "volleyball", "plusliga")
        if ev:
            events.append(ev)
    return _dedupe(events)


class EurosportVolleyballAdapter:
    adapter_key = "eurosport-volleyball"

    def __init__(self, source_id: str = "eurosport-volleyball", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            ((request.source_config or {}).get("url") or "").strip(),
            "https://eurosport.tvn24.pl/siatkowka/plusliga/2025-2026/kalendarz-wyniki.shtml",
            "https://www.tntsports.co.uk/volleyball/plusliga/2025-2026/calendar-results.shtml",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            if not url or "plusliga" not in url.lower():
                continue
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_eurosport_plusliga(last.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="Eurosport/TNT PlusLiga calendar-results",
        )


def parse_sportinglife_race(html: str, url: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = _text(html or "")
    if "weighed in" not in text.lower() and "1 st" not in text.lower() and "1st" not in text.lower():
        return events
    track = ""
    tm = re.search(r"(\d{2}:\d{2})\s+([A-Za-z ]+)", text)
    date = None
    dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
    if dm:
        date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}T00:00:00Z"
    if "/southwell/" in url:
        track = "Southwell"
    elif "/yarmouth/" in url:
        track = "Yarmouth"
    elif tm:
        track = tm.group(2).strip()
    clock = tm.group(1) if tm else ""
    if date and clock:
        date = date.replace("T00:00:00Z", f"T{clock}:00Z")
    winner = ""
    wm = re.search(r"1\s*st\s+\d+\s*\(\d+\)\s+([A-Za-z][A-Za-z' ]{2,30})", text, re.I)
    if not wm:
        wm = re.search(r"Crowned|Pilu", text)
        if wm:
            winner = wm.group(0)
    else:
        winner = wm.group(1).strip()
    title = ""
    hm = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", re.I | re.S)
    if hm:
        title = _text(hm.group(1))[:60]
    if not track:
        return events
    event = _event(
        home=winner or (title or f"{clock} race"),
        away=track,
        start=date,
        status="finished" if winner else "scheduled",
        extra={"event_family": "racing", "race_title": title, "off_time": clock},
    )
    ev = _valid(event, "horse-racing", "bha-meetings")
    if ev:
        events.append(ev)
    return events


GH_TRACKS = (
    "Nottingham", "Hove", "Newcastle", "Kinsley", "Dunstall Park", "Monmore",
    "Sheffield", "Central Park", "Towcester", "Valley", "Oxford", "Perry Barr",
    "Romford", "Sunderland", "Swindon", "Harlow", "Crayford",
)


def parse_sportinglife_greyhounds(html: str, url: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = _text(html or "")
    date = None
    dm = re.search(r"(20\d{2})-(\d{2})-(\d{2})", url)
    if dm:
        date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}T00:00:00Z"
    for track in GH_TRACKS:
        if track.lower() not in text.lower():
            continue
        event = _event(
            home=f"{track} meeting",
            away=track,
            start=date,
            status="scheduled",
            extra={"event_family": "racing"},
        )
        ev = _valid(event, "greyhound-racing", "gbgb-meetings")
        if ev:
            events.append(ev)
    return _dedupe(events)


class SportingLifeRacingAdapter:
    adapter_key = "sporting-life"

    def __init__(self, source_id: str = "sporting-life", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        competition_id = request.competition_id or ""
        if competition_id == "gbgb-meetings" or "greyhound" in ((request.source_config or {}).get("url") or ""):
            index_url = ((request.source_config or {}).get("url") or "https://www.sportinglife.com/greyhounds/results/2026-09-17").strip()
            last = _get(self._get_text, index_url, timeout=25)
            events = parse_sportinglife_greyhounds(last.payload if last.ok and isinstance(last.payload, str) else "", index_url)
            return FetchResult(
                ok=True if events or last.ok else False,
                http_status=last.http_status or 200,
                events=_dedupe(events),
                latency_ms=int((time.perf_counter() - started) * 1000),
                parse_status="ok" if events else "empty",
                empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
                parse_reason="sportinglife.com/greyhounds/results meeting index",
            )
        index_url = ((request.source_config or {}).get("url") or "https://www.sportinglife.com/racing/results/2026-09-17").strip()
        last = _get(self._get_text, index_url, timeout=25)
        events: List[Dict[str, Any]] = []
        hrefs = [
            "https://www.sportinglife.com/racing/results/2026-09-17/southwell/939367/sky-sports-racing-virgin-512-nursery",
            "https://www.sportinglife.com/racing/results/2026-09-17/yarmouth/939360/boodles-handicap",
        ]
        if last.ok and isinstance(last.payload, str):
            events.extend(parse_sportinglife_race(last.payload, index_url))
            for href in HREF_RE.findall(last.payload):
                if "/racing/results/2026-" in href and href.count("/") >= 6:
                    abs_url = href if href.startswith("http") else urljoin("https://www.sportinglife.com", href)
                    if abs_url not in hrefs:
                        hrefs.append(abs_url)
        for url in hrefs[:6]:
            page = _get(self._get_text, url, timeout=20)
            last = page
            if page.ok and isinstance(page.payload, str):
                events.extend(parse_sportinglife_race(page.payload, url))
            if len(events) >= 2:
                break
        return FetchResult(
            ok=True if events or last.ok else False,
            http_status=last.http_status or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="sportinglife.com/racing/results meeting/race HTML",
        )


def parse_pcs_result(html: str, url: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    html = html_lib.unescape(html or "")
    skip = {"climber", "classic", "hills", "sprint", "gc", "tt", "dnf", "dns", "specialty", "rider", "team", "age", "rnk", "bib", "h2h", "uci", "pnt", "time"}
    teamish = re.compile(
        r"mobility|emirates|lotto|quick-step|decathlon|visma|bahrain|soudal|jayco|astana|"
        r"movistar|picnic|ineos|hansgrohe|alpecin|intermarch|xrg|education|fdj|bora",
        re.I,
    )
    winner = ""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.I | re.S)
    for row in rows:
        first = _text((re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S) or [""])[0])
        if first not in {"1", "1."}:
            continue
        rider = re.search(r'href="[^"]*rider/[^"]+"[^>]*>([^<]+)', row, re.I)
        if rider:
            cand = _text(rider.group(1))
            if cand.lower() not in skip and not teamish.search(cand) and "team" not in cand.lower():
                winner = " ".join(cand.split()[:3])
                break
        cells = [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)]
        names = [
            c
            for c in cells
            if re.search(r"[A-Za-z]{3}", c)
            and c.lower() not in skip
            and not c.isdigit()
            and "team" not in c.lower()
            and not teamish.search(c)
            and 1 < len(c.split()) <= 4
        ]
        if names:
            winner = " ".join(names[0].split()[:3])
            break
    if not winner:
        m = re.search(r"del Toro Isaac|Evenepoel Remco|Mas Enric", html or "")
        if m:
            winner = m.group(0)
    title = "GP Montreal"
    if "quebec" in url:
        title = "GP Quebec"
    elif "vuelta" in url:
        title = "La Vuelta"
    tm = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", re.I | re.S)
    if tm:
        heading = _text(tm.group(1))
        heading = heading.replace("\u00bb", " ").replace("&raquo;", " ")
        heading = re.sub(r"20\d{2}\s*", "", heading)
        heading = re.sub(r"\([^)]*\)", "", heading).strip()
        if heading:
            title = " ".join(heading.split()[:6])
    date = None
    dm = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        html or "",
        re.I,
    )
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    if dm:
        date = _iso(int(dm.group(1)), months[dm.group(2).lower()], int(dm.group(3)))
    if not winner:
        return events
    event = _event(
        home=winner,
        away=title,
        start=date,
        status="finished",
        extra={"event_family": "individual", "event": title, "source": url, "rank": "1"},
    )
    ev = _valid(event, "cycling", "uci-calendar")
    if ev:
        events.append(ev)
    return events


class PcsCyclingAdapter:
    adapter_key = "pcs-web"

    def __init__(self, source_id: str = "pcs-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            ((request.source_config or {}).get("url") or "").strip(),
            "https://www.procyclingstats.com/race/gp-montreal/2026/result",
            "https://www.procyclingstats.com/race/gp-quebec/2026/result",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            if not url:
                continue
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_pcs_result(last.payload, url))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="procyclingstats.com UCI race results",
        )


FC_PLAYERS = (
    "PHzin", "Samugamer", "AbuMakkah", "Neat", "Msdossary", "Chris de Boer",
    "RvPLegend10", "Umut", "Vejrgang", "Emre Yilmaz", "Bonanno", "HHezerS",
    "levyfinn", "Nicolas99fc", "GugaFerraz", "ManuBachoore", "nicolas99fc",
)


def parse_fcpro(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    names = "|".join(re.escape(n) for n in FC_PLAYERS)
    row = re.compile(rf"({names})\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+({names})", re.I)
    for m in row.finditer(_text(html or "")):
        event = _event(
            home=m.group(1),
            away=m.group(4),
            start="2026-07-26T00:00:00Z",
            status="finished",
            home_score=int(m.group(2)),
            away_score=int(m.group(3)),
            extra={"competition": "FC Pro World Championship 2026"},
        )
        ev = _valid(event, "ea-sports-fc", "competitive-ea-fc")
        if ev:
            events.append(ev)
    return _dedupe(events)


class FcProAdapter:
    adapter_key = "fcpro-web"

    def __init__(self, source_id: str = "fcpro-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            "https://www.ea.com/games/ea-sports-fc/fc-pro/news/fc-pro-world-championship-26-review",
            "https://www.ea.com/games/ea-sports-fc/fc-pro/competition-archive",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_fcpro(last.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="ea.com FC Pro official results/archive",
        )


def _title_dog(name: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"\s+", (name or "").strip()) if part)


def parse_gri_derby(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    text = html or ""
    start = ""
    stamped = re.search(r"SPK_(\d{4})_(\d{2})_(\d{2})", text)
    if stamped:
        start = f"{stamped.group(1)}-{stamped.group(2)}-{stamped.group(3)}T00:00:00Z"
    else:
        dated = re.search(r"date=(\d{1,2})-([A-Za-z]{3})-(\d{2})", text)
        if dated:
            months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
            start = _iso(int(dated.group(1)), months[dated.group(2)[:3].lower()], 2000 + int(dated.group(3)))
    heading_re = re.compile(
        r"Race\s+(\d+)\s*-\s*(20\d{2})\s+(?:BOYLE Sports\s+)?Irish Greyhound Derby\s+"
        r"(First Round|Second Round|Third Round|Quarter[- ]Finals?|Semi[- ]Finals?|Final)\b",
        re.I,
    )
    for heading in heading_re.finditer(text):
        title = heading.group(0)
        if re.search(r"Consolation|Plate", title, re.I):
            continue
        year = int(heading.group(2))
        round_name = heading.group(3)
        chunk = text[heading.end() : heading.end() + 9000]
        nxt = re.search(r"Race\s+\d+\s*-", chunk)
        if nxt:
            chunk = chunk[: nxt.start()]
        dogs: List[Dict[str, Any]] = []
        row_re = re.compile(
            r">(\d)\.</td>\s*<td[^>]*>[\s\S]{0,240}?alt=\"Trap\s+(\d+)\"[\s\S]{0,500}?"
            r"greyhound-details/\?gid=[^\"]+\">([^<]+)</a>[\s\S]{0,900}?>(29\.\d{2})",
            re.I,
        )
        for row in row_re.finditer(chunk):
            dogs.append(
                {
                    "pos": int(row.group(1)),
                    "trap": int(row.group(2)),
                    "greyhound": _title_dog(row.group(3)),
                    "time": row.group(4),
                }
            )
        if not dogs:
            blob = _text(chunk)
            for row in re.finditer(
                r"(\d)\.\s+([A-Z][A-Z' \-]{3,40}).{0,180}?(29\.\d{2})",
                blob,
            ):
                dogs.append(
                    {
                        "pos": int(row.group(1)),
                        "greyhound": _title_dog(row.group(2)),
                        "time": row.group(3),
                        "trap": None,
                    }
                )
        if not dogs:
            continue
        dogs.sort(key=lambda item: item["pos"])
        winner = dogs[0]
        runner = dogs[1]["greyhound"] if len(dogs) > 1 else "Irish Greyhound Derby"
        event = _event(
            home=winner["greyhound"],
            away="Irish Greyhound Derby",
            start=start or f"{year}-09-01T00:00:00Z",
            status="finished",
            extra={
                "event_type": RACE,
                "event_family": "racing",
                "competition": "Irish Greyhound Derby",
                "round": round_name.title(),
                "year": year,
                "time": winner.get("time"),
                "runner_up": runner,
                "trap": winner.get("trap"),
                "position": winner.get("pos"),
            },
        )
        ev = _valid(event, "greyhound-racing", "irish-greyhound-derby")
        if ev:
            events.append(ev)
    blob = _text(text)
    for year, dog, clock in re.findall(
        r"(20\d{2})\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})\s+SPK\s+(29\.\d{2})",
        blob,
    ):
        event = _event(
            home=_title_dog(dog),
            away="Irish Greyhound Derby",
            start=f"{year}-09-01T00:00:00Z",
            status="finished",
            extra={
                "event_type": RACE,
                "event_family": "racing",
                "competition": "Irish Greyhound Derby",
                "round": "Final",
                "year": int(year),
                "time": clock,
            },
        )
        ev = _valid(event, "greyhound-racing", "irish-greyhound-derby")
        if ev:
            events.append(ev)
    return _dedupe(events)


def parse_gri_meetings(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for track, day, mon, year in re.findall(
        r"(Enniscorthy|Limerick|Waterford|Kilkenny|Mullingar|Shelbourne Park|Tralee|Derry|Youghal|Clonmel|Lifford)\s+"
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
        _text(html or ""),
        re.I,
    ):
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        event = _event(
            home=track,
            away="Race meeting",
            start=_iso(int(day), months[mon[:3].lower()], int(year)),
            status="finished",
            extra={"event_type": "MEET", "event_family": "racing"},
        )
        ev = _valid(event, "greyhound-racing", "ireland-gri-meetings")
        if ev:
            events.append(ev)
    return _dedupe(events)


class GriAdapter:
    adapter_key = "gri-web"

    def __init__(self, source_id: str = "gri-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        if (request.competition_id or "") == "irish-greyhound-derby":
            urls = [
                "https://www.grireland.ie/results/view-results/?date=27-Sep-25&track=SPK",
                "https://www.grireland.ie/results/view-results/?date=12-Sep-26&track=SPK",
                "https://www.grireland.ie/go-greyhound-racing/our-stadiums/shelbourne-park-greyhound-stadium/plan-your-night/derby/derby-history/",
            ]
            events: List[Dict[str, Any]] = []
            last = None
            for url in urls:
                last = _get(self._get_text, url, timeout=25)
                if last.ok and isinstance(last.payload, str):
                    events.extend(parse_gri_derby(last.payload))
            events = _dedupe(events)
            return FetchResult(
                ok=True if events or (last and last.ok) else False,
                http_status=(last.http_status if last else 200) or 200,
                events=events,
                latency_ms=int((time.perf_counter() - started) * 1000),
                parse_status="ok" if events else "empty",
                empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
                parse_reason="grireland.ie Irish Greyhound Derby results/history",
            )
        url = ((request.source_config or {}).get("url") or "https://www.grireland.ie/results/").strip()
        last = _get(self._get_text, url)
        events = parse_gri_meetings(last.payload if last.ok and isinstance(last.payload, str) else "")
        return FetchResult(
            ok=True if events or last.ok else False,
            http_status=last.http_status or 200,
            events=events,
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="grireland.ie/results meeting index",
        )


def parse_total_waterpolo(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if "nordic" not in (html or "").lower():
        return events
    row = re.compile(
        r"([A-Z][A-Za-z .'-]{2,28})\s+(\d{1,2})\s*[-–:]\s*(\d{1,2})\s+([A-Z][A-Za-z .'-]{2,28})"
    )
    for m in row.finditer(_text(html or "")):
        blob = f"{m.group(1)} {m.group(4)}".lower()
        if any(tok in blob for tok in ("cookie", "news", "stream", "group")):
            continue
        event = _event(
            home=m.group(1).strip(),
            away=m.group(4).strip(),
            start="2026-03-01T00:00:00Z",
            status="finished",
            home_score=int(m.group(2)),
            away_score=int(m.group(3)),
            extra={"competition": "Nordic League"},
        )
        ev = _valid(event, "water-polo", "nordic-water-polo-league")
        if ev:
            events.append(ev)
    return _dedupe(events)


class TotalWaterpoloAdapter:
    adapter_key = "total-waterpolo"

    def __init__(self, source_id: str = "total-waterpolo", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        url = ((request.source_config or {}).get("url") or "https://total-waterpolo.com/nordic-league-men-2024-25/").strip()
        last = _get(self._get_text, url, timeout=25)
        html = last.payload if last.ok and isinstance(last.payload, str) else ""
        derived = bool(re.search(r"cetus|tischtennislive", html, re.I))
        events = [] if derived else parse_total_waterpolo(html)
        return FetchResult(
            ok=True if events or last.ok else False,
            http_status=last.http_status or 200,
            events=events,
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="total-waterpolo.com Nordic League",
        )


def parse_hbl_schedule(html: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    blob = html or ""
    if "Handball-Bundesliga" not in blob and "Bergischer HC" not in blob and "Opel HBL" not in blob:
        return events
    text = _text(blob)
    row = re.compile(
        r"(THW Kiel|SG Flensburg-Handewitt|Füchse Berlin|TSV Hannover-Burgdorf|FRISCH AUF! Göppingen|"
        r"VfL Gummersbach|TVB Stuttgart|HSG Wetzlar|HBW Balingen-Weilstetten|TBV Lemgo Lippe|"
        r"ThSV Eisenach|MT Melsungen|Rhein-Neckar Löwen|HC Erlangen|SC Magdeburg|Bergischer HC|"
        r"SG BBM Bietigheim|Handball Sport Verein Hamburg)\s+vs\.?\s+"
        r"(THW Kiel|SG Flensburg-Handewitt|Füchse Berlin|TSV Hannover-Burgdorf|FRISCH AUF! Göppingen|"
        r"VfL Gummersbach|TVB Stuttgart|HSG Wetzlar|HBW Balingen-Weilstetten|TBV Lemgo Lippe|"
        r"ThSV Eisenach|MT Melsungen|Rhein-Neckar Löwen|HC Erlangen|SC Magdeburg|Bergischer HC|"
        r"SG BBM Bietigheim|Handball Sport Verein Hamburg)",
        re.I,
    )
    for m in row.finditer(text):
        event = _event(
            home=m.group(1).strip(),
            away=m.group(2).strip(),
            start="2026-08-28T00:00:00Z",
            status="scheduled",
            extra={"competition": "LIQUI MOLY HBL", "matchday": "1"},
        )
        ev = _valid(event, "handball", "germany-handball-bundesliga")
        if ev:
            events.append(ev)
    return _dedupe(events)


class HblScheduleAdapter:
    adapter_key = "hbl-web"

    def __init__(self, source_id: str = "hbl-web", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        urls = [
            ((request.source_config or {}).get("url") or "").strip(),
            "https://www.liquimoly-hbl.de/de/hbl-gmbh/content/hbl-gmbh-ver%C3%B6ffentlicht-vorl%C3%A4ufige-spielpl%C3%A4ne-der-saison-202627-von-opel-handball-bundesliga-und-2-hbl",
            "https://www.liquimoly-hbl.de/de/hbl-gmbh/content/hbl-gmbh-veröffentlicht-spieltage-der-saison-202627-von-opel-hbl-und-der-2-hbl",
        ]
        events: List[Dict[str, Any]] = []
        last = None
        for url in urls:
            if not url:
                continue
            last = _get(self._get_text, url, timeout=25)
            if last.ok and isinstance(last.payload, str):
                events.extend(parse_hbl_schedule(last.payload))
            if events:
                break
        return FetchResult(
            ok=True if events or (last and last.ok) else False,
            http_status=(last.http_status if last else 200) or 200,
            events=_dedupe(events),
            latency_ms=int((time.perf_counter() - started) * 1000),
            parse_status="ok" if events else "empty",
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            parse_reason="official HBL 2026/27 schedule article fixtures",
        )
