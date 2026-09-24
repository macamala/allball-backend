"""One-time safe repair for recent football rows hidden by an over-broad quality gate."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy.orm import Session

from collector.enrichment import is_display_eligible, quality_flags_for_event
from collector.models import SportsEvent
from collector.util import dump_json, load_json

_ran = False


def repair_recent_football_visibility(db: Session) -> Dict[str, int]:
    global _ran
    if _ran:
        return {"scanned": 0, "restored": 0, "still_hidden": 0}
    _ran = True

    now = datetime.utcnow()
    lower = now - timedelta(days=3)
    upper = now + timedelta(days=3)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.start_time >= lower,
            SportsEvent.start_time <= upper,
            SportsEvent.display_eligible.is_(False),
        )
        .all()
    )

    stats = {"scanned": 0, "restored": 0, "still_hidden": 0}
    for row in rows:
        stats["scanned"] += 1
        participants = load_json(row.participants_json, {}) or {}
        score = load_json(row.score_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        event = {
            "sport": row.sport_id,
            "home": participants.get("home") or {},
            "away": participants.get("away") or {},
            "participant_a": participants.get("participant_a") or {},
            "participant_b": participants.get("participant_b") or {},
            "score": score,
        }
        flags = quality_flags_for_event(event)
        eligible = is_display_eligible(event)
        extra["quality_flags"] = flags
        if eligible:
            row.display_eligible = True
            extra["display_eligible"] = True
            row.extra_json = dump_json(extra)
            stats["restored"] += 1
        else:
            stats["still_hidden"] += 1
            if extra.get("display_eligible") is not False:
                extra["display_eligible"] = False
                row.extra_json = dump_json(extra)

    if stats["restored"]:
        db.commit()
    else:
        db.flush()
    return stats
