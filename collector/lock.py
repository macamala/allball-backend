"""Single-owner results scheduler lease. Accidental second workers cannot collect."""

from __future__ import annotations

import os
import socket
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from collector.models import SportsSchedulerLease

LOCK_NAME = "results-scheduler"
DEFAULT_TTL_SECONDS = 90


def owner_identity() -> str:
    replica = os.getenv("RAILWAY_REPLICA_ID") or os.getenv("RAILWAY_DEPLOYMENT_ID") or ""
    host = socket.gethostname()
    pid = os.getpid()
    return f"{host}:{pid}:{replica}".strip(":")


def _now() -> datetime:
    return datetime.utcnow()


def acquire_scheduler_lock(
    db: Session,
    *,
    owner: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    owner = owner or owner_identity()
    now = _now()
    expires = now + timedelta(seconds=max(30, ttl_seconds))
    query = db.query(SportsSchedulerLease).filter_by(lock_name=LOCK_NAME)
    try:
        row = query.with_for_update().first()
    except Exception:
        row = query.first()
    if row is None:
        db.add(
            SportsSchedulerLease(
                lock_name=LOCK_NAME,
                owner_id=owner,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires,
            )
        )
        db.flush()
        return True
    expired = row.expires_at is None or row.expires_at <= now
    if row.owner_id == owner or expired:
        if expired or row.owner_id != owner:
            row.acquired_at = now
        row.owner_id = owner
        row.heartbeat_at = now
        row.expires_at = expires
        db.flush()
        return True
    return False


def heartbeat_scheduler_lock(
    db: Session,
    *,
    owner: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> bool:
    owner = owner or owner_identity()
    row = db.query(SportsSchedulerLease).filter_by(lock_name=LOCK_NAME).first()
    if row is None or row.owner_id != owner:
        return False
    now = _now()
    row.heartbeat_at = now
    row.expires_at = now + timedelta(seconds=max(30, ttl_seconds))
    db.flush()
    return True


def release_scheduler_lock(db: Session, *, owner: Optional[str] = None) -> None:
    owner = owner or owner_identity()
    row = db.query(SportsSchedulerLease).filter_by(lock_name=LOCK_NAME).first()
    if row is None or row.owner_id != owner:
        return
    row.owner_id = None
    row.expires_at = _now()
    row.heartbeat_at = _now()
    db.flush()


def lock_status(db: Session) -> dict:
    row = db.query(SportsSchedulerLease).filter_by(lock_name=LOCK_NAME).first()
    if row is None:
        return {"lock_name": LOCK_NAME, "owner_id": None, "held": False}
    held = bool(row.owner_id) and row.expires_at is not None and row.expires_at > _now()
    return {
        "lock_name": LOCK_NAME,
        "owner_id": row.owner_id if held else None,
        "held": held,
        "acquired_at": row.acquired_at.isoformat() + "Z" if row.acquired_at else None,
        "heartbeat_at": row.heartbeat_at.isoformat() + "Z" if row.heartbeat_at else None,
        "expires_at": row.expires_at.isoformat() + "Z" if row.expires_at else None,
    }


def advisory_locks_enabled() -> bool:
    """Session advisory locks are opt-in.

    Railway and other pooled/proxied Postgres connections can outlive an app
    container, so session-level advisory locks may survive a rolling deploy.
    The row leases below are transactional, TTL-bound, and remain the primary
    single-writer guard.
    """
    return str(os.getenv("RESULTS_USE_POSTGRES_ADVISORY_LOCKS") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def postgres_try_advisory(db: Session) -> Optional[bool]:
    """Optional extra guard for direct Postgres sessions only."""
    if not advisory_locks_enabled():
        return None
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return None
    from sqlalchemy import text

    result = db.execute(text("SELECT pg_try_advisory_lock(88442201)")).scalar()
    return bool(result)


def postgres_advisory_unlock(db: Session) -> None:
    if not advisory_locks_enabled():
        return
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_unlock(88442201)"))


WRITE_LOCK_NAME = "results-write"
WRITE_ADVISORY = 88442202
WRITE_TTL_SECONDS = 180


def heartbeat_write_lock(
    db: Session,
    *,
    owner: Optional[str] = None,
    ttl_seconds: int = WRITE_TTL_SECONDS,
) -> bool:
    owner = owner or owner_identity()
    row = db.query(SportsSchedulerLease).filter_by(lock_name=WRITE_LOCK_NAME).first()
    if row is None or row.owner_id != owner:
        return False
    now = _now()
    row.heartbeat_at = now
    row.expires_at = now + timedelta(seconds=max(60, ttl_seconds))
    db.flush()
    return True


def acquire_write_lock(
    db: Session,
    *,
    owner: Optional[str] = None,
    ttl_seconds: int = WRITE_TTL_SECONDS,
) -> bool:
    """Exclusive results persist lock. Second writer is refused, not overlapped."""
    owner = owner or owner_identity()
    now = _now()
    expires = now + timedelta(seconds=max(60, ttl_seconds))
    query = db.query(SportsSchedulerLease).filter_by(lock_name=WRITE_LOCK_NAME)
    try:
        row = query.with_for_update().first()
    except Exception:
        row = query.first()
    if row is None:
        db.add(
            SportsSchedulerLease(
                lock_name=WRITE_LOCK_NAME,
                owner_id=owner,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires,
            )
        )
        db.flush()
    else:
        expired = row.expires_at is None or row.expires_at <= now
        if row.owner_id not in {None, owner} and not expired:
            return False
        if expired or row.owner_id != owner:
            row.acquired_at = now
        row.owner_id = owner
        row.heartbeat_at = now
        row.expires_at = expires
        db.flush()
    bind = db.get_bind()
    if advisory_locks_enabled() and bind.dialect.name == "postgresql":
        from sqlalchemy import text

        got = db.execute(text(f"SELECT pg_try_advisory_lock({WRITE_ADVISORY})")).scalar()
        if not got:
            row = db.query(SportsSchedulerLease).filter_by(lock_name=WRITE_LOCK_NAME).first()
            if row and row.owner_id == owner:
                row.owner_id = None
                row.expires_at = now
                db.flush()
            return False
    return True


def release_write_lock(db: Session, *, owner: Optional[str] = None) -> None:
    owner = owner or owner_identity()
    row = db.query(SportsSchedulerLease).filter_by(lock_name=WRITE_LOCK_NAME).first()
    if row is not None and row.owner_id == owner:
        row.owner_id = None
        row.expires_at = _now()
        row.heartbeat_at = _now()
        db.flush()
    bind = db.get_bind()
    if advisory_locks_enabled() and bind.dialect.name == "postgresql":
        from sqlalchemy import text

        db.execute(text(f"SELECT pg_advisory_unlock({WRITE_ADVISORY})"))


def write_lock_status(db: Session) -> dict:
    row = db.query(SportsSchedulerLease).filter_by(lock_name=WRITE_LOCK_NAME).first()
    if row is None:
        return {"lock_name": WRITE_LOCK_NAME, "owner_id": None, "held": False}
    held = bool(row.owner_id) and row.expires_at is not None and row.expires_at > _now()
    return {
        "lock_name": WRITE_LOCK_NAME,
        "owner_id": row.owner_id if held else None,
        "held": held,
        "expires_at": row.expires_at.isoformat() + "Z" if row.expires_at else None,
    }


# Keep imported time for tests that patch monotonic-style waits.
sleep = time.sleep
