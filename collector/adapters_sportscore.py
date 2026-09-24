"""SportScore public widget family.

Developer docs: https://sportscore.com/developers/
No API key. Attribution "Powered by SportScore" with dofollow to
https://sportscore.com/ is required wherever this data is displayed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

ATTRIBUTION = {
    "required": True,
    "text": "Powered by SportScore",
    "url": "https://sportscore.com/",
    "rel": "dofollow",
    "html": '<a href="https://sportscore.com/" rel="dofollow">Powered by SportScore</a>',
}

MATCHES_URL = "https://sportscore.com/api/widget/matches/?sport={sport}&limit={limit}&src=ninkosports"
STANDINGS_URL = "https://sportscore.com/api/widget/standings/?sport={sport}&slug={slug}&src=ninkosports"
TEAM_URL = "https://sportscore.com/api/widget/team/?sport={sport}&slug={slug}&limit=30&src=ninkosports"

# SportScore edge responses are cached for ~60s. Keep our own cache bounded as
# well: match boards stay fresh, while standings/team schedules are refreshed
# slowly enough to remain well inside the public fair-use budget.
_MATCH_TTL_S = 90
_STANDINGS_TTL_S = 6 * 3600
_TEAM_TTL_S = 4 * 3600
_MATCH_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_STANDINGS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_TEAM_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _cached(cache: Dict[str, Tuple[float, Any]], key: str, ttl: int) -> Any:
    hit = cache.get(key)
    if not hit:
        return None
    at, value = hit
    if time.monotonic() - at >= ttl:
        cache.pop(key, None)
        return None
    return value


def _store(cache: Dict[str, Tuple[float, Any]], key: str, value: Any) -> Any:
    cache[key] = (time.monotonic(), value)
    return value


def _match_slug(row: Dict[str, Any]) -> str:
    direct = str(row.get("slug") or row.get("match_slug") or "").strip()
    if direct:
        return direct.strip("/")
    raw = str(row.get("url") or "").strip()
    if raw:
        path = urlparse(raw).path.rstrip("/")
        if path:
            return path.rsplit("/", 1)[-1]
    return ""


def _dedupe_matches(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        slug = _match_slug(row)
        key = slug or str(row.get("id") or row.get("match_id") or row.get("url") or "")
        if not key:
            key = "|".join(
                str(row.get(name) or "")
                for name in ("home", "away", "time", "competition")
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out

# sport, name tokens (all must match unless any=True), optional standings slugs.
SPORTSCORE_COMPETITIONS: Dict[str, Dict[str, Any]] = {
    "usa-usl-championship": {
        "sport": "football",
        "tokens": ["usl championship"],
        "slugs": ["usl-championship"],
    },
    "usa-nwsl": {
        "sport": "football",
        "tokens_any": ["women's national soccer league", "nwsl"],
        "slugs": ["united-states-womens-national-soccer-league", "nwsl"],
    },
    "mls": {
        "sport": "football",
        "tokens_any": ["major league soccer", "united states major league soccer"],
        "deny": ["usl"],
        "slugs": ["mls", "major-league-soccer"],
    },
    "copa-libertadores": {
        "sport": "football",
        "tokens": ["copa libertadores"],
        "slugs": ["copa-libertadores"],
    },
    "copa-sudamericana": {
        "sport": "football",
        "tokens": ["sudamericana"],
        "slugs": ["copa-sudamericana"],
    },
    "argentina-primera": {
        "sport": "football",
        "tokens_any": ["argentine primera", "argentine division", "liga profesional", "primera division argentina"],
        "slugs": ["argentine-primera-division", "liga-profesional"],
    },
    "afc-champions-league": {
        "sport": "football",
        "tokens": ["afc champion"],
        "slugs": ["afc-champions-league"],
    },
    "caf-champions-league": {
        "sport": "football",
        "tokens": ["caf champion"],
        "slugs": ["caf-champions-league"],
    },
    "australia-a-league": {
        "sport": "football",
        "tokens_any": ["a-league men", "a league men", "australian a-league"],
        "deny": ["women"],
        "slugs": ["a-league", "australia-a-league"],
    },
    "australia-a-league-women": {
        "sport": "football",
        "tokens_any": ["a-league women", "a league women", "womens a-league"],
        "slugs": ["a-league-women"],
    },
    "mexico-liga-mx": {
        "sport": "football",
        "tokens_any": ["liga mx", "mexican primera", "mexico liga mx"],
        "slugs": ["liga-mx"],
    },
    "brazil-serie-a": {
        "sport": "football",
        "tokens_any": ["brazilian serie a", "brazil serie a", "brasileirao"],
        "deny": ["serie b", "serie c"],
        "slugs": ["brazilian-serie-a"],
    },
    "denmark-superliga": {
        "sport": "football",
        "tokens_any": ["danish superliga", "denmark superliga"],
        "slugs": ["danish-superliga", "superliga"],
    },
    "sweden-allsvenskan": {
        "sport": "football",
        "tokens": ["allsvenskan"],
        "slugs": ["allsvenskan"],
    },
    "czech-first-league": {
        "sport": "football",
        "tokens_any": ["czech first", "fortuna liga", "chance liga"],
        "slugs": ["czech-first-league", "fortuna-liga"],
    },
    "india-super-league": {
        "sport": "football",
        "tokens_any": ["indian super league", "india super league"],
        "slugs": ["indian-super-league"],
    },
    "thai-league-1": {
        "sport": "football",
        "tokens_any": ["thai league", "thailand premier"],
        "slugs": ["thai-league", "thai-league-1"],
    },
    "malaysia-super-league": {
        "sport": "football",
        "tokens": ["malaysia"],
        "slugs": ["malaysia-super-league"],
    },
    "serbia-superliga": {
        "sport": "football",
        "tokens_any": ["serbian super", "serbia superliga", "mozzart bet"],
        "slugs": ["serbian-superliga", "superliga-serbia"],
    },
    "slovakia-super-liga": {
        "sport": "football",
        "tokens_any": ["slovak", "nike liga"],
        "slugs": ["slovak-super-liga", "nike-liga"],
    },
    "uzbekistan-super-league": {
        "sport": "football",
        "tokens": ["uzbekistan"],
        "slugs": ["uzbekistan-super-league"],
    },
    "concacaf-champions-cup": {
        "sport": "football",
        "tokens_any": ["concacaf champions cup", "concacaf champions league"],
        "slugs": ["concacaf-champions-cup"],
    },
    "iran-pro-league": {
        "sport": "football",
        "tokens": ["iran pro"],
        "slugs": ["iran-pro-league"],
    },
    "ireland-premier-division": {
        "sport": "football",
        "tokens": ["ireland premier"],
        "slugs": ["ireland-premier-division"],
    },
    "kazakhstan-premier-league": {
        "sport": "football",
        "tokens": ["kazakhstan"],
        "slugs": ["kazakhstan-premier-league"],
    },
    "spain-la-liga": {
        "sport": "football",
        "tokens_any": ["spanish la liga", "la liga"],
        "deny": ["liga 2", "segunda", "hypermotion"],
        "slugs": ["spanish-la-liga"],
    },
    "switzerland-super-league": {
        "sport": "football",
        "tokens": ["switzerland super"],
        "slugs": ["switzerland-super-league"],
    },
    "scotland-premiership": {
        "sport": "football",
        "tokens_any": ["scottish premiership", "scotland premiership"],
        "slugs": ["scottish-premiership"],
    },
    "austria-bundesliga": {
        "sport": "football",
        "tokens_any": ["austrian bundesliga", "austria bundesliga"],
        "slugs": ["austrian-bundesliga"],
    },
    "spain-acb": {
        "sport": "basketball",
        "tokens_any": ["acb", "liga endesa"],
        "slugs": ["acb", "liga-endesa"],
    },
    "nba": {
        "sport": "basketball",
        "tokens_any": ["national basketball association", "nba"],
        "deny": ["wnba", "g league", "nbl"],
        "slugs": ["nba"],
    },
    "mexico-lnbp": {
        "sport": "basketball",
        "tokens_any": ["lnbp", "liga nacional de baloncesto profesional"],
        "slugs": ["lnbp"],
    },
    "wnba": {
        "sport": "basketball",
        "tokens_any": ["women's national basketball association", "wnba"],
        "slugs": ["wnba"],
    },
    "internationals-and-leagues": {
        "sport": "cricket",
        "tokens_any": ["odi series", "test series", "t20i ", "t20 international", "one-day international"],
        "deny": ["t10", "minor league", "premier league, women"],
        "slugs": [],
    },
    "t20-internationals": {
        "sport": "cricket",
        "tokens_any": ["t20i", "t20 international", "twenty20 international"],
        "deny": ["asian games", "premier league", "t10"],
        "slugs": [],
    },
    "wta-tour": {
        "sport": "tennis",
        "tokens": ["wta "],
        "deny": ["utr "],
        "slugs": [],
    },
    "atp-tour": {
        "sport": "tennis",
        "tokens": ["atp "],
        "deny": ["utr "],
        "slugs": [],
    },
}


def match_competition(name: str, spec: Dict[str, Any]) -> bool:
    blob = (name or "").lower()
    if not blob:
        return False
    for token in spec.get("deny") or []:
        if token.lower() in blob:
            return False
    any_tokens = spec.get("tokens_any") or []
    if any_tokens:
        return any(token.lower() in blob for token in any_tokens)
    tokens = spec.get("tokens") or []
    return all(token.lower() in blob for token in tokens) if tokens else False


def _score(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(str(value).split(".")[0])
    except (TypeError, ValueError):
        return None


def _status(row: Dict[str, Any]) -> str:
    blob = f"{row.get('status') or ''} {row.get('status_text') or ''}".lower()
    if any(token in blob for token in ("finished", "ended", "final", "ft", "aet")):
        return "finished"
    if any(token in blob for token in ("live", "in progress", "inprogress", "halftime", "ht", "1st half", "2nd half")):
        return "live"
    return "scheduled"


def match_to_event(row: Dict[str, Any], competition_id: str) -> Optional[Dict[str, Any]]:
    home = (row.get("home") or "").strip()
    away = (row.get("away") or "").strip()
    if not home or not away:
        return None
    status = _status(row)
    home_score = _score(row.get("home_score"))
    away_score = _score(row.get("away_score"))
    if status == "scheduled":
        home_score = None if home_score == 0 else home_score
        away_score = None if away_score == 0 else away_score
    score: Dict[str, Any] = {"home": home_score, "away": away_score}
    minute = row.get("minute") or row.get("clock")
    period = row.get("period") or row.get("quarter") or row.get("set")
    status_text = str(row.get("status_text") or "")
    if period in (None, "") and status_text:
        lowered = status_text.lower()
        if "2nd" in lowered or "2h" in lowered:
            period = 2
        elif "1st" in lowered or "1h" in lowered:
            period = 1
        elif "ht" in lowered or "half" in lowered:
            period = "HT"
        minute = minute or status_text
    if minute not in (None, ""):
        score["minute"] = minute
    if period not in (None, ""):
        score["period"] = period
    slug = _match_slug(row)
    source_event_id = slug or str(row.get("id") or row.get("match_id") or "")
    event = {
        "id": row.get("url") or (f"sportscore:{source_event_id}" if source_event_id else f"sportscore:{competition_id}:{home}:{away}:{row.get('time')}"),
        "home": {
            "id": str(row.get("home_id") or row.get("home_team_id") or ""),
            "name": home,
            "logo": row.get("home_logo") or row.get("home_badge") or row.get("home_image"),
            "country_id": row.get("home_country_code") or row.get("home_country") or row.get("home_nationality"),
        },
        "away": {
            "id": str(row.get("away_id") or row.get("away_team_id") or ""),
            "name": away,
            "logo": row.get("away_logo") or row.get("away_badge") or row.get("away_image"),
            "country_id": row.get("away_country_code") or row.get("away_country") or row.get("away_nationality"),
        },
        "status": status,
        "score": score,
        "start_time": row.get("time"),
        "competition": row.get("competition") or competition_id,
        "competition_key": competition_id,
        "source_url": row.get("url"),
        "source_family": "sportscore",
        "source_event_id": source_event_id or None,
        "source_event_ids": {"sportscore": source_event_id} if source_event_id else {},
        "source_competition_id": row.get("competition"),
        "competition_logo": row.get("competition_logo") or row.get("league_logo") or row.get("tournament_logo"),
        "extra": {
            "attribution": ATTRIBUTION,
            "upstream_family": "thesports",
            "source_family": "sportscore",
            "source_event_id": source_event_id or None,
            "source_event_ids": {"sportscore": source_event_id} if source_event_id else {},
        },
    }
    return event


def _payload_matches(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get("matches") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


class SportScoreAdapter:
    adapter_key = "sportscore"

    def __init__(self, source_id: str = "sportscore", getter=None):
        self.source_id = source_id
        self._get = getter or fetch_url

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        competition_id = request.competition_id or ""
        spec = SPORTSCORE_COMPETITIONS.get(competition_id)
        if spec is None:
            return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
        sport = spec["sport"]
        matches, last = self._matches_for_sport(sport, request)
        if last is not None and not last.ok:
            return last
        events = self._filter(matches, spec, competition_id)

        # The global matches endpoint is capped at 50 across a sport. That is
        # excellent for live polling but not enough for a complete daily
        # fixture/results board. For non-live collection, expand the mapped
        # competition through all team schedules and merge those rows.
        if request.capability not in {"live", "live_scores"}:
            team_matches, team_last = self._team_matches(sport, spec)
            if team_last is not None and not team_last.ok and not events:
                return team_last
            events.extend(self._filter(team_matches, spec, competition_id))
        elif not events:
            # Never fan out fresh requests for every team during the fast live
            # loop. Cached schedules may still rescue a league that fell
            # outside the global top-50 board.
            events.extend(self._filter(self._cached_team_matches(sport, spec), spec, competition_id))
        events = self._dedupe_events(events)
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(
            ok=True,
            http_status=200,
            events=events,
            empty_reason=empty_reason,
            payload={"attribution": ATTRIBUTION, "competition": competition_id},
        )

    def _filter(
        self, matches: List[Dict[str, Any]], spec: Dict[str, Any], competition_id: str
    ) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for row in matches:
            if not match_competition(str(row.get("competition") or ""), spec):
                continue
            event = match_to_event(row, competition_id)
            if event:
                events.append(event)
        return events

    @staticmethod
    def _dedupe_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for event in events:
            source_id = str(event.get("source_event_id") or "")
            key = source_id or "|".join(
                [
                    str((event.get("home") or {}).get("name") or ""),
                    str((event.get("away") or {}).get("name") or ""),
                    str(event.get("start_time") or ""),
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(event)
        return out

    def _matches_for_sport(self, sport: str, request: FetchRequest) -> Tuple[List[Dict[str, Any]], Optional[FetchResult]]:
        use_cache = self._get is fetch_url
        if use_cache:
            cached = _cached(_MATCH_CACHE, sport, _MATCH_TTL_S)
            if cached is not None:
                return cached, None
        url = MATCHES_URL.format(sport=sport, limit=50)
        result = self._get(url)
        if not result.ok:
            return [], result
        rows = _payload_matches(result.payload)
        if use_cache:
            _store(_MATCH_CACHE, sport, rows)
        return rows, result

    @staticmethod
    def _team_slugs(payload: Dict[str, Any]) -> List[str]:
        slugs: List[str] = []
        for table in payload.get("tables") or []:
            for row in table.get("rows") or []:
                slug_row = row.get("team_slug")
                if slug_row and slug_row not in slugs:
                    slugs.append(str(slug_row))
                if len(slugs) >= 40:
                    return slugs
        return slugs

    def _cached_team_matches(self, sport: str, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for competition_slug in spec.get("slugs") or []:
            standings_key = f"{sport}:{competition_slug}"
            payload = _cached(_STANDINGS_CACHE, standings_key, _STANDINGS_TTL_S)
            if not isinstance(payload, dict):
                continue
            for team_slug in self._team_slugs(payload):
                cached = _cached(_TEAM_CACHE, f"{sport}:{team_slug}", _TEAM_TTL_S)
                if cached:
                    rows.extend(cached)
        return _dedupe_matches(rows)

    def _team_matches(self, sport: str, spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[FetchResult]]:
        rows: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        for competition_slug in spec.get("slugs") or []:
            standings_key = f"{sport}:{competition_slug}"
            payload = _cached(_STANDINGS_CACHE, standings_key, _STANDINGS_TTL_S)
            if not isinstance(payload, dict):
                last = self._get(STANDINGS_URL.format(sport=sport, slug=competition_slug))
                if not last.ok:
                    continue
                payload = last.payload if isinstance(last.payload, dict) else {}
                _store(_STANDINGS_CACHE, standings_key, payload)

            team_slugs = self._team_slugs(payload)
            for team_slug in team_slugs:
                team_key = f"{sport}:{team_slug}"
                team_rows = _cached(_TEAM_CACHE, team_key, _TEAM_TTL_S)
                if team_rows is None:
                    last = self._get(TEAM_URL.format(sport=sport, slug=team_slug))
                    if not last.ok:
                        continue
                    team_rows = _payload_matches(last.payload)
                    _store(_TEAM_CACHE, team_key, team_rows)
                rows.extend(team_rows)
            if rows:
                break
        return _dedupe_matches(rows), last
