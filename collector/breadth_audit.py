"""Small production breadth diagnostics for the livescore worker."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from collector.models import SportsEvent
from collector.util import load_json

SYDNEY = ZoneInfo("Australia/Sydney")


def tomorrow_football_snapshot(db) -> Dict[str, Any]:
    now_local = datetime.now(timezone.utc).astimezone(SYDNEY)
    day = now_local.date() + timedelta(days=1)
    local_start = datetime.combine(day, datetime.min.time(), tzinfo=SYDNEY)
    local_end = local_start + timedelta(days=1)
    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    rows: List[SportsEvent] = (
        db.query(SportsEvent)
        .filter(SportsEvent.sport_id == "football")
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.start_time >= utc_start)
        .filter(SportsEvent.start_time < utc_end)
        .order_by(SportsEvent.start_time.asc())
        .all()
    )

    eligible = [row for row in rows if getattr(row, "display_eligible", True) is not False]
    competitions = Counter(row.competition_id for row in eligible)
    events = []
    for row in eligible[:160]:
        sides = load_json(row.participants_json, {}) or {}
        home = (sides.get("home") or {}).get("name") if isinstance(sides.get("home"), dict) else sides.get("home")
        away = (sides.get("away") or {}).get("name") if isinstance(sides.get("away"), dict) else sides.get("away")
        events.append(
            {
                "competition": row.competition_id,
                "home": home,
                "away": away,
                "utc": row.start_time.isoformat() + "Z" if row.start_time else None,
            }
        )

    return {
        "local_date": day.isoformat(),
        "utc_from": utc_start.isoformat() + "Z",
        "utc_to": utc_end.isoformat() + "Z",
        "total": len(eligible),
        "all_rows": len(rows),
        "competitions": dict(competitions.most_common()),
        "events": events,
    }
