"""Global EHF handball breadth from official old.eurohandball.com pages."""

from __future__ import annotations

import hashlib
import html as html_lib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urljoin, urlparse

from sqlalchemy.orm import Session

from collector.adapters_sites import parse_eurohandball
from collector.http import fetch_text, fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "ehf-global-breadth-v2"
SOURCE_ID = "ehf-global"
INDEX_URL = "https://old.eurohandball.com/events/competitions"
BASE = "https://old.eurohandball.com"
CURRENT_API = "https://www.eurohandball.com/umbraco/api/livescoreapi/GetLiveScoreMatches/100358"

# Guaranteed current-season round pages. Index discovery adds any other
# 2026/27 EHF round pages that are active.
FALLBACK_ROUND_URLS = (
    "https://old.eurohandball.com/ec/cl/men/2026-27/round/1/Group+Phase",
    "https://old.eurohandball.com/ec/cl/women/2026-27/round/1/Group+Phase",
    "https://old.eurohandball.com/ec/00-04/ct/men/2026-27/round/1/Round+1",
    "https://old.eurohandball.com/ec/00-04/ct/men/2026-27/round/2/Round+2",
    "https://old.eurohandball.com/ec/00-04/ct/women/2026-27/round/2/Round+2",
)

ROUND_LINK_RE = re.compile(
    r'href=["\'](?P<href>[^"\']*/ec/[^"\']*/2026-27/round[^"\']*)["\']',
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


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


def discover_round_urls(index_html: str, *, max_urls: int = 30) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()
    for match in ROUND_LINK_RE.finditer(index_html or ""):
        href = html_lib.unescape(match.group("href"))
        url = urljoin(BASE + "/", href)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= max_urls:
            break
    for url in FALLBACK_ROUND_URLS:
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls[:max_urls]


def _page_title(html: str) -> str:
    match = TITLE_RE.search(html or "")
    if not match:
        return ""
    raw = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", html_lib.unescape(raw)).strip()


def competition_meta(url: str, page_title: str = "") -> Tuple[str, str, str, str]:
    lower = unquote(urlparse(url).path).lower()
    gender = "women" if "/women/" in lower else "men" if "/men/" in lower else "mixed"

    if "/cl/" in lower or "/00-01/cl/" in lower:
        family = "champions-league"
        display = "EHF Champions League"
    elif "/ct/" in lower or "/00-04/" in lower:
        family = "european-cup"
        display = "EHF European Cup"
    elif "/00-03/" in lower:
        family = "european-league"
        display = "EHF European League"
    else:
        digest = hashlib.sha1(lower.encode("utf-8")).hexdigest()[:8]
        family = f"competition-{digest}"
        display = re.sub(
            r"^European Handball Federation\s*-\s*",
            "",
            page_title or "EHF Competition",
            flags=re.I,
        ).strip()

    suffix = {"men": "Men", "women": "Women", "mixed": "Mixed"}[gender]
    competition_id = f"handball-ehf-{family}-{gender}"
    competition_name = f"{display} {suffix}"
    stage = unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("+", " ").strip()
    if stage.lower() == "round":
        stage = ""
    return competition_id, competition_name, gender, stage


def _stable_event(
    row: Dict[str, Any],
    *,
    competition_id: str,
    competition_name: str,
    gender: str,
    stage: str,
    page_url: str,
) -> Optional[Dict[str, Any]]:
    home = row.get("home") if isinstance(row.get("home"), dict) else {}
    away = row.get("away") if isinstance(row.get("away"), dict) else {}
    home_name = str(home.get("name") or "").strip()
    away_name = str(away.get("name") or "").strip()
    start = str(row.get("start_time") or "").strip()
    if not home_name or not away_name or not start:
        return None
    material = f"{competition_id}|{start}|{home_name.casefold()}|{away_name.casefold()}"
    source_event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]
    extra = dict(row.get("extra") or {})
    extra.update(
        {
            "source_family": "ehf-web",
            "source_event_id": source_event_id,
            "source_event_ids": {"ehf-web": source_event_id},
            "source_competition_id": competition_id,
            "source_competition_name": competition_name,
            "public_competition_key": competition_id,
            "source_url": page_url,
            "gender": gender,
            "round": stage or extra.get("round"),
        }
    )
    out = dict(row)
    out.update(
        {
            "id": f"ehf:{source_event_id}",
            "source_event_id": source_event_id,
            "source_event_ids": {"ehf-web": source_event_id},
            "sport": "handball",
            "event_family": "team_match",
            "competition": competition_name,
            "competition_key": competition_id,
            "source_family": "ehf-web",
            "source_competition_id": competition_id,
            "source_competition_name": competition_name,
            "gender": gender,
            "round": stage or row.get("round"),
            "stage": stage or row.get("stage"),
            "extra": extra,
        }
    )
    return out


