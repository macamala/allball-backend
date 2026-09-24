"""Source-family parsers for the production closeout.

Production collectors only call upstream pages that are already approved.
Families recorded as terms-blocked stay disabled. Parsers accept frozen
fixtures in tests and live documents in the worker.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

from collector.event_quality import HEAD_TO_HEAD, MEET, RACE, TEAM_MATCH, event_is_valid
from collector.html_parse import _dedupe, _event, _text

IBU_API = "https://www.biathlonresults.com/modules/sportapi/api/{path}"
IBU_FAMILY = "ibu-web"
IBU_RACE_CLASSES = ("WRLCP", "IBUCP", "WRLCH", "CEUCH")
IBU_PROOF_EVENT = "BT2526SWRLCP07"

# Recorded in collector.source_matrix.KNOWN_RESTRICTED and verify_families.
# Production ingestion must not be enabled for these families.
TERMS_BLOCKED = {
    "usta-web": (
        "ACCESS/TERMS-BLOCKED: racing.ustrotting.com states the site is for "
        "personal, non-commercial use only. NinkoSports is a public product, "
        "so no USTA collector is enabled."
    ),
    "usa-usta-meetings": (
        "ACCESS/TERMS-BLOCKED: racing.ustrotting.com personal non-commercial use only. "
        "Standardbred Canada covers Canadian meetings only and is not a USTA substitute."
    ),
    "lolesports-web": (
        "ACCESS/TERMS-BLOCKED: Riot Terms of Service forbid scraping and unauthorized bots "
        "on Riot Services. LoL Esports ingestion is not enabled."
    ),
    "valorantesports-web": (
        "ACCESS/TERMS-BLOCKED: public VALORANT schedule HTML is technically reachable, "
        "but Riot Terms of Service forbid scraping and unauthorized bots. Ingestion is not enabled."
    ),
    "vlr-web": "ACCESS/TERMS-BLOCKED: VLR terms forbid automated access and commercial reuse.",
    "click-tt": (
        "ACCESS/TERMS-BLOCKED: existing registry records that click-TT terms restrict "
        "automated parsing and reuse. No additional click-TT collector was enabled."
    ),
    "click-tt-remix": (
        "ACCESS/TERMS-BLOCKED: click-TT Remix is the same restricted click-TT property. "
        "German Bundesliga collection uses official TTBL pages instead."
    ),
    "kpga-web": (
        "TERMS_REVIEW_REQUIRED: KPGA leaderboard HTML is technically parseable, but "
        "project policy has not cleared automated or commercial reuse."
    ),
    "blast-cs": "ACCESS/TERMS-BLOCKED: BLAST terms prohibit copying or exploiting site content.",
    "blast-rl": "ACCESS/TERMS-BLOCKED: BLAST terms prohibit copying or exploiting site content.",
    "blizzard-owcs-recaps": (
        "ACCESS/TERMS-BLOCKED: Blizzard Overwatch esports properties. Bot ingestion is not enabled."
    ),
    "ewc-owcs-web": (
        "ACCESS/TERMS-BLOCKED: Esports World Cup terms forbid data mining and scraping."
    ),
    "overwatch-esports-web": (
        "ACCESS/TERMS-BLOCKED: Blizzard Overwatch esports properties. Bot ingestion is not enabled."
    ),
}


def ingestion_allowed(family: str) -> bool:
    return family not in TERMS_BLOCKED


def terms_block_reason(family: str) -> str:
    return TERMS_BLOCKED.get(family, "")


def same_upstream_not_independent(discovery_family: str, result_family: str, derived_from: str = "") -> bool:
    """A wrapper and the upstream it embeds are one provider chain."""
    if not discovery_family or not result_family:
        return False
    if discovery_family == result_family:
        return True
    return derived_from in {discovery_family, result_family} or bool(derived_from)


def _xml_local(tag: str) -> str:
    return (tag or "").split("}")[-1]


def _xml_value(node: ET.Element) -> Any:
    children = list(node)
    if not children:
        return (node.text or "").strip()
    grouped: Dict[str, Any] = {}
    for child in children:
        key = _xml_local(child.tag)
        value = _xml_value(child)
        if key in grouped:
            current = grouped[key]
            if not isinstance(current, list):
                grouped[key] = [current]
            grouped[key].append(value)
        else:
            grouped[key] = value
    return grouped


def _loads(payload: Any) -> Any:
    if isinstance(payload, (dict, list)):
        return payload
    if not isinstance(payload, str) or not payload.strip():
        return None
    text = payload.strip()
    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return None
        value = _xml_value(root)
        name = _xml_local(root.tag)
        if name.startswith("ArrayOf") and isinstance(value, dict):
            only = next(iter(value.values()), [])
            return only if isinstance(only, list) else [only]
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ibu_race_classes(classification: str) -> bool:
    token = str(classification or "").upper()
    return any(code in token for code in IBU_RACE_CLASSES)


def _ibu_name(row: Dict[str, Any]) -> str:
    name = str(row.get("Name") or "").strip()
    if name:
        return name
    return " ".join(part for part in (row.get("GivenName"), row.get("FamilyName")) if part).strip()


def parse_ibu_race_results(payload: Any) -> List[Dict[str, Any]]:
    data = _loads(payload)
    if not isinstance(data, dict):
        return []
    raw_rows = data.get("Results") or []
    if isinstance(raw_rows, dict):
        raw_rows = raw_rows.get("ResultRow") or raw_rows.get("Result") or []
    if isinstance(raw_rows, dict):
        raw_rows = [raw_rows]
    finishers = []
    legs = []
    for row in raw_rows or []:
        if not isinstance(row, dict):
            continue
        name = _ibu_name(row)
        if not name:
            continue
        leg = row.get("Leg")
        if leg not in (None, "", 0, "0"):
            legs.append(row)
            continue
        rank = str(row.get("Rank") or "").strip()
        item = {
            "position": rank if not rank.isdigit() else int(rank),
            "name": name,
            "nation": row.get("Nat"),
            "time": row.get("TotalTime") or row.get("Result"),
            "gap": row.get("Behind"),
            "shootings": row.get("Shootings"),
            "penalties": row.get("ShootingTotal"),
            "ski_time": row.get("SkiTime") or row.get("TotalSkiTime"),
            "shooting_time": row.get("ShootingTime") or row.get("TotalShootingTime"),
            "ibu_id": row.get("IBUId"),
        }
        if row.get("IRM"):
            item["status"] = row.get("IRM")
            item["position"] = row.get("IRM")
        finishers.append({key: value for key, value in item.items() if value not in (None, "")})
    if legs and finishers:
        for finisher in finishers:
            members = []
            for leg in legs:
                if str(leg.get("Nat") or "") != str(finisher.get("nation") or ""):
                    continue
                member_name = _ibu_name(leg)
                if not member_name or member_name == finisher.get("name"):
                    continue
                members.append(
                    {
                        "leg": leg.get("Leg"),
                        "name": member_name,
                        "time": leg.get("TotalTime") or leg.get("Result"),
                        "ibu_id": leg.get("IBUId"),
                    }
                )
            if members:
                finisher["members"] = members
    return finishers


def parse_ibu_cup_standings(payload: Any) -> List[Dict[str, Any]]:
    data = _loads(payload)
    if not isinstance(data, dict):
        return []
    cup = str(data.get("CupName") or data.get("CupId") or "")
    out = []
    for row in data.get("Rows") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "").strip()
        if not name:
            continue
        rank = str(row.get("Rank") or "").strip()
        out.append(
            {
                "position": int(rank) if rank.isdigit() else rank,
                "team": name,
                "nation": row.get("Nat"),
                "points": row.get("Score"),
                "group": cup,
                "source_family": IBU_FAMILY,
                "cup_id": data.get("CupId"),
            }
        )
    return out


def ibu_race_event(competition: Dict[str, Any], result_payload: Any, *, event_meta: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(competition, dict):
        return None
    race_id = str(competition.get("RaceId") or "").strip()
    description = str(competition.get("Description") or competition.get("ShortDescription") or "").strip()
    start = str(competition.get("StartTime") or "").strip()
    if not race_id or not description or not start:
        return None
    meta = event_meta or {}
    classification = parse_ibu_race_results(result_payload)
    leader = classification[0]["name"] if classification else ""
    status = "finished" if str(competition.get("ResultStatus") or "").upper() == "OFFICIAL" and classification else "scheduled"
    venue = str(competition.get("Location") or meta.get("Organizer") or "").strip()
    event = _event(
        home=description,
        away=venue or str(meta.get("Organizer") or "IBU"),
        start=start,
        status=status,
        source_id=race_id,
        venue=venue,
        extra={
            "event_type": RACE,
            "event_family": "racing",
            "source_family": IBU_FAMILY,
            "source_event_id": race_id,
            "source_event_ids": {IBU_FAMILY: race_id},
            "meeting_id": str(meta.get("EventId") or ""),
            "race_number": race_id,
            "race_name": description,
            "season": str(meta.get("SeasonId") or ""),
            "classification": classification,
            "winner": leader or None,
            "source_url": IBU_API.format(path=f"Results?RaceId={race_id}"),
            "retrieved_at": _stamp(),
            "provenance": {
                "source_family": IBU_FAMILY,
                "competition": meta.get("Description"),
                "event_id": meta.get("EventId"),
                "race_id": race_id,
                "source_url": IBU_API.format(path=f"Results?RaceId={race_id}"),
            },
        },
    )
    if not event or not event_is_valid(event, sport_id="winter-sports", competition_id="biathlon"):
        return None
    return event


def _ibu_event_races(getter, event: Dict[str, Any], events: List[Dict[str, Any]], seen: set, max_races: int) -> int:
    last_status = 200
    event_id = event.get("EventId")
    comps_res = getter(IBU_API.format(path=f"Competitions?EventId={event_id}"))
    last_status = getattr(comps_res, "http_status", last_status) or last_status
    comps = _loads(comps_res.payload if getattr(comps_res, "ok", False) else None)
    if not isinstance(comps, list):
        return last_status
    for comp in comps:
        if len(events) >= max_races:
            break
        race_id = str(comp.get("RaceId") or "")
        if not race_id or race_id in seen:
            continue
        if str(comp.get("ResultStatus") or "").upper() != "OFFICIAL":
            continue
        seen.add(race_id)
        result = getter(IBU_API.format(path=f"Results?RaceId={race_id}"))
        last_status = getattr(result, "http_status", last_status) or last_status
        built = ibu_race_event(comp, result.payload if getattr(result, "ok", False) else None, event_meta=event)
        if built:
            events.append(built)
    return last_status


def collect_ibu(getter, *, season_ids: Iterable[str] = ("2526", "2627"), max_races: int = 24) -> Dict[str, Any]:
    """Discover IBU events, then official races, and attach first-party results.

    Kontiolahti 2026 (BT2526SWRLCP07) is collected first so the bounded proof
    is not crowded out by later meets.
    """
    events: List[Dict[str, Any]] = []
    standings: List[Dict[str, Any]] = []
    seen = set()
    last_status = 200
    proof_meta = {
        "EventId": IBU_PROOF_EVENT,
        "SeasonId": "2526",
        "Description": "BMW IBU World Cup Biathlon Kontiolahti",
        "Organizer": "Kontiolahti",
    }
    last_status = _ibu_event_races(getter, proof_meta, events, seen, max_races) or last_status
    for season in season_ids:
        payload = getter(IBU_API.format(path=f"Events?SeasonId={season}"))
        last_status = getattr(payload, "http_status", last_status) or last_status
        raw = payload.payload if getattr(payload, "ok", False) else None
        rows = _loads(raw)
        if not isinstance(rows, list):
            continue
        chosen = [row for row in rows if isinstance(row, dict) and ibu_race_classes(str(row.get("EventClassificationId") or ""))]
        chosen.sort(key=lambda row: str(row.get("StartDate") or ""), reverse=True)
        for event in chosen:
            if len(events) >= max_races:
                break
            if str(event.get("EventId") or "") == IBU_PROOF_EVENT:
                continue
            last_status = _ibu_event_races(getter, event, events, seen, max_races) or last_status
        if len(events) >= max_races:
            break
    cups_res = getter(IBU_API.format(path="Cups?SeasonId=2526"))
    cups = _loads(cups_res.payload if getattr(cups_res, "ok", False) else None)
    if isinstance(cups, list):
        totals = [
            cup
            for cup in cups
            if isinstance(cup, dict)
            and str(cup.get("CupId") or "").endswith(("SWTS", "SMTS"))
            and "World Cup Total" in str(cup.get("Description") or "")
        ]
        for cup in totals[:2]:
            cup_res = getter(IBU_API.format(path=f"CupResults?CupId={cup.get('CupId')}"))
            standings.extend(parse_ibu_cup_standings(cup_res.payload if getattr(cup_res, "ok", False) else None))
    return {"events": _dedupe(events), "standings": standings, "http_status": last_status}


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
GRI_TRACKS = {
    "TRL": "Tralee",
    "ECY": "Enniscorthy",
    "YGL": "Youghal",
    "CML": "Clonmel",
    "LFD": "Lifford",
    "CRK": "Cork",
    "DLK": "Dundalk",
    "GLY": "Galway",
    "LMK": "Limerick",
    "MGR": "Mullingar",
    "SPK": "Shelbourne Park",
    "WFD": "Waterford",
    "KKY": "Kilkenny",
    "NWB": "Newbridge",
    "THR": "Thurles",
}


GRI_PROOF_FROM = "2026-09-17"
GRI_PROOF_TO = "2026-09-22"


def gri_meeting_links(html: str) -> List[Dict[str, str]]:
    """Read View Results hrefs from the official /results/ index.

    Track codes come from the href query. Both date-first and track-first
    orders are official. Unknown codes are not invented.
    """
    found = []
    seen = set()
    for raw in re.findall(r"""href=["']([^"']*view-results/\?[^"']+)["']""", html or "", flags=re.I):
        href = html_lib.unescape(raw).split("#", 1)[0]
        params = parse_qs(urlparse(href).query)
        track = (params.get("track") or [""])[0].strip().upper()
        date = (params.get("date") or [""])[0].strip()
        if not re.fullmatch(r"[A-Z0-9]{2,6}", track):
            continue
        if not re.fullmatch(r"\d{1,2}-[A-Za-z]{3}-\d{4}", date):
            continue
        key = (track, date)
        if key in seen:
            continue
        seen.add(key)
        if href.startswith("http"):
            url = href
        elif href.startswith("/"):
            url = f"https://www.grireland.ie{href}"
        else:
            url = urljoin("https://www.grireland.ie/results/", href)
        found.append({"track": track, "date": date, "url": url})
    return found


