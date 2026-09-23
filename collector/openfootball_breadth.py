"""Global CC0 football breadth from OpenFootball public-domain repositories."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.competition_identity import unique_label_competition
from collector.http import fetch_text, fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "openfootball-global-breadth-v1"
SOURCE_ID = "openfootball-global"

REPOSITORIES = (
    "england",
    "europe",
    "italy",
    "deutschland",
    "espana",
    "belgium",
    "south-america",
    "world",
    "worldcup",
    "champions-league",
    "internationals.more",
)

TREE_URL = "https://api.github.com/repos/openfootball/{repo}/git/trees/master?recursive=1"
RAW_URL = "https://raw.githubusercontent.com/openfootball/{repo}/master/{path}"

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
_DATE_RE = re.compile(
    r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$"
)
_TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s+(.*)$")
_SCORE_RE = re.compile(r"^(.*?)(?:\s{2,})(\d+\s*[-:]\s*\d+(?:\s.*)?)\s*$", re.IGNORECASE)
_RESULT_RE = re.compile(r"(\d+)\s*[-:]\s*(\d+)")
_COUNTRY_TAG_RE = re.compile(r"\s+\([A-Z]{2,3}\)\s*$")
_YEAR_RE = re.compile(r"\b(20\d{2})(?:[/\-]\d{2,4})?\b")


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


def current_season_tokens(today: Optional[date] = None) -> Tuple[str, str]:
    today = today or datetime.utcnow().date()
    if today.month >= 7:
        season = f"{today.year}-{str(today.year + 1)[-2:]}"
    else:
        season = f"{today.year - 1}-{str(today.year)[-2:]}"
    return str(today.year), season


def _path_is_current(path: str, *, today: Optional[date] = None) -> bool:
    calendar, season = current_season_tokens(today)
    lowered = str(path or "").lower()
    if not lowered.endswith(".txt"):
        return False
    if any(mark in lowered for mark in ("/archive/", "/rsssf/", "_squads", "squads.")):
        return False
    return (
        season in lowered
        or f"/{calendar}/" in lowered
        or f"/{calendar}_" in lowered
        or f"{calendar}_" in lowered
        or f"/{calendar}--" in lowered
        or lowered.endswith(f"/{calendar}.txt")
    )


def discover_current_paths(payload: Any, *, today: Optional[date] = None, max_paths: int = 120) -> List[str]:
    tree = payload.get("tree") if isinstance(payload, dict) else []
    paths = [
        str(item.get("path") or "")
        for item in tree or []
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and _path_is_current(str(item.get("path") or ""), today=today)
    ]
    return sorted(paths)[:max_paths]


def _header_name(text: str, path: str) -> str:
    for raw in str(text or "").splitlines()[:30]:
        line = raw.strip()
        if line.startswith("="):
            name = line.lstrip("=").split("#", 1)[0].strip()
            name = re.sub(r"\s+20\d{2}(?:[/\-]\d{2,4})?\s*$", "", name).strip()
            if name:
                return name
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = re.sub(r"^(?:20\d{2}(?:-\d{2})?[_-])", "", stem)
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Football"


def _base_year(text: str, path: str, *, today: Optional[date] = None) -> int:
    for raw in str(text or "").splitlines()[:30]:
        if raw.strip().startswith("="):
            match = _YEAR_RE.search(raw)
            if match:
                return int(match.group(1))
    match = _YEAR_RE.search(path)
    if match:
        return int(match.group(1))
    return (today or datetime.utcnow().date()).year


def _clean_team(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    return _COUNTRY_TAG_RE.sub("", name).strip()


def _competition_id(repo: str, path: str, competition_name: str) -> str:
    canonical = unique_label_competition(competition_name, sport_id="football")
    if canonical:
        return canonical
    digest = hashlib.sha1(f"{repo}|{path}".encode("utf-8")).hexdigest()[:8]
    return f"football-of-{digest}-{slugify(competition_name)}"[:120].rstrip("-")


def _score(tail: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    match = _RESULT_RE.search(str(tail or ""))
    if not match:
        return None, None, None
    lowered = str(tail or "").lower()
    result_type = "penalties" if "pen." in lowered or " pen" in lowered else "extra_time" if "aet" in lowered else None
    return int(match.group(1)), int(match.group(2)), result_type


def parse_football_txt(
    text: str,
    *,
    repo: str,
    path: str,
    today: Optional[date] = None,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    competition_name = _header_name(text, path)
    competition_id = _competition_id(repo, path, competition_name)
    current_year = _base_year(text, path, today=today)
    current_month: Optional[int] = None
    current_day: Optional[int] = None
    last_month: Optional[int] = None
    round_name = ""
    events: List[Dict[str, Any]] = []

    for raw in str(text or "").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("="):
            continue
        if stripped.startswith("▪") or stripped.startswith("•"):
            round_name = stripped.lstrip("▪•").strip()
            continue

        date_match = _DATE_RE.match(raw)
        if date_match:
            month_name, day_text, explicit_year = date_match.groups()
            month = _MONTHS.get(month_name)
            if month is None:
                continue
            if explicit_year:
                current_year = int(explicit_year)
            elif last_month is not None and last_month >= 11 and month <= 2:
                current_year += 1
            current_month = month
            current_day = int(day_text)
            last_month = month
            continue

        if current_month is None or current_day is None or " v " not in raw:
            continue

        body = raw.rstrip()
        time_value = None
        time_match = _TIME_RE.match(body)
        if time_match:
            time_value = time_match.group(1)
            body = time_match.group(2).strip()
        else:
            body = body.strip()

        if " v " not in body:
            continue
        home_raw, right = body.split(" v ", 1)
        score_tail = ""
        score_match = _SCORE_RE.match(right)
        if score_match:
            away_raw, score_tail = score_match.groups()
        else:
            away_raw = right

        home = _clean_team(home_raw)
        away = _clean_team(away_raw)
        if not home or not away:
            continue
        try:
            event_date = date(current_year, current_month, current_day)
        except ValueError:
            continue

        home_score, away_score, result_type = _score(score_tail)
        finished = home_score is not None and away_score is not None
        material = f"{repo}|{path}|{event_date.isoformat()}|{home}|{away}"
        source_event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]
        events.append(
            {
                "id": f"openfootball:{source_event_id}",
                "source_event_id": source_event_id,
                "source_event_ids": {"openfootball": source_event_id},
                "sport": "football",
                "competition": competition_name,
                "competition_key": competition_id,
                "source_family": "openfootball",
                "source_competition_id": f"{repo}:{path}",
                "source_competition_name": competition_name,
                "home": {"name": home},
                "away": {"name": away},
                "status": "finished" if finished else "scheduled",
                "score": {"home": home_score, "away": away_score, "period": "ft" if finished else None},
                # The TXT time is local but many files do not declare an IANA
                # timezone. Date precision is truthful; guessed UTC is not.
                "start_time": f"{event_date.isoformat()}T12:00:00Z",
                "start_date": event_date.isoformat(),
                "start_precision": "day",
                "round": round_name or None,
                "result_type": result_type,
                "extra": {
                    "source_family": "openfootball",
                    "source_competition_id": f"{repo}:{path}",
                    "source_competition_name": competition_name,
                    "public_competition_key": competition_id,
                    "openfootball_repo": repo,
                    "openfootball_path": path,
                    "openfootball_local_time": time_value,
                    "start_date": event_date.isoformat(),
                    "start_precision": "day",
                    "round": round_name or None,
                    "result_type": result_type,
                },
            }
        )

    return competition_id, competition_name, events


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
    repo: str,
    path: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="football",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            region_id="world",
            event_model="team_match",
            competition_type="league",
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
            priority=20,
            source_competition_id=f"{repo}:{path}",
            enabled=True,
            coverage_scope="full",
            coverage_notes="OpenFootball CC0 current-season public-domain fixtures/results",
            verification="OpenFootball CC0 Football.TXT current-season file",
            polling_class="SLOW",
            source_config_json=dump_json({"repo": repo, "path": path, "source_competition_name": competition_name}),
            independence_status="established",
            upstream_family="openfootball",
        )
        db.add(mapping)
        db.flush()
    return mapping


def _in_window(event: Dict[str, Any], *, now: datetime) -> bool:
    try:
        day = date.fromisoformat(str(event.get("start_date") or ""))
    except ValueError:
        return False
    return now.date() - timedelta(days=14) <= day <= now.date() + timedelta(days=220)


def run_breadth_ingest(
    db: Session,
    *,
    tree_getter=None,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    max_files: int = 100,
    max_ingest: int = 7000,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "files": 0, "events": 0, "ingested": 0}

    tree_get = tree_getter or fetch_url
    text_get = text_getter or fetch_text
    now = datetime.utcnow()
    stats: Dict[str, Any] = {
        "status": "ok",
        "repositories": {},
        "files": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "errors": 0,
    }
    seen_competitions = set()

    for repo in REPOSITORIES:
        if stats["files"] >= max_files or stats["ingested"] >= max_ingest:
            stats["status"] = "bounded"
            break
        tree_result = tree_get(TREE_URL.format(repo=repo))
        tree_payload = tree_result.payload if getattr(tree_result, "ok", False) else {}
        paths = discover_current_paths(tree_payload, today=now.date())
        repo_stats = {
            "tree_status": int(getattr(tree_result, "http_status", 0) or 0),
            "paths": len(paths),
            "files": 0,
            "events": 0,
            "ingested": 0,
        }

        for path in paths:
            if stats["files"] >= max_files or stats["ingested"] >= max_ingest:
                stats["status"] = "bounded"
                break
            result = text_get(RAW_URL.format(repo=repo, path=path))
            if not getattr(result, "ok", False) or not isinstance(result.payload, str):
                stats["errors"] += 1
                continue
            competition_id, competition_name, events = parse_football_txt(
                result.payload, repo=repo, path=path, today=now.date()
            )
            if not events:
                continue
            mapping = _ensure_mapping(
                db,
                source=source,
                competition_id=competition_id,
                competition_name=competition_name,
                repo=repo,
                path=path,
            )
            stats["files"] += 1
            repo_stats["files"] += 1
            stats["events"] += len(events)
            repo_stats["events"] += len(events)
            seen_competitions.add(competition_id)

            for event in events:
                if not _in_window(event, now=now):
                    continue
                stats["eligible"] += 1
                if _ingest(db, event, mapping.source_id):
                    stats["ingested"] += 1
                    repo_stats["ingested"] += 1
                if stats["ingested"] >= max_ingest:
                    break

            db.commit()
            if heartbeat:
                heartbeat()

        stats["repositories"][repo] = repo_stats
        if heartbeat:
            heartbeat()

    stats["competitions"] = len(seen_competitions)
    cache_clear(db)
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
    min_interval_hours: int = 12,
    owner: Optional[str] = None,
    heartbeat: Optional[Callable[[], None]] = None,
    tree_getter=None,
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
        and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours)
    ):
        return None
    job.last_status = "running"
    job.last_error = dump_json({"state": "running"})
    db.flush()
    return run_breadth_ingest(
        db,
        tree_getter=tree_getter,
        text_getter=text_getter,
        heartbeat=heartbeat,
    )
