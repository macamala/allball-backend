"""Canonical competition resolution.

Provider/source competition IDs dominate. Similar names never merge
competitions. A mapping bucket is not identity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# BBC/SportScore group labels that identify a mapping. `any` is OR; `all` is AND.
# Deny tokens block false positives (women's A-League vs men, etc.).
COMPETITION_LABELS: Dict[str, Dict[str, Any]] = {
    "fa-cup": {"any": ["fa cup", "emirates fa cup"]},
    "australia-a-league": {
        "any": ["a-league men", "australian a-league", "isuzu utes a-league", "isuzu ute a-league"],
        "all_any": [["a-league", "australia"]],
        "deny": ["women", "w-league", "a-league women"],
    },
    "australia-a-league-women": {"any": ["a-league women", "womens a-league", "women's a-league"]},
    "brazil-serie-a": {
        "any": ["brasileiro", "brasileirão", "brazilian serie a", "campeonato brasileiro", "brazil serie a"],
        "deny": ["serie b", "serie c", "italy", "italian"],
    },
    "italy-serie-a": {"any": ["italian serie a", "serie a tim"], "all_any": [["serie a", "italy"], ["serie a", "italian"]]},
    "chile-primera": {"any": ["chilean primera", "primera división de chile", "liga de primera"]},
    "argentina-primera": {"any": ["argentine primera", "liga profesional", "primera división argentina"]},
    "england-premier-league": {"any": ["premier league", "english premier"], "deny": ["women"]},
    "england-championship": {"any": ["championship", "sky bet championship"], "deny": ["australian"]},
    "england-league-one": {"any": ["league one", "sky bet league one"]},
    "england-league-two": {"any": ["league two", "sky bet league two"]},
    "scotland-premiership": {"any": ["scottish premiership", "cinch premiership"]},
    "womens-super-league": {"any": ["women's super league", "womens super league", "barclays wsl", " wsl"]},
    "uefa-europa-league": {"any": ["europa league", "uefa europa"]},
    "uefa-conference-league": {"any": ["conference league", "uefa conference", "europa conference"]},
    "uefa-nations-league": {"any": ["nations league"]},
    "norway-eliteserien": {"any": ["eliteserien"]},
    "denmark-superliga": {"any": ["danish superliga", "denmark superliga", "3f superliga"]},
    "sweden-allsvenskan": {"any": ["allsvenskan"]},
    "mexico-liga-mx": {"any": ["liga mx"]},
    "usa-usl-championship": {"any": ["usl championship"]},
    "usa-nwsl": {"any": ["nwsl", "national soccer league"]},
    "copa-libertadores": {"any": ["copa libertadores"]},
    "copa-sudamericana": {"any": ["sudamericana"]},
    "afc-champions-league": {"any": ["afc champion"]},
    "caf-champions-league": {"any": ["caf champion"]},
    "serbia-superliga": {"any": ["serbian super", "mozzart bet", "serbia superliga"]},
    "czech-first-league": {"any": ["czech first", "chance liga", "fortuna liga"]},
    "germany-bundesliga": {
        "any": ["1. bundesliga", "1.bundesliga", "german bundesliga", "bundesliga"],
        "deny": ["2. bundesliga", "2.bundesliga", "3. liga", "3.liga", "frauen", "handball", "zweite"],
    },
    "germany-2-bundesliga": {
        "any": ["2. bundesliga", "2.bundesliga", "german 2. bundesliga", "zweite bundesliga"],
        "deny": ["3. liga", "3.liga", "frauen", "handball"],
    },
    "germany-3-liga": {"any": ["3. liga", "3.liga", "3rd liga"], "deny": ["bundesliga", "frauen"]},
}


def _blob(value: Any) -> str:
    return str(value or "").strip().lower()


def label_matches_competition(label: str, competition_id: str) -> bool:
    """True only when the source competition label belongs to this canonical id."""
    blob = _blob(label)
    if not blob or not competition_id:
        return False
    spec = COMPETITION_LABELS.get(competition_id)
    if spec:
        for token in spec.get("deny") or []:
            if token.lower() in blob:
                return False
        for token in spec.get("any") or []:
            if token.lower() in blob:
                return True
        for group in spec.get("all_any") or []:
            if all(part.lower() in blob for part in group):
                return True
        return False
    tokens = [
        part
        for part in competition_id.split("-")
        if part not in {"world", "uk", "usa", "and", "the"} and (part.isdigit() or len(part) > 2)
    ]
    if not tokens:
        return competition_id.replace("-", " ") in blob
    return all(token in blob for token in tokens)


def stamped_mapping_label(name: str, mapping_competition_id: str) -> bool:
    blob = _blob(name).replace(" ", "-")
    mapping = _blob(mapping_competition_id)
    return bool(blob) and blob == mapping


def provider_competition_crosswalk() -> Dict[str, str]:
    """source_competition_id (any family) → canonical id when the id is unique."""
    from collector.verified_coverage import OPENLIGADB_LEAGUES, THESPORTSDB_LEAGUES

    counts: Dict[str, set] = {}
    for row in OPENLIGADB_LEAGUES:
        key = _blob(row.get("shortcut"))
        counts.setdefault(key, set()).add(row["competition_id"])
    for row in THESPORTSDB_LEAGUES:
        key = _blob(row.get("source_competition_id"))
        counts.setdefault(key, set()).add(row["competition_id"])
    return {key: next(iter(ids)) for key, ids in counts.items() if key and len(ids) == 1}


def canonical_for_source_competition_id(source_competition_id: Optional[str]) -> Optional[str]:
    if not source_competition_id:
        return None
    return provider_competition_crosswalk().get(_blob(source_competition_id))


def labeled_competition_ids(sport_id: str = "") -> Dict[str, str]:
    from collector.verified_coverage import OPENLIGADB_LEAGUES, THESPORTSDB_LEAGUES

    ids = {key: "" for key in COMPETITION_LABELS}
    for row in list(OPENLIGADB_LEAGUES) + list(THESPORTSDB_LEAGUES):
        if sport_id and row.get("sport_id") and row.get("sport_id") != sport_id:
            continue
        ids[row["competition_id"]] = row.get("sport_id") or ""
    return ids


def unique_label_competition(label: str, *, sport_id: str = "", exclude: Optional[str] = None) -> Optional[str]:
    if not label or stamped_mapping_label(label, exclude or ""):
        return None
    matches = []
    for competition_id in labeled_competition_ids(sport_id):
        if exclude and competition_id == exclude:
            continue
        if label_matches_competition(label, competition_id):
            matches.append(competition_id)
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_competition(
    *,
    mapping_competition_id: str,
    source_competition_id: Optional[str] = None,
    source_competition_name: Optional[str] = None,
    source_family: str = "",
    sport_id: str = "",
) -> Dict[str, Any]:
    name = source_competition_name or ""
    independent_name = name and not stamped_mapping_label(name, mapping_competition_id)
    mapped_from_id = canonical_for_source_competition_id(source_competition_id)
    base = {
        "source_family": source_family,
        "source_competition_id": source_competition_id,
        "source_competition_name": name,
        "suggested_competition_id": None,
    }
    if mapped_from_id and mapped_from_id != mapping_competition_id:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "suggested_competition_id": mapped_from_id,
            "resolution_method": "rejected_source_id_other_competition",
            "resolution_confidence": 0,
            "accepted": False,
        }
    if mapped_from_id and mapped_from_id == mapping_competition_id:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "source_competition_id",
            "resolution_confidence": 100,
            "accepted": True,
        }
    if source_competition_id and source_competition_id == mapping_competition_id:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "source_competition_id",
            "resolution_confidence": 100,
            "accepted": True,
        }
    if independent_name and label_matches_competition(name, mapping_competition_id):
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "source_label",
            "resolution_confidence": 90,
            "accepted": True,
        }
    other = unique_label_competition(name, sport_id=sport_id, exclude=mapping_competition_id) if independent_name else None
    if other:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "suggested_competition_id": other,
            "resolution_method": "rejected_label_other_competition",
            "resolution_confidence": 0,
            "accepted": False,
        }
    hub = source_family in {"bbc-sport", "sportscore", "espn-html"}
    if not independent_name and not source_competition_id:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "mapping_unlabeled",
            "resolution_confidence": 40,
            "accepted": not hub,
        }
    if independent_name and not label_matches_competition(name, mapping_competition_id):
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "rejected_label_mismatch",
            "resolution_confidence": 0,
            "accepted": False,
        }
    if hub:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "rejected_label_mismatch",
            "resolution_confidence": 0,
            "accepted": False,
        }
    return {
        **base,
        "canonical_competition_id": mapping_competition_id,
        "resolution_method": "mapping_request_trusted",
        "resolution_confidence": 55,
        "accepted": True,
    }


def event_accepted_for_mapping(raw: Dict[str, Any], mapping_competition_id: str) -> Tuple[bool, Dict[str, Any]]:
    resolved = resolve_competition(
        mapping_competition_id=mapping_competition_id,
        source_competition_id=str(raw.get("source_competition_id") or "") or None,
        source_competition_name=str(
            raw.get("source_competition_name") or raw.get("competition") or raw.get("competition_name") or ""
        ),
        source_family=str(raw.get("source_family") or ""),
        sport_id=str(raw.get("sport") or raw.get("sport_id") or ""),
    )
    unlabeled_ok = resolved["resolution_method"] == "mapping_unlabeled"
    family = str(raw.get("source_family") or "")
    if unlabeled_ok and family in {"bbc-sport", "sportscore", "espn-html"}:
        resolved["accepted"] = False
        resolved["resolution_method"] = "rejected_unlabeled_hub"
        resolved["resolution_confidence"] = 0
    return bool(resolved["accepted"]), resolved
