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

from collector.adapters_fotmob import FOTMOB_LEAGUES, LEAGUE_URL, _league_ids
from collector.fotmob_asset_backfill import _roster
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


def _unique_team(
    query_name: str,
    payload: Any,
    *,
    allowed_team_ids: set[str],
) -> Optional[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen = set()
    for item in _walk_team_candidates(payload):
        key = (item["id"], fold_for_identity(item["name"]))
        if key in seen:
            continue
        seen.add(key)
        if item["id"] in allowed_team_ids and names_equivalent(query_name, item["name"]):
            candidates.append(item)

    if not candidates:
        return None

    exact_fold = fold_for_identity(query_name)
    exact = [row for row in candidates if fold_for_identity(row["name"]) == exact_fold]
    if exact:
        pool = exact
    else:
        query_tokens = exact_fold.split()
        safe_expanded = [
            row
            for row in candidates
            if len(query_tokens) >= 2
            and len(fold_for_identity(row["name"]).split()) >= 2
        ]
        pool = safe_expanded
    if not pool:
        return None
    ids = {row["id"] for row in pool}
    if len(ids) != 1:
        return None
    return sorted(pool, key=lambda row: (len(row["name"]), row["name"]))[0]


def _candidate_names(db: Session, now: float) -> List[Tuple[str, str, int]]:
    start = datetime.utcnow() - timedelta(days=PAST_DAYS)
    end = datetime.utcnow() + timedelta(days=FUTURE_DAYS)
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    display: Dict[Tuple[str, str], str] = {}
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
        competition_id = str(row.competition_id or "").strip()
        if competition_id not in FOTMOB_LEAGUES:
            continue
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
            cache_key = f"{competition_id}:{folded}"
            if now - float(_last_search.get(cache_key) or 0.0) < RUN_INTERVAL_S:
                continue
            key = (competition_id, folded)
            counts[key] += 1
            display.setdefault(key, name)

    return [
        (competition_id, display[(competition_id, folded)], count)
        for (competition_id, folded), count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ][:MAX_SEARCH_LOOKUPS]


def _apply_asset(
    db: Session,
    competition_id: str,
    query_name: str,
    team: Dict[str, str],
) -> Tuple[int, int]:
    start = datetime.utcnow() - timedelta(days=PAST_DAYS)
    end = datetime.utcnow() + timedelta(days=FUTURE_DAYS)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.competition_id == competition_id,
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
            merged.setdefault("fotmob_team_name", team["name"])
            participants[side_name] = merged

            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and _missing_logo(mirror):
                mirror_merged = dict(mirror)
                mirror_merged["logo"] = logo
                mirror_merged.setdefault("logo_source", "fotmob-search")
                mirror_merged.setdefault("fotmob_team_id", team["id"])
                mirror_merged.setdefault("fotmob_team_name", team["name"])
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


def cleanup_unsafe_prior_search_assets(db: Session) -> Dict[str, int]:
    """Remove all old search-derived crests before league-roster revalidation."""
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.display_eligible.is_(True),
        )
        .all()
    )
    rows_updated = 0
    logos_removed = 0
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(side_name)
            if not isinstance(side, dict):
                continue
            if str(side.get("logo_source") or "") != "fotmob-search":
                continue
            merged = dict(side)
            for key in ("logo", "logo_source", "fotmob_team_id", "fotmob_team_name"):
                merged.pop(key, None)
            participants[side_name] = merged
            changed = True
            logos_removed += 1
        if changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
            rows_updated += 1
    if rows_updated:
        db.commit()
    return {"rows_updated": rows_updated, "logos_removed": logos_removed}


def _roster_ids(getter, competition_id: str) -> Tuple[set[str], int, int]:
    spec = FOTMOB_LEAGUES.get(competition_id) or {}
    ids: set[str] = set()
    requests = 0
    errors = 0
    for league_id in _league_ids(spec):
        result = getter(LEAGUE_URL.format(league_id=league_id))
        requests += 1
        if not getattr(result, "ok", False):
            errors += 1
            continue
        for row in _roster(result.payload):
            team_id = str(row.get("id") or "").strip()
            if team_id.isdigit():
                ids.add(team_id)
    return ids, requests, errors


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
        "roster_requests": 0,
        "matched_names": 0,
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "http_errors": 0,
        "ambiguous_or_unmatched": 0,
        "no_roster": 0,
        "matches": {},
    }

    roster_cache: Dict[str, set[str]] = {}
    for competition_id, _name, _occurrences in candidates:
        if competition_id in roster_cache:
            continue
        allowed, requests, errors = _roster_ids(getter, competition_id)
        roster_cache[competition_id] = allowed
        stats["requests"] += requests
        stats["roster_requests"] += requests
        stats["http_errors"] += errors

    for competition_id, name, occurrences in candidates:
        folded = fold_for_identity(name)
        cache_key = f"{competition_id}:{folded}"
        allowed_team_ids = roster_cache.get(competition_id) or set()
        if not allowed_team_ids:
            stats["no_roster"] += 1
            _last_search[cache_key] = now
            continue

        result = getter(SEARCH_URL.format(term=quote(name)))
        stats["requests"] += 1
        _last_search[cache_key] = now
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue

        team = _unique_team(
            name,
            result.payload,
            allowed_team_ids=allowed_team_ids,
        )
        if not team:
            stats["ambiguous_or_unmatched"] += 1
            continue

        changed_rows, slots = _apply_asset(
            db,
            competition_id,
            name,
            team,
        )
        if changed_rows:
            db.commit()
        stats["matched_names"] += 1
        stats["rows_updated"] += changed_rows
        stats["participant_logos_filled"] += slots
        stats["matches"][f"{competition_id}:{name}"] = {
            "fotmob_id": team["id"],
            "fotmob_name": team["name"],
            "occurrences": occurrences,
            "rows_updated": changed_rows,
            "slots_filled": slots,
        }

    return stats