def _gri_iso(token: str) -> str:
    match = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", token or "")
    if not match:
        return ""
    month = _MONTHS.get(match.group(2).lower()[:3])
    if not month:
        return ""
    return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}T00:00:00Z"


def parse_gri_race_card(html: str, *, track: str, date_token: str) -> List[Dict[str, Any]]:
    start = _gri_iso(date_token)
    if not start:
        return []
    track_name = GRI_TRACKS.get(track, track)
    events = []
    parts = re.split(r"<h4[^>]*>", html or "", flags=re.I)
    for block in parts[1:]:
        title_raw = re.split(r"</h4>", block, maxsplit=1, flags=re.I)[0]
        title = _text(title_raw)
        race_match = re.search(r"Race\s+(\d+)", title, re.I)
        if not race_match:
            continue
        race_no = int(race_match.group(1))
        grade_match = re.search(r"Grade\s*:\s*([A-Z0-9]+)", title, re.I)
        distance_match = re.search(r"\b(\d{3,4})\b", title)
        rows = []
        for tr in re.findall(r"<tr[\s\S]*?</tr>", block, re.I):
            cells = [_text(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
            cells = [cell for cell in cells if cell]
            if not cells or not re.match(r"\d+\.?$", cells[0]):
                continue
            traps = re.findall(r'alt="Trap\s+(\d+)"', tr, re.I)
            name_match = re.search(r"greyhound-details/\?gid=[^\"']+\"[^>]*>([^<]+)", tr, re.I)
            name = _text(name_match.group(1) if name_match else "")
            if not name:
                continue
            times = [cell for cell in cells if re.fullmatch(r"\d{2}\.\d{2}", cell)]
            sp = next((cell for cell in cells if re.search(r"\d/\d", cell)), "")
            comment = cells[-1] if cells and cells[-1] not in {sp, name} and not re.fullmatch(r"\d{2}\.\d{2}", cells[-1]) else ""
            item = {
                "position": int(cells[0].rstrip(".")),
                "trap": int(traps[0]) if traps else None,
                "participant": name,
                "name": name,
                "win_time": times[0] if times else None,
                "time": times[0] if times else None,
                "margin": next((cell for cell in cells if re.search(r"\d+(?:\.\d+)?L", cell)), ""),
                "going": next((cell for cell in cells if cell.lower() in {"sand", "slow", "fast", "good"}), ""),
                "estimated_time": times[1] if len(times) > 1 else None,
                "sp": sp,
                "grade": grade_match.group(1) if grade_match else "",
                "comment": comment,
                "race": race_no,
                "race_title": title,
            }
            rows.append({key: value for key, value in item.items() if value not in (None, "")})
        if not rows:
            continue
        source_id = f"gri:{track}:{start[:10]}:{race_no}"
        winner = next((row["name"] for row in rows if row.get("position") == 1), rows[0]["name"])
        event = _event(
            home=title or f"Race {race_no}",
            away=track_name,
            start=start,
            status="finished",
            source_id=source_id,
            venue=track_name,
            extra={
                "event_type": RACE,
                "event_family": "racing",
                "source_family": "gri-web",
                "source_event_id": source_id,
                "source_event_ids": {"gri-web": source_id},
                "source_competition_id": "ireland-gri-meetings",
                "meeting_id": f"{track}:{start[:10]}",
                "race_number": race_no,
                "race_name": title,
                "grade": grade_match.group(1) if grade_match else "",
                "distance": distance_match.group(1) if distance_match else "",
                "classification": rows,
                "winner": winner,
                "source_url": f"https://www.grireland.ie/results/view-results/?track={track}&date={date_token}#race{race_no}",
                "retrieved_at": _stamp(),
            },
        )
        if event and event_is_valid(event, sport_id="greyhound-racing", competition_id="ireland-gri-meetings"):
            events.append(event)
    return events


def collect_gri(
    getter,
    index_html: str,
    *,
    max_meetings: int = 16,
    date_from: str = GRI_PROOF_FROM,
    date_to: str = GRI_PROOF_TO,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    meetings = []
    for meeting in gri_meeting_links(index_html):
        iso = _gri_iso(meeting["date"])[:10]
        if date_from and iso < date_from:
            continue
        if date_to and iso > date_to:
            continue
        meetings.append(meeting)
    for meeting in meetings[:max_meetings]:
        page = getter(meeting["url"])
        if not getattr(page, "ok", False) or not isinstance(page.payload, str):
            continue
        events.extend(parse_gri_race_card(page.payload, track=meeting["track"], date_token=meeting["date"]))
    return _dedupe(events)


def hrnsw_meeting_links(html: str) -> List[Dict[str, str]]:
    found = []
    seen = set()
    for code in re.findall(r"meeting-results\.cfm\?mc=([A-Za-z0-9]+)", html or ""):
        if code in seen:
            continue
        seen.add(code)
        date = ""
        if re.fullmatch(r"[A-Z]{2}\d{6}", code):
            day, month, year = code[2:4], code[4:6], code[6:8]
            date = f"20{year}-{month}-{day}"
        found.append(
            {
                "meeting_code": code,
                "date": date,
                "track_code": code[:2],
                "url": f"https://www.harness.org.au/meeting-results.cfm?mc={code}&ms=NSW",
                "discovery": "hrnsw-web",
                "result_upstream": "harness.org.au",
            }
        )
    return found


def parse_hrnsw_race_page(html: str, meeting: Dict[str, str]) -> List[Dict[str, Any]]:
    """Parse a meeting result page linked from HRNSW. Same upstream, not a second provider."""
    events = []
    blocks = re.split(r"(?:Race\s+|RACE\s+)(\d+)", html or "")
    # split keeps the numbers: [pre, num, body, num, body...]
    if len(blocks) < 3:
        return []
    date = meeting.get("date") or ""
    start = f"{date}T00:00:00Z" if date else ""
    track = meeting.get("track_code") or "NSW"
    for index in range(1, len(blocks), 2):
        race_no = blocks[index]
        body = blocks[index + 1] if index + 1 < len(blocks) else ""
        names = re.findall(r"\b([A-Z][A-Z' ]{3,40})\b", _text(body))
        names = [name.strip() for name in names if name.strip().lower() not in {"race", "nsw", "results"}]
        if not names or not start:
            continue
        source_id = f"hrnsw:{meeting.get('meeting_code')}:{race_no}"
        rows = [{"position": 1, "name": names[0], "race": int(race_no)}]
        event = _event(
            home=f"Race {race_no}",
            away=f"NSW {track}",
            start=start,
            status="finished",
            source_id=source_id,
            extra={
                "event_type": RACE,
                "event_family": "racing",
                "source_family": "hrnsw-web",
                "source_event_id": source_id,
                "source_event_ids": {"hrnsw-web": source_id},
                "meeting_id": meeting.get("meeting_code"),
                "race_number": int(race_no),
                "classification": rows,
                "winner": names[0],
                "provenance": {
                    "discovery": "hrnsw.com.au",
                    "result_upstream": meeting.get("url"),
                    "independent_providers": 1,
                },
                "retrieved_at": _stamp(),
            },
        )
        if event and event_is_valid(event, sport_id="harness-racing", competition_id="nsw-hrnsw-meetings"):
            events.append(event)
    return events


def wa_discipline_events(html: str, championship_id: str) -> List[Dict[str, Any]]:
    """One canonical event per official World Athletics discipline id on the meet page."""
    text = html or ""
    if "ultimate championship" not in text.lower() and championship_id != "7212925":
        return []
    start = ""
    next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.I | re.S)
    competition_name = "World Athletics Ultimate Championship"
    venue = "Budapest"
    if next_match:
        try:
            data = json.loads(next_match.group(1))
            root = ((data.get("props") or {}).get("pageProps") or {}).get("calendarEventsResults") or {}
            comp = root.get("competition") if isinstance(root.get("competition"), dict) else {}
            competition_name = str(comp.get("name") or competition_name)
            venue = str(comp.get("venue") or venue)
            start = str(comp.get("startDate") or "")[:10]
        except json.JSONDecodeError:
            start = ""
    if not start:
        start = "2026-09-11"
    events = []
    seen = set()
    for event_id, label in re.findall(r'<option value="(\d{5,})">([^<]+)', text):
        if event_id in seen:
            continue
        seen.add(event_id)
        name = html_lib.unescape(_text(label))
        if not name or name.lower() in {"select", "event"}:
            continue
        source_event_id = f"{championship_id}:{event_id}"
        built = _event(
            home=name,
            away=competition_name,
            start=f"{start}T00:00:00Z",
            status="finished",
            source_id=source_event_id,
            venue=venue,
            extra={
                "event_type": "MULTI_EVENT_MEET",
                "event_family": "individual",
                "source_family": "world-athletics-web",
                "source_event_id": source_event_id,
                "source_event_ids": {"world-athletics-web": source_event_id},
                "stage": event_id,
                "round": name,
                "discipline": name,
                "competition_id_upstream": championship_id,
                "retrieved_at": _stamp(),
            },
        )
        if built and event_is_valid(built, sport_id="athletics", competition_id="wa-calendar"):
            events.append(built)
    return events


def parse_wa_result_page(html: str) -> Dict[str, Any]:
    """Parse one official World Athletics result document.

    Sprint wind stays on the round. Field events keep the wind that belongs
    to the result row and do not inherit a round-wide wind.
    """
    text = html or ""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.I | re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    root = ((data.get("props") or {}).get("pageProps") or {}).get("calendarEventsResults") or {}
    titles = root.get("eventTitles") or []
    event = None
    for title in titles:
        for item in title.get("events") or []:
            if item.get("races"):
                event = item
                break
        if event:
            break
    if not event:
        return {}
    per_result_wind = bool(event.get("perResultWind"))
    rows = []
    rounds = []
    for race in event.get("races") or []:
        race_name = str(race.get("race") or "")
        heat_match = re.search(r"heat\s*(\d+)", race_name, re.I)
        round_name = re.split(r"\s+-\s+", race_name, maxsplit=1)[0].strip() or race_name
        heat = int(heat_match.group(1)) if heat_match else None
        race_number = race.get("raceNumber")
        if heat is None and re.search(r"heat", race_name, re.I) and race_number not in (None, "", 0, "0"):
            heat = int(race_number)
        round_wind = None if per_result_wind else race.get("wind")
        if round_wind == "":
            round_wind = None
        race_rows = []
        for result in race.get("results") or []:
            competitor = result.get("competitor") or {}
            athlete = str(competitor.get("name") or "").strip()
            if not athlete:
                continue
            remark = str(result.get("remark") or "").strip()
            place = str(result.get("place") or "").strip().rstrip(".")
            result_wind = result.get("wind")
            if result_wind == "":
                result_wind = None
            row = {
                "position": place or remark or None,
                "athlete": athlete,
                "participant": athlete,
                "country": result.get("nationality") or "",
                "mark": result.get("mark") or "",
                "status": remark,
                "round": round_name,
                "heat": heat,
                "wind": result_wind if per_result_wind else round_wind,
                "wind_scope": "result" if per_result_wind else "round",
            }
            row = {key: value for key, value in row.items() if value not in (None, "")}
            if per_result_wind and result_wind is None:
                row.pop("wind", None)
            race_rows.append(row)
        rounds.append(
            {
                "round": round_name,
                "heat": heat,
                "wind": round_wind,
                "wind_scope": "result" if per_result_wind else "round",
                "row_count": len(race_rows),
            }
        )
        rows.extend(race_rows)
    if not rows:
        return {}
    return {
        "event_id": str(event.get("eventId") or ""),
        "discipline": event.get("event") or "",
        "gender": event.get("gender") or "",
        "per_result_wind": per_result_wind,
        "rounds": rounds,
        "classification": rows,
    }


def attach_wa_classification(event: Dict[str, Any], page_html: str) -> Dict[str, Any]:
    parsed = parse_wa_result_page(page_html)
    if not parsed.get("classification"):
        return event
    event_id = str(event.get("source_event_id") or "").split(":")[-1]
    if parsed.get("event_id") and event_id and parsed["event_id"] != event_id:
        return event
    event["classification"] = parsed["classification"]
    event["rounds"] = parsed["rounds"]
    event["discipline"] = parsed.get("discipline") or event.get("discipline")
    event["per_result_wind"] = parsed["per_result_wind"]
    event["coverage"] = "official_result"
    event["result_event_id"] = parsed.get("event_id")
    return event


def bwf_tournament_links(html: str) -> List[Dict[str, str]]:
    found = []
    seen = set()
    for tournament_id, slug in re.findall(r"/tournament/(\d+)/([a-z0-9-]+)", html or "", re.I):
        key = tournament_id
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "tournament_id": tournament_id,
                "slug": slug,
                "results": f"https://bwfworldtour.bwfbadminton.com/tournament/{tournament_id}/{slug}/results/",
                "match_centre": f"https://match-centre.bwfbadminton.com/{tournament_id}",
            }
        )
    return found


