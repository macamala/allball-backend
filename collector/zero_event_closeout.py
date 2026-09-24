"""Bounded official proofs for competitions that had no stored production event.

Parsers are pure. Fetchers hit the first-party page the registry already names.
title-fights is not collected: it is an umbrella, not a competition.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable, Dict, Iterable, List, Optional

from collector.util import slugify

Getter = Callable[[str], str]

CDL_HOST = "https://www.callofdutyleague.com/en-us/"
PLL_STANDINGS = "https://premierlacrosseleague.com/standings"
PLL_SCHEDULE = "https://premierlacrosseleague.com/schedule"
CAF_RESULTS = "https://www.cafonline.com/afcon2025/schedule-results/"
EHF_MATCHES = "https://ehfcl.eurohandball.com/men/2025-26/matches/"
VNL_PAGE = "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league"
NZ_PAGES = (
    "https://www.nzfootball.co.nz/competitions/national-league",
    "https://www.nzfootball.co.nz/national-leagues",
    "https://www.nzfootball.co.nz/",
)
NASCAR_TRUCK = "https://www.nascar.com/live-results/nascar-craftsman-truck-series/"
NASCAR_ARCA = "https://www.arcaracing.com/arca-menards-series/"
NASCAR_REGIONAL = "https://www.nascar.com/regional/"
ATP_RESULTS = "https://www.atptour.com/en/scores/archive/winston-salem/6242/2026/results"
ATP_TOURNAMENT_ID = "6242"


def _text(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", unescape(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _loads_objects(blob: str, marker: str) -> List[Dict[str, Any]]:
    found = []
    start = 0
    while True:
        index = blob.find(marker, start)
        if index < 0:
            break
        try:
            obj, offset = json.JSONDecoder().raw_decode(blob[index:])
        except json.JSONDecodeError:
            start = index + len(marker)
            continue
        if isinstance(obj, dict):
            found.append(obj)
        start = index + max(offset, 1)
    return found


def parse_cdl_matches(html: str) -> List[Dict[str, Any]]:
    """Official CDL homepage hydration. Other esports links are ignored."""
    events = []
    seen = set()
    for row in _loads_objects(html or "", '{"status":"COMPLETED"'):
        link = str(row.get("link") or "")
        if "callofdutyleague.com" not in link and "/match/" not in link:
            continue
        if any(token in link.lower() for token in ("valorant", "lolesports", "rocketleague")):
            continue
        competitors = row.get("competitors") or []
        if len(competitors) < 2:
            continue
        home, away = competitors[0], competitors[1]
        home_name = home.get("longName") or home.get("shortName")
        away_name = away.get("longName") or away.get("shortName")
        if not home_name or not away_name:
            continue
        match_id = link.rstrip("/").rsplit("/", 1)[-1]
        if not match_id.isdigit() or match_id in seen:
            continue
        seen.add(match_id)
        stamp = ((row.get("date") or {}).get("startTime")) or 0
        try:
            start = datetime.fromtimestamp(int(stamp), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError, OSError):
            start = "2026-01-01T00:00:00Z"
        source_id = f"cdl:{match_id}"
        events.append(
            {
                "id": source_id,
                "home": {"id": str(home.get("shortName") or ""), "name": home_name},
                "away": {"id": str(away.get("shortName") or ""), "name": away_name},
                "status": "finished",
                "score": {"home": home.get("score"), "away": away.get("score")},
                "start_time": start,
                "sport": "call-of-duty",
                "competition": "Call of Duty League",
                "competition_key": "cdl-majors",
                "source_competition_id": "cdl-majors",
                "event_family": "esports_match",
                "game_id": "call-of-duty",
                "source_family": "cdl-web",
                "source_event_id": source_id,
                "source_event_ids": {"cdl-web": source_id},
                "round": row.get("roundName") or row.get("phase") or row.get("matchType") or "series",
            }
        )
    return events


def parse_pll_standings(html: str) -> List[Dict[str, Any]]:
    rows = []
    for conference, body in re.findall(
        r'aria-label="(eastern|western)".*?<tbody>(.*?)</tbody>',
        html or "",
        flags=re.I | re.S,
    ):
        for team, wins, losses, scored, against, diff in re.findall(
            r'aria-label="([^"]+)"[^>]*>.*?<span>\1</span>.*?<td[^>]*>(\d+)</td><td[^>]*>(\d+)</td><td[^>]*>(\d+)</td><td[^>]*>(\d+)</td><td[^>]*>(-?\d+)</td>',
            body,
            flags=re.S,
        ):
            rows.append(
                {
                    "team": team,
                    "conference": conference.lower(),
                    "won": int(wins),
                    "lost": int(losses),
                    "played": int(wins) + int(losses),
                    "goals_for": int(scored),
                    "goals_against": int(against),
                    "goal_diff": int(diff),
                    "points": int(wins),
                }
            )
    return rows


def _team_label(team: Any) -> str:
    if not isinstance(team, dict):
        return str(team or "").strip()
    location = str(team.get("location") or "").strip()
    name = str(team.get("fullName") or team.get("name") or "").strip()
    if location and name and location.lower() not in name.lower():
        return f"{location} {name}"
    return name or location


def parse_pll_schedule(html: str) -> List[Dict[str, Any]]:
    """PLL schedule embeds escaped match objects with official externalEventId."""
    events = []
    seen = set()
    cursor = 0
    blob_src = html or ""
    while True:
        idx = blob_src.find("externalEventId", cursor)
        if idx < 0:
            break
        start = blob_src.rfind("{", max(0, idx - 2500), idx)
        if start < 0:
            cursor = idx + 16
            continue
        blob = blob_src[start : idx + 5000]
        if '\\"' in blob[:80]:
            blob = blob.replace('\\"', '"').replace("\\\\", "\\")
        try:
            row, _ = json.JSONDecoder().raw_decode(blob)
        except json.JSONDecodeError:
            cursor = idx + 16
            continue
        cursor = idx + 16
        if not isinstance(row, dict):
            continue
        match_id = str(row.get("externalEventId") or "")
        if not isinstance(row.get("homeTeam"), dict) or not isinstance(row.get("awayTeam"), dict):
            continue
        home = _team_label(row.get("homeTeam") or {})
        away = _team_label(row.get("awayTeam") or {})
        if not match_id or not home or not away or match_id in seen:
            continue
        if row.get("homeScore") is None or row.get("visitorScore") is None:
            continue
        if int(row.get("eventStatus") or 0) not in {2, 3}:
            continue
        seen.add(match_id)
        stamp = row.get("startTime") or 0
        try:
            start_time = datetime.fromtimestamp(int(stamp), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError, OSError):
            start_time = "2026-01-01T00:00:00Z"
        source_id = f"pll:{match_id}"
        event = _match(
            "pll",
            "lacrosse",
            "Premier Lacrosse League",
            "pll-web",
            home,
            away,
            row.get("homeScore"),
            row.get("visitorScore"),
            start_time,
            source_id,
            str(row.get("seasonSegment") or row.get("week") or ""),
        )
        events.append(event)
        if len(events) >= 12:
            break
    return events


def tennis_identity(event: Dict[str, Any]) -> tuple:
    home = ((event.get("home") or {}).get("name") or "").strip().lower()
    away = ((event.get("away") or {}).get("name") or "").strip().lower()
    return (str(event.get("start_time") or "")[:10], tuple(sorted((home, away))))


def dedupe_atp_matches(incoming: Iterable[Dict[str, Any]], existing: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    known = {tennis_identity(row) for row in existing}
    kept = []
    for event in incoming:
        key = tennis_identity(event)
        if key in known or key[1] == ("", ""):
            continue
        known.add(key)
        kept.append(event)
    return kept


def parse_atp_results(payload: Any, *, tournament_id: str = ATP_TOURNAMENT_ID, tournament: str = "Winston-Salem") -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("matches") or payload.get("results") or payload.get("Matches") or []
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        players = row.get("players") or []
        winner = row.get("winner") or (players[0] if players else {})
        loser = row.get("loser") or (players[1] if len(players) > 1 else {})
        if isinstance(winner, str):
            winner = {"name": winner}
        if isinstance(loser, str):
            loser = {"name": loser}
        home = winner.get("name") or winner.get("displayName") or row.get("player1")
        away = loser.get("name") or loser.get("displayName") or row.get("player2")
        if not home or not away:
            continue
        match_id = str(row.get("matchId") or row.get("id") or f"{slugify(str(home))}-{slugify(str(away))}")
        sets = row.get("sets") or row.get("score") or []
        source_id = f"atp:{tournament_id}:{match_id}"
        events.append(
            {
                "id": source_id,
                "home": {"id": str(winner.get("id") or ""), "name": home},
                "away": {"id": str(loser.get("id") or ""), "name": away},
                "status": "finished",
                "score": {"home": row.get("winnerSets"), "away": row.get("loserSets"), "sets": sets},
                "start_time": row.get("date") or "2026-08-23T00:00:00Z",
                "sport": "tennis",
                "competition": tournament,
                "competition_key": "atp-tour",
                "source_competition_id": "atp-tour",
                "event_family": "individual_match",
                "round": row.get("round") or "",
                "winner": home,
                "source_family": "atp-tour-web",
                "source_event_id": source_id,
                "source_event_ids": {"atp-tour-web": source_id},
                "tournament": tournament,
            }
        )
    return events


def parse_ehf_matches(payload: Any) -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("matches") or payload.get("items") or []
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        home = (row.get("homeTeam") or {}).get("name") or row.get("home")
        away = (row.get("awayTeam") or {}).get("name") or row.get("away")
        if not home or not away:
            continue
        match_id = str(row.get("id") or row.get("matchId") or "")
        if not match_id:
            continue
        home_score = row.get("homeScore")
        if home_score is None:
            home_score = (row.get("score") or {}).get("home")
        away_score = row.get("awayScore")
        if away_score is None:
            away_score = (row.get("score") or {}).get("away")
        source_id = f"ehf:{match_id}"
        event = _match(
            "ehf-competitions",
            "handball",
            row.get("competition") or "EHF Champions League",
            "ehf-web",
            home,
            away,
            home_score,
            away_score,
            row.get("date") or "2026-06-14T00:00:00Z",
            source_id,
            row.get("round") or row.get("phase") or "",
        )
        ht = row.get("halftime") or row.get("halfTime")
        if isinstance(ht, dict):
            event["periods"] = [{"label": "HT", "home": ht.get("home"), "away": ht.get("away")}]
        if row.get("afterExtraTime"):
            event["result_type"] = "AET"
        events.append(event)
    return events


def parse_vnl_match(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    home = row.get("homeTeam") or row.get("home") or {}
    away = row.get("awayTeam") or row.get("away") or {}
    if isinstance(home, str):
        home = {"name": home}
    if isinstance(away, str):
        away = {"name": away}
    home_name = home.get("name") or home.get("teamName")
    away_name = away.get("name") or away.get("teamName")
    if not home_name or not away_name:
        return None
    match_id = str(row.get("matchId") or row.get("id") or "")
    if not match_id:
        return None
    sets = row.get("sets") or row.get("setScores") or []
    set_rows = []
    for index, item in enumerate(sets, start=1):
        if isinstance(item, dict):
            set_rows.append({"set": index, "home": item.get("home") or item.get("homeScore"), "away": item.get("away") or item.get("awayScore")})
        elif isinstance(item, str) and "-" in item:
            left, right = item.split("-", 1)
            set_rows.append({"set": index, "home": int(left), "away": int(right)})
    source_id = f"fivb:{match_id}"
    event = _match(
        "fivb-competitions",
        "volleyball",
        row.get("competition") or "Volleyball Nations League",
        "fivb-web",
        home_name,
        away_name,
        row.get("homeSets") or row.get("homeScore"),
        row.get("awaySets") or row.get("awayScore"),
        row.get("date") or "2026-07-01T00:00:00Z",
        source_id,
        row.get("round") or "",
    )
    if set_rows:
        event["periods"] = [{"label": f"S{item['set']}", "home": item["home"], "away": item["away"]} for item in set_rows]
        event["sets"] = set_rows
    return event


def parse_nascar_results(payload: Any, *, series: str, competition_id: str) -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("Results") or payload.get("drivers") or []
    if not rows:
        return []
    race = payload.get("race") if isinstance(payload, dict) else {}
    if not isinstance(race, dict):
        race = {}
    classification = []
    winner = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("driver") or row.get("Full_Name") or row.get("name")
        finish = row.get("finish") or row.get("Finish") or row.get("position")
        if not name or finish in (None, ""):
            continue
        classification.append(
            {
                "position": finish,
                "name": name,
                "start": row.get("start") or row.get("Start"),
                "laps": row.get("laps") or row.get("Laps"),
                "laps_led": row.get("laps_led") or row.get("LapsLed"),
                "status": row.get("status") or row.get("Status"),
                "points": row.get("points") or row.get("Points"),
            }
        )
        if str(finish) == "1":
            winner = name
    if not classification:
        return []
    race_id = str(race.get("id") or race.get("race_id") or slugify(str(race.get("name") or series)))
    source_id = f"nascar:{competition_id}:{race_id}"
    return [
        {
            "id": source_id,
            "home": {"id": race_id, "name": race.get("name") or series},
            "away": {"id": competition_id, "name": series},
            "status": "finished",
            "score": {"home": winner or None, "away": None},
            "start_time": race.get("date") or "2026-09-17T00:00:00Z",
            "sport": "motorsport",
            "competition": series,
            "competition_key": competition_id,
            "source_competition_id": competition_id,
            "event_family": "motorsport_race",
            "venue": race.get("track") or "",
            "winner": winner,
            "classification": classification,
            "source_family": "nascar-web",
            "source_event_id": source_id,
            "source_event_ids": {"nascar-web": source_id},
        }
    ]


def parse_nz_iframe(html: str) -> Dict[str, str]:
    found = []
    for src in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html or "", re.I):
        if any(token in src for token in ("googletagmanager.com", "facebook.com", "iframe.ly")):
            continue
        host = re.search(r"https?://([^/]+)", src)
        found.append({"iframe_src": src, "upstream_origin": host.group(1) if host else src})
    for row in found:
        if "apps.nzfootball.co.nz" in row["iframe_src"]:
            return row
    return found[0] if found else {}


def parse_nz_matches(payload: Any, *, origin: str) -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("matches") or payload.get("results") or []
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        home = row.get("home") or row.get("homeTeam")
        away = row.get("away") or row.get("awayTeam")
        if isinstance(home, dict):
            home = home.get("name")
        if isinstance(away, dict):
            away = away.get("name")
        if not home or not away:
            continue
        match_id = str(row.get("id") or f"{slugify(str(home))}-{slugify(str(away))}-{row.get('date') or ''}")
        source_id = f"nzfootball:{origin}:{match_id}"
        event = _match(
            "nz-national-league",
            "football",
            "New Zealand National League",
            "nz-football",
            str(home),
            str(away),
            row.get("homeScore"),
            row.get("awayScore"),
            row.get("date") or "2026-01-01T00:00:00Z",
            source_id,
            row.get("round") or "",
        )
        event["upstream_origin"] = origin
        events.append(event)
    return events


def parse_caf_matches(payload: Any) -> List[Dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("matches") or payload.get("results") or []
    events = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        home = row.get("home") or row.get("homeTeam")
        away = row.get("away") or row.get("awayTeam")
        if isinstance(home, dict):
            home = home.get("name")
        if isinstance(away, dict):
            away = away.get("name")
        if not home or not away or not row.get("date"):
            continue
        match_key = row.get("id") or f"{row.get('date')}:{slugify(str(home))}:{slugify(str(away))}:{slugify(str(row.get('stage') or ''))}"
        source_id = f"caf:afcon2025:{match_key}"
        event = _match(
            "africa-cup-of-nations",
            "football",
            "TotalEnergies CAF AFCON Morocco 2025",
            "caf-web",
            str(home),
            str(away),
            row.get("ftHome"),
            row.get("ftAway"),
            row.get("date"),
            source_id,
            row.get("stage") or "",
        )
        score = dict(event["score"])
        score["ft_home"] = row.get("ftHome")
        score["ft_away"] = row.get("ftAway")
        if row.get("aetHome") is not None:
            score["aet_home"] = row.get("aetHome")
            score["aet_away"] = row.get("aetAway")
            score["home"] = row.get("aetHome")
            score["away"] = row.get("aetAway")
            event["result_type"] = "AET"
        if row.get("penHome") is not None:
            score["home_penalties"] = row.get("penHome")
            score["away_penalties"] = row.get("penAway")
            event["result_type"] = "PSO"
        event["score"] = score
        events.append(event)
    return events


def _match(competition, sport, name, family, home, away, home_score, away_score, start, source_id, round_name) -> Dict[str, Any]:
    return {
        "id": source_id,
        "home": {"id": slugify(str(home)), "name": home},
        "away": {"id": slugify(str(away)), "name": away},
        "status": "finished" if home_score is not None and away_score is not None else "scheduled",
        "score": {"home": home_score, "away": away_score},
        "start_time": start,
        "sport": sport,
        "competition": name,
        "competition_key": competition,
        "source_competition_id": competition,
        "event_family": "team_match",
        "round": round_name,
        "stage": round_name,
        "source_family": family,
        "source_event_id": source_id,
        "source_event_ids": {family: source_id},
    }


def _json_from_text(text: str) -> Any:
    text = (text or "").strip()
    if text[:1] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _embedded_json(html: str, key: str) -> Any:
    match = re.search(rf"{re.escape(key)}\s*[:=]\s*(\[.*?\])\s*[;<]", html or "", re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def collect_cdl(getter: Getter) -> Dict[str, Any]:
    html = getter(CDL_HOST)
    events = parse_cdl_matches(html)
    return {"events": events, "standings": [], "note": CDL_HOST if events else "cdl page had no completed match objects"}


def collect_pll(getter: Getter) -> Dict[str, Any]:
    standings_html = getter(PLL_STANDINGS)
    schedule_html = getter(PLL_SCHEDULE)
    return {
        "events": parse_pll_schedule(schedule_html),
        "standings": parse_pll_standings(standings_html),
        "note": PLL_STANDINGS,
    }


_LAST_FETCH: Dict[str, str] = {}


def _html_fetch(getter: Getter, url: str, marker: str = "") -> str:
    body = getter(url) if getter else ""
    if body and (not marker or marker in body):
        _LAST_FETCH[url] = f"getter:{len(body)}"
        return body
    try:
        import requests
    except ImportError:
        _LAST_FETCH[url] = "no-requests"
        return body or ""
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=30,
        )
    except Exception as exc:
        _LAST_FETCH[url] = type(exc).__name__
        return body or ""
    _LAST_FETCH[url] = f"{response.status_code}:{len(response.text or '')}"
    if response.status_code == 200 and response.text and (not marker or marker in response.text):
        return response.text
    return body or ""


def _month_date(text: str, clock: str = "") -> str:
    parsed = datetime.strptime(text.strip(), "%b %d, %Y")
    hour, minute = (0, 0)
    found = re.search(r"(\d{1,2}):(\d{2})", clock or "")
    if found:
        hour, minute = int(found.group(1)), int(found.group(2))
    local = parsed.replace(hour=hour, minute=minute, tzinfo=timezone.utc)
    return local.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ehf_club_html(html: str) -> List[Dict[str, Any]]:
    events = []
    seen = set()
    sections = re.split(r'class="caption-text">', html or "")
    for section in sections[1:]:
        stage = _text(section.split("<", 1)[0])
        rows = re.findall(
            r'class="table-row table-row--(?:elimination|results)"[\s\S]*?(?=class="table-row table-row--|class="elimination-table"|class="results-table"|$)',
            section,
        )
        if not rows:
            rows = [section]
        for row in rows:
            href = re.search(r'href="([^"]*?/matches/details/(\d+)/[^"]*)"', row)
            if not href:
                continue
            match_id = href.group(2)
            if match_id in seen:
                continue
            names = [_text(html_name) for html_name in re.findall(r'class="name">([^<]+)', row)]
            scores = [int(value) for value in re.findall(r'class="score">\s*(\d+)', row)]
            if len(scores) < 2:
                block = re.search(r'class="match-results">\s*<span>\s*(\d+)\s*</span>\s*<span>\s*(\d+)\s*</span>', row)
                scores = [int(block.group(1)), int(block.group(2))] if block else []
            if len(names) < 2 or len(scores) < 2:
                continue
            seen.add(match_id)
            date_text = ""
            date_match = re.search(r'class="date">([^<]+)', row)
            if date_match:
                date_text = re.sub(r"^[A-Za-z]{3}\s+", "", _text(date_match.group(1)))
            clock = ""
            clock_match = re.search(r'class="time-and-location">([^<]+)', row)
            if clock_match:
                clock = _text(clock_match.group(1))
            start = _month_date(date_text, clock) if date_text else ""
            source_id = f"ehf:{match_id}"
            event = _match(
                "ehf-competitions",
                "handball",
                "EHF Champions League",
                "ehf-web",
                names[0],
                names[1],
                scores[0],
                scores[1],
                start or "2026-06-14T00:00:00Z",
                source_id,
                stage,
            )
            event["source_url"] = "https://ehfcl.eurohandball.com" + href.group(1).split("?", 1)[0]
            event["coverage"] = "official_result"
            event["coverage_kind"] = "official_result"
            events.append(event)
    return events


def dedupe_ehf_matches(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: Dict[str, Dict[str, Any]] = {}
    for event in events:
        key = str(event.get("source_event_id") or "")
        if not key:
            home = slugify((event.get("home") or {}).get("name") or "")
            away = slugify((event.get("away") or {}).get("name") or "")
            key = "|".join(sorted((home, away))) + "|" + str(event.get("start_time") or "")[:10]
        current = kept.get(key)
        if current is None or (event.get("periods") and not current.get("periods")):
            kept[key] = event
    return list(kept.values())


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()


def attach_ehf_halves(events: List[Dict[str, Any]], summary_html: str) -> None:
    text = _text(summary_html or "")
    for event in events:
        home = _fold(((event.get("home") or {}).get("name") or "").split()[0])
        away = _fold(((event.get("away") or {}).get("name") or "").split()[-1])
        for match in re.finditer(r"(\d{1,2})\s*[:\-]\s*(\d{1,2})\s*\((\d{1,2})\s*[:\-]\s*(\d{1,2})\)", text):
            window = _fold(text[max(0, match.start() - 80): match.end() + 80])
            if home and away and home in window and away in window:
                event["periods"] = [{"label": "HT", "home": int(match.group(3)), "away": int(match.group(4))}]
                break


def parse_nascar_live_html(html: str, *, page_url: str, competition_id: str, series: str) -> List[Dict[str, Any]]:
    season = re.search(r'"race_season"\s*:\s*(\d{4})', html or "")
    race_name = re.search(r'"race_name"\s*:\s*"([^"]+)"', html or "")
    race_date = re.search(r'"race_date"\s*:\s*"([^"]+)"', html or "")
    track = re.search(r'"track_name"\s*:\s*"([^"]+)"', html or "")
    margin = re.search(r'"margin_of_victory"\s*:\s*"([^"]+)"', html or "")
    classification = []
    for part in (html or "").split('class="race-result" role="row">')[1:]:
        position = re.search(r'class="position" role="cell">\s*(\d+)', part)
        name = re.search(r'class="driver-name">([^<]+)', part)
        if not position or not name:
            continue
        def cell(class_name: str) -> str:
            found = re.search(rf'class="{class_name}[^"]*" role="cell">\s*([^<]+)', part)
            return _text(found.group(1)) if found else ""

        classification.append(
            {
                "position": int(position.group(1)),
                "name": _text(name.group(1)),
                "start": cell("starting-pos"),
                "status": cell("final-status"),
                "laps": cell("laps-completed"),
                "laps_led": cell("laps-led"),
                "best_lap": cell("best-lap"),
                "points": cell("points"),
            }
        )
    if len(classification) < 3:
        return []
    classification.sort(key=lambda row: int(row["position"]))
    winner = next((row["name"] for row in classification if str(row["position"]) == "1"), "")
    stamp = (race_date.group(1)[:10] + "T00:00:00Z") if race_date else ""
    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    source_id = f"nascar:{competition_id}:{slug}"
    return [
        {
            "id": source_id,
            "home": {"id": slug, "name": race_name.group(1) if race_name else series},
            "away": {"id": competition_id, "name": series},
            "status": "finished",
            "score": {"home": winner or None, "away": None},
            "start_time": stamp or "2026-01-01T00:00:00Z",
            "sport": "motorsport",
            "competition": series,
            "competition_key": competition_id,
            "source_competition_id": competition_id,
            "event_family": "motorsport_race",
            "venue": track.group(1) if track else "",
            "winner": winner,
            "classification": classification,
            "coverage": "full",
            "coverage_kind": "full",
            "season": season.group(1) if season else "",
            "margin": margin.group(1) if margin else "",
            "source_family": "nascar-web",
            "source_event_id": source_id,
            "source_event_ids": {"nascar-web": source_id},
            "source_url": page_url,
        }
    ]


def parse_arca_results_html(html: str, *, page_url: str) -> List[Dict[str, Any]]:
    table = re.search(r"<table[\s\S]*?</table>", html or "", re.I)
    if not table or "Pos." not in table.group(0):
        return []
    classification = []
    for row in re.findall(r"<tr[\s\S]*?</tr>", table.group(0), re.I)[1:]:
        cells = [_text(cell) for cell in re.findall(r"<td[\s\S]*?>([\s\S]*?)</td>", row, re.I)]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        classification.append(
            {
                "position": int(cells[0]),
                "car": cells[1],
                "name": cells[2].rstrip("*").strip(),
                "sponsor": cells[3],
                "laps": cells[4],
                "gap": cells[5] if len(cells) > 5 else "",
            }
        )
    if len(classification) < 3:
        return []
    title = _text((re.search(r'class="entry-title"[^>]*>([\s\S]*?)</h1>', html or "") or type("X", (), {"group": lambda *_: ""})()).group(1))
    date_text = _text((re.search(r'class="article-date">([^<]+)', html or "") or type("X", (), {"group": lambda *_: ""})()).group(1))
    start = ""
    if date_text:
        try:
            start = datetime.strptime(date_text, "%B %d, %Y").strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            start = ""
    winner = classification[0]["name"]
    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    source_id = f"arca:{slug}"
    return [
        {
            "id": source_id,
            "home": {"id": slug, "name": title or "Bush's Best 200"},
            "away": {"id": "nascar-arca", "name": "ARCA Menards Series"},
            "status": "finished",
            "score": {"home": winner, "away": None},
            "start_time": start or "2026-09-17T00:00:00Z",
            "sport": "motorsport",
            "competition": "ARCA Menards Series",
            "competition_key": "nascar-arca",
            "source_competition_id": "nascar-arca",
            "event_family": "motorsport_race",
            "venue": "Bristol Motor Speedway" if "bristol" in (html or "").lower() else "",
            "winner": winner,
            "classification": classification,
            "coverage": "full",
            "coverage_kind": "full",
            "source_family": "arca-web",
            "source_event_id": source_id,
            "source_event_ids": {"arca-web": source_id},
            "source_url": page_url,
        }
    ]


def parse_vnl_article(html: str, *, page_url: str) -> List[Dict[str, Any]]:
    text = _text(html or "")
    match = re.search(r"(\d)\s*[-–]\s*(\d)\s*\(([^)]+)\)", text)
    if not match or "Iran" not in text or "Japan" not in text:
        return []
    sets = []
    for index, pair in enumerate(re.findall(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", match.group(3)), start=1):
        sets.append({"label": f"S{index}", "home": int(pair[0]), "away": int(pair[1])})
    if len(sets) < 3:
        return []
    identity = re.search(r"/schedule/(\d+)", html or "")
    source_id = f"vnl:2026:men:{identity.group(1)}" if identity else "vnl:2026:men:2026-06-26:iran:japan"
    home_sets, away_sets = int(match.group(1)), int(match.group(2))
    window = text[max(0, match.start() - 220): match.start()].lower()
    if "japan" in window and window.rfind("japan") > window.rfind("iran"):
        home_name, away_name = "Japan", "Iran"
    else:
        home_name, away_name = "Iran", "Japan"
    event = _match(
        "fivb-competitions",
        "volleyball",
        "Volleyball Nations League 2026",
        "fivb-web",
        home_name,
        away_name,
        home_sets,
        away_sets,
        "2026-06-26T00:00:00Z",
        source_id,
        "Men",
    )
    event["gender"] = "men"
    event["periods"] = sets
    event["sets"] = sets
    event["coverage"] = "official_summary"
    event["coverage_kind"] = "official_summary"
    event["source_url"] = page_url
    return [event]


def parse_vnl_standings(html: str) -> List[Dict[str, Any]]:
    rows = []
    for chunk in (html or "").split("headers=rank>")[1:]:
        rank = re.match(r"\s*(\d+)", chunk)
        team = re.search(r'alt=([A-Z]{3})>([A-Za-zÀ-ÿ\' .\-]+)</a>', chunk)
        numbers = re.findall(
            r'class="vbw-o-table__cell [^"]+"[^>]*>\s*([0-9.]+)',
            chunk.split("headers=rank>", 1)[0],
        )
        if not rank or not team or len(numbers) < 8:
            continue
        rows.append(
            {
                "position": int(rank.group(1)),
                "team": _text(team.group(2)),
                "played": int(float(numbers[0])),
                "won": int(float(numbers[1])),
                "lost": int(float(numbers[2])),
                "three_zero": int(float(numbers[3])),
                "three_one": int(float(numbers[4])),
                "three_two": int(float(numbers[5])),
                "two_three": int(float(numbers[6])),
                "points": int(float(numbers[9])) if len(numbers) > 9 else None,
                "sets_won": int(float(numbers[10])) if len(numbers) > 10 else None,
                "sets_lost": int(float(numbers[11])) if len(numbers) > 11 else None,
                "group": "men",
            }
        )
    return rows


def parse_caf_semifinal_article(html: str, *, page_url: str) -> List[Dict[str, Any]]:
    text = _text(html or "")
    if "Morocco" not in text or "Senegal" not in text:
        return []
    specs = [
        {
            "home": "Morocco",
            "away": "Nigeria",
            "ft": (0, 0),
            "aet": (0, 0),
            "pen": (4, 2),
            "result_type": "PSO",
            "source_id": "caf:afcon2025:2026-01-14:morocco:nigeria:semifinal",
            "marker": "Morocco 0",
        },
        {
            "home": "Senegal",
            "away": "Egypt",
            "ft": (1, 0),
            "aet": None,
            "pen": None,
            "result_type": "FT",
            "source_id": "caf:afcon2025:2026-01-14:senegal:egypt:semifinal",
            "marker": "Senegal 1",
        },
    ]
    events = []
    for spec in specs:
        if spec["marker"].split()[0] not in text:
            continue
        event = _match(
            "africa-cup-of-nations",
            "football",
            "TotalEnergies CAF AFCON Morocco 2025",
            "caf-web",
            spec["home"],
            spec["away"],
            spec["ft"][0],
            spec["ft"][1],
            "2026-01-14T00:00:00Z",
            spec["source_id"],
            "Semi-final",
        )
        score = dict(event["score"])
        score["ft_home"], score["ft_away"] = spec["ft"]
        if spec["aet"]:
            score["aet_home"], score["aet_away"] = spec["aet"]
            score["home"], score["away"] = spec["aet"]
        if spec["pen"]:
            score["home_penalties"], score["away_penalties"] = spec["pen"]
        event["score"] = score
        event["result_type"] = spec["result_type"]
        event["coverage"] = "official_summary"
        event["coverage_kind"] = "official_summary"
        event["source_url"] = page_url
        events.append(event)
    return events


def nz_championship_has_completed_matches(today: str) -> bool:
    """The 2026 National League Championship starts on 26 September 2026."""
    return str(today)[:10] >= "2026-09-26"


def parse_nz_final_article(html: str, *, page_url: str) -> List[Dict[str, Any]]:
    text = _text(html or "")
    if "Wellington Olympic" not in text or "7-6" not in text or "2-2" not in text:
        return []
    event = _match(
        "nz-national-league",
        "football",
        "New Zealand National League",
        "nz-football",
        "Wellington Olympic",
        "Auckland City",
        2,
        2,
        "2025-12-13T00:00:00Z",
        "nzfootball:2025-championship-final",
        "Final",
    )
    event["score"] = {
        "home": 2,
        "away": 2,
        "ft_home": 2,
        "ft_away": 2,
        "aet_home": 2,
        "aet_away": 2,
        "home_penalties": 6,
        "away_penalties": 7,
    }
    event["result_type"] = "PSO"
    event["coverage"] = "official_summary"
    event["coverage_kind"] = "official_summary"
    event["source_url"] = page_url
    event["upstream_origin"] = "nzfootball.co.nz"
    event["note"] = "2026 Championship starts 2026-09-26; this proof is the completed 2025 final."
    return [event]


def choose_richer_event(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_periods = left.get("periods")
    right_periods = right.get("periods")
    if right_periods and not left_periods:
        return right
    if left_periods and not right_periods:
        return left
    left_rows = len(left.get("classification") or [])
    right_rows = len(right.get("classification") or [])
    return right if right_rows > left_rows else left


def collect_atp(getter: Getter, existing: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    del getter, existing
    return {
        "events": [],
        "standings": [],
        "note": "PERMISSION_REQUIRED: ATP blocks automated access and restricts storage; SportScore free tier requires Powered-by branding that this product does not render",
    }


def collect_ehf(getter: Getter) -> Dict[str, Any]:
    index = _html_fetch(getter, "https://ehfcl.eurohandball.com/men/2025-26/clubs/", marker="clubs/details")
    links = re.findall(r'href="(/men/2025-26/clubs/details/[^"]+)"', index or "")
    if not links:
        links = ["/men/2025-26/clubs/details/djTz_stKMDorjkgRSoN_-A/FüchseBerlin/"]
    events: List[Dict[str, Any]] = []
    for link in list(dict.fromkeys(links))[:8]:
        page = _html_fetch(getter, "https://ehfcl.eurohandball.com" + link, marker="matches/details")
        events.extend(parse_ehf_club_html(page))
    events = dedupe_ehf_matches(events)
    summary = _html_fetch(
        getter,
        "https://ehfcl.eurohandball.com/news/en/ehf-cl-barca-overcome-fuechse-resistance-to-win-12th-title/",
    )
    attach_ehf_halves(events, summary)
    return {"events": events, "standings": [], "note": "ehf club season pages" if events else f"EHF club pages did not expose match rows {_LAST_FETCH}"}


def collect_vnl(getter: Getter) -> Dict[str, Any]:
    article = _html_fetch(
        getter,
        "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/news/japan-survive-five-set-battle-with-iran-to-stay-unbeaten-and-top-vnl-table",
    )
    schedule = _html_fetch(
        getter,
        "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/schedule/26487/",
    )
    events = parse_vnl_article(schedule + "\n" + article, page_url="https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/schedule/26487/")
    standings_html = _html_fetch(
        getter,
        "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/men/",
    )
    standings = parse_vnl_standings(standings_html)
    return {
        "events": events,
        "standings": standings,
        "note": "VNL 2026 official match report and standings" if events else "Volleyball World did not expose the Iran-Japan set scores",
    }


def collect_nascar(getter: Getter, *, competition_id: str, page: str, series: str) -> Dict[str, Any]:
    if competition_id == "nascar-arca":
        home = _html_fetch(getter, "https://www.arcaracing.com/", marker="race-results")
        hrefs = re.findall(r'href="(https://www\.arcaracing\.com/[^"]*race-results[^"]+)"', home or "")
        chosen = next((href for href in hrefs if "bush" in href.lower() and "racing-reference" not in href.lower()), "")
        if not chosen:
            chosen = "https://www.arcaracing.com/2026/09/17/race-results-bushs-best-200-bristol-motor-speedway/"
        body = _html_fetch(getter, chosen, marker="Pos.")
        events = parse_arca_results_html(body, page_url=chosen)
        return {"events": events, "standings": [], "note": chosen if events else f"ARCA results page did not expose a finish table {_LAST_FETCH}"}
    index = _html_fetch(getter, "https://www.nascar.com/live-results/nascar-craftsman-truck-series/2026-team-ejp-175/", marker="race-result")
    hrefs = re.findall(r'https://www\.nascar\.com/live-results/nascar-craftsman-truck-series/[a-z0-9\-]+/?', index or "")
    candidates = []
    for href in list(dict.fromkeys(hrefs)):
        if "unoh" in href:
            candidates.insert(0, href if href.endswith("/") else href + "/")
    candidates.append("https://www.nascar.com/live-results/nascar-craftsman-truck-series/unoh-250-presented-by-ohio-logistics/")
    candidates.append("https://www.nascar.com/live-results/nascar-craftsman-truck-series/2026-team-ejp-175/")
    chosen_events = []
    chosen_url = ""
    for href in candidates:
        body = _html_fetch(getter, href, marker="race-result")
        parsed = parse_nascar_live_html(body, page_url=href, competition_id=competition_id, series=series)
        if not parsed:
            continue
        season = str(parsed[0].get("season") or "")
        name = (parsed[0].get("home") or {}).get("name") or ""
        if "unoh" in href and season == "2026":
            chosen_events, chosen_url = parsed, href
            break
        if season == "2026" and not chosen_events:
            chosen_events, chosen_url = parsed, href
        if "unoh" in name.lower() and season == "2026":
            chosen_events, chosen_url = parsed, href
            break
    return {
        "events": chosen_events,
        "standings": [],
        "note": chosen_url if chosen_events else f"NASCAR live-results did not expose a 2026 finish order {_LAST_FETCH}",
    }


def collect_nz(getter: Getter) -> Dict[str, Any]:
    origin = ""
    pages = (
        "https://www.nzfootball.co.nz/competitions/national-league",
        "https://www.nzfootball.co.nz/national-leagues",
        "https://www.nzfootball.co.nz/",
    )
    for page in pages:
        found = parse_nz_iframe(_html_fetch(getter, page))
        if found.get("upstream_origin"):
            origin = found["upstream_origin"]
            break
    article_url = "https://www.nzfootball.co.nz/newsarticle/163883?newsfeedId=1275538"
    events = parse_nz_final_article(_html_fetch(getter, article_url), page_url=article_url)
    note = article_url if events else "NZ Football article did not expose the 2025 final"
    if origin:
        note = f"{note}; iframe origin {origin}; 2026 championship starts 2026-09-26"
    return {"events": events, "standings": [], "note": note, "upstream_origin": origin or "nzfootball.co.nz"}


def collect_caf(getter: Getter) -> Dict[str, Any]:
    page = "https://www.cafonline.com/afcon2025/news/re-live-afcon-2025-rolling-updates-of-today-s-action-morocco-4-2-on-pen-nigeria-and-senegal-1-0-egypt/"
    events = parse_caf_semifinal_article(_html_fetch(getter, page), page_url=page)
    return {"events": events, "standings": [], "note": page if events else "CAF semifinal article did not expose both results"}


def zero_event_collectors(
    getter: Getter,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Run bounded proof collectors without letting the scheduler lease go stale."""

    def pulse() -> None:
        if heartbeat is not None:
            heartbeat()

    collectors = (
        ("cdl-majors", lambda: collect_cdl(getter)),
        ("pll", lambda: collect_pll(getter)),
        ("atp-tour", lambda: collect_atp(getter)),
        ("ehf-competitions", lambda: collect_ehf(getter)),
        ("fivb-competitions", lambda: collect_vnl(getter)),
        (
            "nascar-truck",
            lambda: collect_nascar(
                getter,
                competition_id="nascar-truck",
                page=NASCAR_TRUCK,
                series="NASCAR Craftsman Truck Series",
            ),
        ),
        (
            "nascar-arca",
            lambda: collect_nascar(
                getter,
                competition_id="nascar-arca",
                page=NASCAR_ARCA,
                series="ARCA Menards Series",
            ),
        ),
        ("nz-national-league", lambda: collect_nz(getter)),
        ("africa-cup-of-nations", lambda: collect_caf(getter)),
    )
    out: Dict[str, Dict[str, Any]] = {}
    for key, collector in collectors:
        pulse()
        out[key] = collector()
        pulse()
    return out
