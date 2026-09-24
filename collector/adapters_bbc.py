"""BBC Sport family parser.

Uses the public window.__INITIAL_DATA__ payload already present on BBC Sport
pages, plus same-host scores-fixtures links. Does not call GraphQL, logins,
or anti-bot bypasses.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.html_parse import _dict_event, _quoted_window_json, fixture_urls, parse_html
from collector.http import fetch_text

SPORT_PATH = {
    "football": "football",
    "tennis": "tennis",
    "cricket": "cricket",
    "rugby": "rugby-union",
    "rugby-league": "rugby-league",
    "netball": "netball",
    "boxing": "boxing",
    "snooker": "snooker",
    "athletics": "athletics",
    "horse-racing": "horse-racing",
    "swimming": "swimming",
    "winter-sports": "winter-sports",
}

COMPETITION_PATH = {
    "turkey-super-lig": "/sport/football/turkish-super-lig/scores-fixtures",
    "ukraine-premier-league": "/sport/football/ukrainian-premier-league/scores-fixtures",
    "uefa-nations-league": "/sport/football/nations-league/scores-fixtures",
    "spain-copa-del-rey": "/sport/football/copa-del-rey/scores-fixtures",
    "biathlon": "/sport/winter-sports",
    "chile-primera": "/sport/football/chilean-primera-division/scores-fixtures",
    "argentina-primera": "/sport/football/argentine-primera-division/scores-fixtures",
    "denmark-superliga": "/sport/football/danish-superliga/scores-fixtures",
    "sweden-allsvenskan": "/sport/football/swedish-allsvenskan/scores-fixtures",
    "mexico-liga-mx": "/sport/football/mexican-liga-mx/scores-fixtures",
    "australia-a-league": "/sport/football/australian-a-league/scores-fixtures",
    "australia-a-league-women": "/sport/football/womens-a-league/scores-fixtures",
    "usa-nwsl": "/sport/football/us-nwsl/scores-fixtures",
    "afc-champions-league": "/sport/football/afc-champions-league/scores-fixtures",
    "caf-champions-league": "/sport/football/caf-champions-league/scores-fixtures",
    "copa-libertadores": "/sport/football/copa-libertadores/scores-fixtures",
    "copa-sudamericana": "/sport/football/copa-sudamericana/scores-fixtures",
    "india-super-league": "/sport/football/indian-super-league/scores-fixtures",
    "czech-first-league": "/sport/football/czech-first-league/scores-fixtures",
    "france-top-14": "/sport/rugby-union/top-14/scores-fixtures",
    "france-pro-d2": "/sport/rugby-union/pro-d2/scores-fixtures",
    "super-rugby": "/sport/rugby-union/super-rugby/scores-fixtures",
    "super-league": "/sport/rugby-league/super-league/scores-fixtures",
    "nrl": "/sport/rugby-league/nrl/scores-fixtures",
    "atp-tour": "/sport/tennis/scores-and-schedule",
    "wta-tour": "/sport/tennis/scores-and-schedule",
    "bha-meetings": "/sport/horse-racing/results",
    "gbgb-meetings": "/sport/horse-racing",
    "wst-events": "/sport/snooker",
    "world-netball": "/sport/netball",
    "ssn-australia": "/sport/netball",
    "fis-disciplines": "/sport/winter-sports",
    "uci-calendar": "/sport/cycling",
    "wa-calendar": "/sport/athletics/diamond-league-paris/results",
    "all-england-open": "/sport/badminton/live/cwy8nzqwkn9t",
    "tour-de-france": "/sport/cycling",
    "formula-2": "/sport/formula1",
    "formula-3": "/sport/formula1",
}


from collector.competition_identity import label_matches_competition


def _label_matches(label: str, competition_id: str) -> bool:
    return label_matches_competition(label, competition_id)


def extract_bbc_events(payload: Any, competition_id: str = "") -> List[Dict[str, Any]]:
    matched: List[Dict[str, Any]] = []
    grouped = False

    def walk(node: Any) -> None:
        nonlocal grouped
        if isinstance(node, dict):
            groups = node.get("eventGroups")
            if isinstance(groups, list):
                grouped = True
                for group in groups:
                    group_label = (group or {}).get("displayLabel") or ""
                    secondaries = (group or {}).get("secondaryGroups") or [group]
                    for secondary in secondaries:
                        for raw in (secondary or {}).get("events") or []:
                            event = _dict_event(raw)
                            if not event:
                                continue
                            event["competition"] = group_label
                            event["source_competition_name"] = group_label
                            event["source_family"] = "bbc-sport"
                            if not competition_id or _label_matches(group_label, competition_id):
                                matched.append(event)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return matched if grouped else []


class BbcSportAdapter:
    adapter_key = "bbc-sport"

    def __init__(self, source_id: str = "bbc-sport", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        url = ((request.source_config or {}).get("url") or "").strip()
        if not url:
            path = COMPETITION_PATH.get(request.competition_id or "")
            url = "https://www.bbc.com" + (path or "/sport")
        result = self._get(url)
        if not result.ok and ("getaddrinfo" in (result.error or "") or "Name or service" in (result.error or "") or "timed out" in (result.error or "").lower()):
            alt = url.replace("://www.bbc.com", "://www.bbc.co.uk").replace("://bbc.com", "://www.bbc.co.uk")
            if alt != url:
                result = self._get(alt)
                url = alt
        latency = int((time.perf_counter() - started) * 1000)
        if not result.ok:
            result.latency_ms = latency
            return result
        html = result.payload if isinstance(result.payload, str) else ""
        events = self._events_from_html(html, request.competition_id or "")
        if not events:
            for extra in self._follow_urls(html, url, request.sport_id, request.competition_id)[:8]:
                extra_result = self._get(extra, timeout=8)
                if not extra_result.ok or not isinstance(extra_result.payload, str):
                    continue
                events = self._events_from_html(extra_result.payload, request.competition_id or "")
                if events:
                    break
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(
            ok=True,
            http_status=result.http_status or 200,
            events=events[:80],
            latency_ms=latency,
            parse_status="ok",
            empty_reason=empty_reason,
        )

    def _events_from_html(self, html: str, competition_id: str) -> List[Dict[str, Any]]:
        data = _quoted_window_json(html, "__INITIAL_DATA__")
        if data is not None:
            extracted = extract_bbc_events(data, competition_id)
            if extracted:
                return extracted
        if competition_id == "wa-calendar":
            from collector.adapters_mass import parse_diamond_league_pdf

            meets = parse_diamond_league_pdf(html)
            if meets:
                return meets
        if competition_id == "all-england-open":
            from collector.adapters_mass import parse_bbc_all_england

            matches = parse_bbc_all_england(html)
            if matches:
                return matches
        if data is not None:
            return []
        # Unfiltered HTML tables inherit the mapping competition. Skip.
        return []

    def _get(self, url: str, timeout: Optional[int] = None) -> FetchResult:
        try:
            if timeout is not None:
                return self._get_text(url, timeout=timeout)
            return self._get_text(url)
        except TypeError:
            return self._get_text(url)

    def _follow_urls(self, html: str, base: str, sport_id: Optional[str], competition_id: Optional[str] = None) -> List[str]:
        parsed = urlparse(base)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        found = []
        path = COMPETITION_PATH.get(competition_id or "")
        if path:
            found.append(urljoin(origin, path))
            today = datetime.utcnow().date()
            # Prefer future dated boards first. Live-score breadth is most
            # valuable for today/tomorrow; older pages remain as fallback.
            for offset in (1, 2, 3, 0, -1, -2, -3, 7, 14):
                day = (today + timedelta(days=offset)).isoformat()
                found.append(urljoin(origin, path.rstrip("/") + "/" + day))
        for href in fixture_urls(html, base):
            if "scores-fixtures" in href or "/results" in href or "/fixtures" in href:
                found.append(href)
        slug = SPORT_PATH.get(sport_id or "")
        if slug:
            suffix = "scores-and-schedule" if slug == "tennis" else "scores-fixtures"
            found.append(urljoin(origin, f"/sport/{slug}/{suffix}"))
        return list(dict.fromkeys(found))
