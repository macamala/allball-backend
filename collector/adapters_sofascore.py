"""SofaScore ordinary public www.sofascore.com JSON.

Railway-proven 200 on /api/v1/sport/{sport}/events/live (2026-09-20).
Does not use api.sofascore.com (403). Does not infer LIVE from wall clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url

LIVE_URL = "https://www.sofascore.com/api/v1/sport/{sport}/events/live"
SCHED_URL = "https://www.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date}"
SOFA_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}


def sofa_fetch_url(url: str):
    """Public SofaScore JSON with ordinary browser headers and host fallback."""
    result = fetch_url(url, headers=SOFA_BROWSER_HEADERS)
    if result.ok:
        return result
    if "://www.sofascore.com/" in url:
        alternate = url.replace("://www.sofascore.com/", "://api.sofascore.com/", 1)
        retry = fetch_url(alternate, headers=SOFA_BROWSER_HEADERS)
        if retry.ok or retry.http_status != 0:
            return retry
    return result

# One live + dated board fetch is reused across competitions in the same sport.
_BOARD: Dict[str, List[Dict[str, Any]]] = {}

SOFA_COMPETITIONS: Dict[str, Dict[str, Any]] = {
    "nrl": {
        "sport": "rugby",
        "sport_id": "rugby-league",
        "tokens_any": ["nrl"],
        "deny": ["nrlw", "women"],
    },
    "npb": {
        "sport": "baseball",
        "sport_id": "baseball",
        "tokens_any": ["pacific league", "central league", "npb", "pro yakyu"],
    },
    "kbo": {
        "sport": "baseball",
        "sport_id": "baseball",
        "tokens_any": ["kbo", "korea baseball"],
    },
    "cpbl": {
        "sport": "baseball",
        "sport_id": "baseball",
        "tokens_any": ["cpbl", "chinese professional baseball"],
    },
    "sweden-shl": {
        "sport": "ice-hockey",
        "sport_id": "ice-hockey",
        "tokens_any": ["shl"],
        "deny": ["khl", "vhl", "swiss"],
        "category_any": ["sweden"],
    },
    "germany-handball-bundesliga": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["bundesliga", "liquimoly hbl", "hbl"],
        "category_any": ["germany"],
        "deny": ["2. bundesliga"],
    },
    "denmark-handball-league": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["herreligaen", "håndboldligaen", "handboldligaen", "danish handball"],
        "category_any": ["denmark"],
    },
    "france-lnh": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["starligue", "liquimoly starligue", "lnh"],
        "category_any": ["france"],
    },
    "spain-asobal": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["asobal"],
    },
    "ehf-champions-league": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["ehf champions", "champions league"],
        "deny": ["european league", "european cup"],
        "category_any": ["international", "europe"],
    },
    "ehf-competitions": {
        "sport": "handball",
        "sport_id": "handball",
        "tokens_any": ["ehf european league", "ehf european cup"],
        "deny": ["champions league"],
    },
    "france-top-14": {
        "sport": "rugby",
        "sport_id": "rugby",
        "tokens_any": ["top 14"],
    },
    "france-pro-d2": {
        "sport": "rugby",
        "sport_id": "rugby",
        "tokens_any": ["pro d2"],
    },
    "premiership-rugby": {
        "sport": "rugby",
        "sport_id": "rugby",
        "tokens_any": ["premiership rugby", "gallagher premiership", "investec premiership", "premiership"],
        "deny": ["premiership rugby cup"],
    },
    "super-rugby": {
        "sport": "rugby",
        "sport_id": "rugby",
        "tokens_any": ["super rugby"],
    },
    "nz-npc": {
        "sport": "rugby",
        "sport_id": "rugby",
        "tokens_any": ["npc", "bunnings"],
    },
    "cfl": {
        "sport": "american-football",
        "sport_id": "canadian-football",
        "tokens_any": ["cfl", "canadian football"],
    },
    "ufc": {
        "sport": "mma",
        "sport_id": "mma",
        "tokens_any": ["ufc"],
    },
    "pga-tour": {
        "sport": "golf",
        "sport_id": "golf",
        "tokens_any": ["pga"],
        "deny": ["korn ferry", "dp world", "liv"],
    },
    "korn-ferry-tour": {
        "sport": "golf",
        "sport_id": "golf",
        "tokens_any": ["korn ferry"],
    },
    "european-challenge-tour": {
        "sport": "golf",
        "sport_id": "golf",
        "tokens_any": ["challenge tour", "hotelplanner tour"],
    },
    "formula-1": {
        "sport": "motorsport",
        "sport_id": "motorsport",
        "tokens_any": ["formula 1", "formula one"],
        "deny": ["formula 2", "formula 3", "formula e"],
    },
    "formula-2": {
        "sport": "motorsport",
        "sport_id": "motorsport",
        "tokens_any": ["formula 2"],
    },
    "formula-3": {
        "sport": "motorsport",
        "sport_id": "motorsport",
        "tokens_any": ["formula 3"],
    },
    "formula-e": {
        "sport": "motorsport",
        "sport_id": "motorsport",
        "tokens_any": ["formula e"],
    },
    "brazil-lnf": {
        "sport": "futsal",
        "sport_id": "futsal",
        "tokens_any": ["lnf", "liga nacional de futsal"],
    },
    "uefa-futsal-champions-league": {
        "sport": "futsal",
        "sport_id": "futsal",
        "tokens_any": ["uefa futsal champions", "futsal champions league"],
    },
    "fifa-futsal-when-listed": {
        "sport": "futsal",
        "sport_id": "futsal",
        "tokens_any": ["fifa futsal", "futsal world cup"],
    },
    "nz-national-league": {
        "sport": "football",
        "sport_id": "football",
        "tokens_any": ["national league"],
        "category_any": ["new zealand"],
        "deny": ["championship"],
        "unique_id": 594,
    },
    "nordic-water-polo-league": {
        "sport": "waterpolo",
        "sport_id": "water-polo",
        "tokens_any": ["nordic league water polo", "nordic water polo"],
        "unique_id": 27690,
    },
    "ssn-australia": {
        "sport": "netball",
        "sport_id": "netball",
        "tokens_any": ["super netball", "suncorp"],
    },
    "vct": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["vct", "valorant champions"],
    },
    "tier1": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["blast", "cs2", "counter-strike", "pgl"],
        "deny": ["dota"],
    },
    "rlcs": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["rlcs", "rocket league"],
    },
    "cdl-majors": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["cdl", "call of duty league"],
    },
    "competitive-ea-fc": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["ea fc", "fc pro", "eafc"],
    },
    "owcs-world-finals": {
        "sport": "esports",
        "sport_id": "esports",
        "tokens_any": ["owcs", "overwatch"],
    },
    "indonesia-open": {
        "sport": "badminton",
        "sport_id": "badminton",
        "tokens_any": ["indonesia open"],
    },
}


def _dates() -> List[str]:
    now = datetime.now(timezone.utc)
    return [(now + timedelta(days=delta)).strftime("%Y-%m-%d") for delta in (-1, 0, 1)]


def _source_tournament(row: Dict[str, Any]) -> Dict[str, Any]:
    tour = row.get("tournament") if isinstance(row.get("tournament"), dict) else {}
    unique = tour.get("uniqueTournament") if isinstance(tour.get("uniqueTournament"), dict) else {}
    return unique or tour


def _source_tournament_id(row: Dict[str, Any]) -> str:
    source = _source_tournament(row)
    return str(source.get("id") or "").strip()


def _source_tournament_name(row: Dict[str, Any]) -> str:
    source = _source_tournament(row)
    return str(source.get("name") or "").strip()


def _source_country(row: Dict[str, Any]) -> str:
    tour = row.get("tournament") if isinstance(row.get("tournament"), dict) else {}
    category = tour.get("category") if isinstance(tour.get("category"), dict) else {}
    country = category.get("country") if isinstance(category.get("country"), dict) else {}
    value = (
        country.get("alpha2")
        or country.get("alpha3")
        or country.get("name")
        or category.get("countryCode")
        or ""
    )
    return str(value or "").strip()


def _blob(row: Dict[str, Any]) -> str:
    tour = row.get("tournament") or {}
    unique = tour.get("uniqueTournament") or {}
    cat = tour.get("category") or {}
    return " ".join(
        str(part or "")
        for part in (unique.get("name"), tour.get("name"), tour.get("slug"), cat.get("name"), cat.get("slug"))
    ).lower()


def _matches_spec(row: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    blob = _blob(row)
    deny = spec.get("deny") or []
    if any(tok in blob for tok in deny):
        return False
    uid = spec.get("unique_id")
    if uid is not None:
        got = ((row.get("tournament") or {}).get("uniqueTournament") or {}).get("id")
        if got is not None:
            return str(got) == str(uid)
    tokens = spec.get("tokens") or []
    if tokens and not all(tok in blob for tok in tokens):
        return False
    any_tokens = spec.get("tokens_any") or []
    if any_tokens and not any(tok in blob for tok in any_tokens):
        return False
    cats = spec.get("category_any") or []
    if cats:
        cat = str(((row.get("tournament") or {}).get("category") or {}).get("name") or "").lower()
        if not any(tok in cat for tok in cats):
            return False
    return True


def sofa_event(row: Dict[str, Any], competition_id: str, sport_id: str) -> Optional[Dict[str, Any]]:
    home = row.get("homeTeam") or {}
    away = row.get("awayTeam") or {}
    home_name = home.get("name") or home.get("shortName")
    away_name = away.get("name") or away.get("shortName")
    if not home_name or not away_name:
        return None
    st = row.get("status") or {}
    stype = str(st.get("type") or "").lower()
    if stype in {"inprogress", "in_progress"}:
        status = "live"
    elif stype in {"finished", "complete"}:
        status = "finished"
    else:
        status = "scheduled"
    home_score = (row.get("homeScore") or {}).get("current")
    away_score = (row.get("awayScore") or {}).get("current")
    score: Dict[str, Any] = {
        "home": home_score if status != "scheduled" else None,
        "away": away_score if status != "scheduled" else None,
    }
    clock = (row.get("time") or {}).get("played") or st.get("description")
    period = (row.get("time") or {}).get("period") or (row.get("status") or {}).get("description")
    if clock not in (None, "") and status == "live":
        score["clock"] = clock
    if period not in (None, "") and status == "live":
        score["period"] = period
    periods = []
    hs = row.get("homeScore") if isinstance(row.get("homeScore"), dict) else {}
    aws = row.get("awayScore") if isinstance(row.get("awayScore"), dict) else {}
    for index in range(1, 8):
        home_p = hs.get(f"period{index}")
        away_p = aws.get(f"period{index}")
        if home_p is None and away_p is None:
            continue
        periods.append({"label": str(index), "home": home_p, "away": away_p})
    start = row.get("startTimestamp")
    start_time = None
    if isinstance(start, (int, float)):
        start_time = datetime.fromtimestamp(int(start), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tour = row.get("tournament") or {}
    unique = tour.get("uniqueTournament") or {}
    source_competition_id = _source_tournament_id(row)
    source_competition_name = _source_tournament_name(row) or unique.get("name") or tour.get("name") or competition_id
    source_country = _source_country(row)
    payload = {
        "id": f"sofascore:{row.get('id')}",
        "home": {"id": str(home.get("id") or ""), "name": home_name},
        "away": {"id": str(away.get("id") or ""), "name": away_name},
        "status": status,
        "score": score,
        "start_time": start_time,
        "sport": sport_id,
        "competition": source_competition_name,
        "competition_key": competition_id,
        "country_id": source_country or None,
        "event_family": "team_match",
        "source_family": "sofascore-web",
        "source_event_id": str(row.get("id") or ""),
        "source_competition_id": source_competition_id or None,
        "source_competition_name": source_competition_name,
        "extra": {
            "source_family": "sofascore-web",
            "source_event_ids": {"sofascore-web": str(row.get("id") or "")},
            "source_event_id": str(row.get("id") or ""),
            "source_competition_id": source_competition_id or None,
            "source_competition_name": source_competition_name,
        },
    }
    if periods:
        payload["periods"] = periods
    return payload


class SofaScoreWebAdapter:
    adapter_key = "sofascore-web"
    source_id = "sofascore-web"

    def __init__(self, source_id: str = "sofascore-web", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        competition_id = request.competition_id or ""
        spec = SOFA_COMPETITIONS.get(competition_id)
        source_config = request.source_config or {}
        target_tournament_id = str(source_config.get("sofascore_tournament_id") or "").strip()
        if spec is None and target_tournament_id:
            sport = str(source_config.get("sofascore_sport") or request.sport_id or "").strip()
            sport_id = str(source_config.get("sport_id") or request.sport_id or sport).strip()
            if not sport:
                return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
            rows = list(self._board(sport))
            events = []
            for row in rows:
                if _source_tournament_id(row) != target_tournament_id:
                    continue
                event = sofa_event(row, competition_id, sport_id)
                if event:
                    events.append(event)
        else:
            if spec is None:
                return FetchResult(ok=True, http_status=200, events=[], empty_reason="SOURCE_HEALTHY_NO_EVENTS")
            sport = spec["sport"]
            # Live + dated sport boards only. unique-tournament/* is 403 from Railway.
            rows = list(self._board(sport))
            events = []
            for row in rows:
                if not _matches_spec(row, spec):
                    continue
                event = sofa_event(row, competition_id, spec.get("sport_id") or sport)
                if event:
                    events.append(event)
        cap = request.capability
        if cap == "live_scores":
            events = [e for e in events if e.get("status") == "live"]
        elif cap == "results":
            events = [e for e in events if e.get("status") == "finished"]
        elif cap == "fixtures":
            events = [e for e in events if e.get("status") == "scheduled"]
        return FetchResult(ok=True, http_status=200, events=events)

    def _board(self, sport: str) -> List[Dict[str, Any]]:
        if sport in _BOARD:
            return _BOARD[sport]
        seen: Dict[Any, Dict[str, Any]] = {}
        live = self._get(LIVE_URL.format(sport=sport))
        if live.ok and isinstance(live.payload, dict):
            for row in live.payload.get("events") or []:
                if isinstance(row, dict) and row.get("id") is not None:
                    seen[row["id"]] = row
        for day in _dates():
            sched = self._get(SCHED_URL.format(sport=sport, date=day))
            if not sched.ok or not isinstance(sched.payload, dict):
                continue
            for row in sched.payload.get("events") or []:
                if isinstance(row, dict) and row.get("id") is not None:
                    seen[row["id"]] = row
        rows = list(seen.values())
        _BOARD[sport] = rows
        return rows

    def _unique_events(self, unique_id: int) -> List[Dict[str, Any]]:
        # Intentionally unused at runtime: unique-tournament APIs return 403 on Railway.
        return []
