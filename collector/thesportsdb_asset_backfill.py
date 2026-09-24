"""Bounded TheSportsDB artwork catalogue backfill.

This job is intentionally asset-only. It never uses TheSportsDB as the live
score authority. Known verified league IDs are used to fetch team badges and
league artwork, then missing canonical artwork is filled by strict team-name
identity matching. Existing ids/logos are never overwritten.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters import FetchResult
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
MAX_LEAGUES_PER_RUN = 8

_next_run_at = 0.0
_last_fetch: Dict[str, float] = {}

TSDB_BY_COMP = {
    row["competition_id"]: row
    for row in THESPORTSDB_LEAGUES
    if row.get("event_model") == "team_match"
}


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
        out.append({
            "id": team_id,
            "name": name,
            "folded": fold_for_identity(name),
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
    exact = [row for row in roster if row["folded"] == folded]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    aliases = [row for row in roster if names_equivalent(name, row["name"])]
    return aliases[0] if len(aliases) == 1 else None


def _candidates(db: Session, now: float) -> List[Tuple[str, str, int]]:
    counts: Dict[str, int] = defaultdict(int)
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.display_eligible.is_(True))
        .all()
    )
    for row in rows:
        competition_id = str(row.competition_id or "")
        spec = TSDB_BY_COMP.get(competition_id)
        if not spec:
            continue
        participants = load_json(row.participants_json, {}) or {}
        missing = sum(
            1
            for key in ("home", "away")
            if isinstance(participants.get(key), dict) and _missing_logo(participants.get(key))
        )
        counts[competition_id] += missing
    output = []
    for competition_id, missing in counts.items():
        if not missing:
            continue
        last = float(_last_fetch.get(competition_id) or 0.0)
        if now - last < LEAGUE_TTL_S:
            continue
        league_id = str(TSDB_BY_COMP[competition_id].get("source_competition_id") or "")
        if league_id.isdigit():
            output.append((competition_id, league_id, missing))
    output.sort(key=lambda item: (-item[2], item[0]))
    return output


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S
    getter = getter or fetch_url
    candidates = _candidates(db, now)[:MAX_LEAGUES_PER_RUN]
    stats: Dict[str, Any] = {
        "status": "ok" if candidates else "idle",
        "leagues": 0,
        "requests": 0,
        "rows_updated": 0,
        "participants_filled": 0,
        "competition_logos_filled": 0,
        "http_errors": 0,
        "by_competition": {},
    }
    for competition_id, league_id, _missing in candidates:
        team_result = getter(f"{BASE}/lookup_all_teams.php?id={league_id}")
        stats["requests"] += 1
        if heartbeat:
            heartbeat()
        league_result = getter(f"{BASE}/lookupleague.php?id={league_id}")
        stats["requests"] += 1
        if heartbeat:
            heartbeat()
        _last_fetch[competition_id] = now

        roster = _teams(team_result.payload) if getattr(team_result, "ok", False) else []
        logo = _league_logo(league_result.payload) if getattr(league_result, "ok", False) else ""
        if not getattr(team_result, "ok", False):
            stats["http_errors"] += 1
        if not getattr(league_result, "ok", False):
            stats["http_errors"] += 1

        comp_rows_updated = 0
        comp_participants = 0
        comp_logos = 0
        rows = (
            db.query(SportsEvent)
            .filter(
                SportsEvent.competition_id == competition_id,
                SportsEvent.display_eligible.is_(True),
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
