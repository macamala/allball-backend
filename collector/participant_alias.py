"""Participant alias/crosswalk. Name similarity alone never creates an alias."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy.orm import Session

from collector.models import SportsParticipantAlias
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

_ABBREV = (
    (re.compile(r"\butd\b"), "united"),
    (re.compile(r"\bath\b"), "athletic"),
    (re.compile(r"\bwolves\b"), "wolverhampton"),
    (re.compile(r"\bmunchen\b"), "munich"),
    (re.compile(r"\bkoln\b"), "cologne"),
)

_LEADING_CLUB = {
    "fc",
    "cf",
    "sc",
    "afc",
    "vfl",
    "sv",
    "spvgg",
    "1",
    "i",
    "the",
}


def expand_abbreviations(folded: str) -> str:
    text = folded
    for pattern, replacement in _ABBREV:
        text = pattern.sub(replacement, text)
    tokens = text.split()
    while len(tokens) > 1 and tokens[0] in _LEADING_CLUB and len(" ".join(tokens[1:])) >= 8:
        tokens = tokens[1:]
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def names_equivalent(left: str, right: str) -> bool:
    a = fold_for_identity(left)
    b = fold_for_identity(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return expand_abbreviations(a) == expand_abbreviations(b)


_PREFIX_DENY = {
    "wfc",
    "women",
    "womens",
    "ladies",
    "ii",
    "b",
    "u19",
    "u21",
    "u23",
    "res",
    "reserves",
    "youth",
    "xi",
}


def prefix_variant(left: str, right: str) -> bool:
    a = fold_for_identity(left)
    b = fold_for_identity(right)
    if not a or not b or a == b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < 10:
        return False
    if not longer.startswith(shorter + " "):
        return False
    extra = longer[len(shorter) :].strip()
    tokens = extra.split()
    if not extra or extra in {"fc", "cf", "sc"}:
        return False
    if any(token in _PREFIX_DENY for token in tokens):
        return False
    if len(extra) < 5:
        return False
    return True


def prefer_display(left: str, right: str) -> str:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if len(a) == len(b):
        return a if "(" not in a else b
    return a if len(a) > len(b) else b


def load_alias_map(db: Session, sport_id: str) -> Dict[str, str]:
    cache = db.info.setdefault("participant_aliases", {})
    if sport_id in cache:
        return cache[sport_id]
    mapping: Dict[str, str] = {}
    for row in db.query(SportsParticipantAlias).filter_by(sport_id=sport_id).all():
        mapping[row.alias_folded] = row.canonical_folded
        mapping[row.canonical_folded] = row.canonical_folded
    cache[sport_id] = mapping
    return mapping


def resolve_folded(db: Optional[Session], sport_id: str, name: str) -> str:
    folded = fold_for_identity(name)
    expanded = expand_abbreviations(folded)
    if db is None:
        return expanded or folded
    aliases = load_alias_map(db, sport_id)
    return aliases.get(expanded) or aliases.get(folded) or expanded or folded


def persist_alias(
    db: Session,
    *,
    sport_id: str,
    canonical_display: str,
    alias_display: str,
    source_family: str = "",
    source_participant_id: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
    confidence: int = 90,
) -> bool:
    canonical_folded = expand_abbreviations(fold_for_identity(canonical_display))
    alias_folded = expand_abbreviations(fold_for_identity(alias_display))
    if not canonical_folded or not alias_folded or canonical_folded == alias_folded:
        return False
    if len(alias_folded) < 10:
        return False
    pending = db.info.setdefault("alias_pending", set())
    key = (sport_id, alias_folded)
    if key in pending:
        return False
    existing = (
        db.query(SportsParticipantAlias)
        .filter_by(sport_id=sport_id, alias_folded=alias_folded)
        .first()
    )
    if existing:
        pending.add(key)
        return False
    pending.add(key)
    db.add(
        SportsParticipantAlias(
            sport_id=sport_id,
            canonical_folded=canonical_folded,
            alias_folded=alias_folded,
            canonical_display_name=canonical_display,
            source_family=source_family or None,
            source_participant_id=source_participant_id,
            evidence_json=dump_json(evidence or {}),
            confidence=confidence,
        )
    )
    cache = db.info.setdefault("participant_aliases", {})
    mapping = cache.setdefault(sport_id, {})
    mapping[alias_folded] = canonical_folded
    mapping[canonical_folded] = canonical_folded
    return True


def contextual_pair_match(
    left: Dict[str, Any],
    right: Dict[str, Any],
    *,
    db: Optional[Session] = None,
) -> Tuple[bool, str]:
    """True when two events share identity beyond fuzzy names."""
    if (left.get("sport") or "") != (right.get("sport") or ""):
        return False, "sport"
    if (left.get("competition_key") or left.get("competition")) != (
        right.get("competition_key") or right.get("competition")
    ):
        return False, "competition"
    sport = str(left.get("sport") or "")
    lh = (left.get("home") or {}).get("name") or ""
    la = (left.get("away") or {}).get("name") or ""
    rh = (right.get("home") or {}).get("name") or ""
    ra = (right.get("away") or {}).get("name") or ""
    left_pair = {resolve_folded(db, sport, lh), resolve_folded(db, sport, la)}
    right_pair = {resolve_folded(db, sport, rh), resolve_folded(db, sport, ra)}
    if not all(left_pair) or left_pair != right_pair:
        raw_ok = (
            names_equivalent(lh, rh)
            and names_equivalent(la, ra)
            or names_equivalent(lh, ra)
            and names_equivalent(la, rh)
            or (prefix_variant(lh, rh) and names_equivalent(la, ra))
            or (prefix_variant(la, ra) and names_equivalent(lh, rh))
            or (prefix_variant(lh, ra) and names_equivalent(la, rh))
            or (prefix_variant(la, rh) and names_equivalent(lh, ra))
        )
        if not raw_ok:
            return False, "participants"
    left_score = left.get("score") or {}
    right_score = right.get("score") or {}
    if (
        left_score.get("home") not in (None, "")
        and right_score.get("home") not in (None, "")
        and (left_score.get("home"), left_score.get("away"))
        != (right_score.get("home"), right_score.get("away"))
        and (left_score.get("home"), left_score.get("away"))
        != (right_score.get("away"), right_score.get("home"))
    ):
        return False, "score"
    return True, "ok"


def discover_aliases_from_pair(db: Session, left: Dict[str, Any], right: Dict[str, Any]) -> int:
    created = 0
    sport = str(left.get("sport") or "")
    pairs = (
        ((left.get("home") or {}).get("name"), (right.get("home") or {}).get("name")),
        ((left.get("away") or {}).get("name"), (right.get("away") or {}).get("name")),
        ((left.get("home") or {}).get("name"), (right.get("away") or {}).get("name")),
        ((left.get("away") or {}).get("name"), (right.get("home") or {}).get("name")),
    )
    for a, b in pairs:
        if not a or not b or fold_for_identity(a) == fold_for_identity(b):
            continue
        if names_equivalent(a, b) or prefix_variant(a, b):
            canonical = prefer_display(a, b)
            alias = b if canonical == a else a
            evidence = {
                "competition": left.get("competition_key"),
                "event_ids": [left.get("event_id"), right.get("event_id")],
                "method": "abbrev" if names_equivalent(a, b) else "prefix_with_context",
            }
            if persist_alias(
                db,
                sport_id=sport,
                canonical_display=canonical,
                alias_display=alias,
                source_family=str((left.get("extra") or {}).get("source_family") or ""),
                evidence=evidence,
                confidence=92,
            ):
                created += 1
    return created
