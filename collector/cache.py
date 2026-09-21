"""Read-side TTL cache for collected payloads. API never talks to adapters.

List and detail are separate. Scoreboard writes invalidate overlapping list keys
once per cycle. Rich-detail-only writes do not touch the list cache.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set

from sqlalchemy.orm import Session

from collector.models import SportsReadCache
from collector.util import dump_json, load_json
from sports_registry.cache_policy import policy_for

LIST_CACHE_VERSION = "p0v18"
LIST_PREFIX = f"events:{LIST_CACHE_VERSION}|"
_DAY = re.compile(r"(\d{4}-\d{2}-\d{2})")


def list_cache_key(
    sport: Optional[str],
    competition: Optional[str],
    status: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    allow_unfiltered: bool,
) -> str:
    return (
        f"{LIST_PREFIX}{sport}|{competition}|{status}|{date_from}|{date_to}|{int(allow_unfiltered)}"
    )


def cache_get(db: Session, key: str, now: Optional[datetime] = None) -> Any:
    now = now or datetime.utcnow()
    row = db.query(SportsReadCache).filter_by(cache_key=key).first()
    if row is None or row.expires_at <= now:
        return None
    return load_json(row.payload, None)


def cache_set(db: Session, key: str, payload: Any, policy_key: str) -> None:
    ttl = int(policy_for(policy_key).get("ttl_seconds") or 300)
    expires = datetime.utcnow() + timedelta(seconds=ttl)
    row = db.query(SportsReadCache).filter_by(cache_key=key).first()
    raw = dump_json(payload)
    if row is None:
        db.add(SportsReadCache(cache_key=key, payload=raw, expires_at=expires))
        return
    row.payload = raw
    row.expires_at = expires


def cache_clear(db: Session, prefix: Optional[str] = None) -> None:
    query = db.query(SportsReadCache)
    if prefix:
        query = query.filter(SportsReadCache.cache_key.like(f"{prefix}%"))
    query.delete(synchronize_session=False)


def _day(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    match = _DAY.search(text)
    return match.group(1) if match else None


def note_list_invalidation(
    db: Session,
    *,
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    start_time: Any = None,
    scoreboard_visible: bool = True,
) -> None:
    if not scoreboard_visible:
        return
    bucket: Dict[str, Set[str]] = db.info.setdefault(
        "list_inval", {"sports": set(), "comps": set(), "days": set()}
    )
    if sport:
        bucket["sports"].add(str(sport))
    if competition:
        bucket["comps"].add(str(competition))
    day = _day(start_time)
    if day:
        bucket["days"].add(day)


def _key_window(key: str) -> Optional[tuple[str, str]]:
    days = _DAY.findall(key)
    if not days:
        return None
    return days[0], days[-1]


def _key_sport(key: str) -> Optional[str]:
    if key.startswith(LIST_PREFIX):
        part = key[len(LIST_PREFIX) :].split("|", 1)[0]
        return None if part in {"None", ""} else part
    return None


def _list_key_hit(key: str, bucket: Dict[str, Set[str]]) -> bool:
    if not key.startswith("events:"):
        return False
    window = _key_window(key)
    days = bucket.get("days") or set()
    if window and days:
        start, end = window
        if not any(start <= day <= end for day in days):
            return False
    elif days and not window:
        return False
    sport = _key_sport(key)
    sports = bucket.get("sports") or set()
    if sport and sports and sport not in sports:
        return False
    return True


def flush_list_invalidations(db: Session) -> int:
    bucket = db.info.pop("list_inval", None)
    if not bucket:
        return 0
    if not (bucket.get("days") or bucket.get("sports") or bucket.get("comps")):
        return 0
    deleted = 0
    rows = db.query(SportsReadCache).filter(SportsReadCache.cache_key.like("events:%")).all()
    for row in rows:
        if _list_key_hit(row.cache_key, bucket):
            db.delete(row)
            deleted += 1
    return deleted
