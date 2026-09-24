"""Official Liga ASOBAL near-window breadth.

ASOBAL exposes a stable public calendar route per matchday (/calendario/{n}/).
The root calendar identifies the current round. We fetch a small rolling round
window instead of hammering all 30 matchdays every cycle.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from collector.html_parse import _text
from collector.http import fetch_text
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json

JOB_KEY = "asobal-season-breadth-v1"
SOURCE_ID = "asobal-global"
COMPETITION_ID = "spain-asobal"
ROOT_URL = "https://asobal.es/liga/calendario/"
ROUND_URL = "https://asobal.es/liga/calendario/{round_no}/"
MADRID = ZoneInfo("Europe/Madrid")

TEAM_NAMES = {
    "BAR": "Barça",
    "LOG": "Dicorpebal Logroño La Rioja",
    "GRA": "Fraikin BM. Granollers",
    "BID": "IRUDEK Bidasoa Irun",
    "TLV": "Bathco BM. Torrelavega",
    "ATV": "Recoletas Salud At. Valladolid",
    "ADE": "ABANCA Ademar León",
    "CAS": "BM. Caserío Ciudad Real",
    "EON": "HORNEO BM. Alicante",
    "VDA": "Tubos Aranda Villa de Aranda",
    "CQN": "REBI Balonmano Cuenca",
    "CNG": "Frigoríficos del Morrazo",
    "PGE": "Cajasol Ángel Ximénez P. Genil",
    "NAV": "Viveros Herol BM. Nava",
    "SEV": "Cajasol Sevilla BM. Proin",
    "PSG": "Fertiberia Puerto Sagunto",
}

HOME_VENUES = {
    "BAR": "Palau Blaugrana",
    "LOG": "Palacio de los Deportes de La Rioja",
    "GRA": "Palau d'Esports de Granollers",
    "BID": "Pabellón Artaleku",
    "TLV": "Pabellón Municipal Vicente Trueba",
    "ATV": "Polideportivo Huerta Del Rey",
    "ADE": "Palacio Municipal de los Deportes Urbano González",
    "CAS": "Pabellón Quijote Arena",
    "EON": "Pabellón Pitiu Rochel",
    "VDA": "Pabellón Santiago Manguan",
    "CQN": "Pabellón Municipal El Sargal",
    "CNG": "Pabellón Municipal de O Gatañal",
    "PGE": "Pabellón Municipal Alcalde Miguel Salas",
    "NAV": "Pabellón Municipal Guerrer@s Naveros",
    "SEV": "Centro Deportivo Amate",
    "PSG": "Pabellón Polideportivo Port de Sagunt",
}

ROUND_RE = re.compile(r"Partidos\s+Jornada\s+(\d+)", re.I)
DATE_MATCH_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{1,2}:\d{2}).*?"
    r"\b([A-Z]{3})\s+(\d{1,3})\s*-\s*(\d{1,3})\s+([A-Z]{3})\b",
    re.I,
)
STATUS_FINAL_RE = re.compile(r"Partido\s+finalizado", re.I)
STATUS_NOT_STARTED_RE = re.compile(r"No\s+ha\s+comenzado", re.I)


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def _source(db: Session) -> Optional[SportsSource]:
    row = db.get(SportsSource, SOURCE_ID)
    if row is not None and source_collectable(row):
        return row
    return None


def current_round(html: str) -> Optional[int]:
    match = ROUND_RE.search(_text(html or ""))
    if not match:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 30 else None


def _utc_start(day_text: str, time_text: str) -> Optional[str]:
    try:
        local = datetime.strptime(f"{day_text} {time_text}", "%d/%m/%Y %H:%M").replace(tzinfo=MADRID)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_asobal_round(html: str) -> List[Dict[str, Any]]:
    text = _text(html or "")
    round_no = current_round(html)
    if not round_no:
        return []
    matches = list(DATE_MATCH_RE.finditer(text))
    out: List[Dict[str, Any]] = []
    for index, match in enumerate(matches):
        day_text, time_text, home_code, home_raw, away_raw, away_code = match.groups()
        home_code = home_code.upper()
        away_code = away_code.upper()
        if home_code not in TEAM_NAMES or away_code not in TEAM_NAMES:
            continue
        start_time = _utc_start(day_text, time_text)
        if not start_time:
            continue
        tail_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        tail = text[match.end():tail_end]
        finished = bool(STATUS_FINAL_RE.search(tail))
        scheduled = bool(STATUS_NOT_STARTED_RE.search(tail))
        status = "finished" if finished else "scheduled" if scheduled else "scheduled"
        home_score = int(home_raw) if finished else None
        away_score = int(away_raw) if finished else None
        source_event_id = f"r{round_no}:{home_code}:{away_code}"
        venue = HOME_VENUES.get(home_code)
        extra = {
            "source_family": "asobal-web",
            "source_event_id": source_event_id,
            "source_event_ids": {"asobal-web": source_event_id},
            "source_competition_id": COMPETITION_ID,
            "source_competition_name": "Liga ASOBAL",
            "public_competition_key": COMPETITION_ID,
            "round": f"Jornada {round_no}",
            "home_code": home_code,
            "away_code": away_code,
            "venue": venue,
        }
        out.append({
            "id": f"asobal:{source_event_id}",
            "source_event_id": source_event_id,
            "source_event_ids": {"asobal-web": source_event_id},
            "sport": "handball",
            "event_family": "team_match",
            "competition": "Liga ASOBAL",
            "competition_key": COMPETITION_ID,
            "source_family": "asobal-web",
            "source_competition_id": COMPETITION_ID,
            "source_competition_name": "Liga ASOBAL",
            "home": {"id": home_code, "name": TEAM_NAMES[home_code]},
            "away": {"id": away_code, "name": TEAM_NAMES[away_code]},
            "status": status,
            "score": {"home": home_score, "away": away_score},
            "start_time": start_time,
            "round": f"Jornada {round_no}",
            "stage": f"Jornada {round_no}",
            "venue": venue,
            "country_id": "ESP",
            "extra": extra,
        })
    return out


def _ensure_mapping(db: Session, source: SportsSource) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, COMPETITION_ID)
    if competition is None:
        competition = SportsCompetition(
            competition_id=COMPETITION_ID,
            sport_id="handball",
            name="Liga ASOBAL",
            official_name="Liga NEXUS ENERGÍA ASOBAL",
            slug=COMPETITION_ID,
            country_id="ESP",
            region_id="europe",
            event_model="team_match",
            competition_type="league",
            country_based=True,
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()
    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=COMPETITION_ID, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=COMPETITION_ID,
            source_id=source.source_id,
            priority=10,
            source_competition_id=COMPETITION_ID,
            enabled=True,
            coverage_scope="full",
            coverage_notes="Official ASOBAL rolling matchday calendar",
            verification="asobal.es public calendar",
            polling_class="MEDIUM",
            source_config_json=dump_json({"url": ROOT_URL}),
            independence_status="established",
            upstream_family="asobal-web",
        )
        db.add(mapping)
        db.flush()
    return mapping


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    rounds_back: int = 1,
    rounds_forward: int = 4,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    root = getter(ROOT_URL)
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 1,
        "root_http_status": int(getattr(root, "http_status", 0) or 0),
        "current_round": None,
        "rounds": [],
        "events": 0,
        "ingested": 0,
        "http_errors": 0,
    }
    if not getattr(root, "ok", False) or not isinstance(getattr(root, "payload", None), str):
        stats["status"] = "unavailable"
        return stats

    round_no = current_round(root.payload)
    stats["current_round"] = round_no
    if round_no is None:
        stats["status"] = "unparsed"
        return stats

    mapping = _ensure_mapping(db, source)
    first = max(1, round_no - rounds_back)
    last = min(30, round_no + rounds_forward)
    for value in range(first, last + 1):
        result = root if value == round_no else getter(ROUND_URL.format(round_no=value))
        if value != round_no:
            stats["requests"] += 1
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), str):
            stats["http_errors"] += 1
            stats["rounds"].append({"round": value, "http": getattr(result, "http_status", None), "events": 0})
            continue
        events = parse_asobal_round(result.payload)
        stats["events"] += len(events)
        written = 0
        for event in events:
            if _ingest(db, event, mapping.source_id):
                stats["ingested"] += 1
                written += 1
        stats["rounds"].append({
            "round": value,
            "http": int(getattr(result, "http_status", 0) or 0),
            "events": len(events),
            "ingested": written,
        })
        db.commit()
        if heartbeat:
            heartbeat()

    cache_clear(db, prefix="events:")
    job = _job(db)
    job.last_run_at = datetime.utcnow()
    job.last_status = stats["status"]
    job.items_written = int(stats["ingested"])
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats


def run_if_due(
    db: Session,
    *,
    min_interval_minutes: int = 30,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    text_getter=None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None
    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if (
        payload.get("state") == "done"
        and job.last_run_at
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
    ):
        return None
    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(db, heartbeat=heartbeat, text_getter=text_getter)
