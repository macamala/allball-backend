"""Retry/backoff and per-source rate limiting. Never used to hammer protected sources."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, TypeVar

from sqlalchemy.orm import Session

from collector.models import SportsSource, SportsSourceHealth

T = TypeVar("T")

_hits: Dict[str, List[float]] = {}


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.01,
    sleeper: Callable[[float], None] = time.sleep,
) -> T:
    last_error: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — collector isolates adapter errors
            last_error = exc
            if attempt + 1 >= attempts:
                break
            sleeper(base_delay * (2**attempt))
    assert last_error is not None
    raise last_error


def is_rate_limited(db: Session, source_id: str, now: Optional[datetime] = None, *, cached_only: bool = False) -> bool:
    now = now or datetime.utcnow()
    health = db.query(SportsSourceHealth).filter_by(source_id=source_id).first()
    if health and health.rate_limited_until and health.rate_limited_until > now:
        return True
    if cached_only:
        return False  # No HTTP request; persistent cooldown above is still enforced.
    source = db.query(SportsSource).filter_by(source_id=source_id).first()
    limit = source.rate_limit_per_minute if source else None
    if not limit:
        return False
    window = now.timestamp() - 60
    stamps = [hit for hit in _hits.get(source_id, []) if hit >= window]
    _hits[source_id] = stamps
    return len(stamps) >= int(limit)


def record_hit(source_id: str, now: Optional[datetime] = None) -> None:
    now = now or datetime.utcnow()
    _hits.setdefault(source_id, []).append(now.timestamp())


def mark_rate_limited(db: Session, source_id: str, seconds: int = 60) -> None:
    from collector.health import _health

    health = _health(db, source_id)
    health.rate_limited_until = datetime.utcnow() + timedelta(seconds=seconds)
    health.status = "degraded"
    health.updated_at = datetime.utcnow()
