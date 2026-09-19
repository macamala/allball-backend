"""EliteProspects public league scores family.

Parses __NEXT_DATA__ games on eliteprospects.com/league/{slug}/scores/{season}.
Requires the page's league identity to match the mapped competition.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from collector.adapters import FetchRequest, FetchResult
from collector.event_quality import event_is_valid
from collector.html_parse import NEXT_RE, _dedupe, _event, _team_name
from collector.http import fetch_text

BASE = "https://www.eliteprospects.com"

LEAGUE_SLUGS: Dict[str, Dict[str, Any]] = {
    "finland-liiga": {"slug": "liiga", "names": ("liiga",), "seasons": ("2026-2027", "2025-2026")},
    "sweden-shl": {"slug": "shl", "names": ("shl",), "seasons": ("2026-2027", "2025-2026")},
    "germany-del": {"slug": "del", "names": ("del",), "seasons": ("2026-2027", "2025-2026")},
    "germany-del2": {"slug": "del2", "names": ("del2",), "seasons": ("2026-2027", "2025-2026")},
    "khl": {"slug": "khl", "names": ("khl",), "seasons": ("2026-2027", "2025-2026")},
    "champions-hockey-league": {
        "slug": "chl",
        "names": ("champions hockey league", "chl"),
        "seasons": ("2026-2027", "2025-2026"),
    },
}

_PAGE_CACHE: Dict[str, FetchResult] = {}


def _league_blob(row: Dict[str, Any]) -> str:
    league = row.get("league") or row.get("League") or {}
    if isinstance(league, dict):
        return " ".join(str(league.get(key) or "") for key in ("name", "slug", "id", "displayName")).lower()
    return str(league or "").lower()


def _league_matches(row: Dict[str, Any], names: Tuple[str, ...], slug: str) -> bool:
    blob = _league_blob(row)
    if slug and slug.lower() in blob:
        return True
    return any(name.lower() in blob for name in names)


def parse_eliteprospects_games(html: str, *, slug: str, names: Tuple[str, ...], season: str = "") -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    match = NEXT_RE.search(html or "")
    payload: Any = None
    if match:
        try:
            payload = json.loads(match.group(1))
        except (TypeError, ValueError):
            payload = None
    games: List[Dict[str, Any]] = []

    def collect(node: Any, depth: int = 0) -> None:
        if depth > 12 or node is None:
            return
        if isinstance(node, list):
            for item in node[:400]:
                collect(item, depth + 1)
            return
        if not isinstance(node, dict):
            return
        if node.get("homeTeam") and (node.get("awayTeam") or node.get("visitingTeam")):
            games.append(node)
        for value in node.values():
            collect(value, depth + 1)

    if payload is not None:
        collect(payload)
    for row in games:
        if not _league_matches(row, names, slug):
            continue
        home = _team_name(row.get("homeTeam") or row.get("home"))
        away = _team_name(row.get("awayTeam") or row.get("visitingTeam") or row.get("away"))
        home_score = row.get("homeTeamScore")
        away_score = row.get("awayTeamScore") if row.get("awayTeamScore") is not None else row.get("visitingTeamScore")
        if home_score is None and isinstance(row.get("homeTeam"), dict):
            home_score = row["homeTeam"].get("score")
        if away_score is None and isinstance(row.get("awayTeam") or row.get("visitingTeam"), dict):
            away_score = (row.get("awayTeam") or row.get("visitingTeam") or {}).get("score")
        status = "finished" if home_score not in (None, "") and away_score not in (None, "") else "scheduled"
        extra: Dict[str, Any] = {"competition": slug, "season": row.get("season") or season}
        score_type = str(row.get("scoreType") or row.get("gameType") or "").upper()
        if row.get("overtime") or row.get("ot") or score_type in {"OT", "SO"}:
            extra["ot"] = True
            extra["score_type"] = score_type or "OT"
        venue = row.get("arena") or row.get("venue")
        game_venue = row.get("gameVenue")
        if isinstance(game_venue, dict):
            venue = venue or game_venue.get("name")
        elif game_venue:
            venue = venue or game_venue
        event = _event(
            home=home,
            away=away,
            start=row.get("dateTime") or row.get("date") or row.get("startDate") or row.get("gameDate") or row.get("datetime"),
            status=status,
            home_score=home_score,
            away_score=away_score,
            venue=venue,
            source_id=str(row.get("id") or row.get("gameId") or f"{home}-{away}"),
            extra=extra,
        )
        if event and event_is_valid(event, sport_id="ice-hockey"):
            events.append(event)
    if not events:
        return events
    return _dedupe(events)


class EliteProspectsAdapter:
    adapter_key = "eliteprospects"

    def __init__(self, source_id: str = "eliteprospects", text_getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def _get(self, url: str, timeout: int = 25) -> FetchResult:
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
        spec = LEAGUE_SLUGS.get(competition_id) or {}
        slug = spec.get("slug") or ""
        names = tuple(spec.get("names") or (slug,))
        seasons = list(spec.get("seasons") or ("2026-2027", "2025-2026"))
        events: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        urls = []
        if slug:
            urls.append(urljoin(BASE, f"/league/{slug}"))
            for season in seasons:
                urls.append(urljoin(BASE, f"/league/{slug}/scores/{season}"))
        configured = ((request.source_config or {}).get("url") or "").strip()
        if configured:
            urls.insert(0, configured)
        for url in urls:
            last = self._get(url)
            if not last.ok or not isinstance(last.payload, str):
                continue
            events.extend(parse_eliteprospects_games(last.payload, slug=slug, names=names, season=url.rsplit("/", 1)[-1]))
            if events:
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
            parse_reason=f"eliteprospects {slug}",
        )
