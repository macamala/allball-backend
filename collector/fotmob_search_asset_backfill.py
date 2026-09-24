"""Strict FotMob search-based football crest backfill.

For public football events in the rolling score window, search only participants
whose logo is blank. A FotMob suggestion is accepted only when exactly one team
identity matches under the existing conservative identity matcher. Existing
logos, scores, statuses, names and kickoff times are never overwritten.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from sqlalchemy.orm import Session

from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.models import SportsEvent
from collector.participant_alias import names_equivalent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

SEARCH_URL = "https://www.fotmob.com/api/data/search/suggest?hits=20&lang=en&term={term}"
RUN_INTERVAL_S = 12 * 3600
PAST_DAYS = 8
FUTURE_DAYS = 15
MAX_SEARCH_LOOKUPS = 90

_next_run_at = 0.0
_last_search: Dict[str, float] = {}


def _missing_logo(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return not bool(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or side.get("logo_url")
        or side.get("logoUrl")
    )


def _walk_team_candidates(node: Any, inherited_type: str = "") -> Iterable[Dict[str, str]]:
    if isinstance(node, list):
        for item in node:
            yield from _walk_team_candidates(item, inherited_type)
        return
    if not isinstance(node, dict):
        return

    raw_type = str(
        node.get("type")
        or node.get("entityType")
        or node.get("suggestionType")
        or node.get("category")
        or inherited_type
        or ""
    ).strip().lower()
    route = str(
        node.get("url")
        or node.get("pageUrl")
        or node.get("href")
        or node.get("path")
        or ""
    ).strip().lower()
    team_id = str(
        node.get("teamId")
        or node.get("team_id")
        or (node.get("id") if ("team" in raw_type or "/teams/" in route) else "")
        or ""
    ).strip()
    name = str(
        node.get("name")
        or node.get("teamName")
        or node.get("displayName")
        or node.get("title")
        or ""
    ).strip()

    is_team = (
        "team" in raw_type
        or "/teams/" in route
        or bool(node.get("teamId"))
        or bool(node.get("team_id"))
    )
    if is_team and team_id.isdigit() and name:
        yield {"id": team_id, "name": name}

    for key, value in node.items():
        child_type = raw_type
        key_fold = str(key).lower()
        if "team" in key_fold:
            child_type = "team"
        elif "league" in key_fold or "tournament" in key_fold:
            child_type = "league"
        elif "player" in key_fold or "squad" in key_fold:
            child_type = "player"
        yield from _walk_team_candidates(value, child_type)


def _unique_team(query_name: str, payload: Any) -> Optional[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen = set()
    for item in _walk_team_candidates(payload):
        key = (item["id"], fold_for_identity(item["name"]))
        if key in seen:
            continue
        seen.add(key)
        if names_equivalent(query_name, item["name"]):
            candidates.append(item)

    if not candidates:
        return None

    exact_fold = fold_for_identity(query_name)
    exact = [row for row in candidates if fold_for_identity(row["name"]) == exact_fold]
    pool = exact or candidates
    ids = {row["id"] for row in pool}
    if len(ids) != 1:
        return None
    return sorted(pool, key=lambda row: (len(row["name"]), row["name"]))[0]


def _candidate_names(db: Session, now: float) -> List[Tuple[str, int]]:
    start = datetime.utcnow() - timedelta(days=PAST_DAYS)
    end = datetime.utcnow() + timedelta(days=FUTURE_DAYS)
    counts: Dict[str, int] = defaultdict(int)
    display: Dict[str, str] = {}
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.canonical_event_id.is_(None),
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= start,
            SportsEvent.start_time <= end,
        )
        .all()
    )
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        for side_name in ("home", "away"):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            name = str(side.get("display_name") or side.get("name") or "").strip()
            if not name or name.casefold() == "tbd":
                continue
            folded = fold_for_identity(name)
            if not folded:
                continue
            if now - float(_last_search.get(folded) or 0.0) < RUN_INTERVAL_S:
                continue
            counts[folded] += 1
            display.setdefault(folded, name)

    return [
        (display[folded], count)
        for folded, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ][:MAX_SEARCH_LOOKUPS]


def _apply_asset(db: Session, query_name: str, team: Dict[str, str]) -> Tuple[int, int]:
    start = datetime.utcnow() - timedelta(days=PAST_DAYS)
    end = datetime.utcnow() + timedelta(days=FUTURE_DAYS)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.canonical_event_id.is_(None),
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= start,
            SportsEvent.start_time <= end,
        )
        .all()
    )
    logo = f"https://images.fotmob.com/image_resources/logo/teamlogo/{team['id']}.png"
    rows_updated = 0
    slots_filled = 0
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            side_text = str(side.get("display_name") or side.get("name") or "").strip()
            if not side_text or not names_equivalent(query_name, side_text):
                continue
            merged = dict(side)
            merged["logo"] = logo
            merged.setdefault("logo_source", "fotmob-search")
            merged.setdefault("fotmob_team_id", team["id"])
            participants[side_name] = merged

            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and _missing_logo(mirror):
                mirror_merged = dict(mirror)
                mirror_merged["logo"] = logo
                mirror_merged.setdefault("logo_source", "fotmob-search")
                mirror_merged.setdefault("fotmob_team_id", team["id"])
                participants[mirror_name] = mirror_merged

            changed = True
            slots_filled += 1

        if changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
            rows_updated += 1
    return rows_updated, slots_filled


def run_if_due(db: Session, *, getter=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S
    getter = getter or fetch_url

    candidates = _candidate_names(db, now)
    stats: Dict[str, Any] = {
        "status": "ok" if candidates else "idle",
        "candidate_names": len(candidates),
        "requests": 0,
        "matched_names": 0,
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "http_errors": 0,
        "ambiguous_or_unmatched": 0,
        "matches": {},
    }

    for name, occurrences in candidates:
        folded = fold_for_identity(name)
        result = getter(SEARCH_URL.format(term=quote(name)))
        stats["requests"] += 1
        _last_search[folded] = now
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue
        team = _unique_team(name, result.payload)
        if not team:
            stats["ambiguous_or_unmatched"] += 1
            continue
        changed_rows, slots = _apply_asset(db, name, team)
        if changed_rows:
            db.commit()
        stats["matched_names"] += 1
        stats["rows_updated"] += changed_rows
        stats["participant_logos_filled"] += slots
        stats["matches"][name] = {
            "fotmob_id": team["id"],
            "fotmob_name": team["name"],
            "occurrences": occurrences,
            "rows_updated": changed_rows,
            "slots_filled": slots,
        }

    return stats