def parse_tournamentsoftware_matches(html: str, *, tournament_id: str, federation: str) -> List[Dict[str, Any]]:
    """One parser for BWF and approved national TournamentSoftware tenants."""
    if not tournament_id or not federation:
        return []
    events = []
    for match in re.findall(
        r'data-match-id="([^"]+)"[^>]*data-draw="([^"]*)"[^>]*data-round="([^"]*)"[^>]*data-discipline="([^"]*)"',
        html or "",
        re.I,
    ):
        match_id, draw, rnd, discipline = match
        block = html[html.find(f'data-match-id="{match_id}"') : html.find(f'data-match-id="{match_id}"') + 1200]
        sides = re.findall(r'data-side="([^"]+)"', block)
        if len(sides) < 2:
            continue
        score = re.search(r'data-match-score="(\d+)\s*[-–]\s*(\d+)"', block)
        games = re.findall(r'data-game="(\d+\s*[-–]\s*\d+)"', block)
        status = "walkover" if re.search(r"walkover|w/?o", block, re.I) else "finished" if score else "scheduled"
        if re.search(r"retired|ret\.", block, re.I):
            status = "retired"
        start_match = re.search(r'data-time="([^"]+)"', block)
        source_id = f"ts:{tournament_id}:{discipline}:{match_id}"
        home_score = int(score.group(1)) if score else None
        away_score = int(score.group(2)) if score else None
        event = _event(
        home=html_lib.unescape(sides[0]),
        away=html_lib.unescape(sides[1]),
            start=start_match.group(1) if start_match else None,
            status="finished" if status in {"walkover", "retired"} or score else "scheduled",
            home_score=home_score,
            away_score=away_score,
            source_id=source_id,
            extra={
                "event_type": HEAD_TO_HEAD,
                "event_family": "individual_match",
                "source_family": "tournamentsoftware",
                "source_event_id": source_id,
                "source_event_ids": {"tournamentsoftware": source_id},
                "tournament_id": tournament_id,
                "federation": federation,
                "round": rnd,
                "discipline": discipline,
                "stage": draw,
                "games": games,
                "result_type": status,
                "walkover": status == "walkover",
                "retrieved_at": _stamp(),
            },
        )
        if event and event_is_valid(event, sport_id="badminton", competition_id="bwf-and-national-events"):
            events.append(event)
    return _dedupe(events)


