"""Propagate known identity assets across canonical sports events.

Once one trusted observation supplies competition artwork, a participant logo,
or participant country, reuse that already-stored identity on other canonical
rows that are missing the same field. Existing non-empty identity is never
overwritten and no artwork is invented.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from collector.competition_presentation import metadata_for
from collector.list_extra import store_list_extra
from collector.models import SportsEvent, SportsStandingSnapshot
from collector.participant_text import fold_for_identity
from sports_registry.geography import get_geo
from collector.util import dump_json, load_json


TEAM_FAMILIES = {"team_match", "esports_match"}
INDIVIDUAL_FAMILIES = {"individual_match", "combat"}

_NHL_ABBREVS = {
    "ANA","BOS","BUF","CAR","CBJ","CGY","CHI","COL","DAL","DET","EDM","FLA",
    "LAK","MIN","MTL","NJD","NSH","NYI","NYR","OTT","PHI","PIT","SEA","SJS",
    "STL","TBL","TOR","UTA","VAN","VGK","WPG","WSH",
}


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


def _country_identity_from_name(name: Any) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    candidates = [
        raw,
        raw.lower().replace(" ", "-"),
        raw.lower().replace(" ", "-").replace(".", ""),
    ]
    aliases = {
        "uae": "ae",
        "usa": "us",
        "dr-congo": "cd",
        "czechia": "cz",
        "south-korea": "kr",
        "north-korea": "kp",
        "ivory-coast": "ci",
        "cape-verde": "cv",
        "curacao": "cw",
    }
    for value in candidates:
        key = aliases.get(value, value)
        geo = get_geo(key)
        if not geo or geo.get("kind") == "region":
            continue
        canonical_name = str(geo.get("name") or "").casefold()
        if raw.casefold() not in {
            canonical_name,
            str(geo.get("id") or "").casefold(),
            str(geo.get("slug") or "").replace("-", " ").casefold(),
            str(geo.get("iso_code") or "").casefold(),
        } and value not in aliases:
            continue
        return str(geo.get("iso_code") or geo.get("id") or "").strip()
    return ""


def _standing_rows(payload: Any):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows") or payload.get("standings") or payload.get("table") or []
    return rows if isinstance(rows, list) else []


def _standing_asset(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    team = item.get("team")
    team_meta = team if isinstance(team, dict) else {}
    name = (
        team_meta.get("name")
        or team_meta.get("display_name")
        or (team if isinstance(team, str) else "")
        or item.get("name")
        or ""
    )
    team_id = (
        item.get("team_id")
        or item.get("teamId")
        or team_meta.get("id")
        or ""
    )
    logo = (
        item.get("logo")
        or item.get("crest")
        or item.get("badge")
        or item.get("team_logo")
        or item.get("teamLogo")
        or team_meta.get("logo")
        or team_meta.get("crest")
        or team_meta.get("badge")
        or ""
    )
    country = (
        item.get("country_id")
        or item.get("country")
        or team_meta.get("country_id")
        or team_meta.get("country")
        or ""
    )
    return {
        "name": str(name or "").strip(),
        "team_id": str(team_id or "").strip(),
        "logo": str(logo or "").strip(),
        "country_id": str(country or "").strip(),
    }


def _fotmob_identity_context(row: SportsEvent, extra: Dict[str, Any]) -> bool:
    family = str(extra.get("source_family") or "").strip().lower()
    primary = str(getattr(row, "primary_source_id", "") or "").strip().lower()
    if family == "fotmob" or primary.startswith("fotmob"):
        return True
    field_sources = extra.get("field_sources") if isinstance(extra.get("field_sources"), dict) else {}
    return any("fotmob" in str(value or "").lower() for value in field_sources.values())


def _derive_fotmob_assets(row: SportsEvent, extra: Dict[str, Any], participants: Dict[str, Any]) -> Tuple[bool, bool, int]:
    """Derive official FotMob CDN artwork only when stored IDs are known to be FotMob-owned."""
    if not _fotmob_identity_context(row, extra):
        return False, False, 0
    row_changed = False
    extra_changed = False
    participant_filled = 0
    competition_id = str(extra.get("source_competition_id") or "").strip()
    if competition_id and competition_id.isdigit() and not extra.get("competition_logo"):
        extra["competition_logo"] = (
            f"https://images.fotmob.com/image_resources/logo/leaguelogo/{competition_id}.png"
        )
        row_changed = True
        extra_changed = True
    field_sources = extra.get("field_sources") if isinstance(extra.get("field_sources"), dict) else {}
    for side_name in ("home", "away", "participant_a", "participant_b"):
        side = participants.get(side_name)
        if not isinstance(side, dict) or _asset(side).get("logo"):
            continue
        source_owner = str(field_sources.get(side_name) or "").lower()
        if source_owner and "fotmob" not in source_owner:
            continue
        team_id = str(side.get("id") or "").strip()
        if not team_id.isdigit():
            continue
        merged = dict(side)
        merged["logo"] = f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png"
        participants[side_name] = merged
        row_changed = True
        participant_filled += 1
    return row_changed, extra_changed, participant_filled


def _derive_competition_native_assets(
    row: SportsEvent,
    extra: Dict[str, Any],
    participants: Dict[str, Any],
) -> Tuple[bool, bool, int]:
    """Fill artwork from competition-native official IDs only when unambiguous."""
    competition = str(row.competition_id or "")
    changed = False
    extra_changed = False
    participant_filled = 0

    if competition == "nhl":
        if not extra.get("competition_logo"):
            extra["competition_logo"] = "https://assets.nhle.com/logos/nhl/svg/NHL_light.svg"
            changed = True
            extra_changed = True
        for side_name in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _asset(side).get("logo"):
                continue
            candidates = [
                str(side.get("id") or "").strip().upper(),
                str(side.get("slug") or "").strip().upper(),
                str(side.get("name") or "").strip().upper(),
            ]
            abbrev = next((value for value in candidates if value in _NHL_ABBREVS), "")
            if not abbrev:
                continue
            merged = dict(side)
            merged["logo"] = f"https://assets.nhle.com/logos/nhl/svg/{abbrev}_light.svg"
            participants[side_name] = merged
            changed = True
            participant_filled += 1

    elif competition == "mlb":
        if not extra.get("competition_logo"):
            extra["competition_logo"] = "https://www.mlbstatic.com/team-logos/league-on-light/1.svg"
            changed = True
            extra_changed = True
        for side_name in ("home", "away", "participant_a", "participant_b"):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _asset(side).get("logo"):
                continue
            team_id = str(side.get("id") or "").strip()
            if not team_id.isdigit():
                continue
            merged = dict(side)
            merged["logo"] = f"https://www.mlbstatic.com/team-logos/{team_id}.svg"
            participants[side_name] = merged
            changed = True
            participant_filled += 1

    return changed, extra_changed, participant_filled


def _sofascore_identity_context(row: SportsEvent, extra: Dict[str, Any]) -> bool:
    family = str(extra.get("source_family") or "").strip().lower()
    primary = str(getattr(row, "primary_source_id", "") or "").strip().lower()
    if family == "sofascore-web" or "sofascore" in primary:
        return True
    field_sources = extra.get("field_sources") if isinstance(extra.get("field_sources"), dict) else {}
    return any("sofascore" in str(value or "").lower() for value in field_sources.values())


def _derive_sofascore_assets(
    row: SportsEvent,
    extra: Dict[str, Any],
    participants: Dict[str, Any],
) -> Tuple[bool, bool, int]:
    """Derive SofaScore artwork only when stored IDs are SofaScore-owned."""
    if not _sofascore_identity_context(row, extra):
        return False, False, 0
    row_changed = False
    extra_changed = False
    participant_filled = 0
    competition_id = str(
        extra.get("sofascore_tournament_id")
        or extra.get("source_competition_id")
        or ""
    ).strip()
    if competition_id and competition_id.isdigit() and not extra.get("competition_logo"):
        extra["competition_logo"] = (
            f"https://img.sofascore.com/api/v1/unique-tournament/{competition_id}/image"
        )
        row_changed = True
        extra_changed = True

    field_sources = extra.get("field_sources") if isinstance(extra.get("field_sources"), dict) else {}
    for side_name in ("home", "away", "participant_a", "participant_b"):
        side = participants.get(side_name)
        if not isinstance(side, dict) or _asset(side).get("logo"):
            continue
        source_owner = str(field_sources.get(side_name) or "").lower()
        if source_owner and "sofascore" not in source_owner:
            continue
        team_id = str(side.get("id") or "").strip()
        if not team_id.isdigit():
            continue
        merged = dict(side)
        merged["logo"] = f"https://img.sofascore.com/api/v1/team/{team_id}/image"
        participants[side_name] = merged
        row_changed = True
        participant_filled += 1
    return row_changed, extra_changed, participant_filled


def propagate_identity_assets(db) -> Dict[str, int]:
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.display_eligible.is_(True))
        .all()
    )

    competition_assets: Dict[Tuple[str, str], str] = {}
    participant_assets: Dict[Tuple[str, str, str, str], Dict[str, str]] = {}
    standing_assets: Dict[Tuple[str, str, str, str], Dict[str, str]] = {}

    # Standings are a trusted competition-scoped source of club identity.
    standing_snapshots = db.query(SportsStandingSnapshot).all()
    for snapshot in standing_snapshots:
        sport = str(snapshot.sport_id or "")
        competition = str(snapshot.competition_id or "")
        payload = load_json(snapshot.rows_json, {}) or {}
        for item in _standing_rows(payload):
            observed = _standing_asset(item)
            if not observed.get("logo") and not observed.get("country_id"):
                continue
            if observed.get("team_id"):
                standing_assets[(sport, competition, "id", observed["team_id"])] = observed
            folded = fold_for_identity(observed.get("name") or "")
            if folded:
                standing_assets[(sport, competition, "name", folded)] = observed

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
        "source_native_competition_logos_filled": 0,
        "source_native_participant_logos_filled": 0,
        "sofascore_competition_logos_filled": 0,
        "sofascore_participant_logos_filled": 0,
        "competition_native_logos_filled": 0,
        "competition_native_participant_logos_filled": 0,
        "standing_participant_logos_filled": 0,
        "standing_participant_countries_filled": 0,
        "national_team_countries_filled": 0,
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

        meta = metadata_for(competition, sport)
        non_domestic_team_scope = (
            _bucket(family) == "team"
            and str(meta.get("scope_type") or "").upper() in {
                "WORLD", "INTERNATIONAL", "CONTINENTAL", "REGIONAL"
            }
        )
        if non_domestic_team_scope:
            for side_name in ("home", "away", "participant_a", "participant_b"):
                side = participants.get(side_name)
                if not isinstance(side, dict) or _asset(side).get("country_id"):
                    continue
                country_id = _country_identity_from_name(
                    side.get("display_name") or side.get("name")
                )
                if not country_id:
                    continue
                merged = dict(side)
                merged["country_id"] = country_id
                participants[side_name] = merged
                stats["national_team_countries_filled"] += 1
                row_changed = True

        direct_changed, direct_extra_changed, direct_participants = _derive_fotmob_assets(
            row, extra, participants
        )
        if direct_changed:
            row_changed = True
        if direct_extra_changed:
            extra_changed = True
            stats["source_native_competition_logos_filled"] += 1
        if direct_participants:
            stats["source_native_participant_logos_filled"] += direct_participants

        sofa_changed, sofa_extra_changed, sofa_participants = _derive_sofascore_assets(
            row, extra, participants
        )
        if sofa_changed:
            row_changed = True
        if sofa_extra_changed:
            extra_changed = True
            stats["sofascore_competition_logos_filled"] += 1
        if sofa_participants:
            stats["sofascore_participant_logos_filled"] += sofa_participants

        native_changed, native_extra_changed, native_participants = _derive_competition_native_assets(
            row, extra, participants
        )
        if native_changed:
            row_changed = True
        if native_extra_changed:
            extra_changed = True
            stats["competition_native_logos_filled"] += 1
        if native_participants:
            stats["competition_native_participant_logos_filled"] += native_participants

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
            known: Dict[str, Any] = {}
            if _bucket(family) == "team":
                participant_id = str(side.get("id") or "").strip()
                if participant_id:
                    scoped = standing_assets.get((sport, competition, "id", participant_id)) or {}
                    if scoped.get("logo"):
                        known["logo"] = scoped["logo"]
                    if scoped.get("country_id"):
                        known["country_id"] = scoped["country_id"]
                folded_name = fold_for_identity(side.get("display_name") or side.get("name") or "")
                if folded_name:
                    scoped = standing_assets.get((sport, competition, "name", folded_name)) or {}
                    if scoped.get("logo") and not known.get("logo"):
                        known["logo"] = scoped["logo"]
                        known["_standing_logo"] = True
                    if scoped.get("country_id") and not known.get("country_id"):
                        known["country_id"] = scoped["country_id"]
                        known["_standing_country"] = True
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
                if known.get("_standing_logo"):
                    stats["standing_participant_logos_filled"] += 1
                row_changed = True
            if known.get("country_id") and not _asset(merged).get("country_id"):
                merged["country_id"] = known["country_id"]
                stats["participant_countries_filled"] += 1
                if known.get("_standing_country"):
                    stats["standing_participant_countries_filled"] += 1
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
