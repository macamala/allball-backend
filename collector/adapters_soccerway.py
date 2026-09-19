"""One Soccerway public-HTML family for football competitions.

Parses the match feed already embedded in www.soccerway.com competition
pages (results/fixtures/archive). Country subdomains are the same family.
Does not call private APIs, logins, or anti-bot bypasses.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import HREF_RE, _dedupe, _event, datetime_from_unix
from collector.http import fetch_text

BASE = "https://www.soccerway.com"
KV = "\u00f7"
SEP = "\u00ac"
FEED_RE = re.compile(r"data:\s*`([^`]{80,})`")
ARCHIVE_RE = re.compile(r"var league_archive_data\s*=\s*(\{.*?\});", re.S)

# One path map for the family. Not one adapter per league.
COMPETITION_PATHS: Dict[str, str] = {
    "afc-champions-league": "/asia/afc-champions-league/",
    "australia-a-league-women": "/australia/a-league-women/",
    "caf-champions-league": "/africa/caf-champions-league/",
    "copa-sudamericana": "/south-america/copa-sudamericana/",
    "serbia-superliga": "/serbia/mozzart-bet-super-liga/",
    "slovakia-super-liga": "/slovakia/nike-liga/",
    "thai-league-1": "/thailand/thai-league-1/",
    "uzbekistan-super-league": "/uzbekistan/super-league/",
    "malaysia-super-league": "/malaysia/super-league/",
    "india-super-league": "/india/indian-super-league/",
}

PATH_ALIASES: Dict[str, List[str]] = {
    "serbia-superliga": [
        "/serbia/mozzart-bet-super-liga/",
        "/serbia/super-liga/",
        "/serbia/super-liga-srbije/",
        "/national/serbia/super-liga/",
    ],
}

COUNTRY_INDEX: Dict[str, str] = {
    "serbia-superliga": "/serbia/",
    "malaysia-super-league": "/malaysia/",
}

COMPETITION_TOKENS: Dict[str, Tuple[str, ...]] = {
    "afc-champions-league": ("afc-champions-league",),
    "australia-a-league-women": ("a-league-women",),
    "caf-champions-league": ("caf-champions-league",),
    "copa-sudamericana": ("copa-sudamericana",),
    "serbia-superliga": ("super-liga", "superliga"),
    "slovakia-super-liga": ("nike-liga",),
    "thai-league-1": ("thai-league-1",),
    "uzbekistan-super-league": ("super-league",),
    "malaysia-super-league": ("super-league",),
    "india-super-league": ("indian-super-league", "super-league"),
}

_PAGE_CACHE: Dict[str, FetchResult] = {}


def _league_matches(league_name: str, league_path: str, competition_id: str, path_hint: str) -> bool:
    name = (league_name or "").lower()
    path = (league_path or "").lower()
    hint = (path_hint or COMPETITION_PATHS.get(competition_id) or "").lower().rstrip("/")
    if hint and hint in path:
        return True
    tokens = COMPETITION_TOKENS.get(competition_id) or ()
    if any(token in path for token in tokens):
        return True
    slug_bits = [part for part in (competition_id or "").split("-") if part not in {"world", "usa"}]
    significant = [bit for bit in slug_bits if len(bit) > 3]
    if significant and all(bit in f"{name} {path}" for bit in significant[-2:]):
        return True
    return False


def parse_soccerway_html(
    html: str,
    *,
    competition_id: str = "",
    path_hint: str = "",
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for blob in FEED_RE.findall(html or ""):
        if f"AA{KV}" not in blob:
            continue
        league_name = ""
        league_path = ""
        for rec in blob.split(SEP + "~"):
            fields: Dict[str, str] = {}
            for part in rec.split(SEP):
                if KV not in part:
                    continue
                key, value = part.split(KV, 1)
                fields[key] = value
            if "ZA" in fields:
                league_name = fields.get("ZA") or ""
                league_path = fields.get("ZL") or league_path
                continue
            if "AA" not in fields:
                continue
            if competition_id and not _league_matches(league_name, league_path, competition_id, path_hint):
                continue
            home = (fields.get("AE") or fields.get("FH") or "").strip()
            away = (fields.get("AF") or fields.get("FK") or "").strip()
            if not home or not away:
                continue
            start = datetime_from_unix(fields.get("AD") or fields.get("ADE"))
            home_score = fields.get("AG")
            away_score = fields.get("AH")
            try:
                home_score = int(home_score) if home_score not in (None, "") else None
                away_score = int(away_score) if away_score not in (None, "") else None
            except ValueError:
                home_score = away_score = None
            code = fields.get("AC") or ""
            status = "scheduled"
            if code == "2":
                status = "live"
            elif code == "3":
                status = "finished"
            elif home_score is not None and away_score is not None:
                status = "finished"
            event = _event(
                home=home,
                away=away,
                start=start,
                status=status,
                home_score=home_score,
                away_score=away_score,
                source_id=fields.get("AA") or f"{home}-{away}-{start}",
                extra={"competition": league_name or competition_id, "soccerway_path": league_path},
            )
            if event and event_is_valid(event, sport_id="football", competition_id=competition_id):
                events.append(event)
    return _dedupe(events)[:80]


def archive_season_paths(html: str) -> List[str]:
    match = ARCHIVE_RE.search(html or "")
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return []
    out = []
    for row in payload.get("seasons") or []:
        url = (row or {}).get("url") or ""
        if url.startswith("/") and url.count("/") >= 3:
            out.append(url)
    return out[:4]


def discover_competition_path(html: str, competition_id: str) -> Optional[str]:
    tokens = COMPETITION_TOKENS.get(competition_id) or ()
    if not tokens:
        return None
    for href in HREF_RE.findall(html or ""):
        path = urlparse(href).path.lower()
        if "soccerway.com" in href.lower() or href.startswith("/"):
            if any(token in path for token in tokens) and path.count("/") >= 3:
                if any(skip in path for skip in ("/match/", "/team/", "/player/", "/live/")):
                    continue
                return path if path.endswith("/") else path + "/"
    return None


def _page_urls(path: str) -> List[str]:
    base = BASE + path
    if not base.endswith("/"):
        base += "/"
    return [base, base + "results/", base + "fixtures/"]


class SoccerwayAdapter:
    adapter_key = "soccerway-html"

    def __init__(self, source_id: str = "soccerway", text_getter=None):
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
        config = request.source_config or {}
        configured = (config.get("url") or "").strip()
        path = COMPETITION_PATHS.get(competition_id, "")
        if configured and "soccerway.com" in configured:
            parsed = urlparse(configured).path or path
            path = parsed if parsed.endswith("/") else parsed + "/"
        aliases = [path] if path else []
        for extra in PATH_ALIASES.get(competition_id) or []:
            if extra not in aliases:
                aliases.append(extra)
        events: List[Dict[str, Any]] = []
        last = None
        used_path = path
        tried = set()
        for alias in aliases:
            for url in _page_urls(alias):
                if url in tried:
                    continue
                tried.add(url)
                last = self._get(url)
                if not last.ok or not isinstance(last.payload, str):
                    continue
                used_path = alias
                parsed = parse_soccerway_html(
                    last.payload, competition_id=competition_id, path_hint=alias
                )
                events.extend(parsed)
                if not parsed:
                    continue
                for season_path in archive_season_paths(last.payload)[:2]:
                    season_url = urljoin(BASE, season_path.rstrip("/") + "/results/")
                    if season_url in tried:
                        continue
                    tried.add(season_url)
                    extra = self._get(season_url)
                    if extra.ok and isinstance(extra.payload, str):
                        events.extend(
                            parse_soccerway_html(
                                extra.payload,
                                competition_id=competition_id,
                                path_hint=season_path,
                            )
                        )
                if events:
                    break
            if events:
                break
        if not events:
            index = COUNTRY_INDEX.get(competition_id)
            if index:
                last = self._get(BASE + index)
                if last.ok and isinstance(last.payload, str):
                    found = discover_competition_path(last.payload, competition_id)
                    if found and found not in aliases:
                        last = self._get(urljoin(BASE, found.rstrip("/") + "/results/"))
                        if last.ok and isinstance(last.payload, str):
                            events = parse_soccerway_html(
                                last.payload, competition_id=competition_id, path_hint=found
                            )
                            used_path = found
        events = _dedupe(events)
        latency = int((time.perf_counter() - started) * 1000)
        if last is not None and not last.ok and not events:
            last.latency_ms = latency
            return last
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(
            ok=True,
            http_status=(last.http_status if last is not None else 200) or 200,
            events=events,
            latency_ms=latency,
            parse_status="ok" if events else "empty",
            empty_reason=empty_reason,
            parse_reason=f"soccerway {used_path}",
        )