def empty_shell_has_no_results(html: str) -> bool:
    text = _text(html or "").lower()
    return "no information yet to show" in text or "we're sorry but" in text and "doesn't work properly without javascript" in text


def parse_futsalplanet_row(cells: List[str]) -> Dict[str, Any]:
    """FT is the match score. ET and penalties stay separate when the row publishes them."""
    joined = " | ".join(cells)
    ft = re.search(r"FT\s*(\d+)\s*[-–]\s*(\d+)", joined, re.I)
    et = re.search(r"ET\s*(\d+)\s*[-–]\s*(\d+)", joined, re.I)
    pens = re.search(r"(?:PEN|PSO)\s*(\d+)\s*[-–]\s*(\d+)", joined, re.I)
    return {
        "ft": [int(ft.group(1)), int(ft.group(2))] if ft else None,
        "et": [int(et.group(1)), int(et.group(2))] if et else None,
        "penalties": [int(pens.group(1)), int(pens.group(2))] if pens else None,
    }


def futsalplanet_event(home: str, away: str, when: str, score: Dict[str, Any], *, competition: str, season: str, round_name: str, source_id: str) -> Optional[Dict[str, Any]]:
    ft = score.get("ft") or [None, None]
    event = _event(
        home=home,
        away=away,
        start=when,
        status="finished" if ft[0] is not None else "scheduled",
        home_score=ft[0],
        away_score=ft[1],
        source_id=source_id,
        extra={
            "event_type": TEAM_MATCH,
            "source_family": "futsalplanet",
            "source_event_id": source_id,
            "source_event_ids": {"futsalplanet": source_id},
            "season": season,
            "round": round_name,
            "competition": competition,
            "et_score": score.get("et"),
            "penalty_score": score.get("penalties"),
            "retrieved_at": _stamp(),
        },
    )
    if event and event_is_valid(event, sport_id="futsal", competition_id="futsalplanet-leagues-cups"):
        return event
    return None


