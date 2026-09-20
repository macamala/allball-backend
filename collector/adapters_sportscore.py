"""SportScore public widget family.

Developer docs: https://sportscore.com/developers/
No API key. Attribution "Powered by SportScore" with dofollow to
https://sportscore.com/ is required wherever this data is displayed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
TEAM_URL = "https://sportscore.com/api/widget/team/?sport={sport}&slug={slug}&src=ninkosports"

# One fetch per sport is reused across competitions.
_MATCH_CACHE: Dict[str, List[Dict[str, Any]]] = {}
_STANDINGS_CACHE: Dict[str, Dict[str, Any]] = {}
_TEAM_CACHE: Dict[str, List[Dict[str, Any]]] = {}

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
    event = {
        "id": row.get("url") or f"sportscore:{competition_id}:{home}:{away}:{row.get('time')}",
        "home": {"name": home, "logo": row.get("home_logo")},
        "away": {"name": away, "logo": row.get("away_logo")},
        "status": status,
        "score": score,
        "start_time": row.get("time"),
        "competition": row.get("competition") or competition_id,
        "source_url": row.get("url"),
        "source_family": "sportscore",
        "source_competition_id": row.get("competition"),
        "extra": {"attribution": ATTRIBUTION, "upstream_family": "thesports"},
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
        if not events:
            team_matches, team_last = self._team_matches(sport, spec)
            if team_last is not None and not team_last.ok and not events:
                return team_last
            events = self._filter(team_matches, spec, competition_id)
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

    def _matches_for_sport(self, sport: str, request: FetchRequest) -> Tuple[List[Dict[str, Any]], Optional[FetchResult]]:
        use_cache = self._get is fetch_url
        if use_cache and sport in _MATCH_CACHE:
            return _MATCH_CACHE[sport], None
        url = MATCHES_URL.format(sport=sport, limit=50)
        result = self._get(url)
        if not result.ok:
            return [], result
        rows = _payload_matches(result.payload)
        if use_cache:
            _MATCH_CACHE[sport] = rows
        return rows, result

    def _team_matches(self, sport: str, spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[FetchResult]]:
        rows: List[Dict[str, Any]] = []
        last: Optional[FetchResult] = None
        for slug in spec.get("slugs") or []:
            standings_key = f"{sport}:{slug}"
            if standings_key not in _STANDINGS_CACHE:
                last = self._get(STANDINGS_URL.format(sport=sport, slug=slug))
                if not last.ok:
                    continue
                payload = last.payload if isinstance(last.payload, dict) else {}
                _STANDINGS_CACHE[standings_key] = payload
            payload = _STANDINGS_CACHE[standings_key]
            tables = payload.get("tables") or []
            team_slugs: List[str] = []
            for table in tables:
                for row in table.get("rows") or []:
                    slug_row = row.get("team_slug")
                    if slug_row and slug_row not in team_slugs:
                        team_slugs.append(slug_row)
                    if len(team_slugs) >= 3:
                        break
                if len(team_slugs) >= 3:
                    break
            for team_slug in team_slugs:
                team_key = f"{sport}:{team_slug}"
                if team_key not in _TEAM_CACHE:
                    last = self._get(TEAM_URL.format(sport=sport, slug=team_slug))
                    if not last.ok:
                        continue
                    _TEAM_CACHE[team_key] = _payload_matches(last.payload)
                rows.extend(_TEAM_CACHE[team_key])
            if rows:
                break
        return rows, last
