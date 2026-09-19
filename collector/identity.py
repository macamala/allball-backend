"""Canonical Ninko IDs and source-ID mappings. Source IDs never become public IDs."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from collector.ids import bound_source_key
from collector.models import SportsEntity, SportsIdMap
from collector.util import sha_id, slugify
from collector.identity_events import (  # noqa: F401
    IDENTITY_MERGE_THRESHOLD,
    identity_confidence,
    should_merge_enrichment,
)


def _stored_entity_key(source_id: str, source_entity_id: str) -> str:
    return bound_source_key(source_id, str(source_entity_id), limit=200)


def mapped_ninko_id(
    db: Session, entity_kind: str, source_id: str, source_entity_id: Optional[str]
) -> Optional[str]:
    if not source_entity_id:
        return None
    original = str(source_entity_id)
    key = _stored_entity_key(source_id, original)
    cache = db.info.setdefault("id_map", {})
    cache_key = (entity_kind, source_id, key)
    if cache_key in cache:
        return cache[cache_key]
    for candidate in (key, original):
        row = (
            db.query(SportsIdMap)
            .filter_by(
                entity_kind=entity_kind,
                source_id=source_id,
                source_entity_id=candidate,
            )
            .first()
        )
        if row:
            cache[cache_key] = row.ninko_id
            return row.ninko_id
    for pending in db.new:
        if not isinstance(pending, SportsIdMap):
            continue
        if pending.entity_kind != entity_kind or pending.source_id != source_id:
            continue
        if pending.source_entity_id in {key, original}:
            cache[cache_key] = pending.ninko_id
            return pending.ninko_id
    return None


def remember_mapping(
    db: Session,
    *,
    entity_kind: str,
    ninko_id: str,
    source_id: str,
    source_entity_id: Optional[str],
) -> None:
    if not source_entity_id:
        return
    existing = mapped_ninko_id(db, entity_kind, source_id, source_entity_id)
    if existing:
        return
    original = str(source_entity_id)
    key = _stored_entity_key(source_id, original)
    db.add(
        SportsIdMap(
            entity_kind=entity_kind,
            ninko_id=ninko_id,
            source_id=source_id,
            source_entity_id=key,
            source_entity_id_original=original,
        )
    )
    db.info.setdefault("id_map", {})[(entity_kind, source_id, key)] = ninko_id


def ensure_entity(
    db: Session,
    *,
    sport_id: str,
    kind: str,
    name: str,
    source_id: Optional[str] = None,
    source_entity_id: Optional[str] = None,
    country_id: Optional[str] = None,
) -> Optional[str]:
    if not name:
        return None
    if source_id and source_entity_id:
        existing = mapped_ninko_id(db, kind, source_id, source_entity_id)
        if existing:
            return existing
    slug = slugify(name)
    entity_id = sha_id("ninko-ent-", sport_id, kind, slug)
    cache = db.info.setdefault("entities", {})
    row = cache.get(entity_id)
    if row is None:
        row = db.get(SportsEntity, entity_id)
    if row is None:
        row = db.query(SportsEntity).filter_by(entity_id=entity_id).first()
    if row is None:
        for pending in db.new:
            if isinstance(pending, SportsEntity) and pending.entity_id == entity_id:
                row = pending
                break
    if row is None:
        row = SportsEntity(
            entity_id=entity_id,
            sport_id=sport_id,
            kind=kind,
            name=name,
            slug=slug,
            country_id=country_id,
        )
        db.add(row)
    cache[entity_id] = row
    if source_id:
        remember_mapping(
            db,
            entity_kind=kind,
            ninko_id=entity_id,
            source_id=source_id,
            source_entity_id=source_entity_id or slug,
        )
    return entity_id
