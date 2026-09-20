"""Provider-family aware execution order for collector and audit batches."""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

ARCHIVE_PREFIXES = ("wikipedia", "wiki-")
SHARED_API = {"thesportsdb", "pulselive", "sportscore", "fotmob", "sofascore-web"}
HISTORICAL_FAMILIES = {"cricsheet", "sackmann-tennis"}


def family_refresh_class(family: str) -> str:
    name = family or ""
    if name in SHARED_API:
        return "shared_api"
    if name in HISTORICAL_FAMILIES or name.startswith(ARCHIVE_PREFIXES) or "wikipedia" in name:
        return "archive"
    return "live"


def family_priority(family: str) -> int:
    kind = family_refresh_class(family)
    if kind == "live":
        return 0
    if kind == "shared_api":
        return 2
    return 3


def sort_jobs(jobs: Sequence[Tuple]) -> List[Tuple]:
    """jobs items are (competition_id, sport, side, mapping)."""

    def key(item: Tuple) -> Tuple:
        mapping = item[3] if len(item) > 3 else {}
        family = (mapping.get("source_family") if isinstance(mapping, dict) else "") or ""
        side = item[2] if len(item) > 2 else "A"
        cid = item[0] if item else ""
        return (family_priority(family), 0 if side == "A" else 1, family, cid)

    return sorted(jobs, key=key)
