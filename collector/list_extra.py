"""Slim extra blob used by the score list. Never includes Match Centre sections."""

from __future__ import annotations

from typing import Any, Dict

from collector.util import dump_json, load_json

LIST_EXTRA_KEYS = (
    "periods",
    "winner",
    "runners",
    "round",
    "live_class",
    "start_precision",
    "start_date",
    "best_of",
    "maps",
    "race_number",
    "tournament",
    "tournament_name",
    "current_set",
    "result_type",
    "walkover",
    "stage",
    "observed_at",
    "source_event_updated_at",
    "last_contact_at",
    "source_fetch_time",
    "canonical_last_observed_at",
    "canonical_updated_at",
    "source_status",
    "status_inferred",
    "source_family",
    "source_competition_name",
    "display_eligible",
)

RICH_EXTRA_KEYS = (
    "incidents",
    "statistics",
    "lineups",
    "player_statistics",
    "timeline",
    "leaderboard",
    "classification",
    "field_freshness",
    "source_kickoffs",
)


def slim_extra(extra: Dict[str, Any]) -> Dict[str, Any]:
    return {key: extra[key] for key in LIST_EXTRA_KEYS if extra.get(key) not in (None, "", [], {})}


def extra_for_list(row) -> Dict[str, Any]:
    slim = getattr(row, "list_extra_json", None)
    if slim:
        return load_json(slim, {}) or {}
    try:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(row)
        if "extra_json" in (state.unloaded or set()):
            return {}
    except Exception:
        pass
    extra = load_json(row.extra_json, {}) or {}
    return slim_extra(extra)


def store_list_extra(row, extra: Dict[str, Any]) -> None:
    if hasattr(row, "list_extra_json"):
        row.list_extra_json = dump_json(slim_extra(extra))
