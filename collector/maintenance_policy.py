"""Fail-closed lifecycle policy for automatic historical maintenance.

A retired observation is not a replacement candidate. None of these helpers
changes a score, deletes a row, or clears an existing canonical pointer.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

from collector.list_extra import store_list_extra
from collector.util import dump_json, load_json


def startup_integrity_enabled(env: Mapping[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return (
        values.get("NINKO_RUN_STARTUP_INTEGRITY_BACKFILL") == "1"
        and values.get("NINKO_SKIP_INTEGRITY_BACKFILL") != "1"
    )


def _metadata(row: Any, extra: dict | None = None) -> list[dict]:
    # Inspect each representation independently: a stale slim blob must never
    # cancel a restriction in the rich metadata (or vice versa).
    values = [extra or {}]
    for field in ("extra_json", "list_extra_json"):
        value = load_json(getattr(row, field, None), {}) or {}
        if isinstance(value, dict):
            values.append(value)
    return values


def automatic_promotion_blocked(row: Any, extra: dict | None = None) -> bool:
    if getattr(row, "canonical_event_id", None):
        return True
    return any(
        item.get("canonical_event_id")
        or item.get("collapse_role") == "observation_only"
        or item.get("manual_hidden")
        or item.get("do_not_restore")
        for item in _metadata(row, extra)
    )


def sync_public_visibility(row: Any, extra: dict, eligible: bool) -> bool:
    """Synchronize row, rich metadata and slim metadata without erasing policy."""
    before = (row.display_eligible, row.extra_json, getattr(row, "list_extra_json", None))
    restricted = automatic_promotion_blocked(row, extra)
    if restricted:
        for item in _metadata(row, extra):
            for key in ("manual_hidden", "do_not_restore"):
                if item.get(key):
                    extra[key] = item[key]
            if item.get("collapse_role") == "observation_only":
                extra["collapse_role"] = "observation_only"
            if item.get("canonical_event_id") and not extra.get("canonical_event_id"):
                extra["canonical_event_id"] = item["canonical_event_id"]
        if getattr(row, "canonical_event_id", None):
            extra["canonical_event_id"] = row.canonical_event_id
    visible = bool(eligible) and not restricted
    extra["display_eligible"] = visible
    row.display_eligible = visible
    row.extra_json = dump_json(extra)
    store_list_extra(row, extra)
    after = (row.display_eligible, row.extra_json, getattr(row, "list_extra_json", None))
    return before != after
