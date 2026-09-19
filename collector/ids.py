"""Bounded storage keys for source and source-event identifiers.

Canonical identity is unchanged. Database PKs/indexes use a stable key that
always fits VARCHAR(80). The complete original ID is stored separately.
"""

from __future__ import annotations

import hashlib

from collector.util import slugify

SOURCE_KEY_LIMIT = 80


def bound_source_key(namespace: str, original: str, *, limit: int = SOURCE_KEY_LIMIT) -> str:
    """Deterministic key. Long IDs are hashed; short IDs stay as-is.

    Two originals that share a long prefix but differ later hash differently.
    The same complete original always yields the same key.
    """
    original = str(original or "")
    namespace = str(namespace or "src")
    if len(original) <= limit:
        return original
    digest = hashlib.sha256(f"{namespace}\0{original}".encode("utf-8")).hexdigest()
    ns = "".join(ch for ch in slugify(namespace) if ch.isalnum())[:16] or "src"
    return f"{ns}:{digest[:40]}"[:limit]


def source_key_and_original(namespace: str, original: str) -> tuple[str, str]:
    original = str(original or "")
    key = bound_source_key(namespace, original)
    return key, original
