"""Identity-asset coverage audit for Live Scores.

A competition is not asset-complete until:
- domestic competition geography can render a country flag,
- the competition has a real logo,
- every observed team/club participant in team-style events has a real logo.

This is an internal audit surface only. It does not invent or synthesize artwork.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

from collector.competition_presentation import metadata_for
from collector.models import SportsEvent
from collector.util import load_json

TEAM_FAMILIES = {"team_match", "esports_match"}
INDIVIDUAL_FAMILIES = {"individual_match", "combat"}


def _participant_key(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    return str(
        side.get("id")
        or side.get("slug")
        or side.get("display_name")
        or side.get("name")
        or ""
    ).strip().lower()


def _participant_name(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    return str(side.get("display_name") or side.get("name") or "").strip()


def _has_country(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return bool(
        side.get("country_id")
        or side.get("country")
        or side.get("nationality")
        or [value for value in (side.get("country_ids") or []) if value]
    )


def _has_logo(side: Any) -> bool:
    if not isinstance(side, dict):
        return False
    return bool(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or side.get("logo_url")
        or side.get("logoUrl")
        or side.get("image_url")
        or side.get("imageUrl")
        or side.get("emblem")
        or side.get("icon")
    )


def asset_coverage_payload(db) -> Dict[str, Any]:
    rows = (
        db.query(
            SportsEvent.sport_id,
            SportsEvent.competition_id,
            SportsEvent.event_family,
            SportsEvent.country_id,
            SportsEvent.participants_json,
            SportsEvent.extra_json,
        )
        .filter(SportsEvent.display_eligible.is_(True))
        .all()
    )

    comps: Dict[str, Dict[str, Any]] = {}
    participant_seen = defaultdict(dict)
    individual_seen = defaultdict(dict)

    for row in rows:
        sport_id = str(row.sport_id or "")
        competition_id = str(row.competition_id or "")
        key = f"{sport_id}:{competition_id}"
        meta = metadata_for(competition_id, sport_id)
        extra = load_json(row.extra_json, {}) or {}
        participants = load_json(row.participants_json, {}) or {}

        item = comps.setdefault(
            key,
            {
                "sport": sport_id,
                "competition": competition_id,
                "scope_type": meta.get("scope_type") or "",
                "country_id": meta.get("country_code") or row.country_id or None,
                "country_flag_required": (meta.get("scope_type") == "DOMESTIC"),
                "competition_logo_present": False,
                "observed_team_participants": 0,
                "team_participants_with_logo": 0,
                "team_participants_with_identity": 0,
                "missing_participants": [],
                "observed_individual_participants": 0,
                "individual_participants_with_country": 0,
                "missing_country_participants": [],
            },
        )

        if meta.get("logo") or extra.get("competition_logo"):
            item["competition_logo_present"] = True

        family = str(row.event_family or "")
        if family in TEAM_FAMILIES:
            for side_name in ("home", "away", "participant_a", "participant_b"):
                side = participants.get(side_name)
                participant_key = _participant_key(side)
                name = _participant_name(side)
                if not participant_key or not name or name.upper() == "TBD":
                    continue
                bucket = participant_seen[key]
                current = bucket.get(participant_key) or {
                    "name": name,
                    "logo": False,
                    "country": False,
                    "sources": set(),
                }
                current["logo"] = current["logo"] or _has_logo(side)
                current["country"] = current["country"] or _has_country(side)
                source_family = str(extra.get("source_family") or "unknown")
                if source_family:
                    current.setdefault("sources", set()).add(source_family)
                bucket[participant_key] = current
        elif family in INDIVIDUAL_FAMILIES:
            for side_name in ("home", "away", "participant_a", "participant_b"):
                side = participants.get(side_name)
                participant_key = _participant_key(side)
                name = _participant_name(side)
                if not participant_key or not name or name.upper() == "TBD":
                    continue
                bucket = individual_seen[key]
                current = bucket.get(participant_key) or {"name": name, "country": False, "sources": set()}
                current["country"] = current["country"] or _has_country(side)
                source_family = str(extra.get("source_family") or "unknown")
                if source_family:
                    current.setdefault("sources", set()).add(source_family)
                bucket[participant_key] = current

    output = []
    for key, item in comps.items():
        participants = participant_seen.get(key, {})
        item["observed_team_participants"] = len(participants)
        item["team_participants_with_logo"] = sum(1 for row in participants.values() if row["logo"])
        non_domestic = str(item.get("scope_type") or "").upper() in {
            "WORLD", "INTERNATIONAL", "CONTINENTAL", "REGIONAL"
        }
        item["team_participants_with_identity"] = sum(
            1
            for row in participants.values()
            if row["logo"] or (non_domestic and row.get("country"))
        )
        missing_team_rows = [
            row
            for row in participants.values()
            if not row["logo"] and not (non_domestic and row.get("country"))
        ]
        item["missing_participants"] = [row["name"] for row in missing_team_rows][:200]
        team_source_counts: Dict[str, int] = {}
        for row in missing_team_rows:
            for source in row.get("sources") or {"unknown"}:
                team_source_counts[source] = team_source_counts.get(source, 0) + 1
        item["missing_participant_sources"] = dict(
            sorted(team_source_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        item["country_flag_present"] = bool(item["country_id"]) if item["country_flag_required"] else True
        item["participant_logos_complete"] = (
            item["observed_team_participants"] == item["team_participants_with_identity"]
        )
        individuals = individual_seen.get(key, {})
        item["observed_individual_participants"] = len(individuals)
        item["individual_participants_with_country"] = sum(
            1 for row in individuals.values() if row["country"]
        )
        missing_individual_rows = [row for row in individuals.values() if not row["country"]]
        item["missing_country_participants"] = [row["name"] for row in missing_individual_rows][:200]
        individual_source_counts: Dict[str, int] = {}
        for row in missing_individual_rows:
            for source in row.get("sources") or {"unknown"}:
                individual_source_counts[source] = individual_source_counts.get(source, 0) + 1
        item["missing_country_sources"] = dict(
            sorted(individual_source_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        item["participant_flags_complete"] = (
            item["observed_individual_participants"] == item["individual_participants_with_country"]
        )
        item["asset_complete"] = bool(
            item["country_flag_present"]
            and item["competition_logo_present"]
            and item["participant_logos_complete"]
            and item["participant_flags_complete"]
        )
        output.append(item)

    output.sort(key=lambda row: (row["asset_complete"], row["sport"], row["competition"]))
    by_sport: Dict[str, Dict[str, int]] = {}
    for row in output:
        sport = str(row.get("sport") or "unknown")
        bucket = by_sport.setdefault(
            sport,
            {
                "competitions": 0,
                "asset_complete": 0,
                "missing_competition_logo": 0,
                "missing_required_country_flag": 0,
                "team_participants_missing_logo": 0,
                "individual_participants_missing_country": 0,
            },
        )
        bucket["competitions"] += 1
        bucket["asset_complete"] += int(bool(row.get("asset_complete")))
        bucket["missing_competition_logo"] += int(not row.get("competition_logo_present"))
        bucket["missing_required_country_flag"] += int(
            bool(row.get("country_flag_required")) and not row.get("country_flag_present")
        )
        bucket["team_participants_missing_logo"] += max(
            0,
            int(row.get("observed_team_participants") or 0)
            - int(row.get("team_participants_with_identity") or row.get("team_participants_with_logo") or 0),
        )
        bucket["individual_participants_missing_country"] += max(
            0,
            int(row.get("observed_individual_participants") or 0)
            - int(row.get("individual_participants_with_country") or 0),
        )

    summary = {
        "competitions": len(output),
        "asset_complete": sum(1 for row in output if row["asset_complete"]),
        "missing_competition_logo": sum(1 for row in output if not row["competition_logo_present"]),
        "missing_required_country_flag": sum(
            1 for row in output if row["country_flag_required"] and not row["country_flag_present"]
        ),
        "observed_team_participants": sum(row["observed_team_participants"] for row in output),
        "team_participants_with_logo": sum(row["team_participants_with_logo"] for row in output),
        "team_participants_with_identity": sum(row["team_participants_with_identity"] for row in output),
        "competitions_with_participant_logo_gaps": sum(
            1 for row in output if not row["participant_logos_complete"]
        ),
        "observed_individual_participants": sum(row["observed_individual_participants"] for row in output),
        "individual_participants_with_country": sum(row["individual_participants_with_country"] for row in output),
        "competitions_with_participant_flag_gaps": sum(
            1 for row in output if not row["participant_flags_complete"]
        ),
        "by_sport": by_sport,
    }
    return {"summary": summary, "competitions": output}



def visible_asset_gap_snapshot(db, *, past_hours: int = 6, future_hours: int = 72, limit: int = 80) -> Dict[str, Any]:
    """Source-aware identity gaps for events users are likely to see now/next."""
    lower = datetime.utcnow() - timedelta(hours=past_hours)
    upper = datetime.utcnow() + timedelta(hours=future_hours)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.display_eligible.is_(True),
            SportsEvent.start_time >= lower,
            SportsEvent.start_time <= upper,
        )
        .order_by(SportsEvent.start_time.asc())
        .all()
    )
    gaps = []
    summary: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "events": 0,
            "missing_competition_logo": 0,
            "missing_team_logo_slots": 0,
            "missing_individual_country_slots": 0,
        }
    )
    for row in rows:
        sport = str(row.sport_id or "unknown")
        family = str(row.event_family or "")
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
        away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
        comp_missing = not bool(extra.get("competition_logo"))
        missing_sides = []
        missing_countries = []
        for label, side in (("home", home), ("away", away)):
            if not side or not _participant_name(side):
                continue
            if family in TEAM_FAMILIES and not _has_logo(side):
                missing_sides.append(label)
            if family in INDIVIDUAL_FAMILIES and not _has_country(side):
                missing_countries.append(label)

        bucket = summary[sport]
        bucket["events"] += 1
        bucket["missing_competition_logo"] += int(comp_missing)
        bucket["missing_team_logo_slots"] += len(missing_sides)
        bucket["missing_individual_country_slots"] += len(missing_countries)

        if not (comp_missing or missing_sides or missing_countries):
            continue
        gaps.append(
            {
                "event_id": row.event_id,
                "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
                "sport": sport,
                "competition": row.competition_id,
                "family": family,
                "primary_source": row.primary_source_id,
                "source_family": extra.get("source_family"),
                "source_competition_id": extra.get("source_competition_id"),
                "source_competition_entity_kind": extra.get("source_competition_entity_kind"),
                "competition_logo": bool(extra.get("competition_logo")),
                "home": {
                    "name": _participant_name(home),
                    "id": home.get("id"),
                    "logo": bool(_has_logo(home)),
                    "country": home.get("country_id") or home.get("country"),
                },
                "away": {
                    "name": _participant_name(away),
                    "id": away.get("id"),
                    "logo": bool(_has_logo(away)),
                    "country": away.get("country_id") or away.get("country"),
                },
                "missing_team_logo_sides": missing_sides,
                "missing_individual_country_sides": missing_countries,
            }
        )

    gaps.sort(
        key=lambda row: (
            -len(row.get("missing_team_logo_sides") or []),
            -len(row.get("missing_individual_country_sides") or []),
            -int(not row.get("competition_logo")),
            str(row.get("start_time") or ""),
        )
    )
    return {
        "from": lower.isoformat() + "Z",
        "to": upper.isoformat() + "Z",
        "summary": dict(summary),
        "gaps": gaps[:limit],
    }
