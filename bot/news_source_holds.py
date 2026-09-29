"""Durable cooldowns for News source URLs that failed AI/editorial admission.

Production stores only a SHA-256 source fingerprint plus expiry/reason in the
existing Postgres database. No new Railway service or volume is required.
Offline/non-Postgres modes retain a bounded in-process fallback.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import time

logger = logging.getLogger(__name__)

_MEMORY = {}
_MEMORY_MAX = 1000
_SCHEMA_READY = False
_FSS_PHOTO_REPAIR_URLS = {
    'https://fss.rs/a-tim-promene-u-sastavu-pred-nastavak-lige-nacija/',
    'https://fss.rs/u21-i-u-drugom-testu-lako-sa-irakom-slede-dva-jaca-testa-protiv-rusije/',
}
_ZVEZDA_CIES_REPAIR_URL = 'https://www.crvenazvezdafk.com/vesti/gudelj-medju-najboljim-mladim-stoperima-sveta'
_EDITORIAL_RETRY_REASONS = {
    'direct_quote_requires_review',
    'headline_too_similar_to_source',
    'copied_source_headline',
}


def _retryable_reason(reason: str | None) -> bool:
    value = str(reason or "")
    return (
        value in {
            "validator-unavailable",
            "validator-independent-unavailable",
            "empty",
        }
        or value.startswith("unsupported_proper_name:")
        or value.startswith("unsupported_claim_family:")
    )


def _fingerprint(url: str) -> str:
    return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()


def _memory_held(key: str) -> bool:
    now = time.monotonic()
    expiry = _MEMORY.get(key)
    if expiry is None:
        return False
    if expiry <= now:
        _MEMORY.pop(key, None)
        return False
    return True


def _memory_hold(key: str, hours: int) -> None:
    now = time.monotonic()
    if len(_MEMORY) >= _MEMORY_MAX:
        expired = [k for k, expiry in _MEMORY.items() if expiry <= now]
        for item in expired[:250]:
            _MEMORY.pop(item, None)
        if len(_MEMORY) >= _MEMORY_MAX:
            oldest = min(_MEMORY, key=_MEMORY.get)
            _MEMORY.pop(oldest, None)
    _MEMORY[key] = now + max(1, int(hours)) * 3600


def _postgres_dsn() -> str | None:
    try:
        from news_runtime import accounting_backend, postgres_dsn
        if accounting_backend(os.environ) != "postgres":
            return None
        return postgres_dsn(os.environ)
    except Exception:
        return None


def _connect(dsn: str):
    import psycopg2
    return psycopg2.connect(
        dsn,
        connect_timeout=5,
        application_name="ninkosports-news-source-holds",
    )


def _ensure_schema(cursor) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS news_ai_source_holds ("
        "source_hash CHAR(64) PRIMARY KEY,"
        "expires_at TIMESTAMPTZ NOT NULL,"
        "reason VARCHAR(80),"
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_news_ai_source_holds_expiry "
        "ON news_ai_source_holds (expires_at)"
    )
    _SCHEMA_READY = True


def source_on_cooldown(url: str) -> bool:
    key = _fingerprint(url)
    if not key:
        return False
    dsn = _postgres_dsn()
    if not dsn:
        return _memory_held(key)
    connection = cursor = None
    try:
        connection = _connect(dsn)
        cursor = connection.cursor()
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        _ensure_schema(cursor)
        cursor.execute(
            "SELECT reason FROM news_ai_source_holds "
            "WHERE source_hash=%s AND expires_at > NOW()",
            (key,),
        )
        row = cursor.fetchone()
        connection.commit()
        return bool(row) and not _retryable_reason(row[0])
    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        logger.warning("[source_holds] read fallback: %s", type(exc).__name__)
        return _memory_held(key)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def hold_source(url: str, reason: str = "rejected", hours: int = 6) -> None:
    key = _fingerprint(url)
    if not key:
        return
    hours = max(1, min(int(hours), 72))
    # hold_source runs after the bounded corrective rewrite already failed.
    # Retrying that same quote/headline every ten minutes starves other news.
    # Keep it eligible for a later writer attempt, with a one-hour pause.
    if str(reason or '') in _EDITORIAL_RETRY_REASONS:
        hours = min(hours, 1)
    _memory_hold(key, hours)
    dsn = _postgres_dsn()
    if not dsn:
        return
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)
    connection = cursor = None
    try:
        connection = _connect(dsn)
        cursor = connection.cursor()
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        _ensure_schema(cursor)
        cursor.execute(
            "INSERT INTO news_ai_source_holds(source_hash,expires_at,reason,updated_at) "
            "VALUES (%s,%s,%s,NOW()) "
            "ON CONFLICT(source_hash) DO UPDATE SET "
            "expires_at=EXCLUDED.expires_at,reason=EXCLUDED.reason,updated_at=NOW()",
            (key, expires, str(reason or "rejected")[:80]),
        )
        connection.commit()
    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        logger.warning("[source_holds] write fallback: %s", type(exc).__name__)
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass



def held_source_urls(urls) -> set[str]:
    """Batch-read active source holds with one Postgres round trip.

    This is an efficiency/fairness helper only. A source not returned here still
    passes the normal per-item cooldown check before any AI request.
    """
    values = []
    hashes = {}
    for raw in urls or []:
        url = str(raw or "").strip()
        if not url or url in hashes:
            continue
        key = _fingerprint(url)
        if not key:
            continue
        hashes[url] = key
        values.append(url)
    if not values:
        return set()

    dsn = _postgres_dsn()
    if not dsn:
        return {url for url in values if _memory_held(hashes[url])}

    connection = cursor = None
    try:
        connection = _connect(dsn)
        cursor = connection.cursor()
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        _ensure_schema(cursor)
        keys = [hashes[url] for url in values]
        if _ZVEZDA_CIES_REPAIR_URL in hashes:
            # Audited source explicitly spells CIES as ЦИЕС. Retry only this
            # false lexical rejection; semantic/image/dedupe checks still run.
            cursor.execute(
                "UPDATE news_ai_source_holds SET expires_at=NOW(), "
                "reason='audited-cies-source-spelling-repaired', updated_at=NOW() "
                "WHERE source_hash=%s AND expires_at > NOW() "
                "AND reason='unsupported_acronym:CIES' AND updated_at < %s::timestamptz",
                (hashes[_ZVEZDA_CIES_REPAIR_URL], '2026-09-29T07:35:00Z'),
            )
            if cursor.rowcount:
                logger.info('[source_holds] expired audited pre-fix Zvezda CIES cooldown=%s', cursor.rowcount)
        repaired_photo_keys = [hashes[url] for url in values if url in _FSS_PHOTO_REPAIR_URLS]
        if repaired_photo_keys:
            # Two audited FSS pages expose valid full-size article photos in
            # CSS that the old parser missed. Expire only their pre-fix image
            # cooldowns; new failures and all editorial holds remain in force.
            # The next ingest still probes photos and runs every public gate.
            cursor.execute(
                "UPDATE news_ai_source_holds SET expires_at=NOW(), "
                "reason='audited-fss-photo-parser-repaired', updated_at=NOW() "
                "WHERE source_hash = ANY(%s) AND expires_at > NOW() "
                "AND reason='missing-or-unreachable-publishable-image' "
                "AND updated_at < %s::timestamptz",
                (repaired_photo_keys, '2026-09-29T05:55:00Z'),
            )
            if cursor.rowcount:
                logger.info('[source_holds] expired audited pre-fix FSS photo cooldowns=%s', cursor.rowcount)
        cursor.execute(
            "SELECT source_hash, reason FROM news_ai_source_holds "
            "WHERE source_hash = ANY(%s) AND expires_at > NOW()",
            (keys,),
        )
        held_hashes = {
            row[0] for row in cursor.fetchall()
            if row and row[0] and not _retryable_reason(row[1] if len(row) > 1 else None)
        }
        connection.commit()
        return {url for url in values if hashes[url] in held_hashes}
    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        logger.warning("[source_holds] batch read fallback: %s", type(exc).__name__)
        return {url for url in values if _memory_held(hashes[url])}
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