def parse_round_page(html: str, url: str) -> List[Dict[str, Any]]:
    competition_id, competition_name, gender, stage = competition_meta(url, _page_title(html))
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in parse_eurohandball(html or ""):
        event = _stable_event(
            row,
            competition_id=competition_id,
            competition_name=competition_name,
            gender=gender,
            stage=stage,
            page_url=url,
        )
        if not event:
            continue
        identity = event["source_event_id"]
        if identity in seen:
            continue
        seen.add(identity)
        out.append(event)
    return out



def _api_day_date(day: Dict[str, Any]) -> str:
    for key in ("date", "dateFormatted", "fullDate", "calendarUrl"):
        value = str(day.get(key) or "")
        match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", value)
        if match:
            year, month, daynum = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return f"{year:04d}-{month:02d}-{daynum:02d}"
    return ""


def _api_start(match: Dict[str, Any], stats: Dict[str, Any], day_date: str) -> Optional[str]:
    for key in ("date", "matchDate", "startDate", "dateTime", "startDateTime"):
        value = str(match.get(key) or "").strip()
        if not value:
            continue
        parsed = parse_datetime(value)
        if parsed is not None:
            return value
    clock = str(stats.get("startTime") or match.get("startTime") or "").strip()
    time_match = re.search(r"\b(\d{1,2}):(\d{2})\b", clock)
    if day_date and time_match:
        return f"{day_date}T{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}:00+02:00"
    return None


def _api_score(stats: Dict[str, Any]) -> Optional[int]:
    value = stats.get("totalGoals")
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _api_competition_id(name: str, match: Dict[str, Any]) -> str:
    slug = slugify(name)
    gender_text = " ".join(
        str(match.get(key) or "")
        for key in ("competitionType", "competitionName", "competitionShortName")
    ).lower()
    gender = "women" if any(token in gender_text for token in ("women", "female", "wcl")) else "men" if any(
        token in gender_text for token in ("men", "male", "mcl")
    ) else "mixed"
    if slug:
        return f"handball-ehf-{slug}-{gender}"[:120].rstrip("-")
    digest = hashlib.sha1(repr(sorted(match.items())).encode("utf-8")).hexdigest()[:10]
    return f"handball-ehf-current-{digest}-{gender}"