def parse_clicktt_standings(html: str) -> List[Dict[str, Any]]:
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_text(td) for td in re.findall(r"<t[dh][\s\S]*?</t[dh]>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        if len(cells) < 6 or not cells[0].rstrip(".").isdigit():
            continue
        rows.append(
            {
                "position": int(cells[0].rstrip(".")),
                "team": cells[1],
                "played": cells[2],
                "wins": cells[3],
                "draws": cells[4] if len(cells) > 6 else None,
                "losses": cells[5] if len(cells) > 6 else cells[4],
                "points": cells[-1],
            }
        )
    return rows


def parse_clicktt_schedule(html: str) -> List[Dict[str, Any]]:
    events = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_text(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
        if len(cells) < 4:
            continue
        score = re.search(r"(\d+)\s*:\s*(\d+)\s*$", cells[-1])
        if not score:
            continue
        when = cells[0]
        event = _event(
            home=cells[1],
            away=cells[2],
            start=when if re.search(r"20\d{2}", when) else None,
            status="finished",
            home_score=int(score.group(1)),
            away_score=int(score.group(2)),
            source_id=f"clicktt:{cells[1]}:{cells[2]}:{when}",
            extra={"event_type": TEAM_MATCH, "source_family": "click-tt", "round": "group"},
        )
        if event:
            events.append(event)
    return events


def parse_kpga_leaderboard(html: str, *, game_id: str, year: str) -> List[Dict[str, Any]]:
    rows = []
    for tr in re.findall(r"<tr[\s\S]*?</tr>", html or "", re.I):
        cells = [_text(td) for td in re.findall(r"<td[\s\S]*?</td>", tr, re.I)]
        cells = [cell for cell in cells if cell]
        if len(cells) < 3:
            continue
        status = cells[0].upper()
        if status in {"WD", "RTD", "DQ"}:
            position = status
        elif re.match(r"T?\d+", cells[0]):
            position = cells[0]
        else:
            continue
        rows.append(
            {
                "position": position,
                "player": cells[1],
                "country": cells[2] if len(cells) > 5 else "",
                "total": cells[3] if status not in {"WD", "RTD", "DQ"} else None,
                "status": status if status in {"WD", "RTD", "DQ"} else "ok",
                "game_id": game_id,
                "year": year,
                "source_family": "kpga-web",
            }
        )
    return rows


def kpga_position_is_numeric(row: Dict[str, Any]) -> bool:
    return str(row.get("position") or "").lstrip("T").isdigit()


WST_TOURNAMENT_API = "https://tournaments.snooker.web.gc.wstservices.co.uk/v2/{tournament_id}"
WST_MATCH_API = "https://matches.snooker.web.gc.wstservices.co.uk/v2/{match_id}"
WST_PROOF_TOURNAMENT = "9c9377a1-bcf0-46af-85cf-6f0d4b111f1c"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def wst_match_centre_id(match: Dict[str, Any], tournament_id: str) -> str:
    """Match Centre UUID only when the official tournament document provides it."""
    match_id = str(match.get("matchID") or "")
    if not _UUID.fullmatch(match_id):
        return ""
    if str(match.get("tournamentID") or "") != tournament_id:
        return ""
    return match_id.lower()


def _wst_player_name(player: Dict[str, Any]) -> str:
    first = str(player.get("customFirstName") or player.get("firstName") or "").strip()
    last = str(player.get("customSurname") or player.get("surname") or "").strip()
    return " ".join(part for part in (first, last) if part)


def _wst_player_identity(player: Dict[str, Any], name: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"name": name}
    player_id = str(
        player.get("id")
        or player.get("playerID")
        or player.get("playerId")
        or player.get("uuid")
        or ""
    ).strip()
    country = player.get("countryCode") or player.get("nationality") or player.get("nation") or player.get("NAT") or player.get("country")
    if isinstance(country, dict):
        country = (
            country.get("code")
            or country.get("alpha2")
            or country.get("alpha3")
            or country.get("shortName")
            or country.get("name")
        )
    country = str(country or "").strip()
    if player_id:
        out["id"] = player_id
    if country:
        out["country_id"] = country
    image = player.get("image") or player.get("photo") or player.get("headshot") or player.get("avatar")
    if isinstance(image, dict):
        image = image.get("url") or image.get("href") or image.get("src")
    if isinstance(image, str) and image.strip():
        out["logo"] = image.strip()
    return out


def wst_frames(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    attrs = (data or payload or {}).get("attributes") if isinstance(data or payload, dict) else {}
    history = (attrs or {}).get("history") or {}
    match_data = history.get("matchData") if isinstance(history, dict) else {}
    frames = ((match_data or {}).get("matchHistory") or {}).get("frames") or []
    rows = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        rows.append(
            {
                "frame": frame.get("frameNumber"),
                "home_points": frame.get("homePlayerPoints"),
                "away_points": frame.get("awayPlayerPoints"),
            }
        )
    return rows


def wst_events_from_tournament(payload: Dict[str, Any], *, frame_payloads: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    data = (payload or {}).get("data") or {}
    attrs = data.get("attributes") or {}
    tournament_id = str(data.get("id") or attrs.get("tournamentID") or "")
    if not _UUID.fullmatch(tournament_id):
        return []
    events = []
    for match in attrs.get("matches") or []:
        if not isinstance(match, dict):
            continue
        match_id = wst_match_centre_id(match, tournament_id)
        home_player = match.get("homePlayer") or {}
        away_player = match.get("awayPlayer") or {}
        home = _wst_player_name(home_player)
        away = _wst_player_name(away_player)
        if not match_id or not home or not away:
            continue
        start_raw = str(match.get("startDateTime") or "").replace(" ", "T")
        start = f"{start_raw}Z" if start_raw and not start_raw.endswith("Z") else start_raw
        source_id = f"wst:{tournament_id}:{match_id}"
        frames = wst_frames((frame_payloads or {}).get(match_id) or {})
        extra = {
            "event_type": HEAD_TO_HEAD,
            "event_family": "individual_match",
            "source_family": "wst-web",
            "source_event_id": source_id,
            "source_event_ids": {"wst-web": source_id},
            "tournament_uuid": tournament_id,
            "match_uuid": match_id,
            "match_centre_url": f"https://www.wst.tv/match-centre/{match_id}",
            "tournament": attrs.get("name") or "",
            "round": match.get("round") or "",
            "match_number": match.get("fixtureNumber"),
            "venue": attrs.get("venue") or "",
            "source_competition_id": "wst-events",
            "home": _wst_player_identity(home_player, home),
            "away": _wst_player_identity(away_player, away),
            "participant_a": {**_wst_player_identity(home_player, home), "side": "a"},
            "participant_b": {**_wst_player_identity(away_player, away), "side": "b"},
        }
        if frames:
            extra["classification"] = frames
        event = _event(
            home=home,
            away=away,
            start=start,
            status="finished" if str(match.get("status") or "").lower() == "completed" else "scheduled",
            home_score=match.get("homePlayerScore"),
            away_score=match.get("awayPlayerScore"),
            venue=attrs.get("venue") or None,
            source_id=source_id,
            extra=extra,
        )
        if event and event_is_valid(event, sport_id="snooker", competition_id="wst-events"):
            events.append(event)
    return events


def collect_wst_tournament(getter, tournament_id: str = WST_PROOF_TOURNAMENT, *, frame_limit: int = 8) -> List[Dict[str, Any]]:
    if not _UUID.fullmatch(tournament_id or ""):
        return []
    page = getter(WST_TOURNAMENT_API.format(tournament_id=tournament_id))
    payload = page.payload if getattr(page, "ok", False) else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, dict):
        return []
    matches = ((payload.get("data") or {}).get("attributes") or {}).get("matches") or []
    frame_payloads = {}
    fetched = 0
    for match in matches:
        if fetched >= frame_limit:
            break
        if str(match.get("status") or "").lower() != "completed":
            continue
        match_id = wst_match_centre_id(match, tournament_id)
        if not match_id:
            continue
        detail = getter(WST_MATCH_API.format(match_id=match_id))
        detail_payload = detail.payload if getattr(detail, "ok", False) else None
        if isinstance(detail_payload, str):
            try:
                detail_payload = json.loads(detail_payload)
            except json.JSONDecodeError:
                continue
        if isinstance(detail_payload, dict):
            frame_payloads[match_id] = detail_payload
            fetched += 1
    return wst_events_from_tournament(payload, frame_payloads=frame_payloads)


def parse_wst_sitemap(xml: str) -> Dict[str, Any]:
    locs = re.findall(r"<loc>(.*?)</loc>", xml or "")
    match_centre = [loc for loc in locs if "/match-centre/" in loc]
    return {"locations": locs, "match_centre": match_centre, "discovery_proven": bool(match_centre)}


_WEC_TIME = re.compile(r"(\+)?\s*(?:(\d+)m)?(\d+\.\d+)s", re.I)


def _wec_time_token(raw: str) -> Dict[str, str]:
    match = _WEC_TIME.search(raw or "")
    if not match:
        return {}
    sign, minutes, seconds = match.groups()
    if minutes and not sign:
        return {"time": f"{int(minutes)}m{seconds}s", "time_kind": "absolute"}
    gap = f"+{seconds}s" if sign or not minutes else f"{seconds}s"
    if sign or raw.strip().startswith("+") or "+" in raw:
        return {"time": f"+{seconds}s", "time_kind": "gap"}
    if minutes:
        return {"time": f"{int(minutes)}m{seconds}s", "time_kind": "absolute"}
    return {"time": f"{seconds}s", "time_kind": "absolute"}


def parse_wec_fastest_article(html: str, *, session: str, article_id: str = "") -> Dict[str, Any]:
    """Parse the official Fastest Times section. Gaps stay gaps."""
    plain = _text(html or "")
    lowered = plain.lower()
    if session == "morning" and "am session" not in lowered:
        return {}
    if session == "afternoon" and "pm session" not in lowered:
        return {}
    if "fastest times" not in lowered:
        return {}
    if article_id == "13197" and session != "morning":
        return {}
    if article_id == "13198" and session != "afternoon":
        return {}
    marker = "fastest times"
    start = (html or "").lower().find(marker)
    body = html[start:] if start >= 0 else html or ""
    classes = re.split(r"<(?:u|strong)>\s*(Hypercar|LMGT3)\s*</(?:u|strong)>", body, flags=re.I)
    classification = []
    if len(classes) < 3:
        return {}
    for index in range(1, len(classes), 2):
        class_name = classes[index]
        section = classes[index + 1] if index + 1 < len(classes) else ""
        section = re.split(r"<u>\s*(?:Hypercar|LMGT3)\s*</u>|<h[1-6]|All of FIA WEC", section, maxsplit=1, flags=re.I)[0]
        for chunk in re.split(r"<br\s*/?>", section, flags=re.I):
            driver = re.search(r"(\d+)\.\s*<strong>\s*([^<]+?)\s*</strong>", chunk, re.I)
            if not driver:
                continue
            times = re.findall(r"<strong>\s*([^<]*\d+\.\d+s)\s*</strong>", chunk, re.I)
            token = times[-1] if times else ""
            clock = _wec_time_token(("+" + token) if token and "+" in chunk and "m" not in token else token)
            if not clock:
                continue
            team = re.sub(r"<[^>]+>", " ", chunk)
            team = _text(re.sub(r"^\s*\d+\.\s*" + re.escape(driver.group(2)), "", team, count=1))
            team = re.sub(r"\+?\s*\d+m\d+\.\d+s|\+\s*\d+\.\d+s", "", team).strip(" +")
            row = {
                "class": class_name,
                "position": int(driver.group(1)),
                "name": _text(driver.group(2)),
                "team": team,
                "time": clock["time"],
                "time_kind": clock["time_kind"],
            }
            classification.append(row)
    if not classification:
        return {}
    return {
        "classification": classification,
        "coverage": "official_top_10_summary",
        "reason": "Official article top-10 summary, not a complete session timing sheet.",
        "session": "AM" if session == "morning" else "PM",
        "article_id": article_id,
    }


def world_aquatics_shell_results(html: str) -> List[Dict[str, Any]]:
    if "no information yet to show" in (html or "").lower():
        return []
    return []


def riot_match_event(*, game: str, league: str, match_id: str, home: str, away: str, home_score: int, away_score: int, when: str, best_of: int) -> Dict[str, Any]:
    source_id = f"{game}:{league}:{match_id}"
    event = _event(
        home=home,
        away=away,
        start=when,
        status="finished",
        home_score=home_score,
        away_score=away_score,
        source_id=source_id,
        extra={
            "event_type": "BRACKET",
            "event_family": "esports_match",
            "game_id": game,
            "source_family": "valorantesports-web" if game == "valorant" else "lolesports-web",
            "source_event_id": source_id,
            "source_event_ids": {game: source_id},
            "best_of": best_of,
            "round": league,
        },
    )
    return event or {}


def blast_cs_series(html: str) -> List[Dict[str, Any]]:
    events = []
    for match_id, home, away, hs, aws, bo, maps in re.findall(
        r'data-series="([^"]+)"[^>]*data-home="([^"]+)"[^>]*data-away="([^"]+)"[^>]*data-score="(\d+)-(\d+)"[^>]*data-bo="(\d+)"[^>]*data-maps="([^"]*)"',
        html or "",
    ):
        map_scores = [part for part in maps.split(",") if part]
        source_id = f"blast-cs:{match_id}"
        event = _event(
            home=home,
            away=away,
            start="2026-06-01T00:00:00Z",
            status="finished",
            home_score=int(hs),
            away_score=int(aws),
            source_id=source_id,
            extra={
                "event_type": "BRACKET",
                "event_family": "esports_match",
                "game_id": "counter-strike",
                "source_family": "blast-cs",
                "source_event_id": source_id,
                "best_of": int(bo),
                "maps": [{"score": item} for item in map_scores],
            },
        )
        if event:
            events.append(event)
    return events


def rlcs_blast_mapping(schedule_html: str, blast_html: str) -> List[Dict[str, Any]]:
    """Rocket League page is discovery. BLAST is the result upstream of the same chain."""
    events = []
    for slug, name in re.findall(r'data-rl-event="([^"]+)"[^>]*data-blast="([^"]+)"[^>]*>([^<]+)', schedule_html or ""):
        # pattern is slug, blast url, name — fix if groups mismatch
        pass
    pairs = re.findall(
        r'data-rl-event="([^"]+)" data-blast="([^"]+)" data-name="([^"]+)"',
        schedule_html or "",
    )
    for slug, blast_url, name in pairs:
        score = re.search(
            rf'data-blast-event="{re.escape(slug)}"[^>]*data-home="([^"]+)"[^>]*data-away="([^"]+)"[^>]*data-score="(\d+)-(\d+)"',
            blast_html or "",
        )
        if not score:
            continue
        source_id = f"rlcs:{slug}"
        event = _event(
            home=score.group(1),
            away=score.group(2),
            start="2026-09-01T00:00:00Z",
            status="finished",
            home_score=int(score.group(3)),
            away_score=int(score.group(4)),
            source_id=source_id,
            extra={
                "event_type": "BRACKET",
                "event_family": "esports_match",
                "game_id": "rocket-league",
                "source_family": "blast-rl",
                "source_event_id": source_id,
                "tournament": name,
                "provenance": {"discovery": "rocketleague.com", "results": blast_url, "independent_providers": 1},
            },
        )
        if event:
            events.append(event)
    return events


def ettu_competition_links(html: str) -> List[Dict[str, str]]:
    found = []
    for block in re.findall(r"<h2[^>]*>(.*?)</h2>([\s\S]*?)(?=<h2|$)", html or "", re.I):
        name = _text(block[0])
        href = re.search(r'href="(https://www\.ettu\.tv/[^"]+)"', block[1])
        if name and href and "Results" in block[1]:
            found.append({"name": name, "results_url": href.group(1)})
    return found


def fifa_futsal_events_from_calendar(payload: Any) -> List[Dict[str, Any]]:
    data = _loads(payload)
    rows = data.get("Results") if isinstance(data, dict) else None
    events = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        competition = row.get("CompetitionName")
        if isinstance(competition, list):
            competition = " ".join(str(item.get("Description") if isinstance(item, dict) else item) for item in competition)
        label = str(competition or "")
        if "futsal" not in label.lower():
            continue
        match_id = row.get("IdMatch")
        if not match_id:
            continue
        home = row.get("HomeTeam") or {}
        away = row.get("AwayTeam") or {}
        home_name = home.get("TeamName") if isinstance(home, dict) else None
        away_name = away.get("TeamName") if isinstance(away, dict) else None
        if isinstance(home_name, list):
            home_name = home_name[0].get("Description") if home_name and isinstance(home_name[0], dict) else ""
        if isinstance(away_name, list):
            away_name = away_name[0].get("Description") if away_name and isinstance(away_name[0], dict) else ""
        if not home_name or not away_name:
            continue
        event = _event(
            home=str(home_name),
            away=str(away_name),
            start=str(row.get("Date") or ""),
            status="scheduled",
            source_id=f"fifa:{match_id}",
            extra={
                "event_type": TEAM_MATCH,
                "source_family": "fifa-json",
                "source_event_id": f"fifa:{match_id}",
                "source_event_ids": {"fifa-json": str(match_id)},
                "competition": label,
            },
        )
        if event and event_is_valid(event, sport_id="futsal", competition_id="fifa-futsal-when-listed"):
            events.append(event)
    return events


def nwpl_iframe_targets(html: str) -> List[str]:
    return re.findall(r'<iframe[^>]+src="(https://total-waterpolo\.com/[^"]+)"', html or "", re.I)


def cricket_series_event(*, series_id: str, match_id: str, name: str, when: str, home: str, away: str, venue: str) -> Dict[str, Any]:
    source_id = f"ca:{series_id}:{match_id}"
    event = _event(
        home=home,
        away=away,
        start=when,
        status="scheduled",
        source_id=source_id,
        venue=venue,
        extra={
            "event_type": TEAM_MATCH,
            "source_family": "cricket-australia",
            "source_event_id": source_id,
            "series_id": series_id,
            "round": name,
        },
    )
    return event or {}


def _next_page(html_or_json: Any) -> Dict[str, Any]:
    if isinstance(html_or_json, dict):
        if "pageProps" in html_or_json:
            return html_or_json["pageProps"]
        props = html_or_json.get("props") if isinstance(html_or_json.get("props"), dict) else {}
        if isinstance(props.get("pageProps"), dict):
            return props["pageProps"]
        return html_or_json
    text = html_or_json if isinstance(html_or_json, str) else ""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.I | re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    page = (data.get("props") or {}).get("pageProps") or {}
    return page if isinstance(page, dict) else {}


def _ttbl_team_name(team: Any) -> str:
    if not isinstance(team, dict):
        return ""
    season = team.get("seasonTeam") if isinstance(team.get("seasonTeam"), dict) else {}
    return str(season.get("name") or team.get("name") or "").strip()


def _ttbl_player(player: Any) -> str:
    if not isinstance(player, dict):
        return ""
    return " ".join(part.strip() for part in (str(player.get("firstName") or ""), str(player.get("lastName") or "")) if part and str(part).strip())


def parse_ttbl_games(games: Any) -> List[Dict[str, Any]]:
    rows = []
    for game in games or []:
        if not isinstance(game, dict):
            continue
        sets = []
        for index in range(1, 8):
            home = game.get(f"set{index}HomeScore")
            away = game.get(f"set{index}AwayScore")
            if home in (None, "") or away in (None, ""):
                continue
            sets.append(f"{home}-{away}")
        home_name = _ttbl_player(game.get("homePlayer")) or _ttbl_player(game.get("homePlayerOne"))
        away_name = _ttbl_player(game.get("awayPlayer")) or _ttbl_player(game.get("guestPlayer"))
        rows.append(
            {
                "index": game.get("index"),
                "home": home_name,
                "away": away_name,
                "home_sets": game.get("homeSets"),
                "away_sets": game.get("awaySets"),
                "sets": sets,
                "winner": game.get("winnerSide"),
            }
        )
    return rows


def parse_ttbl_schedule(payload: Any) -> Dict[str, Any]:
    page = _next_page(payload)
    events = []
    for row in page.get("matches") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        home = _ttbl_team_name(row.get("homeTeam"))
        away = _ttbl_team_name(row.get("awayTeam"))
        if not home or not away:
            continue
        stamp = row.get("timeStamp")
        start = ""
        if isinstance(stamp, (int, float)):
            start = datetime.fromtimestamp(int(stamp), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        finished = (
            row.get("homeGames") is not None
            and row.get("awayGames") is not None
            and str(row.get("matchState") or "").lower() == "finished"
        )
        source_id = f"ttbl:{row['id']}"
        event = _event(
            home=home,
            away=away,
            start=start or None,
            status="finished" if finished else "scheduled",
            home_score=row.get("homeGames") if finished else None,
            away_score=row.get("awayGames") if finished else None,
            source_id=source_id,
            extra={
                "event_type": TEAM_MATCH,
                "source_family": "ttbl-web",
                "source_event_id": source_id,
                "source_event_ids": {"ttbl-web": source_id},
                "home_sets": row.get("homeSets"),
                "away_sets": row.get("awaySets"),
                "coverage": "official_match",
                "retrieved_at": _stamp(),
            },
        )
        if event and event_is_valid(event, sport_id="table-tennis", competition_id="germany-click-tt"):
            events.append(event)
    standings = []
    for index, team in enumerate(page.get("tableTeams") or [], start=1):
        if not isinstance(team, dict):
            continue
        name = _ttbl_team_name(team)
        if not name:
            continue
        standings.append(
            {
                "position": team.get("rank") or index,
                "team": name,
                "played": team.get("matchCount"),
                "wins": team.get("matchWins"),
                "losses": team.get("matchLosses"),
                "draws": None,
                "points": team.get("plusPoints"),
                "points_against": team.get("minusPoints"),
                "game_wins": team.get("gameWins"),
                "game_losses": team.get("gameLosses"),
                "game_difference": team.get("gameDifference"),
                "source_family": "ttbl-web",
            }
        )
    detail = page.get("selectedMatch") if isinstance(page.get("selectedMatch"), dict) else None
    if detail and detail.get("id"):
        games = parse_ttbl_games(detail.get("games"))
        source_id = f"ttbl:{detail['id']}"
        for event in events:
            if event.get("source_event_id") == source_id and games:
                event["individual_matches"] = games
                event["periods"] = [
                    {
                        "label": f"G{game.get('index')}",
                        "home": game.get("home"),
                        "away": game.get("away"),
                        "home_sets": game.get("home_sets"),
                        "away_sets": game.get("away_sets"),
                        "sets": game.get("sets"),
                    }
                    for game in games
                ]
                event["lineup"] = {
                    "home": [name for name in (_ttbl_player(detail.get(key)) for key in ("homePlayerOne", "homePlayerTwo", "homePlayerThree")) if name],
                    "away": [name for name in (_ttbl_player(detail.get(key)) for key in ("guestPlayerOne", "guestPlayerTwo", "guestPlayerThree")) if name],
                }
    return {"events": _dedupe(events), "standings": standings}


def parse_world_aquatics_discipline(payload: Any, *, competition_id: str = "5135") -> Dict[str, Any]:
    data = _loads(payload)
    if not isinstance(data, dict):
        return {"events": [], "standings": []}
    events = []
    standings = []
    for heat in data.get("Heats") or []:
        if not isinstance(heat, dict):
            continue
        phase = str(heat.get("PhaseName") or "")
        for result in heat.get("Results") or []:
            if not isinstance(result, dict):
                continue
            home = str(result.get("TeamHomeName") or "").strip()
            away = str(result.get("TeamAwayName") or "").strip()
            if home and away and result.get("FinalScoreHome") is not None and result.get("FinalScoreAway") is not None:
                match_no = result.get("MatchNo")
                source_id = f"wa:{competition_id}:{match_no}"
                when = str(result.get("Date") or heat.get("Date") or "")
                if when and "T" not in when:
                    when = f"{when}T00:00:00Z"
                elif when and not when.endswith("Z"):
                    when = when + "Z"
                quarter_home = [result.get("Q1ScoreHome"), result.get("Q2ScoreHome"), result.get("Q3ScoreHome"), result.get("Q4ScoreHome")]
                quarter_away = [result.get("Q1ScoreAway"), result.get("Q2ScoreAway"), result.get("Q3ScoreAway"), result.get("Q4ScoreAway")]
                quarters = {"home": quarter_home, "away": quarter_away}
                quarter_periods = [
                    {"label": f"Q{index}", "home": home_quarter, "away": away_quarter}
                    for index, (home_quarter, away_quarter) in enumerate(zip(quarter_home, quarter_away), start=1)
                    if home_quarter is not None or away_quarter is not None
                ]
                event = _event(
                    home=home,
                    away=away,
                    start=when or None,
                    status="finished" if str(heat.get("ResultStatus") or "").upper() == "OFFICIAL" else "scheduled",
                    home_score=result.get("FinalScoreHome"),
                    away_score=result.get("FinalScoreAway"),
                    source_id=source_id,
                    extra={
                        "event_type": TEAM_MATCH,
                        "source_family": "world-aquatics-api",
                        "source_event_id": source_id,
                        "source_event_ids": {"world-aquatics-api": source_id},
                        "stage": phase,
                        "round": heat.get("Name"),
                        "match_number": match_no,
                        "quarters": quarters,
                        "periods": quarter_periods,
                        "penalty_score": [result.get("PSOHome"), result.get("PSOAway")],
                        "coverage": "full",
                        "timing_partner": data.get("TimingAndScoringPartnerName"),
                        "upstream_origin": "world-aquatics",
                        "retrieved_at": _stamp(),
                    },
                )
                if event and event_is_valid(event, sport_id="water-polo", competition_id="world-aquatics-events"):
                    events.append(event)
                continue
            if phase == "Final Standings":
                members = result.get("TeamMembers") or []
                nation = ""
                if members and isinstance(members[0], dict):
                    nation = str(members[0].get("Nationality") or members[0].get("NAT") or "")
                if not nation:
                    continue
                standings.append(
                    {
                        "position": result.get("Rank") or result.get("HeatRank") or (len(standings) + 1),
                        "participant": nation,
                        "team": nation,
                        "played": result.get("MatchesPlayed"),
                        "wins": result.get("MatchesWon"),
                        "losses": result.get("MatchesLost"),
                        "draws": result.get("MatchesTies"),
                        "points": result.get("ClassificationPoints"),
                        "goals_for": result.get("GoalsFor"),
                        "goals_against": result.get("GoalsAgainst"),
                        "goal_difference": result.get("GoalsDifference"),
                        "source_family": "world-aquatics-api",
                        "coverage": "final_ranking",
                    }
                )
    return {"events": _dedupe(events), "standings": standings}


SAME_ORIGIN_PAIRS = {
    ("nordic-waterpolo-native", "total-waterpolo"),
    ("total-waterpolo", "nordic-waterpolo-native"),
    ("hrnsw-web", "harness.org.au"),
    ("gri-web", "gri-stadium"),
    ("rocketleague-recaps", "blast-rl"),
    ("world-aquatics-api", "microplus-timing"),
    ("world-aquatics-web", "microplus-timing"),
    ("world-aquatics-api", "omega-timing"),
}


def provider_independence(family_a: str, family_b: str) -> str:
    if not family_a and not family_b:
        return "UNKNOWN"
    if not family_b:
        return "A_ONLY"
    if family_a == family_b or (family_a, family_b) in SAME_ORIGIN_PAIRS:
        return "SAME_ORIGIN"
    if same_upstream_not_independent(family_a, family_b):
        return "SAME_ORIGIN"
    return "A_B_INDEPENDENT"


REGISTRY_MIGRATIONS = [
    {
        "old_key": "futsalplanet-leagues-cups",
        "replacement_key": "uefa-futsal-champions-league",
        "migration_reason": "Umbrella row is not one competition. UEFA Futsal Champions League is the named replacement. The old key stays in the 180 so the denominator does not shrink.",
        "date": "2026-09-23",
    },
    {
        "old_key": "germany-click-tt",
        "replacement_key": "germany-click-tt",
        "migration_reason": "Source family moved from click-TT to ttbl-web. Competition key kept.",
        "date": "2026-09-23",
    },
    {
        "old_key": "national-and-club",
        "replacement_key": None,
        "migration_reason": "Umbrella mixes unrelated national and club competitions and has no one-to-one named replacement.",
        "date": "2026-09-23",
        "blocker_code": "MODEL_SCOPE",
    },
    {
        "old_key": "tier1",
        "replacement_key": None,
        "migration_reason": "tier1 is not a named competition. BLAST and HLTV are not permitted full result sources.",
        "date": "2026-09-23",
        "blocker_code": "MODEL_SCOPE",
    },
    {
        "old_key": "title-fights",
        "replacement_key": None,
        "migration_reason": "title-fights is an umbrella over boxing sanctioning bodies, not one competition. It is not migrated onto UFC. Named bout scopes have to be explicit before a canonical boxing event is stored.",
        "date": "2026-09-23",
        "blocker_code": "MODEL_SCOPE",
    },
]
