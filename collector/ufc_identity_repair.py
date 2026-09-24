"""Source-scoped cleanup for UFC promo text misparsed as fighters."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from collector.models import SportsEvent
from collector.rich_closure import _valid_ufc_fighter_name
from collector.util import dump_json, load_json

_ran = False


def repair_ufc_promo_rows(db: Session) -> Dict[str, int]:
    global _ran
    if _ran:
        return {"scanned": 0, "quarantined": 0}
    _ran = True

    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "mma",
            SportsEvent.competition_id == "ufc",
            SportsEvent.display_eligible.is_(True),
        )
        .all()
    )
    scanned = quarantined = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        source_family = str(extra.get("source_family") or "").strip().lower()
        if source_family != "ufc-web":
            continue
        scanned += 1
        participants = load_json(row.participants_json, {}) or {}
        home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
        away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
        home_name = str(home.get("name") or "").strip()
        away_name = str(away.get("name") or "").strip()
        if _valid_ufc_fighter_name(home_name) and _valid_ufc_fighter_name(away_name):
            continue
        flags = list(extra.get("quality_flags") or [])
        if "ufc_promo_text_contamination" not in flags:
            flags.append("ufc_promo_text_contamination")
        extra["quality_flags"] = flags
        extra["display_eligible"] = False
        row.extra_json = dump_json(extra)
        row.display_eligible = False
        quarantined += 1

    if quarantined:
        db.commit()
        from collector.cache import cache_clear

        cache_clear(db, prefix="events:")
    else:
        db.flush()
    return {"scanned": scanned, "quarantined": quarantined}
