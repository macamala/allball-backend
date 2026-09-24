"""Propagate known identity assets across canonical sports events.

Once one trusted observation supplies competition artwork, a participant logo,
or participant country, reuse that already-stored identity on other canonical
rows that are missing the same field. Existing non-empty identity is never
overwritten and no artwork is invented.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.util import dump_json, load_json


TEAM_FAMILIES = {"team_match", "esports_match"}
INDIVIDUAL_FAMILIES = {"individual_match", "combat"}


def _bucket(family: str) -> str:
    if family in TEAM_FAMILIES:
        return "team"
    if family in INDIVIDUAL_FAMILIES:
        return "individual"
    return family or "other"


def _identity_keys(sport: str, family: str, side: Any) -> Tuple[Tuple[str, str, str, str], ...]:
    if not isinstance(side, dict):
        return ()
    base = (sport or "", _bucket(family), "", "")
    out = []
    participant_id = str(side.get("id") or "").strip()
    if participant_id:
        out.append((base[0], base[1], "id", participant_id))
    slug = str(side.get("slug") or "").strip().casefold()
    if slug:
        out.append((base[0], base[1], "slug", slug))
    name = str(side.get("display_name") or side.get("name") or "").strip().casefold()
    if name and name != "tbd":
        out.append((base[0], base[1], "name", name))
    return tuple(out)


def _asset(side: Any) -> Dict[str, str]:
    if not isinstance(side, dict):
        return {}
    logo = str(
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
        or ""
    ).strip()
    country = str(
        side.get("country_id")
        or side.get("country")
        or side.get("nationality")
        or ""
    ).strip()
    countries = [
        str(value).strip()
        for value in (side.get("country_ids") or [])
        if str(value).strip()
    ]
    out: Dict[str, Any] = {}
    if logo:
        out["logo"] = logo
    if country:
        out["country_id"] = country
    if countries:
        out["country_ids"] = list(dict.fromkeys(countries))
    return out


def propagate_identity_assets(db) -> Dict[str, int]:
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.display_eligible.is_(True))
        .all()
    )

    competition_assets: Dict[Tuple[str, str], str] = {}
    participant_assets: Dict[Tuple[str, str, str, str], Dict[str, str]] = {}

    # Pass 1: build a conservative canonical asset index from already-observed data.
    for row in rows:
        sport = str(row.sport_id or "")
        competition = str(row.competition_id or "")
        extra = load_json(row.extra_json, {}) or {}
        competition_logo = str(extra.get("competition_logo") or "").strip()
        if competition_logo:
            competition_assets.setdefault((sport, competition), competition_logo)

        participants = load_json(row.participants_json, {}) or {}
        family = str(row.event_family or "")
        for side_name in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(side_name)
            observed = _asset(side)
            if not observed:
                continue
            for key in _identity_keys(sport, family, side):
                current = participant_assets.setdefault(key, {})
                if observed.get("logo") and not current.get("logo"):
                    current["logo"] = observed["logo"]
                if observed.get("country_id") and not current.get("country_id"):
                    current["country_id"] = observed["country_id"]
                if observed.get("country_ids") and not current.get("country_ids"):
                    current["country_ids"] = observed["country_ids"]

    stats = {
        "rows_scanned": len(rows),
        "rows_updated": 0,
        "competition_logos_filled": 0,
        "participant_logos_filled": 0,
        "participant_countries_filled": 0,
    }

    # Pass 2: fill blanks only. Never overwrite a non-empty value.
    for row in rows:
        sport = str(row.sport_id or "")
        competition = str(row.competition_id or "")
        family = str(row.event_family or "")
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        row_changed = False
        extra_changed = False

        if not extra.get("competition_logo"):
            logo = competition_assets.get((sport, competition))
            if logo:
                extra["competition_logo"] = logo
                stats["competition_logos_filled"] += 1
                row_changed = True
                extra_changed = True

        for side_name in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(side_name)
            if not isinstance(side, dict):
                continue
            known: Dict[str, str] = {}
            for key in _identity_keys(sport, family, side):
                candidate = participant_assets.get(key) or {}
                if candidate.get("logo") and not known.get("logo"):
                    known["logo"] = candidate["logo"]
                if candidate.get("country_id") and not known.get("country_id"):
                    known["country_id"] = candidate["country_id"]
                if candidate.get("country_ids") and not known.get("country_ids"):
                    known["country_ids"] = candidate["country_ids"]
            if not known:
                continue
            merged = dict(side)
            if known.get("logo") and not _asset(merged).get("logo"):
                merged["logo"] = known["logo"]
                stats["participant_logos_filled"] += 1
                row_changed = True
            if known.get("country_id") and not _asset(merged).get("country_id"):
                merged["country_id"] = known["country_id"]
                stats["participant_countries_filled"] += 1
                row_changed = True
            if known.get("country_ids") and not _asset(merged).get("country_ids"):
                merged["country_ids"] = known["country_ids"]
                stats["participant_countries_filled"] += 1
                row_changed = True
            participants[side_name] = merged

        if row_changed:
            row.participants_json = dump_json(participants)
            if extra_changed:
                row.extra_json = dump_json(extra)
                store_list_extra(row, extra)
            stats["rows_updated"] += 1

    if stats["rows_updated"]:
        db.commit()
    else:
        db.flush()
    return stats
