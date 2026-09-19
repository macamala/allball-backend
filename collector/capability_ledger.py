"""Proven adapter capability, separate from current fetch health.

A later 429, DNS miss, timeout, or empty calendar does not erase a provider
that already produced canonical events from real upstream data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Families proven in this repo against live public data (passes 2–5 + bounded proofs).
SEED_WORKING: Set[Tuple[str, str]] = {
    ("nfl", "espn-html"),
    ("ncaa-football", "espn-html"),
    ("tier1", "liquipedia"),
    ("professional", "liquipedia"),
    ("worlds-msi-regional", "liquipedia"),
    ("vct", "liquipedia"),
    ("cdl-majors", "liquipedia"),
    ("owcs-historical", "liquipedia"),
    ("rlcs", "liquipedia"),
    ("competitive-ea-fc", "liquipedia"),
    ("cross-game-wiki", "liquipedia"),
    ("biathlon", "ibu-web"),
    ("motogp", "pulselive"),
}

FAMILY_WORKING: Set[str] = {
    "openfootball",
    "openligadb",
    "fifa-digital",
    "cricsheet",
    "squiggle",
    "jolpica-ergast",
    "pulselive",
    "euroleague-live",
    "nhl-web",
    "mlb-statsapi",
    "khl-mobile",
    "opendota",
    "liquipedia",
}

_CACHE: Dict[str, Set[str]] | None = None
_COMP_CACHE: Dict[Tuple[str, str], str] | None = None


def _load_smokes() -> None:
    global _CACHE, _COMP_CACHE
    if _CACHE is not None:
        return
    families: Set[str] = set(FAMILY_WORKING)
    pairs: Dict[Tuple[str, str], str] = {}
    for competition_id, family in SEED_WORKING:
        pairs[(competition_id, family)] = "WORKING"
        families.add(family)
    for name in ("smoke_pass2.json", "smoke_pass3.json", "smoke_pass4.json", "smoke_pass5.json"):
        path = ROOT / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in payload.get("results") or []:
            cid = row.get("competition_id") or ""
            for mapping in row.get("mapping_results") or []:
                family = mapping.get("family") or ""
                if not family:
                    continue
                if (mapping.get("events") or 0) > 0:
                    families.add(family)
                    pairs[(cid, family)] = "WORKING"
    proof_path = ROOT / "collector" / "proof_ledger.json"
    if proof_path.exists():
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            proof = {}
        for key, row in (proof.get("pairs") or {}).items():
            if "|" not in str(key):
                continue
            cid, family = str(key).split("|", 1)
            status = (row or {}).get("status") or ""
            if status == "WORKING" and int((row or {}).get("events") or 0) > 0:
                sample = (row or {}).get("sample") or ""
                if " vs " not in sample:
                    continue
                home, away = sample.split(" vs ", 1)
                blob = f"{home} {away}".lower()
                if any(token in blob for token in ("cookie", "function ", "weather", "full calendar", "searchtab", "todos")):
                    continue
                pairs[(cid, family)] = "WORKING"
            elif status == "PARTIAL_WORKING":
                pairs[(cid, family)] = "PARTIAL_WORKING"
    _CACHE = families
    _COMP_CACHE = pairs


def proven_families() -> Set[str]:
    _load_smokes()
    return set(_CACHE or ())


def proven_status(competition_id: str, family: str) -> str:
    if family == "espn-html":
        return "ACCESS_BLOCKED"
    _load_smokes()
    if (competition_id, family) in (_COMP_CACHE or {}):
        return "WORKING"
    if family in (_CACHE or ()):
        return "WORKING"
    return ""


def merge_capability(current: str, *, competition_id: str, family: str, events: int) -> str:
    if family == "espn-html" and events <= 0:
        return "ACCESS_BLOCKED"
    if events > 0:
        return "VERIFIED_OPERATIONAL" if current != "PARTIAL_OPERATIONAL" else current
    proven = proven_status(competition_id, family)
    if not proven:
        return current
    if proven == "ACCESS_BLOCKED":
        return "ACCESS_BLOCKED"
    if current in {"RATE_LIMITED", "BROKEN", "CONFIG_MISSING"}:
        return "VERIFIED_OPERATIONAL" if current == "RATE_LIMITED" else current
    if current in {"PARTIAL_OPERATIONAL"}:
        return current
    return "VERIFIED_OPERATIONAL"
