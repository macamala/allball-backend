"""Public HTTP cache generation. Bump when ingest/repair publishes new rows."""

from __future__ import annotations

import time

_generation = int(time.time())


def cache_generation() -> int:
    return _generation


def bump_public_cache() -> int:
    global _generation
    _generation = int(time.time())
    return _generation
