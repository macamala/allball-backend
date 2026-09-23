"""Canonical competition resolution.

Provider/source competition IDs dominate. Similar names never merge
competitions. A mapping bucket is not identity.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from collector.util import slugify

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"the", "and", "of", "a", "an"}

# Official competitions created by a first-party collector. They are public
# even though they are outside the frozen 180-source coverage matrix.
OFFICIAL_PUBLIC_COMPETITIONS = {
    "ireland-gri-meetings",
}

SOURCE_NATIVE_PUBLIC_FAMILIES_BY_SPORT = {
    "football": {"fifa", "fifa-digital", "fifa-json", "fotmob", "sofascore-web"},
    "basketball": {"sofascore-web", "sportscore"},
    "tennis": {"sofascore-web", "sportscore"},
    "ice-hockey": {"sofascore-web"},
    "baseball": {"sofascore-web"},
    "handball": {"sofascore-web"},
    "volleyball": {"sofascore-web"},
    "american-football": {"sofascore-web"},
    "futsal": {"sofascore-web"},
    "badminton": {"sofascore-web"},
    "table-tennis": {"sofascore-web"},
    "cricket": {"sofascore-web", "sportscore"},
    "water-polo": {"sofascore-web"},
    "netball": {"sofascore-web"},
    "field-hockey": {"sofascore-web"},
    "darts": {"sofascore-web"},
    "snooker": {"sofascore-web"},
    "rugby": {"sofascore-web"},
    "mma": {"sofascore-web"},
}
SOURCE_NATIVE_PUBLIC_FAMILIES = set().union(*SOURCE_NATIVE_PUBLIC_FAMILIES_BY_SPORT.values())


def _native_sport_id(value: str) -> str:
    sport = str(value or "").strip().lower()
    return {"soccer": "football", "waterpolo": "water-polo"}.get(sport, sport)


def source_native_public_competition_id(
    *,
    stored_competition_id: str,
    source_competition_name: Optional[str],
    sport_id: str,
    source_family: str,
) -> Optional[str]:
    """Allow only explicitly trusted source-native competition identities."""
    stored = str(stored_competition_id or "").strip()
    name = str(source_competition_name or "").strip()
    family = str(source_family or "").strip()
    sport = _native_sport_id(sport_id)
    allowed = SOURCE_NATIVE_PUBLIC_FAMILIES_BY_SPORT.get(sport) or set()
    if family not in allowed or not name or not stored:
        return None

    suffix = slugify(name)
    if not suffix:
        return None

    if sport == "football":
        native = f"football-{suffix}"
        country_qualified = bool(re.fullmatch(rf"football-[a-z]{{2,3}}-{re.escape(suffix)}", stored))
        provider_qualified = bool(
            stored.startswith("football-")
            and suffix in stored
            and re.search(r"-t[a-z0-9]+$", stored)
        )
        if stored != native and not country_qualified and not provider_qualified:
            return None
        canonical = unique_label_competition(name, sport_id="football", exclude=stored)
        return canonical or stored

    if not stored.startswith(f"{sport}-"):
        return None
    if family == "sofascore-web":
        if suffix not in stored or not re.search(r"-t[a-z0-9]+$", stored):
            return None
    elif family == "sportscore":
        if not re.fullmatch(rf"{re.escape(sport)}-ss-[a-f0-9]{{10}}-[a-z0-9-]+", stored):
            return None
    elif suffix not in stored:
        return None

    canonical = unique_label_competition(name, sport_id=sport, exclude=stored)
    return canonical or stored


# Adapter families that bind events to a frozen mapping id themselves.
# Series/league labels from those feeds are not hub competition identity.
MAPPING_OWNED_FAMILIES = {
    "opendota",
    "cricsheet",
    "click-tt-remix",
    "dataproject-web",
    "euroleague-live",
    "squiggle-afl",
    "pulselive",
    "cfl-scoreboard-json",
    "pga-graphql",
    "championdata-netball",
    "lolesports-json",
    "gri-web",
}

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
    "england-premier-league": {
        "any": ["english premier"],
        "bounded": {"premier league": ["england", "english", "barclays"]},
        "deny": ["women"],
    },
    "england-championship": {
        "any": ["sky bet championship", "efl championship"],
        "bounded": {"championship": ["england", "english", "sky", "bet", "efl"]},
        "deny": ["australian", "usl", "women"],
    },
    "england-league-one": {
        "any": ["sky bet league one"],
        "bounded": {"league one": ["england", "english", "sky", "bet", "efl"]},
        "deny": ["scottish", "scotland"],
    },
    "england-league-two": {
        "any": ["sky bet league two"],
        "bounded": {"league two": ["england", "english", "sky", "bet", "efl"]},
        "deny": ["scottish", "scotland"],
    },
    "scotland-premiership": {"any": ["scottish premiership", "cinch premiership"]},
    "womens-super-league": {"any": ["women's super league", "womens super league", "barclays wsl", " wsl"]},
    "uefa-europa-league": {"any": ["europa league", "uefa europa"]},
    "uefa-conference-league": {"any": ["conference league", "uefa conference", "europa conference"]},
    "uefa-nations-league": {"any": ["uefa nations league"], "bounded": {"nations league": ["uefa", "europe", "european"]}, "deny": ["concacaf"]},
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


def _leftover_tokens(blob: str, phrase: str) -> List[str]:
    leftover = blob.replace(phrase, " ")
    return [token for token in _WORD_RE.findall(leftover) if token not in _STOPWORDS]


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
        for phrase, allow in (spec.get("bounded") or {}).items():
            needle = phrase.lower()
            if needle in blob:
                allow_set = {item.lower() for item in allow}
                leftover = _leftover_tokens(blob, needle)
                if leftover and all(token in allow_set for token in leftover):
                    return True
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


def _canonical_same_sport(competition_id: str, sport_id: str = "") -> bool:
    if not sport_id:
        return True
    from collector.matrix_guard import frozen_competition_sports

    canonical_sport = frozen_competition_sports().get(str(competition_id or ""))
    return not canonical_sport or canonical_sport == sport_id


def labeled_competition_ids(sport_id: str = "") -> Dict[str, str]:
    from collector.verified_coverage import OPENLIGADB_LEAGUES, THESPORTSDB_LEAGUES

    ids = {
        key: ""
        for key in COMPETITION_LABELS
        if _canonical_same_sport(key, sport_id)
    }
    for row in list(OPENLIGADB_LEAGUES) + list(THESPORTSDB_LEAGUES):
        if sport_id and row.get("sport_id") and row.get("sport_id") != sport_id:
            continue
        if not _canonical_same_sport(row["competition_id"], sport_id):
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
    if mapped_from_id and not _canonical_same_sport(mapped_from_id, sport_id):
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "suggested_competition_id": mapped_from_id,
            "resolution_method": "rejected_source_id_other_sport",
            "resolution_confidence": 0,
            "accepted": False,
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
    hub = source_family in {"bbc-sport", "sportscore", "espn-html"}
    owned = source_family in MAPPING_OWNED_FAMILIES
    if independent_name and label_matches_competition(name, mapping_competition_id):
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "source_label",
            "resolution_confidence": 90,
            "accepted": True,
        }
    other = unique_label_competition(name, sport_id=sport_id, exclude=mapping_competition_id) if independent_name else None
    if other and not owned:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "suggested_competition_id": other,
            "resolution_method": "rejected_label_other_competition",
            "resolution_confidence": 0,
            "accepted": False,
        }
    if not independent_name and not source_competition_id:
        return {
            **base,
            "canonical_competition_id": mapping_competition_id,
            "resolution_method": "mapping_unlabeled",
            "resolution_confidence": 40,
            "accepted": not hub,
        }
    if independent_name and not label_matches_competition(name, mapping_competition_id):
        if owned:
            return {
                **base,
                "canonical_competition_id": mapping_competition_id,
                "resolution_method": "mapping_request_trusted",
                "resolution_confidence": 55,
                "accepted": True,
            }
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


def correct_public_competition_id(
    *,
    stored_competition_id: str,
    source_competition_name: Optional[str] = None,
    sport_id: str = "",
    source_family: str = "",
) -> Optional[str]:
    """Return a safe public competition id, including trusted source-native competitions."""
    from collector.matrix_guard import frozen_competition_ids

    stored = str(stored_competition_id or "").strip()
    name = str(source_competition_name or "").strip()
    frozen = frozen_competition_ids()
    family = str(source_family or "").strip()

    native = source_native_public_competition_id(
        stored_competition_id=stored,
        source_competition_name=name,
        sport_id=sport_id,
        source_family=family,
    )
    if native:
        return native

    if not name:
        return stored if stored in frozen or stored in OFFICIAL_PUBLIC_COMPETITIONS else None
    # FotMob frozen IDs come only from our explicit league-id map. Keep that
    # canonical identity even when the upstream display label is generic.
    if family in {"fotmob", "sofascore-web"} and stored in frozen:
        return stored
    if stored and label_matches_competition(name, stored):
        return stored if stored in frozen or stored in OFFICIAL_PUBLIC_COMPETITIONS else None

    if family in SOURCE_NATIVE_PUBLIC_FAMILIES:
        if stored == "fifa-connected-competitions":
            return stored
        matches = [
            cid
            for cid in frozen
            if cid != stored
            and _canonical_same_sport(cid, sport_id)
            and label_matches_competition(name, cid)
        ]
        return matches[0] if len(matches) == 1 else None

    if family in MAPPING_OWNED_FAMILIES or family in {
        "caf-web",
        "fivb-web",
        "ehf-web",
        "nascar-web",
        "arca-web",
        "nz-football",
    }:
        return stored if stored in frozen or stored in OFFICIAL_PUBLIC_COMPETITIONS else None
    matches = [
        cid
        for cid in frozen
        if cid != stored
        and _canonical_same_sport(cid, sport_id)
        and label_matches_competition(name, cid)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


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