def parse_current_api(payload: Any) -> List[Dict[str, Any]]:
    """Flatten the current EHF Vue livescore model without depending on root names."""
    out: List[Dict[str, Any]] = []
    seen = set()

    def walk(value: Any, day_date: str = "") -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, day_date)
            return
        if not isinstance(value, dict):
            return

        local_day = _api_day_date(value) or day_date
        match = value.get("match") if isinstance(value.get("match"), dict) else None
        if match is not None:
            home = match.get("homeTeam") if isinstance(match.get("homeTeam"), dict) else {}
            away = match.get("guestTeam") if isinstance(match.get("guestTeam"), dict) else {}
            home_name = str(home.get("name") or "").strip()
            away_name = str(away.get("name") or "").strip()
            if home_name and away_name:
                match_stats = value.get("matchStats") if isinstance(value.get("matchStats"), dict) else {}
                home_stats = value.get("homeStats") if isinstance(value.get("homeStats"), dict) else {}
                away_stats = value.get("guestStats") if isinstance(value.get("guestStats"), dict) else {}
                competition_name = str(
                    match.get("competitionName")
                    or match.get("competitionShortName")
                    or match.get("competitionType")
                    or "EHF Competition"
                ).strip()
                competition_id = _api_competition_id(competition_name, match)
                start = _api_start(match, match_stats, local_day)
                source_url = str(match.get("url") or CURRENT_API)
                source_event_id = str(
                    match.get("id")
                    or match.get("matchId")
                    or match.get("externalId")
                    or ""
                ).strip()
                if not source_event_id:
                    material = f"{competition_id}|{start}|{home_name.casefold()}|{away_name.casefold()}"
                    source_event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]
                if source_event_id not in seen:
                    seen.add(source_event_id)
                    home_score = _api_score(home_stats)
                    away_score = _api_score(away_stats)
                    is_live = bool(match_stats.get("isLive"))
                    status_text = " ".join(
                        str(match_stats.get(key) or match.get(key) or "")
                        for key in ("status", "state", "cssClass")
                    ).lower()
                    if is_live:
                        status = "live"
                    elif any(token in status_text for token in ("finished", "final", "ended", "played")):
                        status = "finished"
                    elif home_score is not None and away_score is not None:
                        stamp = parse_datetime(start)
                        now = datetime.utcnow()
                        if stamp is not None and getattr(stamp, "tzinfo", None) is not None:
                            stamp = stamp.replace(tzinfo=None)
                        status = "finished" if stamp is not None and stamp < now - timedelta(hours=2) else "scheduled"
                    else:
                        status = "scheduled"
                    if status == "scheduled":
                        home_score = away_score = None

                    gender = "women" if competition_id.endswith("-women") else "men" if competition_id.endswith("-men") else "mixed"
                    extra = {
                        "source_family": "ehf-web",
                        "source_event_id": source_event_id,
                        "source_event_ids": {"ehf-web": source_event_id},
                        "source_competition_id": competition_id,
                        "source_competition_name": competition_name,
                        "public_competition_key": competition_id,
                        "source_url": source_url,
                        "gender": gender,
                    }
                    out.append(
                        {
                            "id": f"ehf:{source_event_id}",
                            "source_event_id": source_event_id,
                            "source_event_ids": {"ehf-web": source_event_id},
                            "sport": "handball",
                            "event_family": "team_match",
                            "competition": competition_name,
                            "competition_key": competition_id,
                            "source_family": "ehf-web",
                            "source_competition_id": competition_id,
                            "source_competition_name": competition_name,
                            "home": {
                                "id": str(home.get("id") or home.get("teamId") or "").strip(),
                                "name": home_name,
                            },
                            "away": {
                                "id": str(away.get("id") or away.get("teamId") or "").strip(),
                                "name": away_name,
                            },
                            "status": status,
                            "score": {"home": home_score, "away": away_score},
                            "start_time": start,
                            "gender": gender,
                            "venue": match.get("venue") or match.get("location"),
                            "extra": extra,
                        }
                    )

        for child in value.values():
            if child is match:
                continue
            if isinstance(child, (dict, list)):
                walk(child, local_day)

    walk(payload)
    return out


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
    gender: str,
    source_url: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="handball",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            region_id="europe",
            event_model="team_match",
            competition_type="tournament",
            gender=gender,
            country_based=False,
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(competition)
        db.flush()

    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=source.source_id,
            priority=10,
            source_competition_id=competition_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="Official EHF current-season round pages",
            verification="old.eurohandball.com 2026/27 server-rendered schedule/results",
            polling_class="MEDIUM",
            source_config_json=dump_json(
                {
                    "url": source_url,
                    "source_competition_name": competition_name,
                }
            ),
            independence_status="established",
            upstream_family="ehf-web",
        )
        db.add(mapping)
        db.flush()
    else:
        config = load_json(mapping.source_config_json, {}) or {}
        if config.get("url") != source_url:
            config["url"] = source_url
            config["source_competition_name"] = competition_name
            mapping.source_config_json = dump_json(config)
    return mapping


