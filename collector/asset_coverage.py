"""Identity-asset coverage audit for Live Scores.

A competition is not asset-complete until:
- domestic competition geography can render a country flag,
- the competition has a real logo,
- every observed team/club participant in team-style events has a real logo.

This is an internal audit surface only. It does not invent or synthesize artwork.
"""

from __future__ import annotations

from collections import defaultdict
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
    return bool(side.get("country_id") or side.get("country") or side.get("nationality"))


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
                current = bucket.get(participant_key) or {"name": name, "logo": False}
                current["logo"] = current["logo"] or _has_logo(side)
                bucket[participant_key] = current
        elif family in INDIVIDUAL_FAMILIES:
            for side_name in ("home", "away", "participant_a", "participant_b"):
                side = participants.get(side_name)
                participant_key = _participant_key(side)
                name = _participant_name(side)
                if not participant_key or not name or name.upper() == "TBD":
                    continue
                bucket = individual_seen[key]
                current = bucket.get(participant_key) or {"name": name, "country": False}
                current["country"] = current["country"] or _has_country(side)
                bucket[participant_key] = current

    output = []
    for key, item in comps.items():
        participants = participant_seen.get(key, {})
        item["observed_team_participants"] = len(participants)
        item["team_participants_with_logo"] = sum(1 for row in participants.values() if row["logo"])
        item["missing_participants"] = [
            row["name"] for row in participants.values() if not row["logo"]
        ][:200]
        item["country_flag_present"] = bool(item["country_id"]) if item["country_flag_required"] else True
        item["participant_logos_complete"] = (
            item["observed_team_participants"] == item["team_participants_with_logo"]
        )
        individuals = individual_seen.get(key, {})
        item["observed_individual_participants"] = len(individuals)
        item["individual_participants_with_country"] = sum(
            1 for row in individuals.values() if row["country"]
        )
        item["missing_country_participants"] = [
            row["name"] for row in individuals.values() if not row["country"]
        ][:200]
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
    summary = {
        "competitions": len(output),
        "asset_complete": sum(1 for row in output if row["asset_complete"]),
        "missing_competition_logo": sum(1 for row in output if not row["competition_logo_present"]),
        "missing_required_country_flag": sum(
            1 for row in output if row["country_flag_required"] and not row["country_flag_present"]
        ),
        "observed_team_participants": sum(row["observed_team_participants"] for row in output),
        "team_participants_with_logo": sum(row["team_participants_with_logo"] for row in output),
        "competitions_with_participant_logo_gaps": sum(
            1 for row in output if not row["participant_logos_complete"]
        ),
        "observed_individual_participants": sum(row["observed_individual_participants"] for row in output),
        "individual_participants_with_country": sum(row["individual_participants_with_country"] for row in output),
        "competitions_with_participant_flag_gaps": sum(
            1 for row in output if not row["participant_flags_complete"]
        ),
    }
    return {"summary": summary, "competitions": output}
