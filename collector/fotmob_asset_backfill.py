"""Bounded FotMob league-roster identity backfill.

Uses the verified FOTMOB_LEAGUES catalogue plus source-native numeric FotMob
competition IDs already persisted on public rows. One league response supplies
canonical team ids/crests for all existing rows in that competition. Matching is
strict: exact folded identity or one unique deterministic alias equivalence.
Existing ids/logos are never overwritten.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.adapters_fotmob import LEAGUE_URL, asset_league_ids, parse_fotmob_table
from collector.cache import note_list_invalidation
from collector.http import fetch_url
from collector.list_extra import extra_for_list, store_list_extra
from collector.models import SportsEvent
from collector.participant_alias import names_equivalent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 120
LEAGUE_TTL_S = 12 * 3600
MAX_LEAGUES_PER_RUN = 40

_next_run_at = 0.0
_last_league_fetch: Dict[str, float] = {}


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


def _roster(payload: Any) -> List[Dict[str, str]]:
    rows = parse_fotmob_table(payload)
    raw: List[Dict[str, str]] = []

    for row in rows:
        raw.append(
            {
                "id": str(row.get("team_id") or "").strip(),
                "name": str(row.get("team") or "").strip(),
                "logo": str(row.get("logo") or "").strip(),
            }
        )

    # Cups and some leagues do not expose a standings table. Their league
    # payload still carries authoritative home/away team nodes in fixtures.
    def take_team(node: Any) -> None:
        if not isinstance(node, dict):
            return
        team_id = str(node.get("id") or node.get("teamId") or "").strip()
        name = str(node.get("name") or node.get("shortName") or "").strip()
        if team_id.isdigit() and name:
            raw.append(
                {
                    "id": team_id,
                    "name": name,
                    "logo": str(
                        node.get("logo")
                        or node.get("imageUrl")
                        or node.get("image")
                        or ""
                    ).strip(),
                }
            )

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        for key in ("home", "away", "homeTeam", "awayTeam"):
            value = node.get(key)
            if isinstance(value, dict):
                take_team(value)
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value)

    walk(payload)

    out: List[Dict[str, str]] = []
    seen = set()
    for row in raw:
        team_id = str(row.get("id") or "").strip()
        name = str(row.get("name") or "").strip()
        if not team_id.isdigit() or not name:
            continue
        key = (team_id, fold_for_identity(name))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": team_id,
                "name": name,
                "folded": fold_for_identity(name),
                "logo": str(
                    row.get("logo")
                    or f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png"
                ),
            }
        )
    return out


_ROSTER_GENERIC = {
    "united", "city", "athletic", "sporting", "racing", "real", "club",
}
_ROSTER_GENDER = {"wfc", "women", "womens", "ladies"}


def _gender_tokens(value: str) -> List[str]:
    return [
        "women" if token in _ROSTER_GENDER else token
        for token in fold_for_identity(value).split()
    ]


def _consonant_key(token: str) -> str:
    token = token.replace("q", "k")
    return re.sub(r"[aeiouy]+", "", token)


def _roster_variant_equivalent(left: str, right: str) -> bool:
    """Competition-scoped fallback; caller must require a unique roster match."""
    a = _gender_tokens(left)
    b = _gender_tokens(right)
    if not a or not b:
        return False
    if a == b:
        return True

    # Women's feeds vary between WFC / Women / Ladies.
    if len(a) == len(b) and all(x == y for x, y in zip(a, b)):
        return True

    # One-token club short names are allowed only as a unique first/last token
    # in the official roster, never for generic football words.
    if len(a) == 1 and len(a[0]) >= 5 and a[0] not in _ROSTER_GENERIC:
        return a[0] in {b[0], b[-1]}
    if len(b) == 1 and len(b[0]) >= 5 and b[0] not in _ROSTER_GENERIC:
        return b[0] in {a[0], a[-1]}

    # Feed legal/sponsor abbreviations often add one short token (Grêmio FB,
    # Port MTI) around an otherwise unique roster identity.
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 1 and len(longer) - len(shorter) <= 2:
        if longer[: len(shorter)] == shorter or longer[-len(shorter) :] == shorter:
            extras = (
                longer[len(shorter) :]
                if longer[: len(shorter)] == shorter
                else longer[: len(longer) - len(shorter)]
            )
            if all(len(token) <= 4 or token not in _ROSTER_GENERIC for token in extras):
                return True

    # Romanisation variants inside the same confirmed roster:
    # Samarqand/Samarkand, Andijon/Andijan, etc.
    if len(a) == len(b):
        changed = False
        for x, y in zip(a, b):
            if x == y:
                continue
            if min(len(x), len(y)) < 5 or abs(len(x) - len(y)) > 1:
                return False
            if _consonant_key(x) != _consonant_key(y):
                return False
            changed = True
        if changed:
            return True

    return False


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
    if len(aliases) == 1:
        return aliases[0]
    if len(aliases) > 1:
        return None

    variants = [
        row for row in roster
        if _roster_variant_equivalent(name, row["name"])
    ]
    return variants[0] if len(variants) == 1 else None


def _fill_side(side: Any, roster: List[Dict[str, str]]) -> Tuple[Any, bool]:
    if not isinstance(side, dict):
        return side, False
    name = str(side.get("display_name") or side.get("name") or "").strip()
    if not name:
        return side, False
    matched = _unique_match(name, roster)
    if not matched:
        return side, False
    out = dict(side)
    changed = False
    if not str(out.get("id") or "").strip():
        out["id"] = matched["id"]
        changed = True
    if _missing_logo(out):
        out["logo"] = matched["logo"]
        changed = True
    return out, changed


def _candidate_competitions(db: Session, now: float) -> List[Tuple[str, List[str]]]:
    counts: Dict[str, int] = defaultdict(int)
    source_ids: Dict[str, set] = defaultdict(set)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.display_eligible.is_(True),
        )
        .all()
    )
    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        missing = sum(
            1
            for key in ("home", "away")
            if isinstance(participants.get(key), dict) and _missing_logo(participants.get(key))
        )

        competition_id = str(row.competition_id or "")
        extra = load_json(row.extra_json, {}) or {}
        slim = extra_for_list(row) or {}
        for key, value in slim.items():
            if value not in (None, "", [], {}):
                extra[key] = value
        missing_competition_logo = not bool(extra.get("competition_logo"))
        if not missing and not missing_competition_logo:
            continue

        known_ids = asset_league_ids(competition_id)
        for value in known_ids:
            if str(value).isdigit():
                source_ids[competition_id].add(str(value))


        family = str(extra.get("source_family") or "").strip().lower()
        source_competition_id = str(extra.get("source_competition_id") or "").strip()
        if family == "fotmob" and source_competition_id.isdigit():
            source_ids[competition_id].add(source_competition_id)

        if source_ids.get(competition_id):
            counts[competition_id] += missing + (1 if missing_competition_logo else 0)

    candidates: List[Tuple[str, List[str]]] = []
    for competition_id, missing in counts.items():
        last = _last_league_fetch.get(competition_id)
        # No previous fetch means immediately due, even on a freshly booted host.
        if last is not None and now - float(last) < LEAGUE_TTL_S:
            continue
        ids = sorted(source_ids.get(competition_id) or [], key=lambda value: int(value))
        if ids:
            candidates.append((competition_id, ids))
    candidates.sort(key=lambda item: (-counts[item[0]], item[0]))
    return candidates


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now = time.monotonic()
    if now < _next_run_at:
        return None
    _next_run_at = now + RUN_INTERVAL_S

    getter = getter or fetch_url
    candidates = _candidate_competitions(db, now)[:MAX_LEAGUES_PER_RUN]
    if not candidates:
        return {
            "status": "idle",
            "leagues": 0,
            "requests": 0,
            "rows_updated": 0,
            "participants_filled": 0,
        }

    stats: Dict[str, Any] = {
        "status": "ok",
        "leagues": 0,
        "requests": 0,
        "rows_updated": 0,
        "participants_filled": 0,
        "competition_logos_filled": 0,
        "http_errors": 0,
        "by_competition": {},
    }

    for competition_id, league_ids in candidates:
        merged_roster: List[Dict[str, str]] = []
        successful_ids: List[str] = []
        for league_id in league_ids:
            result = getter(LEAGUE_URL.format(league_id=league_id))
            stats["requests"] += 1
            if heartbeat:
                heartbeat()
            if not result.ok:
                stats["http_errors"] += 1
                continue
            successful_ids.append(str(league_id))
            merged_roster.extend(_roster(result.payload))
        _last_league_fetch[competition_id] = now
        if not merged_roster:
            stats["by_competition"][competition_id] = {
                "league_ids": successful_ids,
                "roster": 0,
                "rows_updated": 0,
                "participants_filled": 0,
            }
            continue

        # De-duplicate by team id before matching.
        unique: Dict[str, Dict[str, str]] = {}
        for item in merged_roster:
            unique.setdefault(item["id"], item)
        roster = list(unique.values())

        rows = (
            db.query(SportsEvent)
            .filter(
                SportsEvent.sport_id == "football",
                SportsEvent.competition_id == competition_id,
                SportsEvent.display_eligible.is_(True),
            )
            .all()
        )
        comp_rows_updated = 0
        comp_participants = 0
        comp_logo_filled = 0
        default_league_id = successful_ids[0] if len(successful_ids) == 1 else ""

        for row in rows:
            participants = load_json(row.participants_json, {}) or {}
            extra = load_json(row.extra_json, {}) or {}
            changed = False
            for side_name in ("home", "away"):
                filled, side_changed = _fill_side(participants.get(side_name), roster)
                if side_changed:
                    participants[side_name] = filled
                    alt = "participant_a" if side_name == "home" else "participant_b"
                    alt_side = participants.get(alt)
                    alt_filled, alt_changed = _fill_side(alt_side, roster)
                    if alt_changed:
                        participants[alt] = alt_filled
                    elif isinstance(alt_side, dict):
                        merged_alt = dict(alt_side)
                        if not merged_alt.get("id") and filled.get("id"):
                            merged_alt["id"] = filled["id"]
                        if _missing_logo(merged_alt) and filled.get("logo"):
                            merged_alt["logo"] = filled["logo"]
                        participants[alt] = merged_alt
                    changed = True
                    comp_participants += 1

            if default_league_id and not extra.get("competition_logo"):
                extra["competition_logo"] = (
                    "https://images.fotmob.com/image_resources/logo/"
                    f"leaguelogo/{default_league_id}.png"
                )
                comp_logo_filled += 1
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
        stats["competition_logos_filled"] += comp_logo_filled
        stats["by_competition"][competition_id] = {
            "league_ids": successful_ids,
            "roster": len(roster),
            "rows_updated": comp_rows_updated,
            "participants_filled": comp_participants,
        }

    return stats
