"""ESPN public scoreboard pages (espn-html family).

Primary fetch is www.espn.com HTML. The scoreboard JSON the page embeds is
window.__espnfitt__ (abbreviated keys: evts, lnescrs, hme/awy/lbls).

site.api.espn.com/apis/site/v2/.../scoreboard is the same family's JSON
scoreboard. It currently returns 403 from this collector (workstation and
typically Railway). We do not retry it after HTML 403, do not treat it as a
new provider, and do not call play-by-play.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from collector.adapters import FetchRequest, FetchResult
from collector.html_parse import parse_espnfitt, parse_html, walk_json_events
from collector.http import STATS, fetch_text, fetch_url
from collector.enrichment import (
    competitor_name,
    periods_from_espn_lnescrs,
    periods_from_linescores,
    rhe_from_espn_lnescrs,
)
from collector.family_health import note_family_failure, note_family_success
from collector.metrics import incr


_DATE_CACHE: Dict[str, List[Dict[str, Any]]] = {}

ESPN_SITE_API = "https://site.api.espn.com"

ESPN_HTML = {
    "nfl": "https://www.espn.com/nfl/scoreboard",
    "ncaa-football": "https://www.espn.com/college-football/scoreboard",
    "nba": "https://www.espn.com/nba/scoreboard",
    "wnba": "https://www.espn.com/wnba/scoreboard",
    "mlb": "https://www.espn.com/mlb/scoreboard",
    "nhl": "https://www.espn.com/nhl/scoreboard",
    "ufc": "https://www.espn.com/mma/schedule",
    "nascar-truck": "https://www.espn.com/racing/scoreboard",
    "nascar-arca": "https://www.espn.com/racing/scoreboard",
    "nll": "https://www.espn.com/lacrosse/scoreboard",
    "pll": "https://www.espn.com/lacrosse/scoreboard",
    "argentina-primera": "https://www.espn.com/soccer/scoreboard/_/league/arg.1",
    "denmark-superliga": "https://www.espn.com/soccer/scoreboard/_/league/den.1",
    "sweden-allsvenskan": "https://www.espn.com/soccer/scoreboard/_/league/swe.1",
    "mexico-liga-mx": "https://www.espn.com/soccer/scoreboard/_/league/mex.1",
    "australia-a-league": "https://www.espn.com/soccer/scoreboard/_/league/aus.1",
    "australia-a-league-women": "https://www.espn.com/soccer/scoreboard/_/league/aus.w.1",
    "usa-nwsl": "https://www.espn.com/soccer/scoreboard/_/league/usa.nwsl",
    "usa-usl-championship": "https://www.espn.com/soccer/scoreboard/_/league/usa.usl.1",
    "afc-champions-league": "https://www.espn.com/soccer/scoreboard/_/league/afc.champions",
    "caf-champions-league": "https://www.espn.com/soccer/scoreboard/_/league/caf.champions",
    "copa-libertadores": "https://www.espn.com/soccer/scoreboard/_/league/conmebol.libertadores",
    "copa-sudamericana": "https://www.espn.com/soccer/scoreboard/_/league/conmebol.sudamericana",
    "serbia-superliga": "https://www.espn.com/soccer/scoreboard/_/league/srb.1",
    "slovakia-super-liga": "https://www.espn.com/soccer/scoreboard/_/league/svk.1",
    "malaysia-super-league": "https://www.espn.com/soccer/scoreboard/_/league/mas.1",
    "thai-league-1": "https://www.espn.com/soccer/scoreboard/_/league/tha.1",
    "czech-first-league": "https://www.espn.com/soccer/scoreboard/_/league/cze.1",
    "india-super-league": "https://www.espn.com/soccer/scoreboard/_/league/ind.1",
    "france-top-14": "https://www.espn.com/rugby/scoreboard/_/league/270557",
    "france-pro-d2": "https://www.espn.com/rugby/scoreboard/_/league/270559",
    "super-rugby": "https://www.espn.com/rugby/scoreboard/_/league/244293",
    "super-league": "https://www.espn.com/rugby/scoreboard/_/league/270559",
    "atp-tour": "https://www.espn.com/tennis/scoreboard",
    "wta-tour": "https://www.espn.com/tennis/scoreboard",
    "formula-e": "https://www.espn.com/racing/scoreboard",
    "nrl": "https://www.espn.com/rugby/scoreboard/_/league/242041",
}

SPORT_BY_COMP = {
    "nba": "basketball",
    "wnba": "basketball",
    "mlb": "baseball",
    "nhl": "ice-hockey",
    "atp-tour": "tennis",
    "wta-tour": "tennis",
    "nfl": "american-football",
    "ncaa-football": "american-football",
}

ESPN_SITE_JSON = {
    "nba": f"{ESPN_SITE_API}/apis/site/v2/sports/basketball/nba/scoreboard",
    "wnba": f"{ESPN_SITE_API}/apis/site/v2/sports/basketball/wnba/scoreboard",
    "mlb": f"{ESPN_SITE_API}/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": f"{ESPN_SITE_API}/apis/site/v2/sports/hockey/nhl/scoreboard",
    "atp-tour": f"{ESPN_SITE_API}/apis/site/v2/sports/tennis/scoreboard",
    "wta-tour": f"{ESPN_SITE_API}/apis/site/v2/sports/tennis/scoreboard",
}


def _note_espn(outcome: Dict[str, Any]) -> None:
    bucket = STATS.setdefault("espn", [])
    if isinstance(bucket, list):
        bucket.append(outcome)
        del bucket[:-40]
    by_fam = STATS.setdefault("by_family", {})
    row = by_fam.setdefault(
        "espn-html",
        {"requests": 0, "http_403": 0, "http_429": 0, "timeouts": 0, "bytes": 0, "events": 0, "with_linescores": 0},
    )
    row["requests"] = int(row.get("requests") or 0) + 1
    status = int(outcome.get("http_status") or 0)
    if status == 202:
        row["http_202"] = int(row.get("http_202") or 0) + 1
    if status == 403:
        row["http_403"] = int(row.get("http_403") or 0) + 1
    if status == 429:
        row["http_429"] = int(row.get("http_429") or 0) + 1
    row["bytes"] = int(row.get("bytes") or 0) + int(outcome.get("bytes") or 0)
    row["events"] = int(row.get("events") or 0) + int(outcome.get("events_parsed") or 0)
    row["with_linescores"] = int(row.get("with_linescores") or 0) + int(outcome.get("events_with_linescores") or 0)


def _espn_competitions(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    comps = row.get("competitions")
    if isinstance(comps, dict):
        comps = list(comps.values())
    if isinstance(comps, list) and comps:
        return [item for item in comps if isinstance(item, dict)]
    out: List[Dict[str, Any]] = []
    for group in row.get("groupings") or []:
        if not isinstance(group, dict):
            continue
        nested = group.get("competitions") or []
        if isinstance(nested, dict):
            nested = list(nested.values())
        out.extend(item for item in nested if isinstance(item, dict))
    if out:
        return out
    if row.get("competitors"):
        return [row]
    return []


def _event_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = payload.get("events") or payload.get("evts") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if rows:
        return [item for item in rows if isinstance(item, dict)]
    board = ((payload.get("page") or {}).get("content") or {}).get("scoreboard") or {}
    rows = board.get("evts") or board.get("events") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = [item for item in rows if isinstance(item, dict)]
    comps = board.get("competitions") or payload.get("competitions")
    if isinstance(comps, dict):
        out.extend(item for item in comps.values() if isinstance(item, dict))
    elif isinstance(comps, list):
        out.extend(item for item in comps if isinstance(item, dict))
    return out


def _espn_logo(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    direct = node.get("logo") or node.get("image") or node.get("crest")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    team = node.get("team") if isinstance(node.get("team"), dict) else {}
    direct = team.get("logo") or team.get("image") or team.get("crest")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for owner in (node, team):
        logos = owner.get("logos") if isinstance(owner, dict) else None
        if isinstance(logos, list):
            for item in logos:
                if isinstance(item, dict):
                    href = item.get("href") or item.get("url")
                    if isinstance(href, str) and href.strip():
                        return href.strip()
    return ""


def _espn_country(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    owners = [node]
    for key in ("athlete", "team", "competitor"):
        value = node.get(key)
        if isinstance(value, dict):
            owners.append(value)
    for owner in owners:
        for key in ("countryCode", "country_code", "nationality", "nation", "country"):
            value = owner.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                code = (
                    value.get("abbreviation")
                    or value.get("code")
                    or value.get("alpha2")
                    or value.get("alpha3")
                    or value.get("name")
                )
                if isinstance(code, str) and code.strip():
                    return code.strip()
        flag = owner.get("flag")
        if isinstance(flag, dict):
            code = flag.get("alt") or flag.get("code") or flag.get("abbreviation")
            if isinstance(code, str) and code.strip():
                return code.strip()
    return ""


def _espn_league_logo(leagues: Any, board: Dict[str, Any]) -> str:
    league = leagues[0] if isinstance(leagues, list) and leagues and isinstance(leagues[0], dict) else {}
    for owner in (league, board.get("league") if isinstance(board.get("league"), dict) else {}):
        logo = _espn_logo(owner)
        if logo:
            return logo
    return ""


def _sides(teams: List[Any]) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    home = next((item for item in teams if isinstance(item, dict) and (item.get("homeAway") == "home" or item.get("isHome") is True)), None)
    away = next((item for item in teams if isinstance(item, dict) and (item.get("homeAway") == "away" or item.get("isHome") is False)), None)
    if home is None and away is None and len(teams) >= 2:
        home, away = teams[0], teams[1]
    return home if isinstance(home, dict) else None, away if isinstance(away, dict) else None


def parse_espn_scoreboard(payload: Any, *, sport: str = "") -> List[Dict[str, Any]]:
    events = []
    if not isinstance(payload, dict):
        return events
    rows = _event_rows(payload)
    leagues = payload.get("leagues") or []
    board = ((payload.get("page") or {}).get("content") or {}).get("scoreboard") or {}
    league_name = ""
    if leagues and isinstance(leagues[0], dict):
        league_name = leagues[0].get("name") or ""
    elif isinstance(board.get("league"), dict):
        league_name = board["league"].get("name") or board["league"].get("abbrev") or ""
    sport = sport or str((board.get("league") or {}).get("sport") or "")
    fetched_at = datetime.utcnow().isoformat() + "Z"
    for row in rows:
        competitions = _espn_competitions(row)
        for comp in competitions:
            home, away = _sides(comp.get("competitors") or [])
            if home is None or away is None:
                continue
            status_obj = (comp.get("status") or row.get("status") or {}) if isinstance(comp.get("status") or row.get("status"), dict) else {}
            type_obj = status_obj.get("type") if isinstance(status_obj.get("type"), dict) else {}
            state = str(type_obj.get("state") or status_obj.get("state") or "").lower()
            if state in {"post", "final"} or comp.get("completed") is True or row.get("completed") is True:
                status = "finished"
            elif state in {"in", "live"}:
                status = "live"
            else:
                status = "scheduled"
            venue = None
            if isinstance(comp.get("venue"), dict):
                venue = comp.get("venue").get("fullName")
            elif isinstance(row.get("venue"), dict):
                venue = row.get("venue").get("fullName")
            elif isinstance(row.get("vnue"), dict):
                venue = row.get("vnue").get("fullName") or row.get("vnue").get("name")
            periods = periods_from_linescores(home, away, sport=sport)
            if not periods:
                periods = periods_from_espn_lnescrs(comp.get("lnescrs") or row.get("lnescrs"), sport=sport)
            rhe = rhe_from_espn_lnescrs(comp.get("lnescrs") or row.get("lnescrs"))
            clock = status_obj.get("displayClock") or status_obj.get("clock")
            if isinstance(clock, str) and ("PM" in clock or "AM" in clock or "-" in clock):
                clock = None
            score = {
                "home": _score(home),
                "away": _score(away),
                "clock": clock,
                "period": status_obj.get("period"),
                "clock_state": state or None,
                "clock_fetched_at": fetched_at if clock else None,
                "hits": rhe.get("hits")
                or (
                    {"home": home.get("hits"), "away": away.get("hits")}
                    if home.get("hits") is not None or away.get("hits") is not None
                    else None
                ),
                "errors": rhe.get("errors")
                or (
                    {"home": home.get("errors"), "away": away.get("errors")}
                    if home.get("errors") is not None or away.get("errors") is not None
                    else None
                ),
            }
            events.append(
                {
                    "id": str(comp.get("id") or row.get("id") or ""),
                    "home": {
                        "id": str(home.get("id") or ((home.get("team") or {}).get("id") if isinstance(home.get("team"), dict) else "") or ""),
                        "name": competitor_name(home) or home.get("displayName") or home.get("abbrev"),
                        "logo": _espn_logo(home),
                        "country_id": _espn_country(home) or None,
                    },
                    "away": {
                        "id": str(away.get("id") or ((away.get("team") or {}).get("id") if isinstance(away.get("team"), dict) else "") or ""),
                        "name": competitor_name(away) or away.get("displayName") or away.get("abbrev"),
                        "logo": _espn_logo(away),
                        "country_id": _espn_country(away) or None,
                    },
                    "status": status,
                    "score": {key: value for key, value in score.items() if value is not None},
                    "start_time": row.get("date") or comp.get("date") or comp.get("startDate"),
                    "venue": venue,
                    "competition": league_name or row.get("name"),
                    "source_competition_name": league_name or "",
                    "source_competition_id": (
                        (leagues[0].get("abbreviation") or leagues[0].get("slug") or leagues[0].get("id"))
                        if leagues and isinstance(leagues[0], dict)
                        else None
                    ),
                    "competition_logo": _espn_league_logo(leagues, board),
                    "season": ((row.get("season") or {}).get("year") if isinstance(row.get("season"), dict) else row.get("season")),
                    "periods": periods,
                    "winner": competitor_name(home)
                    if home.get("winner")
                    else (competitor_name(away) if away.get("winner") else None),
                    "form": {
                        "home": {"summary": home.get("form")} if home.get("form") else None,
                        "away": {"summary": away.get("form")} if away.get("form") else None,
                    }
                    if home.get("form") or away.get("form")
                    else None,
                    "source_family": "espn-html",
                    "source_event_id": str(comp.get("id") or row.get("id") or ""),
                    "source_fetch_time": fetched_at,
                }
            )
    return [event for event in events if (event.get("home") or {}).get("name") or (event.get("away") or {}).get("name")]


def _score(competitor: Dict[str, Any]) -> Optional[int]:
    raw = competitor.get("score")
    if raw in (None, ""):
        raw = competitor.get("runs")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class EspnScoreboardAdapter:
    adapter_key = "espn-scoreboard"

    def __init__(self, source_id: str = "espn-html", getter=None, text_getter=None):
        self.source_id = source_id
        self._get = getter
        self._get_text = text_getter or fetch_text

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        url = ESPN_HTML.get(request.competition_id or "") or (request.source_config or {}).get("url") or ""
        if not url:
            url = {
                "american-football": ESPN_HTML["nfl"],
                "mma": ESPN_HTML["ufc"],
                "basketball": ESPN_HTML["nba"],
                "baseball": ESPN_HTML["mlb"],
                "ice-hockey": ESPN_HTML["nhl"],
                "football": "https://www.espn.com/soccer/scoreboard",
            }.get(request.sport_id or "") or ""
        if not url:
            return FetchResult(
                ok=False,
                http_status=0,
                error="no ESPN scoreboard URL",
                classification="CONFIG_MISSING",
                config_missing=True,
            )
        sport = SPORT_BY_COMP.get(request.competition_id or "") or (request.sport_id or "")
        events = []
        last = None
        for candidate in _scoreboard_date_urls(url, request.date_from, request.date_to, request.capability):
            cache_key = f"{request.competition_id}:{candidate}"
            if cache_key in _DATE_CACHE:
                events = _DATE_CACHE[cache_key]
                if events:
                    break
                continue
            endpoint_class = "json" if "site.api.espn.com" in candidate or candidate.lower().endswith(".json") else "html"
            if self._get is not None:
                last = self._get(candidate)
            elif endpoint_class == "json":
                last = fetch_url(candidate)
            else:
                last = self._get_text(candidate)
            status = int(getattr(last, "http_status", 0) or 0) if last else 0
            raw = getattr(last, "payload", None) if last else None
            nbytes = len(raw.encode("utf-8")) if isinstance(raw, str) else (len(raw) if isinstance(raw, (bytes, bytearray)) else 0)
            if last is None or not last.ok:
                _note_espn(
                    {
                        "provider_family": "espn-html",
                        "sport": sport,
                        "endpoint_class": endpoint_class,
                        "url_host": urlparse(candidate).netloc,
                        "http_status": status,
                        "bytes": nbytes,
                        "events_parsed": 0,
                        "events_with_linescores": 0,
                    }
                )
                if status in {202, 403}:
                    note_family_failure("espn-html", http_status=status, error_type="ACCESS_BLOCKED", retry_after_s=21600)
                    break
                continue
            events = self._events(last.payload, candidate, sport=sport)
            _DATE_CACHE[cache_key] = events
            with_ls = sum(1 for event in events if event.get("periods"))
            _note_espn(
                {
                    "provider_family": "espn-html",
                    "sport": sport,
                    "endpoint_class": endpoint_class,
                    "url_host": urlparse(candidate).netloc,
                    "http_status": status,
                    "bytes": nbytes,
                    "events_parsed": len(events),
                    "events_with_linescores": with_ls,
                }
            )
            incr("espn_events_with_linescores", with_ls)
            if last.ok:
                note_family_success("espn-html", http_status=status, events=len(events), parse_ok=bool(events))
            if events:
                break
        json_url = ESPN_SITE_JSON.get(request.competition_id or "")
        if not events and json_url:
            candidate = json_url
            last = self._get(candidate) if self._get is not None else fetch_url(candidate)
            status = int(getattr(last, "http_status", 0) or 0) if last else 0
            raw = getattr(last, "payload", None) if last else None
            nbytes = len(raw.encode("utf-8")) if isinstance(raw, str) else (len(raw) if isinstance(raw, (bytes, bytearray)) else 0)
            parsed = self._events(last.payload, candidate, sport=sport) if last and last.ok else []
            _note_espn(
                {
                    "provider_family": "espn-html",
                    "sport": sport,
                    "endpoint_class": "json",
                    "url_host": urlparse(candidate).netloc,
                    "http_status": status,
                    "bytes": nbytes,
                    "events_parsed": len(parsed),
                    "events_with_linescores": sum(1 for event in parsed if event.get("periods")),
                }
            )
            if status in {202, 403}:
                    note_family_failure("espn-html", http_status=status, error_type="ACCESS_BLOCKED", retry_after_s=21600)
            elif last and last.ok:
                events = parsed
                if events:
                    note_family_success("espn-html", http_status=status, events=len(events), parse_ok=True)
        if last is not None and not last.ok and not events:
            return last
        empty_reason = None if events else "SOURCE_HEALTHY_NO_EVENTS"
        return FetchResult(
            ok=True,
            http_status=(last.http_status if last else 200) or 200,
            events=events,
            empty_reason=empty_reason,
        )

    def _events(self, payload: Any, url: str, sport: str = "") -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            return parse_espn_scoreboard(payload, sport=sport) or walk_json_events(payload)
        if isinstance(payload, str):
            parsed = _parse_espnfitt_scoreboard(payload, sport=sport)
            if parsed:
                return parsed
            return parse_espnfitt(payload) or parse_html(payload, url)
        return []


def _espn_html_team_catalog(html_text: str) -> List[Dict[str, str]]:
    import html as html_lib
    import re

    out: List[Dict[str, str]] = []
    seen = set()
    pattern = re.compile(
        r'''href=["'][^"']*/team/_/id/(\d+)/([^"'/?#]+)[^"']*["'][^>]*>(.*?)</a>''',
        re.I | re.S,
    )
    for match in pattern.finditer(html_text or ""):
        team_id = str(match.group(1) or "").strip()
        slug = str(match.group(2) or "").strip()
        label = re.sub(r"<[^>]+>", " ", match.group(3) or "")
        label = html_lib.unescape(re.sub(r"\s+", " ", label)).strip()
        if not team_id:
            continue
        key = (team_id, slug)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "id": team_id,
            "slug": slug,
            "label": label,
            "slug_name": slug.replace("-", " "),
        })
    return out


def _attach_espn_html_team_ids(events: List[Dict[str, Any]], html_text: str) -> List[Dict[str, Any]]:
    from collector.participant_alias import names_equivalent

    catalog = _espn_html_team_catalog(html_text)
    if not catalog:
        return events
    for event in events:
        for side_name in ("home", "away"):
            side = event.get(side_name)
            if not isinstance(side, dict) or str(side.get("id") or "").strip():
                continue
            name = str(side.get("name") or "").strip()
            if not name:
                continue
            matches = [
                row for row in catalog
                if names_equivalent(name, row.get("label") or "")
                or names_equivalent(name, row.get("slug_name") or "")
            ]
            unique_ids = {row["id"] for row in matches if row.get("id")}
            if len(unique_ids) != 1:
                continue
            team_id = next(iter(unique_ids))
            side["id"] = team_id
    return events


def _parse_espnfitt_scoreboard(html: str, sport: str = "") -> List[Dict[str, Any]]:
    import json
    import re

    match = re.search(r"""window\[['"]__espnfitt__['"]\]\s*=\s*""", html or "")
    if not match:
        return []
    try:
        payload, _end = json.JSONDecoder().raw_decode(html[match.end() :])
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    events = parse_espn_scoreboard(payload, sport=sport)
    return _attach_espn_html_team_ids(events, html)


def _parse_request_day(value: Optional[str]) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return None


def _scoreboard_date_urls(
    url: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    capability: str = "",
) -> List[str]:
    urls = [url]
    if "scoreboard" not in url or "/date/" in url:
        return urls

    today = datetime.utcnow().date()
    start = _parse_request_day(date_from)
    end = _parse_request_day(date_to) or start
    requested: List[date] = []

    if start:
        if end and end < start:
            end = start
        cursor = start
        # A collector request should be bounded. Seven days is enough for our
        # daily/near-term fixture windows without accidentally fanning out.
        while cursor <= (end or start) and len(requested) < 7:
            requested.append(cursor)
            cursor += timedelta(days=1)
    else:
        cap = str(capability or "").lower()
        if cap in {"fixtures", "fixture", "schedule", "scheduled"}:
            requested.extend([today, today + timedelta(days=1)])
        elif cap in {"results", "result", "finished"}:
            requested.extend([today, today - timedelta(days=1), today - timedelta(days=7)])
        else:
            requested.append(today)

    parsed = urlparse(url)
    base_path = parsed.path.rstrip("/")
    # Requested dates must be tried before the undated page for fixture
    # collection. ESPN's undated scoreboard defaults to "today".
    dated: List[str] = []
    for day in requested:
        stamp = day.strftime("%Y%m%d")
        path = f"{base_path}/_/date/{stamp}"
        dated.append(urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, "")))

    return list(dict.fromkeys([*dated, *urls]))
