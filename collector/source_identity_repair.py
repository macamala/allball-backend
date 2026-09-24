"""Repair source-family taxonomy leakage and obvious provider text contamination.

All rules are intentionally source-scoped. They never apply globally and they
never change a legitimate event merely because an asset is missing.
"""

from __future__ import annotations

import re
from typing import Any, Dict

from sqlalchemy.orm import Session

from collector.models import SportsEvent
from collector.util import dump_json, load_json

_ran = False

# These phrases are structural page/UI/article fragments observed in the named
# source families. Rules are deliberately narrow and source-scoped.
_SOURCE_JUNK = {
    "golmates-web": re.compile(
        r"(?:\ben vivo\b|\bfinal\b|\bse impone\b|\bgol de\b|\bpartido\b|"
        r"\bbrasileir[aã]o\b|\bliga\s*1\b|\bcopa chile\b)",
        re.I,
    ),
    "ultimate-rugby": re.compile(
        r"(?:^sep\s+\d{1,2}\b|\bat stadium\b|\b\d{1,2}(?:st|nd|rd|th) sep\b|"
        r"\brugby wxv\b|\bglobal fixtures\b|\battack\b|\bdefence\b)",
        re.I,
    ),
    "varzesh3-web": re.compile(
        r"(?:\d+\s*-\s*\d+|مرحله|گروه|فینال|چهارشنبه|شنبه|یکشنبه|جام جهانی|لیگ ملت)",
        re.I,
    ),
    "concacaf-web": re.compile(
        r"(?:\bgroup stage\b|\bcentral american cup\b|\bcaribbean cup\b|"
        r"\bsemifinals?\b|\bfirst leg\b|\bfinal spot\b|\bpoints in group\b|\bhighlights?\b)",
        re.I,
    ),
    "lnh-web": re.compile(
        r"(?:\bproligue\b|\bstarligue\b|\bligue\s*-\s*j\d+\b|\bj\d+\b.*\b(?:ven|sam|dim)\.|"
        r"\b\d{1,2}h\d{2}\b|\bsuspense\b)",
        re.I,
    ),
    "dfb-web": re.compile(r"(?:mehr anzeigen|gewinnspiel|georgien)", re.I),
}


def _side_name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("display_name") or side.get("name") or "").strip()
    return str(side or "").strip()


def _is_obvious_source_junk(source_family: str, name: str) -> bool:
    pattern = _SOURCE_JUNK.get(source_family)
    if not pattern or not name:
        return False
    return bool(pattern.search(name))


def repair_source_identity_leaks(db: Session) -> Dict[str, Any]:
    global _ran
    if _ran:
        return {"scanned": 0, "quarantined": 0, "by_reason": {}}
    _ran = True

    rows = db.query(SportsEvent).filter(SportsEvent.display_eligible.is_(True)).all()
    scanned = quarantined = 0
    by_reason: Dict[str, int] = {}

    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        source_family = str(extra.get("source_family") or "").strip().lower()
        participants = load_json(row.participants_json, {}) or {}
        home = _side_name(participants.get("home"))
        away = _side_name(participants.get("away"))
        reason = ""

        # A UFC source can only create MMA/combat data. Historical rows that
        # landed in Dota/unknown are taxonomy leakage, not esports.
        if source_family == "ufc-web" and str(row.sport_id or "") != "mma":
            reason = "ufc_source_wrong_sport"
        elif source_family in _SOURCE_JUNK and (
            _is_obvious_source_junk(source_family, home)
            or _is_obvious_source_junk(source_family, away)
        ):
            reason = f"{source_family}_text_contamination"

        if not reason:
            continue

        scanned += 1
        flags = list(extra.get("quality_flags") or [])
        if reason not in flags:
            flags.append(reason)
        extra["quality_flags"] = flags
        extra["display_eligible"] = False
        row.extra_json = dump_json(extra)
        row.display_eligible = False
        quarantined += 1
        by_reason[reason] = by_reason.get(reason, 0) + 1

    if quarantined:
        db.commit()
        from collector.cache import cache_clear

        cache_clear(db, prefix="events:")
    else:
        db.flush()
    return {"scanned": scanned, "quarantined": quarantined, "by_reason": by_reason}
