"""Global FIBA basketball breadth from public server-rendered Next.js data."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from collector.http import fetch_text
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

logger = logging.getLogger(__name__)

JOB_KEY = "fiba-global-breadth-v2"
SOURCE_ID = "fiba-global"
BASE = "https://www.fiba.basketball"
GLOBAL_GAMES_URL = f"{BASE}/en/games"
EVENTS_URL = f"{BASE}/en/events"

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,\s*"(.*?)"\]\)', re.DOTALL)
_UNDEFINED = "$undefined"


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


def _clean(value: Any) -> Any:
    return None if value == _UNDEFINED else value


def decoded_flight_chunks(html: str) -> Iterable[Any]:
    """Yield parsed JSON values from Next.js React Server Component pushes."""
    for raw in _PUSH_RE.findall(html or ""):
        try:
            decoded = json.loads('"' + raw + '"')
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if ":" not in decoded:
            continue
        _chunk, _sep, body = decoded.partition(":")
        body = re.sub(r"^[A-Za-z]?(?=[\[{])", "", body.strip())
        if not body or body[0] not in "[{":
            continue
        try:
            yield json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue


def find_dicts(obj: Any, required: Set[str], *, limit: int = 10000) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    stack: List[Tuple[Any, int]] = [(obj, 0)]
    while stack and len(found) < limit:
        node, depth = stack.pop()
        if depth > 32:
            continue
        if isinstance(node, dict):
            if required.issubset(node.keys()):
                found.append(node)
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, list):
            stack.extend((value, depth + 1) for value in node)
    return found


def parse_event_index(html: str) -> List[Dict[str, Any]]:
    events: Dict[str, Dict[str, Any]] = {}
    for payload in decoded_flight_chunks(html):
        for item in find_dicts(payload, {"slug", "fibaOfficialName"}):
            slug = str(_clean(item.get("slug")) or "").strip()
            name = str(_clean(item.get("fibaOfficialName")) or _clean(item.get("title")) or "").strip()
            if not slug or not name or slug in events:
                continue
            hosts = _clean(item.get("fibaHostJson")) or []
            country = ""
            city = ""
            if isinstance(hosts, list) and hosts and isinstance(hosts[0], dict):
                country = str(hosts[0].get("countryName") or hosts[0].get("countryCode") or "").strip()
                cities = hosts[0].get("cities") or []
                if isinstance(cities, list) and cities and isinstance(cities[0], dict):
                    city = str(cities[0].get("name") or "").strip()
            events[slug] = {
                "slug": slug,
                "name": name,
                "start": str(_clean(item.get("eventDateStart")) or "")[:10],
                "end": str(_clean(item.get("eventDateEnd")) or "")[:10],
                "country": country,
                "city": city,
                "gender": str(_clean(item.get("gender")) or _clean(item.get("fibaGender")) or "").strip(),
                "zone": str(_clean(item.get("fibaSource")) or "").strip(),
            }
    return sorted(events.values(), key=lambda row: (row.get("start") or "", row["slug"]))


def parse_game_dicts(html: str) -> List[Dict[str, Any]]:
    games: Dict[str, Dict[str, Any]] = {}
    for payload in decoded_flight_chunks(html):
        for item in find_dicts(payload, {"gameId", "teamA", "teamB"}):
            gid = str(_clean(item.get("gameId")) or "").strip()
            if not gid or gid in games:
                continue
            if not isinstance(item.get("teamA"), dict) or not isinstance(item.get("teamB"), dict):
                continue
            games[gid] = item
    return list(games.values())


def _event_overlaps(row: Dict[str, Any], *, low: date, high: date) -> bool:
    try:
        start = date.fromisoformat(str(row.get("start") or ""))
    except ValueError:
        start = None
    try:
        end = date.fromisoformat(str(row.get("end") or ""))
    except ValueError:
        end = start
    if start is None and end is None:
        return False
    start = start or end
    end = end or start
    return bool(start and end and start <= high and end >= low)


def _competition_meta(game: Dict[str, Any], event_meta: Optional[Dict[str, Any]]) -> Tuple[str, str, str]:
    comp = _clean(game.get("competition")) or {}
    if not isinstance(comp, dict):
        comp = {}
    slug = str(
        (event_meta or {}).get("slug")
        or _clean(comp.get("slug"))
        or _clean(game.get("eventSlug"))
        or _clean(game.get("competitionSlug"))
        or ""
    ).strip()
    name = str(
        (event_meta or {}).get("name")
        or _clean(comp.get("officialName"))
        or _clean(comp.get("name"))
        or _clean(game.get("competitionName"))
        or "FIBA Basketball"
    ).strip()
    native_id = str(
        _clean(comp.get("competitionId"))
        or _clean(comp.get("id"))
        or _clean(game.get("competitionId"))
        or slug
        or ""
    ).strip()
    if not slug:
        digest = hashlib.sha1(f"{native_id}|{name}".encode("utf-8")).hexdigest()[:10]
        slug = f"{digest}-{slugify(name)}"
    competition_id = f"basketball-fiba-{slugify(slug)}"[:120].rstrip("-")
    return competition_id, name, native_id or slug


def _status(game: Dict[str, Any]) -> str:
    if bool(_clean(game.get("isLive"))):
        return "live"
    raw = " ".join(
        str(_clean(game.get(key)) or "")
        for key in ("gameStatisticStatusCode", "gameStatus", "status", "statusCode")
    ).lower()
    if any(token in raw for token in ("final", "finished", "complete", "official", "ended")):
        return "finished"
    return "scheduled"


def _score(value: Any) -> Any:
    value = _clean(value)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def game_to_event(game: Dict[str, Any], event_meta: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    gid = str(_clean(game.get("gameId")) or "").strip()
    team_a = _clean(game.get("teamA")) or {}
    team_b = _clean(game.get("teamB")) or {}
    if not gid or not isinstance(team_a, dict) or not isinstance(team_b, dict):
        return None
    home_name = str(_clean(team_a.get("officialName")) or _clean(team_a.get("name")) or _clean(team_a.get("code")) or "").strip()
    away_name = str(_clean(team_b.get("officialName")) or _clean(team_b.get("name")) or _clean(team_b.get("code")) or "").strip()
    if not home_name or not away_name:
        return None

    competition_id, competition_name, source_competition_id = _competition_meta(game, event_meta)
    start = str(_clean(game.get("gameDateTime")) or _clean(game.get("startDate")) or "").strip() or None
    round_info = _clean(game.get("round")) or {}
    round_name = round_info.get("roundName") if isinstance(round_info, dict) else round_info
    status = _status(game)
    home_score = _score(game.get("teamAScore"))
    away_score = _score(game.get("teamBScore"))
    if status == "scheduled":
        home_score = away_score = None

    comp = _clean(game.get("competition")) or {}
    zone = comp.get("fibaZone") if isinstance(comp, dict) else None
    country = str(
        _clean(game.get("hostCountry"))
        or (event_meta or {}).get("country")
        or ""
    ).strip()

    home_code = str(_clean(team_a.get("code")) or _clean(team_a.get("shortName")) or "").strip()
    away_code = str(_clean(team_b.get("code")) or _clean(team_b.get("shortName")) or "").strip()
    event_slug = str((event_meta or {}).get("slug") or _clean(game.get("eventSlug")) or "").strip()
    game_url = (
        f"{BASE}/en/events/{event_slug}/games/{gid}-{home_code}-{away_code}"
        if event_slug and home_code and away_code
        else None
    )

    extra = {
        "source_family": "fiba-web",
        "source_event_id": gid,
        "source_event_ids": {"fiba-web": gid},
        "source_competition_id": source_competition_id,
        "source_competition_name": competition_name,
        "public_competition_key": competition_id,
        "fiba_event_slug": (event_meta or {}).get("slug"),
        "fiba_zone": zone or (event_meta or {}).get("zone"),
        "round": round_name,
        "group": _clean(game.get("groupPairingCode")),
        "game_statistic_status": _clean(game.get("gameStatisticStatusCode")),
        "fiba_home_code": home_code or None,
        "fiba_away_code": away_code or None,
        "fiba_game_url": game_url,
    }
    return {
        "id": f"fiba:{gid}",
        "source_event_id": gid,
        "source_event_ids": {"fiba-web": gid},
        "sport": "basketball",
        "event_family": "team_match",
        "competition": competition_name,
        "competition_key": competition_id,
        "source_family": "fiba-web",
        "source_competition_id": source_competition_id,
        "source_competition_name": competition_name,
        "home": {
            "id": str(_clean(team_a.get("organisationId")) or _clean(team_a.get("teamId")) or "").strip(),
            "name": home_name,
        },
        "away": {
            "id": str(_clean(team_b.get("organisationId")) or _clean(team_b.get("teamId")) or "").strip(),
            "name": away_name,
        },
        "status": status,
        "score": {"home": home_score, "away": away_score},
        "start_time": start,
        "venue": str(_clean(game.get("venue")) or _clean(game.get("hostCity")) or (event_meta or {}).get("city") or "").strip() or None,
        "country_id": country or None,
        "round": round_name,
        "stage": round_name,
        "extra": extra,
    }


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
    source_competition_id: str,
    event_meta: Optional[Dict[str, Any]] = None,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="basketball",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            country_id=(event_meta or {}).get("country") or None,
            region_id="world",
            event_model="team_match",
            competition_type="tournament",
            gender=(event_meta or {}).get("gender") or None,
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
            source_competition_id=source_competition_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="FIBA public server-rendered schedule",
            verification="FIBA public /games Next.js RSC",
            polling_class="MEDIUM",
            source_config_json=dump_json({
                "event_slug": (event_meta or {}).get("slug"),
                "source_competition_name": competition_name,
            }),
            independence_status="established",
            upstream_family="fiba-web",
        )
        db.add(mapping)
        db.flush()
    return mapping


def _within_window(event: Dict[str, Any], *, low: datetime, high: datetime) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return False
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return low <= stamp <= high


def run_breadth_ingest(
    db: Session,
    *,
    text_getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    days_back: int = 1,
    days_forward: int = 4,
    max_events_index: int = 40,
    max_ingest: int = 2500,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    getter = text_getter or fetch_text
    now = datetime.utcnow()
    low = now - timedelta(days=days_back)
    high = now + timedelta(days=days_forward + 1)
    low_day, high_day = low.date(), high.date()
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "event_pages": 0,
        "http_errors": 0,
        "global_games": 0,
    }
    seen_games: Set[str] = set()
    seen_competitions: Set[str] = set()

    def ingest_games(rows: List[Dict[str, Any]], meta: Optional[Dict[str, Any]] = None) -> None:
        nonlocal stats
        for raw in rows:
            gid = str(_clean(raw.get("gameId")) or "").strip()
            if not gid or gid in seen_games:
                continue
            event = game_to_event(raw, meta)
            if not event or not _within_window(event, low=low, high=high):
                continue
            seen_games.add(gid)
            stats["eligible"] += 1
            cid = str(event.get("competition_key") or "")
            _ensure_mapping(
                db,
                source=source,
                competition_id=cid,
                competition_name=str(event.get("competition") or cid),
                source_competition_id=str(event.get("source_competition_id") or cid),
                event_meta=meta,
            )
            seen_competitions.add(cid)
            if _ingest(db, event, source.source_id):
                stats["ingested"] += 1
            if stats["ingested"] >= max_ingest:
                stats["status"] = "bounded"
                return

    global_result = getter(GLOBAL_GAMES_URL)
    stats["requests"] += 1
    if getattr(global_result, "ok", False) and isinstance(getattr(global_result, "payload", None), str):
        global_rows = parse_game_dicts(global_result.payload)
        stats["global_games"] = len(global_rows)
        stats["events"] += len(global_rows)
        ingest_games(global_rows)
    else:
        stats["http_errors"] += 1

    # Prefer one global request. Only fan out across event pages when the
    # global board exposes no usable in-window games.
    if stats["eligible"] == 0 and stats["ingested"] < max_ingest:
        index_result = getter(EVENTS_URL)
        stats["requests"] += 1
        if getattr(index_result, "ok", False) and isinstance(getattr(index_result, "payload", None), str):
            active_events = [
                row
                for row in parse_event_index(index_result.payload)
                if _event_overlaps(row, low=low_day, high=high_day)
            ][:max_events_index]
            for meta in active_events:
                if stats["ingested"] >= max_ingest:
                    break
                result = getter(f"{BASE}/en/events/{meta['slug']}/games")
                stats["requests"] += 1
                stats["event_pages"] += 1
                if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), str):
                    stats["http_errors"] += 1
                    continue
                rows = parse_game_dicts(result.payload)
                stats["events"] += len(rows)
                ingest_games(rows, meta)
                db.commit()
                if heartbeat:
                    heartbeat()
        else:
            stats["http_errors"] += 1

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
    min_interval_minutes: int = 60,
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
    return run_breadth_ingest(
        db,
        heartbeat=heartbeat,
        text_getter=text_getter,
    )
