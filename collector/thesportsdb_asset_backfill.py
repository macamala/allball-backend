"""Bounded TheSportsDB artwork catalogue backfill.

This job is intentionally asset-only. It never uses TheSportsDB as the live
score authority. Known verified league IDs are used to fetch team badges and
league artwork, then missing canonical artwork is filled by strict team-name
identity matching. Existing ids/logos are never overwritten.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.adapters import FetchResult
from collector.cache import note_list_invalidation
from collector.adapters_thesportsdb import BASE
from collector.http import fetch_url
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.participant_alias import names_equivalent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json
from collector.verified_coverage import THESPORTSDB_LEAGUES

RUN_INTERVAL_S = 150
LEAGUE_TTL_S = 12 * 3600
MAX_LEAGUES_PER_RUN = 32


def _public_visibility_clause():
    # Public read semantics are "not explicitly false". Legacy canonical rows
    # can still have NULL here and must receive identity assets too.
    return or_(
        SportsEvent.display_eligible.is_(True),
        SportsEvent.display_eligible.is_(None),
    )

_next_run_at = 0.0
_last_fetch: Dict[str, float] = {}
_TEAM_LAST_FETCH: Dict[str, float] = {}
_NAME_LAST_FETCH: Dict[Tuple[str, str], float] = {}
MAX_DIRECT_TEAM_LOOKUPS = 40
MAX_DIRECT_NAME_LOOKUPS = 40

TSDB_BY_COMP = {
    row["competition_id"]: row
    for row in THESPORTSDB_LEAGUES
    if row.get("event_model") == "team_match"
}

# Competition artwork is useful for every event model, not only team sports.
# Keep this catalogue asset-only: these ids are never used as fixture/result
# authority. Formula 1/2 ids are verified TheSportsDB league identities.
TSDB_LOGO_BY_COMP = {
    row["competition_id"]: row
    for row in THESPORTSDB_LEAGUES
    if row.get("source_competition_id")
}
TSDB_LOGO_BY_COMP.update(
    {
        "formula-1": {
            "competition_id": "formula-1",
            "sport_id": "motorsport",
            "event_model": "motorsport_race",
            "source_competition_id": "4370",
            "name": "Formula 1",
        },
        "formula-2": {
            "competition_id": "formula-2",
            "sport_id": "motorsport",
            "event_model": "motorsport_race",
            "source_competition_id": "4486",
            "name": "Formula 2",
        },
    }
)


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
    )


def _team_lookup_asset(payload: Any) -> Dict[str, str]:
    rows = payload.get("teams") if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    item = rows[0]
    logo = str(
        item.get("strBadge")
        or item.get("strTeamBadge")
        or item.get("strLogo")
        or item.get("strTeamLogo")
        or ""
    ).strip()
    if not logo:
        return {}
    return {
        "id": str(item.get("idTeam") or "").strip(),
        "name": str(item.get("strTeam") or item.get("strTeamShort") or "").strip(),
        "logo": logo,
        "country_id": str(item.get("strCountry") or "").strip(),
    }


def _search_team_asset(payload: Any, *, query_name: str, league_id: str) -> Dict[str, str]:
    rows = payload.get("teams") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return {}
    matches: List[Dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        item_league_id = str(item.get("idLeague") or "").strip()
        if league_id and item_league_id != league_id:
            continue
        item_name = str(item.get("strTeam") or item.get("strTeamShort") or "").strip()
        aliases = [
            item_name,
            str(item.get("strTeamShort") or "").strip(),
            str(item.get("strAlternate") or "").strip(),
            str(item.get("strTeamAlternate") or "").strip(),
        ]
        if not any(value and names_equivalent(query_name, value) for value in aliases):
            continue
        logo = str(
            item.get("strBadge")
            or item.get("strTeamBadge")
            or item.get("strLogo")
            or item.get("strTeamLogo")
            or ""
        ).strip()
        if not logo:
            continue
        matches.append(
            {
                "id": str(item.get("idTeam") or "").strip(),
                "name": item_name,
                "logo": logo,
                "country_id": str(item.get("strCountry") or "").strip(),
            }
        )
    unique_ids = {row.get("id") for row in matches if row.get("id")}
    if len(matches) != 1 or len(unique_ids) != 1:
        return {}
    return matches[0]


def _direct_name_candidates(db: Session, now: float) -> List[Tuple[str, str, str]]:
    window_start = datetime.utcnow() - timedelta(days=1)
    window_end = datetime.utcnow() + timedelta(days=3)
    counts: Dict[Tuple[str, str, str], int] = defaultdict(int)
    rows = (
        db.query(SportsEvent)
        .filter(
            _public_visibility_clause(),
            SportsEvent.start_time >= window_start,
            SportsEvent.start_time <= window_end,
        )
        .all()
    )
    for row in rows:
        competition_id = str(row.competition_id or "")
        spec = TSDB_BY_COMP.get(competition_id)
        if not spec:
            continue
        league_id = str(spec.get("source_competition_id") or "").strip()
        if not league_id.isdigit():
            continue
        participants = load_json(row.participants_json, {}) or {}
        for side_name in ("home", "away"):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            name = str(side.get("display_name") or side.get("name") or "").strip()
            if not name or name.casefold() == "tbd":
                continue
            cache_key = (competition_id, fold_for_identity(name))
            if now - float(_NAME_LAST_FETCH.get(cache_key) or 0.0) < LEAGUE_TTL_S:
                continue
            counts[(competition_id, league_id, name)] += 1
    return [
        item
        for item, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0][0], pair[0][2]))
    ][:MAX_DIRECT_NAME_LOOKUPS]


def _apply_name_asset(
    db: Session,
    *,
    competition_id: str,
    query_name: str,
    asset: Dict[str, str],
) -> Tuple[int, int]:
    if not asset.get("logo"):
        return 0, 0
    rows_updated = 0
    participants_filled = 0
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.competition_id == competition_id,
            _public_visibility_clause(),
        )
        .all()
    )
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            side_name_text = str(side.get("display_name") or side.get("name") or "").strip()
            if not names_equivalent(query_name, side_name_text):
                continue
            if asset.get("name") and not names_equivalent(side_name_text, asset["name"]):
                continue
            merged = dict(side)
            merged["logo"] = asset["logo"]
            if not str(merged.get("id") or "").strip() and asset.get("id"):
                merged["id"] = asset["id"]
            if not str(merged.get("country_id") or "").strip() and asset.get("country_id"):
                merged["country_id"] = asset["country_id"]
            participants[side_name] = merged
            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and _missing_logo(mirror):
                mirror_merged = dict(mirror)
                mirror_merged["logo"] = asset["logo"]
                if not str(mirror_merged.get("id") or "").strip() and asset.get("id"):
                    mirror_merged["id"] = asset["id"]
                participants[mirror_name] = mirror_merged
            changed = True
            participants_filled += 1
        if changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
            rows_updated += 1
    return rows_updated, participants_filled


def _direct_team_ids(db: Session, now: float) -> List[str]:
    window_start = datetime.utcnow() - timedelta(days=1)
    window_end = datetime.utcnow() + timedelta(days=3)
    counts: Dict[str, int] = defaultdict(int)
    rows = (
        db.query(SportsEvent)
        .filter(
            _public_visibility_clause(),
            SportsEvent.start_time >= window_start,
            SportsEvent.start_time <= window_end,
        )
        .all()
    )
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "thesportsdb":
            continue
        participants = load_json(row.participants_json, {}) or {}
        for key in ("home", "away"):
            side = participants.get(key)
            if not isinstance(side, dict) or not _missing_logo(side):
                continue
            team_id = str(side.get("id") or "").strip()
            if not team_id.isdigit():
                continue
            last = float(_TEAM_LAST_FETCH.get(team_id) or 0.0)
            if now - last >= LEAGUE_TTL_S:
                counts[team_id] += 1
    return [
        team_id
        for team_id, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ][:MAX_DIRECT_TEAM_LOOKUPS]


def _apply_direct_team_asset(db: Session, team_id: str, asset: Dict[str, str]) -> int:
    if not asset.get("logo"):
        return 0
    rows = db.query(SportsEvent).filter(_public_visibility_clause()).all()
    updated = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if str(extra.get("source_family") or "").strip().lower() != "thesportsdb":
            continue
        participants = load_json(row.participants_json, {}) or {}
        changed = False
        for key, alt in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(key)
            if not isinstance(side, dict) or str(side.get("id") or "").strip() != team_id:
                continue
            if not _missing_logo(side):
                continue
            merged = dict(side)
            merged["logo"] = asset["logo"]
            if not str(merged.get("country_id") or "").strip() and asset.get("country_id"):
                merged["country_id"] = asset["country_id"]
            participants[key] = merged
            alt_side = participants.get(alt)
            if isinstance(alt_side, dict) and _missing_logo(alt_side):
                alt_merged = dict(alt_side)
                alt_merged["logo"] = asset["logo"]
                participants[alt] = alt_merged
            changed = True
        if changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
            updated += 1
    return updated


def _teams(payload: Any) -> List[Dict[str, str]]:
    rows = payload.get("teams") if isinstance(payload, dict) else []
    out: List[Dict[str, str]] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("strTeam") or item.get("strTeamShort") or "").strip()
        if not name:
            continue
        team_id = str(item.get("idTeam") or "").strip()
        logo = str(
            item.get("strBadge")
            or item.get("strTeamBadge")
            or item.get("strLogo")
            or item.get("strTeamLogo")
            or ""
        ).strip()
        if not logo:
            continue
        aliases = []
        for value in (
            name,
            item.get("strTeamShort"),
            item.get("strAlternate"),
            item.get("strTeamAlternate"),
        ):
            text = str(value or "").strip()
            if text and text not in aliases:
                aliases.append(text)
        keywords = str(item.get("strKeywords") or "").strip()
        if keywords:
            for value in keywords.split(","):
                text = value.strip()
                if text and len(text) >= 3 and text not in aliases:
                    aliases.append(text)
        out.append({
            "id": team_id,
            "name": name,
            "folded": fold_for_identity(name),
            "aliases": aliases,
            "folded_aliases": [fold_for_identity(value) for value in aliases if fold_for_identity(value)],
            "logo": logo,
            "country_id": str(item.get("strCountry") or "").strip(),
        })
    return out


def _league_logo(payload: Any) -> str:
    rows = payload.get("leagues") if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows:
        return ""
    row = rows[0] if isinstance(rows[0], dict) else {}
    return str(
        row.get("strBadge")
        or row.get("strLeagueBadge")
        or row.get("strLogo")
        or row.get("strLeagueLogo")
        or ""
    ).strip()


def _unique_match(name: str, roster: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    folded = fold_for_identity(name)
    if not folded:
        return None
    exact = [
        row
        for row in roster
        if row.get("folded") == folded or folded in (row.get("folded_aliases") or [])
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    aliases = []
    for row in roster:
        candidate_names = row.get("aliases") or [row.get("name")]
        if any(names_equivalent(name, candidate) for candidate in candidate_names if candidate):
            aliases.append(row)
    return aliases[0] if len(aliases) == 1 else None


def _candidates(db: Session, now: float) -> List[Tuple[str, str, int]]:
    counts: Dict[str, int] = defaultdict(int)
    priority: Dict[str, int] = defaultdict(int)
    window_start = datetime.utcnow() - timedelta(days=1)
    window_end = datetime.utcnow() + timedelta(days=3)
    rows = (
        db.query(SportsEvent)
        .filter(_public_visibility_clause())
        .all()
    )
    for row in rows:
        competition_id = str(row.competition_id or "")
        logo_spec = TSDB_LOGO_BY_COMP.get(competition_id)
        if not logo_spec:
            continue
        participants = load_json(row.participants_json, {}) or {}
        missing = 0
        if competition_id in TSDB_BY_COMP:
            missing = sum(
                1
                for key in ("home", "away")
                if isinstance(participants.get(key), dict) and _missing_logo(participants.get(key))
            )
        extra = load_json(row.extra_json, {}) or {}
        missing_competition_logo = not bool(extra.get("competition_logo"))
        gap_weight = missing + (1 if missing_competition_logo else 0)
        counts[competition_id] += gap_weight
        if gap_weight and row.start_time and window_start <= row.start_time <= window_end:
            priority[competition_id] += 100 * gap_weight
    output = []
    for competition_id, missing in counts.items():
        if not missing:
            continue
        last = float(_last_fetch.get(competition_id) or 0.0)
        if now - last < LEAGUE_TTL_S:
            continue
        league_id = str(TSDB_LOGO_BY_COMP[competition_id].get("source_competition_id") or "")
        if league_id.isdigit():
            output.append((competition_id, league_id, missing))
    output.sort(key=lambda item: (-(priority.get(item[0], 0) + item[2]), item[0]))
    return output


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S
    getter = getter or fetch_url
    candidates = _candidates(db, now)[:MAX_LEAGUES_PER_RUN]
    direct_team_ids = _direct_team_ids(db, now)
    direct_name_candidates = _direct_name_candidates(db, now)
    stats: Dict[str, Any] = {
        "status": "ok" if (candidates or direct_team_ids or direct_name_candidates) else "idle",
        "leagues": 0,
        "requests": 0,
        "rows_updated": 0,
        "participants_filled": 0,
        "competition_logos_filled": 0,
        "http_errors": 0,
        "direct_team_requests": 0,
        "direct_team_rows_updated": 0,
        "direct_name_requests": 0,
        "direct_name_rows_updated": 0,
        "direct_name_participants_filled": 0,
        "by_competition": {},
    }

    for team_id in direct_team_ids:
        result = getter(f"{BASE}/lookupteam.php?id={team_id}")
        stats["requests"] += 1
        stats["direct_team_requests"] += 1
        if heartbeat:
            heartbeat()
        _TEAM_LAST_FETCH[team_id] = now
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue
        asset = _team_lookup_asset(result.payload)
        changed = _apply_direct_team_asset(db, team_id, asset)
        if changed:
            db.commit()
            stats["rows_updated"] += changed
            stats["participants_filled"] += changed
            stats["direct_team_rows_updated"] += changed

    for competition_id, league_id, query_name in direct_name_candidates:
        cache_key = (competition_id, fold_for_identity(query_name))
        result = getter(f"{BASE}/searchteams.php?t={quote(query_name)}")
        stats["requests"] += 1
        stats["direct_name_requests"] += 1
        if heartbeat:
            heartbeat()
        _NAME_LAST_FETCH[cache_key] = now
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            continue
        asset = _search_team_asset(
            result.payload,
            query_name=query_name,
            league_id=league_id,
        )
        if not asset:
            continue
        changed_rows, filled = _apply_name_asset(
            db,
            competition_id=competition_id,
            query_name=query_name,
            asset=asset,
        )
        if changed_rows:
            db.commit()
            stats["rows_updated"] += changed_rows
            stats["participants_filled"] += filled
            stats["direct_name_rows_updated"] += changed_rows
            stats["direct_name_participants_filled"] += filled

    for competition_id, league_id, _missing in candidates:
        roster: List[Dict[str, str]] = []
        if competition_id in TSDB_BY_COMP:
            team_result = getter(f"{BASE}/lookup_all_teams.php?id={league_id}")
            stats["requests"] += 1
            if heartbeat:
                heartbeat()
            if getattr(team_result, "ok", False):
                roster = _teams(team_result.payload)
            else:
                stats["http_errors"] += 1

        league_result = getter(f"{BASE}/lookupleague.php?id={league_id}")
        stats["requests"] += 1
        if heartbeat:
            heartbeat()
        _last_fetch[competition_id] = now

        logo = _league_logo(league_result.payload) if getattr(league_result, "ok", False) else ""
        if not getattr(league_result, "ok", False):
            stats["http_errors"] += 1

        comp_rows_updated = 0
        comp_participants = 0
        comp_logos = 0
        rows = (
            db.query(SportsEvent)
            .filter(
                SportsEvent.competition_id == competition_id,
                _public_visibility_clause(),
            )
            .all()
        )
        for row in rows:
            participants = load_json(row.participants_json, {}) or {}
            extra = load_json(row.extra_json, {}) or {}
            changed = False
            for side_name in ("home", "away"):
                side = participants.get(side_name)
                if not isinstance(side, dict) or not _missing_logo(side):
                    continue
                name = str(side.get("display_name") or side.get("name") or "").strip()
                match = _unique_match(name, roster)
                if not match:
                    continue
                merged = dict(side)
                merged["logo"] = match["logo"]
                if not str(merged.get("id") or "").strip() and match.get("id"):
                    merged["id"] = match["id"]
                if not str(merged.get("country_id") or "").strip() and match.get("country_id"):
                    merged["country_id"] = match["country_id"]
                participants[side_name] = merged
                alt = "participant_a" if side_name == "home" else "participant_b"
                if isinstance(participants.get(alt), dict):
                    alt_side = dict(participants[alt])
                    if _missing_logo(alt_side):
                        alt_side["logo"] = match["logo"]
                    participants[alt] = alt_side
                changed = True
                comp_participants += 1

            if logo and not extra.get("competition_logo"):
                extra["competition_logo"] = logo
                comp_logos += 1
                changed = True

            if changed:
                row.participants_json = dump_json(participants)
                row.extra_json = dump_json(extra)
                store_list_extra(row, extra)
                note_list_invalidation(
                    db,
                    sport=row.sport_id,
                    competition=row.competition_id,
                    start_time=row.start_time,
                )
                comp_rows_updated += 1

        if comp_rows_updated:
            db.commit()

        stats["leagues"] += 1
        stats["rows_updated"] += comp_rows_updated
        stats["participants_filled"] += comp_participants
        stats["competition_logos_filled"] += comp_logos
        stats["by_competition"][competition_id] = {
            "league_id": league_id,
            "roster": len(roster),
            "rows_updated": comp_rows_updated,
            "participants_filled": comp_participants,
            "competition_logos_filled": comp_logos,
        }

    return stats
