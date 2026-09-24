"""Reusable HTML/JSON document parsers for family adapters.

Not competition-specific. Extracts events from tables, JSON-LD, Next.js
payloads, and public JSON blobs already present on verified pages.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse

from datetime import datetime, timezone

from collector.util import slugify

JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
NEXT_RE = re.compile(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.I | re.S)
NUXT_DATA_RE = re.compile(r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', re.I | re.S)
ESPNFITT_RE = re.compile(r"window\[['\"]__espnfitt__['\"]\]\s*=\s*", re.I)
NUXT_ASSIGN_RE = re.compile(r"window\.__NUXT__\s*=\s*", re.I)
TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
CELL_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
SCORE_CELL = re.compile(r"^\s*(\d{1,3})\s*[-–:]\s*(\d{1,3})\s*$")
VS_CELL = re.compile(r"^\s*(.+?)\s+(?:vs\.?|v)\s+(.+?)\s*$", re.I)
DATE_RE = re.compile(
    r"\b(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2}|"
    r"\d{1,2}\.\d{1,2}\.20\d{2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s*20\d{2})?)\b",
    re.I,
)
FIXTURE_PATH = re.compile(
    r"/(fixture|fixtures|results?|matches|schedule|draw|scores?|timetable|calendar|games|"
    r"races?|resultados|tabela|classement|fechas|jogos|partidas|meetings?|courses|arriv|"
    r"spielbericht|spielplan|ergebnisse|partido|zapasy|kampprogram|scoreboard|calendar)(/|$|\?)",
    re.I,
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
EVENT_LIST_KEYS = {
    "events",
    "evts",
    "matches",
    "games",
    "fixtures",
    "results",
    "meetings",
    "races",
    "sessions",
    "bouts",
    "fights",
    "cards",
    "schedule",
        "eventgroups",
        "partidos",
        "kampprogram",
        "meetings",
        "ottelut",
    }

SKIP_WALK_KEYS = {
    "ads",
    "analytics",
    "footer",
    "routing",
    "featuregating",
    "videos",
    "nws",
    "articles",
    "tms",
    "viewport",
    "user",
}

JUNK_NAMES = {
    "tournament",
    "event",
    "match",
    "home",
    "away",
    "team",
    "vs",
    "v",
    "sex",
    "cheval",
    "driver",
    "entraineur",
    "mannschaft",
    "horse name",
    "betting ui interaction",
    "cookie",
    "subscribe",
    "newsletter",
    "sign in",
}


def _text(value: str) -> str:
    from collector.participant_text import strip_flag_abbr_html

    clean = strip_flag_abbr_html(value or "")
    clean = TAG_RE.sub(" ", clean)
    return WS_RE.sub(" ", clean).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def _junk_name(name: str) -> bool:
    text = (name or "").strip().lower()
    if not text or text in JUNK_NAMES:
        return True
    if any(token in text for token in ("betting", "cookie", "subscribe", "analytics", "newsletter", "like us", "follow us", "arrow_drop", "realtime")):
        return True
    return False


def _team_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        nested = value.get("team") or value.get("competitor") or value.get("athlete")
        if isinstance(nested, dict):
            nested_name = _team_name(nested)
            if nested_name:
                return nested_name
        for key in (
            "name",
            "fullName",
            "shortName",
            "teamName",
            "strTeam",
            "displayName",
            "shortDisplayName",
            "abbrev",
            "label",
            "title",
        ):
            if value.get(key):
                return str(value.get(key)).strip()
        name = value.get("nameFirst") or value.get("firstName")
        last = value.get("nameLast") or value.get("lastName")
        if name or last:
            return f"{name or ''} {last or ''}".strip()
    return ""


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _iso_date(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    dotted = re.match(r"^(\d{1,2})\.(\d{1,2})\.(20\d{2})", text)
    if dotted:
        day, month, year = dotted.group(1), dotted.group(2), dotted.group(3)
        clock = re.search(r"(\d{1,2}:\d{2})", text)
        stamp = f"{year}-{int(month):02d}-{int(day):02d}"
        if clock:
            return f"{stamp}T{clock.group(1)}:00Z"
        return stamp
    if "T" in text:
        if text.endswith("Z") or "+" in text[10:] or text.endswith("Z"):
            return text
        return text
    match = DATE_RE.search(text)
    if match:
        return match.group(0)
    if re.match(r"20\d{2}-\d{2}-\d{2}$", text):
        return text
    return text if len(text) >= 8 else None


def _event(
    *,
    home: str,
    away: str = "",
    start: Optional[str] = None,
    status: str = "scheduled",
    home_score: Any = None,
    away_score: Any = None,
    venue: Optional[str] = None,
    source_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    home = (home or "").strip()
    away = (away or "").strip()
    if not home:
        return None
    if home.lower() in {"home", "team", "date", "time", "versus"} or _junk_name(home):
        return None
    payload = {
        "id": source_id or f"{slugify(home)}-{slugify(away)}-{start or ''}",
        "home": {"name": home},
        "away": {"name": away},
        "status": status,
        "score": {"home": home_score, "away": away_score},
        "start_time": _iso_date(start),
        "venue": venue,
    }
    if payload["start_time"] and "T" not in str(payload["start_time"]):
        payload["start_precision"] = "DATE_ONLY"
    if extra:
        payload.update(extra)
    if home_score not in (None, "") and away_score not in (None, "") and status == "scheduled":
        payload["status"] = "finished"
    return payload


def parse_jsonld(html: str) -> List[Dict[str, Any]]:
    events = []
    for blob in JSONLD_RE.findall(html or ""):
        try:
            data = json.loads(blob)
        except (TypeError, ValueError):
            continue
        for node in _as_list(data):
            events.extend(_jsonld_node(node))
    return _dedupe(events)


def _jsonld_node(node: Any) -> List[Dict[str, Any]]:
    out = []
    if isinstance(node, list):
        for item in node:
            out.extend(_jsonld_node(item))
        return out
    if not isinstance(node, dict):
        return out
    types = node.get("@type") or node.get("type") or ""
    if isinstance(types, list):
        types = " ".join(str(item) for item in types)
    if "SportsEvent" in str(types) or str(types) == "Event":
        home = _team_name(node.get("homeTeam") or node.get("competitor") or {})
        away = ""
        competitors = node.get("competitor") or node.get("performers") or []
        if isinstance(competitors, list) and len(competitors) >= 2:
            home = _team_name(competitors[0]) or home
            away = _team_name(competitors[1])
        elif isinstance(node.get("awayTeam"), (dict, str)):
            away = _team_name(node.get("awayTeam"))
        name = node.get("name") or ""
        if not home and " vs " in str(name).lower():
            left, right = re.split(r"\s+vs\.?\s+", str(name), maxsplit=1, flags=re.I)
            home, away = left, right
        event = _event(
            home=home or str(name),
            away=away,
            start=node.get("startDate") or node.get("startTime"),
            venue=_team_name(node.get("location")) if not isinstance(node.get("location"), str) else node.get("location"),
            source_id=str(node.get("@id") or node.get("identifier") or name),
        )
        if event:
            out.append(event)
    for key in ("@graph", "itemListElement", "subEvent", "event"):
        if key in node:
            out.extend(_jsonld_node(node.get(key)))
    return out


def parse_next_data(html: str) -> List[Dict[str, Any]]:
    match = NEXT_RE.search(html or "")
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return []
    return walk_json_events(payload)


def _racing_meeting_events(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    meetings = []
    if isinstance(payload.get("meetings"), list):
        meetings = payload.get("meetings") or []
    elif isinstance(payload.get("races"), list) and (payload.get("name") or payload.get("course") or payload.get("meetingName")):
        meetings = [payload]
    events: List[Dict[str, Any]] = []
    for meeting in meetings[:40]:
        if not isinstance(meeting, dict):
            continue
        course = str(
            meeting.get("name")
            or meeting.get("course")
            or meeting.get("meetingName")
            or meeting.get("venue")
            or ""
        ).strip()
        races = meeting.get("races") if isinstance(meeting.get("races"), list) else []
        if not races and course:
            start = meeting.get("date") or meeting.get("offTime") or meeting.get("start_time")
            event = _event(home=course, away="meeting", start=start, extra={"event_family": "racing"})
            if event:
                events.append(event)
            continue
        for race in races[:30]:
            if not isinstance(race, dict):
                continue
            number = race.get("raceNumber") or race.get("number") or race.get("race_number")
            winner = _team_name(race.get("winner") or race.get("horse") or race.get("first") or "")
            start = race.get("offTime") or race.get("start_time") or race.get("time") or meeting.get("date")
            home = f"R{number}" if number else (winner or course or "Race")
            away = course or "meeting"
            if home == away:
                away = course or "meeting"
            event = _event(
                home=home,
                away=away,
                start=start,
                status="finished" if winner else "scheduled",
                extra={"event_family": "racing", "venue": course, "winner": winner or None, "race_number": number},
            )
            if event:
                events.append(event)
    return events


def walk_json_events(payload: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 8:
        return []
    events: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        converted = [item for item in (_dict_event(row) for row in payload) if item]
        if converted and len(converted) >= max(1, len(payload) // 4):
            return converted[:80]
        for row in payload[:80]:
            events.extend(walk_json_events(row, depth=depth + 1))
        return _dedupe(events)
    if isinstance(payload, dict):
        racing = _racing_meeting_events(payload)
        if racing:
            events.extend(racing)
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in SKIP_WALK_KEYS:
                continue
            if lowered in EVENT_LIST_KEYS and isinstance(value, list):
                converted = [item for item in (_dict_event(row) for row in value) if item]
                events.extend(converted)
                if not converted:
                    events.extend(walk_json_events(value, depth=depth + 1))
            else:
                events.extend(walk_json_events(value, depth=depth + 1))
        direct = _dict_event(payload)
        if direct and not events:
            events.append(direct)
    return _dedupe(events)


def _dict_event(row: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    home = _team_name(
        row.get("home")
        or row.get("homeTeam")
        or row.get("home_team")
        or row.get("team1")
        or row.get("team1_name")
        or row.get("hometeam")
        or row.get("radiant_name")
        or row.get("fighterA")
        or row.get("red")
        or row.get("local")
        or row.get("localTeam")
        or row.get("equipoLocal")
        or row.get("teamHome")
        or row.get("home_name")
    )
    away = _team_name(
        row.get("away")
        or row.get("awayTeam")
        or row.get("away_team")
        or row.get("team2")
        or row.get("team2_name")
        or row.get("awayteam")
        or row.get("dire_name")
        or row.get("fighterB")
        or row.get("blue")
        or row.get("visitor")
        or row.get("visitorTeam")
        or row.get("equipoVisitante")
        or row.get("teamAway")
        or row.get("away_name")
    )
    if not home:
        competitors = row.get("competitors") or row.get("teams") or row.get("participants") or []
        if isinstance(competitors, list) and len(competitors) >= 2:
            home_row = next((item for item in competitors if isinstance(item, dict) and item.get("homeAway") == "home"), None)
            away_row = next((item for item in competitors if isinstance(item, dict) and item.get("homeAway") == "away"), None)
            if home_row and away_row:
                home = _team_name(home_row)
                away = _team_name(away_row)
                row = dict(row)
                row["_home_row"] = home_row
                row["_away_row"] = away_row
            else:
                home = _team_name(competitors[0])
                away = _team_name(competitors[1])
    meeting = (
        row.get("meeting_name")
        or row.get("raceName")
        or row.get("eventName")
        or row.get("tournament")
        or row.get("ShortDescription")
        or row.get("Description")
    )
    if not meeting and (row.get("circuit") or row.get("circuit_short_name") or row.get("meeting_key") or row.get("date_start")):
        meeting = row.get("name")
    if not home and meeting:
        home = str(meeting)
        away = _team_name(row.get("circuit_short_name") or row.get("circuit") or row.get("location") or "")
        extra = {
            "event_family": "motorsport_race"
            if row.get("circuit_short_name") or row.get("session_key") or row.get("circuit")
            else "tournament"
        }
        return _event(
            home=home,
            away=away,
            start=row.get("date_start")
            or row.get("date")
            or row.get("start_time")
            or row.get("startDate")
            or row.get("StartDate"),
            venue=away or str(row.get("location") or ""),
            source_id=str(row.get("meeting_key") or row.get("session_key") or row.get("id") or row.get("EventId") or meeting),
            extra=extra,
        )
    if not home:
        race_no = row.get("raceNumber") or row.get("race_number") or row.get("raceNo")
        course = _team_name(row.get("course") or row.get("track") or row.get("venue") or row.get("meeting") or "")
        if race_no and course:
            return _event(
                home=f"Race {race_no}",
                away=course,
                start=row.get("offTime") or row.get("off_time") or row.get("time") or row.get("date"),
                extra={"event_family": "racing"},
            )
        if row.get("startAt") and row.get("name"):
            start = row.get("startAt")
            if isinstance(start, (int, float)) and start > 10_000:
                start = datetime_from_unix(start)
            return _event(
                home=str(row.get("name")),
                away="bracket",
                start=start,
                extra={"event_family": "tournament"},
            )
        return None
    score = row.get("score") if isinstance(row.get("score"), dict) else {}
    home_score = _first_defined(
        score.get("home"),
        row.get("homeScore"),
        row.get("intHomeScore"),
        row.get("hscore"),
        row.get("team1_score"),
        row.get("homeTeamScore"),
        row["home"].get("score") if isinstance(row.get("home"), dict) else None,
        row["_home_row"].get("score") if isinstance(row.get("_home_row"), dict) else None,
    )
    away_score = _first_defined(
        score.get("away"),
        row.get("awayScore"),
        row.get("intAwayScore"),
        row.get("ascore"),
        row.get("team2_score"),
        row.get("awayTeamScore"),
        row["away"].get("score") if isinstance(row.get("away"), dict) else None,
        row["_away_row"].get("score") if isinstance(row.get("_away_row"), dict) else None,
    )
    status_raw = row.get("status") or row.get("state") or row.get("eventStatus") or row.get("statusReason") or "scheduled"
    if isinstance(status_raw, dict):
        status_raw = status_raw.get("code") or status_raw.get("name") or "scheduled"
    status = str(status_raw).lower()
    if status in {"ft", "full-time", "full_time", "complete", "completed"}:
        status = "finished"
    return _event(
        home=home,
        away=away,
        start=row.get("start_time")
        or row.get("startTime")
        or row.get("startDate")
        or row.get("date")
        or row.get("kickoff")
        or row.get("utcDate")
        or row.get("match_date"),
        status=status if status in {"scheduled", "live", "finished"} else "scheduled",
        home_score=home_score,
        away_score=away_score,
        venue=row.get("venue") or row.get("stadium") or row.get("location"),
        source_id=str(row.get("id") or row.get("matchId") or row.get("gameId") or f"{home}-{away}"),
    )


def parse_tables(html: str) -> List[Dict[str, Any]]:
    events = []
    for table in TABLE_RE.findall(html or "")[:20]:
        rows = []
        for row_html in ROW_RE.findall(table)[:80]:
            cells = [_text(cell) for cell in CELL_RE.findall(row_html)]
            cells = [cell for cell in cells if cell]
            if len(cells) >= 2:
                rows.append(cells)
        for cells in rows:
            event = _row_event(cells)
            if event:
                events.append(event)
    return _dedupe(events)


def _row_event(cells: List[str]) -> Optional[Dict[str, Any]]:
    joined = " | ".join(cells)
    if joined.lower() in {"home", "team"} or "played" in joined.lower() and "pts" in joined.lower():
        return None
    home = away = ""
    home_score = away_score = None
    start = None
    for cell in cells:
        date = DATE_RE.search(cell)
        if date and not start:
            start = date.group(0)
        score = SCORE_CELL.match(cell)
        if score:
            home_score, away_score = int(score.group(1)), int(score.group(2))
            continue
        vs = VS_CELL.match(cell)
        if vs:
            home, away = vs.group(1).strip(), vs.group(2).strip()
    if not home and len(cells) >= 3:
        # common: date, home, score, away
        maybe_score_idx = next((i for i, cell in enumerate(cells) if SCORE_CELL.match(cell)), None)
        if maybe_score_idx and maybe_score_idx > 0 and maybe_score_idx + 1 < len(cells):
            home = cells[maybe_score_idx - 1]
            away = cells[maybe_score_idx + 1]
            if DATE_RE.search(home or ""):
                start = home
                home = None
        elif len(cells) >= 2 and not SCORE_CELL.match(cells[0]):
            home, away = cells[0], cells[1]
            if DATE_RE.search(home):
                start = home
                home, away = cells[1], cells[2] if len(cells) > 2 else ""
    datetime_name = re.compile(
        r"^\d{1,2}[./]\s*\d{1,2}[./]\s*\d{2,4}(\s+\d{1,2}:\d{2})?$|^\d{4}-\d{2}-\d{2}([ T]\d{1,2}:\d{2})?$"
    )
    if datetime_name.match(home or "") or datetime_name.match(away or ""):
        return None
    if home and away and home != away and not home.isdigit() and not away.isdigit():
        if home.lower() in {"home", "team", "date", "pts", "played"}:
            return None
        return _event(home=home, away=away, start=start, home_score=home_score, away_score=away_score)
    return None


def parse_plaintext_scores(html: str) -> List[Dict[str, Any]]:
    text = _text(html)[:40000]
    events = []
    pattern = re.compile(
        r"([^\W\d_][\w .'\-]{2,40})\s+(\d{1,3})\s*[-–]\s*(\d{1,3})\s+([^\W\d_][\w .'\-]{2,40})",
        re.U,
    )
    vs_pattern = re.compile(
        r"([^\W\d_][\w .'\-]{2,40})\s+vs\.?\s+([^\W\d_][\w .'\-]{2,40})",
        re.I | re.U,
    )
    for index, match in enumerate(pattern.finditer(text)):
        event = _event(
            home=match.group(1),
            away=match.group(4),
            home_score=int(match.group(2)),
            away_score=int(match.group(3)),
            status="finished",
            source_id=f"score-{index}",
        )
        if event:
            events.append(event)
        if len(events) >= 25:
            break
    if events:
        return _dedupe(events)
    for index, match in enumerate(vs_pattern.finditer(text)):
        event = _event(home=match.group(1), away=match.group(2), source_id=f"vs-{index}")
        if event:
            events.append(event)
        if len(events) >= 25:
            break
    return _dedupe(events)


def fixture_urls(html: str, base_url: str) -> List[str]:
    found = []
    host = urlparse(base_url).netloc
    for href in HREF_RE.findall(html or ""):
        if not FIXTURE_PATH.search(href):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != host:
            continue
        if absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        found.append(absolute)
    return list(dict.fromkeys(found))[:5]


def parse_initial_data(html: str) -> List[Dict[str, Any]]:
    data = _quoted_window_json(html, "__INITIAL_DATA__") or _quoted_window_json(html, "__PRELOADED_STATE__")
    if data is None:
        return []
    return walk_json_events(data)


def _quoted_window_json(html: str, marker: str) -> Any:
    """Decode BBC-style window hydration with optional whitespace.

    BBC has emitted both:
      window.__INITIAL_DATA__="<escaped json>"
      window.__INITIAL_DATA__ = "<escaped json>";
    Keep this parser tolerant while still decoding only the requested marker.
    """
    source = html or ""
    match = re.search(
        rf"(?:window\.)?{re.escape(marker)}\s*=\s*\"",
        source,
    )
    if not match:
        return None
    index = match.end()
    buf = []
    while index < len(source):
        char = source[index]
        if char == "\\" and index + 1 < len(source):
            buf.append(source[index : index + 2])
            index += 2
            continue
        if char == '"':
            break
        buf.append(char)
        index += 1
    encoded = "".join(buf)
    try:
        decoded = json.loads('"' + encoded + '"')
        if isinstance(decoded, str):
            return json.loads(decoded)
        return decoded
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        try:
            decoded = encoded.encode("utf-8").decode("unicode_escape")
            return json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
            return None

def _decode_js_object(html: str, match: re.Match) -> Any:
    try:
        obj, _end = json.JSONDecoder().raw_decode(html[match.end() :])
        return obj
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_espnfitt(html: str) -> List[Dict[str, Any]]:
    match = ESPNFITT_RE.search(html or "")
    if not match:
        return []
    payload = _decode_js_object(html, match)
    if not isinstance(payload, dict):
        return []
    board = ((payload.get("page") or {}).get("content") or {}).get("scoreboard") or {}
    rows = board.get("evts") or board.get("events") or []
    events = [item for item in (_dict_event(row) for row in rows) if item]
    if events:
        return events
    return walk_json_events(board)[:80]


def parse_nuxt_data(html: str) -> List[Dict[str, Any]]:
    match = NUXT_DATA_RE.search(html or "")
    if match:
        try:
            payload = json.loads(match.group(1))
        except (TypeError, ValueError):
            payload = None
        if payload is not None:
            events = walk_json_events(payload)
            if events:
                return events
    assign = NUXT_ASSIGN_RE.search(html or "")
    if not assign:
        return []
    payload = _decode_js_object(html, assign)
    if payload is None:
        return []
    return walk_json_events(payload)


def parse_liquipedia_html(html: str) -> List[Dict[str, Any]]:
    events = []
    blocks = re.split(r'(?=<div[^>]+class="[^"]*match-info(?:\s|")[^"]*")', html or "", flags=re.I)
    name_re = re.compile(
        r'class="name"[^>]*>\s*<a[^>]*>([^<]+)</a>|class="[^"]*team-template-text[^"]*"[^>]*>([^<]+)',
        re.I,
    )
    score_re = re.compile(r'class="[^"]*match-info-header-scoreholder-score[^"]*"[^>]*>([^<]+)', re.I)
    sources = blocks if len(blocks) > 2 else [html or ""]
    for block in sources:
        names = []
        for match in name_re.findall(block):
            label = (match[0] or match[1] or "").strip()
            if label:
                names.append(label)
        names = list(dict.fromkeys(names))
        if len(names) < 2:
            continue
        scores = [item.strip() for item in score_re.findall(block)]
        home_score = away_score = None
        if len(scores) >= 2:
            try:
                home_score = int(scores[0])
                away_score = int(scores[1])
            except (TypeError, ValueError):
                home_score = away_score = None
        event = _event(home=names[0], away=names[1], home_score=home_score, away_score=away_score)
        if event:
            events.append(event)
        if len(events) >= 40:
            break
    if events:
        return _dedupe(events)
    teams = [item.strip() for item in re.findall(r'class="[^"]*team-template-text[^"]*"[^>]*>([^<]+)', html or "", re.I)]
    for index in range(0, len(teams) - 1, 2):
        event = _event(home=teams[index], away=teams[index + 1])
        if event:
            events.append(event)
        if len(events) >= 40:
            break
    return _dedupe(events)


def datetime_from_unix(value: Any) -> Optional[str]:
    try:
        stamp = float(value)
    except (TypeError, ValueError):
        return None
    if stamp > 10_000_000_000:
        stamp = stamp / 1000.0
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_html(html: str, base_url: str = "") -> List[Dict[str, Any]]:
    events = parse_espnfitt(html)
    if events:
        return events[:80]
    events = parse_jsonld(html)
    if events:
        return events[:80]
    events.extend(parse_next_data(html))
    if events:
        return _dedupe(events)[:80]
    events.extend(parse_nuxt_data(html))
    if events:
        return _dedupe(events)[:80]
    events.extend(parse_initial_data(html))
    if events:
        return _dedupe(events)[:80]
    if "team-template-text" in (html or "") or "match-info" in (html or ""):
        events.extend(parse_liquipedia_html(html))
    if events:
        return _dedupe(events)[:80]
    events.extend(parse_tables(html))
    if events:
        return _dedupe(events)[:80]
    events.extend(parse_plaintext_scores(html))
    return _dedupe(events)[:80]


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return [value]


def _dedupe(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for event in events:
        home = (event.get("home") or {}).get("name") or ""
        away = (event.get("away") or {}).get("name") or ""
        key = (
            slugify(home),
            slugify(away),
            str(event.get("start_time") or "")[:16],
            str(event.get("source_event_id") or ""),
            str(event.get("race_number") or ""),
            str(event.get("round") or event.get("stage") or ""),
            str(event.get("game_id") or ""),
        )
        if key in seen or not home:
            continue
        seen.add(key)
        out.append(event)
    return out
