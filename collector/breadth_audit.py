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
    def pack(row: SportsEvent) -> Dict[str, Any]:
        sides = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        home = (sides.get("home") or {}).get("name") if isinstance(sides.get("home"), dict) else sides.get("home")
        away = (sides.get("away") or {}).get("name") if isinstance(sides.get("away"), dict) else sides.get("away")
        return {
            "competition": row.competition_id,
            "home": home,
            "away": away,
            "home_id": (sides.get("home") or {}).get("id") if isinstance(sides.get("home"), dict) else None,
            "away_id": (sides.get("away") or {}).get("id") if isinstance(sides.get("away"), dict) else None,
            "country_id": row.country_id,
            "utc": row.start_time.isoformat() + "Z" if row.start_time else None,
            "eligible": getattr(row, "display_eligible", True) is not False,
            "primary_source": row.primary_source_id,
            "source_family": extra.get("source_family"),
            "source_competition_id": extra.get("source_competition_id"),
            "source_competition_name": extra.get("source_competition_name"),
            "quality_flags": extra.get("quality_flags") or [],
            "resolution_method": extra.get("resolution_method"),
            "resolution_confidence": extra.get("resolution_confidence"),
        }

    events = [pack(row) for row in eligible[:160]]
    hidden = [pack(row) for row in rows if getattr(row, "display_eligible", True) is False][:160]

    return {
        "local_date": day.isoformat(),
        "utc_from": utc_start.isoformat() + "Z",
        "utc_to": utc_end.isoformat() + "Z",
        "total": len(eligible),
        "all_rows": len(rows),
        "hidden_count": len(rows) - len(eligible),
        "competitions": dict(competitions.most_common()),
        "events": events,
        "hidden": hidden,
    }



def tomorrow_public_football_snapshot() -> Dict[str, Any]:
    from collector.provider import NinkoCollectedSportsDataProvider

    now_local = datetime.now(timezone.utc).astimezone(SYDNEY)
    day = now_local.date() + timedelta(days=1)
    local_start = datetime.combine(day, datetime.min.time(), tzinfo=SYDNEY)
    local_end = local_start + timedelta(days=1)
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    provider = NinkoCollectedSportsDataProvider()
    events = provider.get_events(
        sport="football",
        date_from=utc_start.isoformat().replace("+00:00", "Z"),
        date_to=utc_end.isoformat().replace("+00:00", "Z"),
        allow_unfiltered=True,
    )
    competitions = Counter(str(row.get("competition_name") or row.get("competition") or row.get("competition_key") or "") for row in events)
    sample = [
        {
            "competition": row.get("competition_name") or row.get("competition"),
            "competition_key": row.get("competition_key"),
            "home": (row.get("home") or {}).get("name"),
            "away": (row.get("away") or {}).get("name"),
            "utc": row.get("start_time"),
        }
        for row in events[:160]
    ]
    return {
        "local_date": day.isoformat(),
        "total": len(events),
        "competitions": dict(competitions.most_common()),
        "events": sample,
    }



def fifa_competition_samples() -> List[Dict[str, Any]]:
    from collector.adapters_feeds import loc
    from collector.http import fetch_url

    result = fetch_url("https://api.fifa.com/api/v3/calendar/matches?count=100&language=en")
    payload = result.payload if getattr(result, "ok", False) and isinstance(result.payload, dict) else {}
    out: List[Dict[str, Any]] = []
    for row in payload.get("Results") or []:
        if not isinstance(row, dict):
            continue
        name = ""
        raw_name = row.get("CompetitionName")
        if isinstance(raw_name, list) and raw_name:
            first = raw_name[0]
            name = str((first or {}).get("Description") or (first or {}).get("Name") or "") if isinstance(first, dict) else str(first)
        elif isinstance(raw_name, dict):
            name = str(raw_name.get("Description") or raw_name.get("Name") or "")
        else:
            name = str(raw_name or "")
        if name not in {"Ligue 1", "Premier League", "Concacaf Nations League", "UEFA Nations League"}:
            continue
        compact = {"CompetitionName": name}
        for key, value in row.items():
            lower = key.lower()
            if any(token in lower for token in ("country", "competition", "association", "confeder", "federation")):
                compact[key] = value
        home = row.get("HomeTeam") or {}
        away = row.get("AwayTeam") or {}
        compact["home"] = loc(home.get("TeamName")) if isinstance(home, dict) else ""
        compact["away"] = loc(away.get("TeamName")) if isinstance(away, dict) else ""
        out.append(compact)
        if len(out) >= 12:
            break
    return out
