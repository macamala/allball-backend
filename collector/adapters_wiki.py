"""Liquipedia MediaWiki parse API — mapped liquipedia family.

Uses the public gzip JSON API the wiki already exposes. Does not scrape
through 403 HTML if the API itself is the documented collection method.
"""

from __future__ import annotations

from typing import Dict, List

from urllib.parse import quote

from collector.adapters import FetchRequest, FetchResult
from collector.html_parse import parse_liquipedia_html
from collector.http import fetch_url

WIKI = {
    "tier1": "counterstrike",
    "professional": "dota2",
    "worlds-msi-regional": "leagueoflegends",
    "lol-world-championship": "leagueoflegends",
    "vct": "valorant",
    "cdl-majors": "callofduty",
    "owcs-historical": "overwatch",
    "owcs-world-finals": "overwatch",
    "rlcs": "rocketleague",
    "competitive-ea-fc": "easportsfc",
    "cross-game-wiki": "counterstrike",
}

PAGE = "Liquipedia:Matches"


class LiquipediaAdapter:
    adapter_key = "liquipedia"

    def __init__(self, source_id: str = "liquipedia", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        config = request.source_config or {}
        wiki = config.get("wiki") or WIKI.get(request.competition_id or "") or "counterstrike"
        page = config.get("page") or PAGE
        encoded = quote(str(page), safe="")
        url = config.get("url") or (
            f"https://liquipedia.net/{wiki}/api.php?action=parse&page={encoded}&prop=text&format=json&redirects=1"
        )
        result = self._get(url)
        if not result.ok:
            return result
        html = ""
        payload = result.payload
        if isinstance(payload, dict):
            html = ((payload.get("parse") or {}).get("text") or {}).get("*") or ""
        elif isinstance(payload, str):
            html = payload
        events = parse_liquipedia_html(html) if html else []
        if request.competition_id == "lol-world-championship":
            from collector.adapters_mass import parse_wiki_lol_worlds

            worlds = parse_wiki_lol_worlds(html)
            if worlds:
                events = worlds
        if request.competition_id == "owcs-world-finals":
            from collector.adapters_mass import parse_owcs_world_finals

            finals = parse_owcs_world_finals(html)
            if finals:
                events = finals
        return FetchResult(
            ok=True,
            http_status=result.http_status or 200,
            events=events,
            empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
        )