def _in_window(event: Dict[str, Any], *, now: datetime) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return False
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.replace(tzinfo=None)
    return now - timedelta(days=45) <= stamp <= now + timedelta(days=260)


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_pages: int = 30,
    max_ingest: int = 2500,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    now = datetime.utcnow()
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "api_http_status": 0,
        "api_events": 0,
        "pages": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "http_errors": 0,
        "by_competition": {},
    }
    seen_competitions: Set[str] = set()

    # Prefer the current EHF JSON origin. It is a separate host from the
    # legacy schedule site and powers the public livescore widget.
    api_result = fetch_url(CURRENT_API)
    stats["requests"] += 1
    stats["api_http_status"] = int(getattr(api_result, "http_status", 0) or 0)
    api_rows = parse_current_api(api_result.payload) if getattr(api_result, "ok", False) else []
    stats["api_events"] = len(api_rows)
    for event in api_rows:
        competition_id = str(event.get("competition_key") or "")
        competition_name = str(event.get("competition") or competition_id)
        gender = str(event.get("gender") or "mixed")
        if not competition_id:
            continue
        _ensure_mapping(
            db,
            source=source,
            competition_id=competition_id,
            competition_name=competition_name,
            gender=gender,
            source_url=CURRENT_API,
        )
        seen_competitions.add(competition_id)
        bucket = stats["by_competition"].setdefault(
            competition_id,
            {"events": 0, "eligible": 0, "ingested": 0},
        )
        bucket["events"] += 1
        if not _in_window(event, now=now):
            continue
        stats["events"] += 1
        stats["eligible"] += 1
        bucket["eligible"] += 1
        if _ingest(db, event, source.source_id):
            stats["ingested"] += 1
            bucket["ingested"] += 1
    db.commit()
    if heartbeat:
        heartbeat()

    index_result = getter(INDEX_URL)
    stats["requests"] += 1
    index_html = (
        index_result.payload
        if getattr(index_result, "ok", False) and isinstance(getattr(index_result, "payload", None), str)
        else ""
    )
    if not index_html:
        stats["http_errors"] += 1
    urls = discover_round_urls(index_html, max_urls=max_pages)

    for url in urls:
        if stats["ingested"] >= max_ingest:
            stats["status"] = "bounded"
            break
        result = getter(url)
        stats["requests"] += 1
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), str):
            stats["http_errors"] += 1
            continue
        stats["pages"] += 1
        rows = parse_round_page(result.payload, url)
        stats["events"] += len(rows)
        if not rows:
            continue

        competition_id = str(rows[0].get("competition_key") or "")
        competition_name = str(rows[0].get("competition") or competition_id)
        gender = str(rows[0].get("gender") or "mixed")
        _ensure_mapping(
            db,
            source=source,
            competition_id=competition_id,
            competition_name=competition_name,
            gender=gender,
            source_url=url,
        )
        seen_competitions.add(competition_id)
        bucket = stats["by_competition"].setdefault(
            competition_id,
            {"events": 0, "eligible": 0, "ingested": 0},
        )
        bucket["events"] += len(rows)

        for event in rows:
            if not _in_window(event, now=now):
                continue
            stats["eligible"] += 1
            bucket["eligible"] += 1
            if _ingest(db, event, source.source_id):
                stats["ingested"] += 1
                bucket["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                break
        db.commit()
        if heartbeat:
            heartbeat()

    stats["competitions"] = len(seen_competitions)
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
    min_interval_minutes: int = 90,
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
    return run_breadth_ingest(db, text_getter=text_getter, heartbeat=heartbeat)
