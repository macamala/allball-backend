"""Global ESPN tennis dated-board breadth.

The public tennis/all scoreboard returns either direct match events or
tournament containers with groupings[].competitions[]. Both shapes are
flattened into provider-neutral individual matches.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.competition_identity import unique_label_competition
from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsCompetition, SportsSource, SportsSourceCompetition
from collector.sources import source_collectable
from collector.util import dump_json, load_json, parse_datetime, slugify

JOB_KEY = "espn-tennis-breadth-v1"
SOURCE_ID = "espn-tennis-global"
URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/all/scoreboard?dates={date}"


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


def _competition_id(name: str) -> str:
    canonical = unique_label_competition(name, sport_id="tennis")
    if canonical:
        return canonical
    cleaned = slugify(name)
    digest = hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"tennis-espn-{digest}-{cleaned}"[:120].rstrip("-")


def _athlete_name(row: Dict[str, Any]) -> str:
    athlete = row.get("athlete") if isinstance(row.get("athlete"), dict) else {}
    return str(
        athlete.get("displayName")
        or athlete.get("fullName")
        or athlete.get("shortName")
        or row.get("displayName")
        or ""
    ).strip()


def _athlete_id(row: Dict[str, Any]) -> str:
    athlete = row.get("athlete") if isinstance(row.get("athlete"), dict) else {}
    return str(athlete.get("id") or row.get("id") or "").strip()


def _country_code(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(
            value.get("abbreviation")
            or value.get("code")
            or value.get("isoCode")
            or value.get("id")
            or value.get("alt")
            or ""
        ).strip()
    return ""


def _athlete_country(row: Dict[str, Any]) -> str:
    athlete = row.get("athlete") if isinstance(row.get("athlete"), dict) else {}
    for owner in (athlete, row):
        for key in ("countryCode", "country", "nationality", "citizenship"):
            code = _country_code(owner.get(key))
            if code:
                return code
        code = _country_code(owner.get("flag"))
        if code:
            return code
    return ""


def _logo_href(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    direct = node.get("logo") or node.get("image")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for key in ("logos", "images"):
        rows = node.get(key)
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, dict):
                    href = item.get("href") or item.get("url")
                    if isinstance(href, str) and href.strip():
                        return href.strip()
    return ""


def _status(raw: Any) -> str:
    status = raw if isinstance(raw, dict) else {}
    typ = status.get("type") if isinstance(status.get("type"), dict) else {}
    value = " ".join(
        str(typ.get(key) or "")
        for key in ("name", "state", "description", "shortDetail", "detail")
    ).lower()
    if any(token in value for token in ("in_progress", "in progress", "live", "1st", "2nd", "3rd", "4th", "5th")):
        return "live"
    if any(token in value for token in ("final", "finished", "complete", "ended")):
        return "finished"
    if any(token in value for token in ("postponed", "cancel", "suspend", "delay")):
        return "postponed"
    return "scheduled"


def _sets(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for index, item in enumerate(row.get("linescores") or [], 1):
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if value is None:
            value = item.get("displayValue")
        out.append({
            "set": index,
            "value": value,
            "tiebreak": item.get("tiebreak") or item.get("tiebreakValue"),
        })
    return out


def _set_wins(home_sets: List[Dict[str, Any]], away_sets: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
    home = away = 0
    seen = 0
    for left, right in zip(home_sets, away_sets):
        try:
            lv = float(left.get("value"))
            rv = float(right.get("value"))
        except (TypeError, ValueError):
            continue
        if lv == rv:
            continue
        seen += 1
        if lv > rv:
            home += 1
        else:
            away += 1
    return (home, away) if seen else (None, None)


def _competition_rows(payload: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], str, Optional[str], str]]:
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        tournament = str(event.get("name") or event.get("shortName") or "Tennis").strip()
        direct = event.get("competitions") or []
        if direct:
            for comp in direct:
                if isinstance(comp, dict):
                    yield comp, tournament, None, _logo_href(event)
        # Some date boards expose a match directly at events[] level.
        if isinstance(event.get("competitors"), list) and len(event.get("competitors") or []) >= 2:
            yield event, tournament, None, _logo_href(event)
        for grouping in event.get("groupings") or []:
            if not isinstance(grouping, dict):
                continue
            grouping_meta = grouping.get("grouping") if isinstance(grouping.get("grouping"), dict) else {}
            grouping_name = str(grouping_meta.get("displayName") or grouping_meta.get("name") or "").strip() or None
            for comp in grouping.get("competitions") or []:
                if isinstance(comp, dict):
                    yield comp, tournament, grouping_name, _logo_href(event)


def parse_board(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    events: List[Dict[str, Any]] = []
    seen = set()
    for comp, tournament, grouping, competition_logo in _competition_rows(payload):
        event_id = str(comp.get("id") or "").strip()
        competitors = [row for row in (comp.get("competitors") or []) if isinstance(row, dict)]
        if len(competitors) < 2:
            continue
        by_side = {str(row.get("homeAway") or "").lower(): row for row in competitors}
        home_raw = by_side.get("home") or competitors[0]
        away_raw = by_side.get("away") or competitors[1]
        home_name = _athlete_name(home_raw)
        away_name = _athlete_name(away_raw)
        if not home_name or not away_name:
            continue
        start_time = comp.get("date")
        if not event_id:
            material = f"{tournament}|{grouping}|{start_time}|{home_name}|{away_name}"
            event_id = hashlib.sha1(material.encode("utf-8")).hexdigest()[:24]
        if event_id in seen:
            continue
        seen.add(event_id)

        competition_name = tournament or "Tennis"
        competition_id = _competition_id(competition_name)
        status = _status(comp.get("status"))
        home_sets = _sets(home_raw)
        away_sets = _sets(away_raw)
        home_score, away_score = _set_wins(home_sets, away_sets)
        if status == "scheduled":
            home_score = away_score = None

        period_rows = []
        for idx in range(max(len(home_sets), len(away_sets))):
            left = home_sets[idx] if idx < len(home_sets) else {}
            right = away_sets[idx] if idx < len(away_sets) else {}
            period_rows.append({
                "label": str(idx + 1),
                "home": left.get("value"),
                "away": right.get("value"),
                "home_tiebreak": left.get("tiebreak"),
                "away_tiebreak": right.get("tiebreak"),
            })

        event = {
            "id": f"espn-tennis:{event_id}",
            "source_event_id": event_id,
            "source_event_ids": {"espn-json": event_id},
            "sport": "tennis",
            "event_family": "individual_match",
            "competition": competition_name,
            "competition_key": competition_id,
            "source_family": "espn-json",
            "source_competition_id": str(comp.get("uid") or competition_name),
            "source_competition_name": competition_name,
            "competition_logo": competition_logo or None,
            "home": {
                "id": _athlete_id(home_raw),
                "name": home_name,
                "country_id": _athlete_country(home_raw) or None,
            },
            "away": {
                "id": _athlete_id(away_raw),
                "name": away_name,
                "country_id": _athlete_country(away_raw) or None,
            },
            "status": status,
            "score": {"home": home_score, "away": away_score},
            "start_time": start_time,
            "round": grouping,
            "stage": grouping,
            "periods": period_rows or None,
            "extra": {
                "source_family": "espn-json",
                "source_event_id": event_id,
                "source_event_ids": {"espn-json": event_id},
                "source_competition_id": str(comp.get("uid") or competition_name),
                "source_competition_name": competition_name,
                "competition_logo": competition_logo or None,
                "public_competition_key": competition_id,
                "round": grouping,
                "periods": period_rows or None,
            },
        }
        events.append(event)
    return events


def _ensure_mapping(
    db: Session,
    *,
    source: SportsSource,
    competition_id: str,
    competition_name: str,
) -> SportsSourceCompetition:
    competition = db.get(SportsCompetition, competition_id)
    if competition is None:
        competition = SportsCompetition(
            competition_id=competition_id,
            sport_id="tennis",
            name=competition_name,
            official_name=competition_name,
            slug=competition_id,
            region_id="world",
            event_model="individual_match",
            competition_type="tournament",
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
            priority=14,
            source_competition_id=competition_id,
            enabled=True,
            coverage_scope="full",
            coverage_notes="ESPN public tennis/all dated scoreboard",
            verification="ESPN tennis/all public JSON",
            polling_class="MEDIUM",
            source_config_json=dump_json({"source_competition_name": competition_name}),
            independence_status="established",
            upstream_family="espn-json",
        )
        db.add(mapping)
        db.flush()
    return mapping


def _in_window(event: Dict[str, Any], *, low: datetime, high: datetime) -> bool:
    stamp = parse_datetime(event.get("start_time"))
    if stamp is None:
        return False
    if getattr(stamp, "tzinfo", None) is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return low <= stamp <= high


def run_breadth_ingest(
    db: Session,
    *,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
    days_back: int = 1,
    days_forward: int = 4,
    max_ingest: int = 1800,
) -> Dict[str, Any]:
    from collector.cache import cache_clear
    from collector.provider_crosswalk import _ingest

    source = _source(db)
    if source is None:
        return {"status": "missing_source", "requests": 0, "events": 0, "ingested": 0}

    fetch = getter or fetch_url
    now = datetime.utcnow()
    low = now - timedelta(days=days_back + 1)
    high = now + timedelta(days=days_forward + 1)
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "events": 0,
        "eligible": 0,
        "ingested": 0,
        "competitions": 0,
        "http_errors": 0,
        "by_date": {},
    }
    competitions = set()

    for offset in range(-days_back, days_forward + 1):
        day = now.date() + timedelta(days=offset)
        key = day.strftime("%Y%m%d")
        result = fetch(URL.format(date=key))
        stats["requests"] += 1
        if not getattr(result, "ok", False) or not isinstance(getattr(result, "payload", None), dict):
            stats["http_errors"] += 1
            stats["by_date"][day.isoformat()] = {"http": getattr(result, "http_status", None), "events": 0, "ingested": 0}
            continue
        rows = parse_board(result.payload)
        day_written = 0
        stats["events"] += len(rows)
        for event in rows:
            if not _in_window(event, low=low, high=high):
                continue
            cid = str(event.get("competition_key") or "")
            if not cid:
                continue
            _ensure_mapping(
                db,
                source=source,
                competition_id=cid,
                competition_name=str(event.get("competition") or cid),
            )
            competitions.add(cid)
            stats["eligible"] += 1
            if _ingest(db, event, source.source_id):
                stats["ingested"] += 1
                day_written += 1
            if stats["ingested"] >= max_ingest:
                stats["status"] = "bounded"
                break
        stats["by_date"][day.isoformat()] = {
            "http": getattr(result, "http_status", None),
            "events": len(rows),
            "ingested": day_written,
        }
        db.commit()
        if heartbeat:
            heartbeat()
        if stats["ingested"] >= max_ingest:
            break

    stats["competitions"] = len(competitions)
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
    getter=None,
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
    return run_breadth_ingest(db, getter=getter, heartbeat=heartbeat)
