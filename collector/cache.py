"""Read-side TTL cache for collected payloads. API never talks to adapters."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from collector.models import SportsReadCache
from collector.util import dump_json, load_json
from sports_registry.cache_policy import policy_for


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
