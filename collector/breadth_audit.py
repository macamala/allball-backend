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

    def has_logo(side: Any) -> bool:
        if not isinstance(side, dict):
            return False
        return bool(
            side.get("logo")
            or side.get("image")
            or side.get("crest")
            or side.get("badge")
            or side.get("team_logo")
            or side.get("teamLogo")
        )

    both_team_assets = sum(
        1 for row in events if has_logo(row.get("home")) and has_logo(row.get("away"))
    )
    competition_assets = sum(1 for row in events if row.get("competition_logo"))
    country_assets = sum(
        1
        for row in events
        if row.get("country_id")
        or str(row.get("scope_type") or "").upper() in {"WORLD", "INTERNATIONAL", "CONTINENTAL", "REGIONAL"}
    )
    sample = [
        {
            "competition": row.get("competition_name") or row.get("competition"),
            "competition_key": row.get("competition_key"),
            "competition_logo": bool(row.get("competition_logo")),
            "country_id": row.get("country_id"),
            "home": (row.get("home") or {}).get("name"),
            "home_id": (row.get("home") or {}).get("id"),
            "home_logo": bool((row.get("home") or {}).get("logo")),
            "away": (row.get("away") or {}).get("name"),
            "away_id": (row.get("away") or {}).get("id"),
            "away_logo": bool((row.get("away") or {}).get("logo")),
            "utc": row.get("start_time"),
        }
        for row in events[:160]
    ]
    return {
        "local_date": day.isoformat(),
        "total": len(events),
        "events_with_both_team_assets": both_team_assets,
        "events_with_competition_logo": competition_assets,
        "events_with_country_or_international_identity": country_assets,
        "competitions": dict(competitions.most_common()),
        "events": sample,
    }



def fifa_competition_samples() -> List[Dict[str, Any]]:
    from collector.adapters_feeds import loc
    from collector.http import fetch_url

    out: List[Dict[str, Any]] = []
    urls = [
        "https://api.fifa.com/api/v3/live/football?language=en",
        "https://api.fifa.com/api/v3/calendar/matches?count=100&language=en",
    ]
    for url in urls:
        result = fetch_url(url)
        payload = result.payload if getattr(result, "ok", False) and isinstance(result.payload, dict) else {}
        for row in payload.get("Results") or []:
            if not isinstance(row, dict):
                continue
            raw_name = row.get("CompetitionName")
            name = loc(raw_name)
            home = row.get("HomeTeam") or {}
            away = row.get("AwayTeam") or {}
            compact: Dict[str, Any] = {
                "endpoint": "live" if "/live/" in url else "calendar",
                "CompetitionName": name,
                "home": loc(home.get("TeamName")) if isinstance(home, dict) else "",
                "away": loc(away.get("TeamName")) if isinstance(away, dict) else "",
                "top_identity": {
                    key: value
                    for key, value in row.items()
                    if any(token in key.lower() for token in ("country", "competition", "association", "confeder", "federation"))
                },
                "home_identity": {
                    key: value
                    for key, value in home.items()
                    if any(token in key.lower() for token in ("country", "association", "confeder", "federation", "team"))
                } if isinstance(home, dict) else {},
                "away_identity": {
                    key: value
                    for key, value in away.items()
                    if any(token in key.lower() for token in ("country", "association", "confeder", "federation", "team"))
                } if isinstance(away, dict) else {},
            }
            if name in {"Ligue 1", "Premier League", "Concacaf Nations League", "UEFA Nations League"}:
                out.append(compact)
            elif len(out) < 4:
                out.append(compact)
            if len(out) >= 12:
                return out
    return out



def public_football_asset_range_snapshot(*, days_back: int = 7, days_forward: int = 14) -> Dict[str, Any]:
    """Audit every public football event across a wider Sydney-local rolling window."""
    from collector.provider import NinkoCollectedSportsDataProvider

    now_local = datetime.now(timezone.utc).astimezone(SYDNEY)
    first_day = now_local.date() - timedelta(days=days_back)
    last_day = now_local.date() + timedelta(days=days_forward)
    local_start = datetime.combine(first_day, datetime.min.time(), tzinfo=SYDNEY)
    local_end = datetime.combine(last_day + timedelta(days=1), datetime.min.time(), tzinfo=SYDNEY)
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    events = NinkoCollectedSportsDataProvider().get_events(
        sport="football",
        date_from=utc_start.isoformat().replace("+00:00", "Z"),
        date_to=utc_end.isoformat().replace("+00:00", "Z"),
        allow_unfiltered=True,
    )

    def side_has_logo(side: Any) -> bool:
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
        )

    missing_by_competition: Dict[str, Dict[str, Any]] = {}
    events_with_comp_logo = 0
    side_slots = 0
    side_logos = 0
    for event in events:
        comp = str(event.get("competition_key") or event.get("competition") or "unknown")
        comp_logo = bool(event.get("competition_logo"))
        if comp_logo:
            events_with_comp_logo += 1
        missing_sides: List[str] = []
        for side_name in ("home", "away"):
            side = event.get(side_name)
            if not isinstance(side, dict):
                continue
            side_slots += 1
            if side_has_logo(side):
                side_logos += 1
            else:
                missing_sides.append(side_name)
        if comp_logo and not missing_sides:
            continue
        item = missing_by_competition.setdefault(
            comp,
            {
                "events": 0,
                "missing_competition_logo": 0,
                "missing_team_logo_slots": 0,
                "examples": [],
            },
        )
        item["events"] += 1
        item["missing_competition_logo"] += 0 if comp_logo else 1
        item["missing_team_logo_slots"] += len(missing_sides)
        if len(item["examples"]) < 3:
            item["examples"].append(
                {
                    "id": event.get("id"),
                    "home": (event.get("home") or {}).get("name"),
                    "away": (event.get("away") or {}).get("name"),
                    "missing_sides": missing_sides,
                    "missing_competition_logo": not comp_logo,
                    "utc": event.get("start_time"),
                }
            )

    return {
        "local_from": str(first_day),
        "local_to": str(last_day),
        "events": len(events),
        "events_with_competition_logo": events_with_comp_logo,
        "side_slots": side_slots,
        "side_logos": side_logos,
        "gap_competitions": missing_by_competition,
    }


TEAM_IDENTITY_FAMILIES = {"team_match", "esports_match"}
INDIVIDUAL_IDENTITY_FAMILIES = {"individual_match", "combat"}

# In national-team-only competitions a federation crest is optional artwork;
# the country's flag is already a truthful, complete participant identity.
# Keep this allow-list narrow so international club competitions still require
# real club crests.
NATIONAL_TEAM_IDENTITY_COMPETITIONS = {
    "cev-eurovolley-men",
}


def _visible_identity_requirement(event: Dict[str, Any]) -> str:
    """Return the side identity asset a public score row genuinely requires."""
    family = str(event.get("event_family") or "").strip().lower()
    competition = str(event.get("competition_key") or event.get("competition") or "").strip()
    if family in TEAM_IDENTITY_FAMILIES:
        if competition in NATIONAL_TEAM_IDENTITY_COMPETITIONS:
            return "country_or_logo"
        return "logo"
    if family in INDIVIDUAL_IDENTITY_FAMILIES:
        return "country"
    return "none"


def public_multisport_day_snapshot(day_offset: int = 1, *, include_samples: bool = True) -> Dict[str, Any]:
    """Sydney-local public canary for any nearby day. Diagnostics only."""
    from collector.provider import NinkoCollectedSportsDataProvider

    now_local = datetime.now(timezone.utc).astimezone(SYDNEY)
    day = now_local.date() + timedelta(days=day_offset)
    local_start = datetime.combine(day, datetime.min.time(), tzinfo=SYDNEY)
    local_end = local_start + timedelta(days=1)
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    provider = NinkoCollectedSportsDataProvider()
    events = provider.get_events(
        date_from=utc_start.isoformat().replace("+00:00", "Z"),
        date_to=utc_end.isoformat().replace("+00:00", "Z"),
        allow_unfiltered=True,
    )
    sport_counts = Counter(str(row.get("sport") or "unknown") for row in events)
    samples: Dict[str, List[Dict[str, Any]]] = {}
    if include_samples:
        for row in events:
            sport = str(row.get("sport") or "unknown")
            bucket = samples.setdefault(sport, [])
            if len(bucket) < 8:
                bucket.append(
                    {
                        "id": row.get("id"),
                        "competition": row.get("competition_name") or row.get("competition"),
                        "competition_key": row.get("competition_key"),
                        "home": (row.get("home") or {}).get("name"),
                        "away": (row.get("away") or {}).get("name"),
                        "utc": row.get("start_time"),
                        "source_family": row.get("source_family"),
                    }
                )

    def _side_logo(side: Any) -> bool:
        if not isinstance(side, dict):
            return False
        return bool(
            side.get("logo")
            or side.get("image")
            or side.get("crest")
            or side.get("badge")
            or side.get("team_logo")
            or side.get("teamLogo")
        )

    def _side_country(side: Any) -> bool:
        if not isinstance(side, dict):
            return False
        return bool(
            side.get("country_id")
            or side.get("country")
            or side.get("nationality")
            or [value for value in (side.get("country_ids") or []) if value]
        )

    assets_by_sport: Dict[str, Dict[str, int]] = {}
    asset_gaps: Dict[str, List[Dict[str, Any]]] = {}
    asset_gap_competitions: Dict[str, Dict[str, Dict[str, int]]] = {}
    for row in events:
        sport = str(row.get("sport") or "unknown")
        bucket = assets_by_sport.setdefault(
            sport,
            {
                "events": 0,
                "events_with_competition_logo": 0,
                "events_with_both_side_logos": 0,
                "events_with_both_side_countries": 0,
                "side_slots": 0,
                "side_logos": 0,
                "side_countries": 0,
            },
        )
        bucket["events"] += 1
        bucket["events_with_competition_logo"] += int(bool(row.get("competition_logo")))
        home = row.get("home") if isinstance(row.get("home"), dict) else {}
        away = row.get("away") if isinstance(row.get("away"), dict) else {}
        sides = [side for side in (home, away) if side and (side.get("name") or side.get("display_name"))]
        identity_requirement = _visible_identity_requirement(row)
        missing_competition_logo = not bool(row.get("competition_logo"))
        missing_side_logos: List[str] = []
        missing_side_countries: List[str] = []

        if len(sides) == 2:
            logos = sum(1 for side in sides if _side_logo(side))
            countries = sum(1 for side in sides if _side_country(side))
            bucket["events_with_both_side_logos"] += int(logos == 2)
            bucket["events_with_both_side_countries"] += int(countries == 2)
            # Raw counters remain useful diagnostics, but only identity assets
            # appropriate to the event family can create a completion gap.
            bucket["side_slots"] += 2
            bucket["side_logos"] += logos
            bucket["side_countries"] += countries
            if identity_requirement == "logo":
                missing_side_logos = [
                    side_name
                    for side_name, side in (("home", home), ("away", away))
                    if not _side_logo(side)
                ]
            elif identity_requirement == "country_or_logo":
                missing_side_logos = [
                    side_name
                    for side_name, side in (("home", home), ("away", away))
                    if not _side_logo(side) and not _side_country(side)
                ]
            elif identity_requirement == "country":
                missing_side_countries = [
                    side_name
                    for side_name, side in (("home", home), ("away", away))
                    if not _side_country(side)
                ]

        if missing_competition_logo or missing_side_logos or missing_side_countries:
            competition_key = str(row.get("competition_key") or row.get("competition") or "unknown")
            by_comp = asset_gap_competitions.setdefault(sport, {})
            comp_gap = by_comp.setdefault(
                competition_key,
                {
                    "events": 0,
                    "missing_competition_logo": 0,
                    "missing_team_logo_slots": 0,
                    "missing_participant_country_slots": 0,
                },
            )
            comp_gap["events"] += 1
            comp_gap["missing_competition_logo"] += int(missing_competition_logo)
            comp_gap["missing_team_logo_slots"] += len(missing_side_logos)
            comp_gap["missing_participant_country_slots"] += len(missing_side_countries)
            gaps = asset_gaps.setdefault(sport, [])
            gap_limit = 128 if sport == "football" else 16
            if len(gaps) < gap_limit:
                gaps.append(
                    {
                        "id": row.get("id"),
                        "competition": row.get("competition_name") or row.get("competition"),
                        "competition_key": row.get("competition_key"),
                        "event_family": row.get("event_family"),
                        "identity_requirement": identity_requirement,
                        "home": home.get("name"),
                        "home_id": home.get("id"),
                        "away": away.get("name"),
                        "away_id": away.get("id"),
                        "missing_competition_logo": missing_competition_logo,
                        "missing_side_logos": missing_side_logos,
                        "missing_side_countries": missing_side_countries,
                        "source_family": row.get("source_family"),
                        "source_competition_id": row.get("source_competition_id"),
                        "utc": row.get("start_time"),
                    }
                )

    distinct_competitions: Dict[str, int] = {}
    for sport in sport_counts:
        distinct_competitions[sport] = len(
            {
                str(row.get("competition_key") or row.get("competition") or "")
                for row in events
                if str(row.get("sport") or "unknown") == sport
            }
        )

    return {
        "day_offset": day_offset,
        "local_date": day.isoformat(),
        "utc_from": utc_start.isoformat().replace("+00:00", "Z"),
        "utc_to": utc_end.isoformat().replace("+00:00", "Z"),
        "total": len(events),
        "sports": dict(sport_counts.most_common()),
        "competitions_by_sport": distinct_competitions,
        "assets_by_sport": assets_by_sport,
        "asset_gaps": asset_gaps,
        "asset_gap_competitions": asset_gap_competitions,
        "samples": samples,
    }


def tomorrow_public_multisport_snapshot() -> Dict[str, Any]:
    return public_multisport_day_snapshot(1, include_samples=True)


def rolling_multisport_public_snapshot() -> Dict[str, Any]:
    return {
        str(offset): public_multisport_day_snapshot(offset, include_samples=False)
        for offset in (0, 1, 2)
    }


def unknown_sport_rows_snapshot(db, *, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.sport_id.in_(["", "unknown"]))
        .order_by(SportsEvent.updated_at.desc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, Any]] = []
    from collector.provider import _blocked_public_sources, _row_public_source_allowed

    blocked_ids, blocked_families = _blocked_public_sources(db)
    for row in rows:
        if row.display_eligible is False:
            continue
        if not _row_public_source_allowed(row, blocked_ids, blocked_families):
            continue
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
        away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
        out.append(
            {
                "id": row.event_id,
                "sport": row.sport_id,
                "competition": row.competition_id,
                "home": home.get("name"),
                "away": away.get("name"),
                "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
                "primary_source": row.primary_source_id,
                "source_family": extra.get("source_family"),
                "source_competition_id": extra.get("source_competition_id"),
                "source_competition_name": extra.get("source_competition_name"),
                "resolution_method": extra.get("resolution_method"),
                "quality_flags": extra.get("quality_flags") or [],
            }
        )
    return out



MATCH_DETAIL_URL = "https://sportscore.com/api/widget/match/?sport={sport}&slug={slug}&src=ninkosports"


def _sportscore_detail_identity(sport: str, row: Dict[str, Any]) -> Dict[str, Any]:
    from urllib.parse import urlparse
    from collector.http import fetch_url

    raw_url = str(row.get("url") or "").strip()
    slug = urlparse(raw_url).path.rstrip("/").rsplit("/", 1)[-1] if raw_url else ""
    if not slug:
        return {}
    result = fetch_url(MATCH_DETAIL_URL.format(sport=sport, slug=slug))
    payload = result.payload if getattr(result, "ok", False) and isinstance(result.payload, dict) else {}
    match = payload.get("match") if isinstance(payload.get("match"), dict) else payload
    competition = match.get("competition") if isinstance(match.get("competition"), dict) else {}
    return {
        "status": int(getattr(result, "http_status", 0) or 0),
        "ok": bool(getattr(result, "ok", False)),
        "slug": slug,
        "top_keys": sorted(str(key) for key in payload.keys())[:60],
        "match_keys": sorted(str(key) for key in match.keys())[:80] if isinstance(match, dict) else [],
        "competition": competition,
        "competition_name": match.get("competition") if isinstance(match.get("competition"), str) else None,
        "competition_slug": match.get("competition_slug") or match.get("league_slug") or competition.get("slug"),
        "competition_id": match.get("competition_id") or match.get("league_id") or competition.get("id"),
        "country": match.get("country") or competition.get("country"),
        "season": match.get("season"),
        "stage": match.get("stage"),
        "round": match.get("round"),
    }

def sportscore_breadth_probe() -> Dict[str, Any]:
    """Production transport/competition probe for the public SportScore board."""
    from collector.adapters_sportscore import MATCHES_URL, _payload_matches
    from collector.http import fetch_url

    probes = {
        "basketball": ["basketball"],
        "tennis": ["tennis"],
        "handball": ["handball"],
        "volleyball": ["volleyball"],
        "baseball": ["baseball"],
        "ice-hockey": ["ice-hockey", "hockey"],
        "cricket": ["cricket"],
    }
    out: Dict[str, Any] = {}
    for sport_id, upstream_names in probes.items():
        best: Dict[str, Any] = {"status": 0, "rows": 0, "competitions": {}}
        attempts: List[Dict[str, Any]] = []
        for upstream in upstream_names:
            result = fetch_url(MATCHES_URL.format(sport=upstream, limit=50))
            rows = _payload_matches(result.payload) if getattr(result, "ok", False) else []
            competitions = Counter(
                str(row.get("competition") or "").strip()
                for row in rows
                if str(row.get("competition") or "").strip()
            )
            attempt = {
                "upstream": upstream,
                "status": int(getattr(result, "http_status", 0) or 0),
                "ok": bool(getattr(result, "ok", False)),
                "rows": len(rows),
                "competitions": dict(competitions.most_common(12)),
                "sample": [
                    {
                        "competition": row.get("competition"),
                        "home": row.get("home"),
                        "away": row.get("away"),
                        "time": row.get("time"),
                        "slug": row.get("slug") or row.get("match_slug"),
                        "url": row.get("url"),
                        "competition_slug": row.get("competition_slug") or row.get("league_slug"),
                        "home_slug": row.get("home_slug") or row.get("home_team_slug"),
                        "away_slug": row.get("away_slug") or row.get("away_team_slug"),
                        "country": row.get("country") or row.get("competition_country"),
                        "keys": sorted(str(key) for key in row.keys())[:40],
                    }
                    for row in rows[:4]
                ],
            }
            attempts.append(attempt)
            if len(rows) > int(best.get("rows") or 0) or (attempt["ok"] and not best.get("ok")):
                best = attempt
            if rows:
                break
        best["attempts"] = attempts
        if best.get("rows") and sport_id in {"basketball", "tennis", "cricket"}:
            source_sport = str(best.get("upstream") or sport_id)
            board_result = fetch_url(MATCHES_URL.format(sport=source_sport, limit=50))
            detail_rows = _payload_matches(board_result.payload) if getattr(board_result, "ok", False) else []
            best["detail_identity"] = _sportscore_detail_identity(
                source_sport, detail_rows[0] if detail_rows else {}
            )
        out[sport_id] = best
    return out



def sportscore_directory_probe() -> Dict[str, Any]:
    """Prove stable competition IDs and fixture extraction from SportScore hubs."""
    import re as _re
    from collector.http import fetch_text
    from collector.html_parse import parse_html

    out: Dict[str, Any] = {}
    targets = {
        "basketball": {"womens-national-basketball-association", "euroleague"},
        "tennis": {"atp-hangzhou-china-men-singles"},
        "cricket": {"australia-domestic-one-day-cup"},
    }
    link_re = _re.compile(
        r'href=["\']/(?P<sport>basketball|tennis|cricket)/competition/'
        r'(?P<country>[^/]+)/(?P<slug>[^/]+)/(?P<source_id>[^/"\']+)/?["\']',
        _re.I,
    )
    for sport, wanted in targets.items():
        landing_url = f"https://sportscore.com/{sport}/"
        landing = fetch_text(landing_url)
        html = landing.payload if getattr(landing, "ok", False) and isinstance(landing.payload, str) else ""
        found = []
        seen = set()
        for match in link_re.finditer(html):
            slug = match.group("slug").lower()
            if slug not in wanted:
                continue
            key = (slug, match.group("source_id"))
            if key in seen:
                continue
            seen.add(key)
            url = (
                f"https://sportscore.com/{sport}/competition/"
                f"{match.group('country')}/{slug}/{match.group('source_id')}/"
            )
            page = fetch_text(url)
            page_html = page.payload if getattr(page, "ok", False) and isinstance(page.payload, str) else ""
            parsed = parse_html(page_html, url) if page_html else []
            found.append(
                {
                    "country": match.group("country"),
                    "slug": slug,
                    "source_id": match.group("source_id"),
                    "page_status": int(getattr(page, "http_status", 0) or 0),
                    "page_bytes": len(page_html.encode("utf-8")) if page_html else 0,
                    "parsed_events": len(parsed),
                    "sample_events": [
                        {
                            "home": ((row.get("home") or {}).get("name") if isinstance(row.get("home"), dict) else row.get("home")),
                            "away": ((row.get("away") or {}).get("name") if isinstance(row.get("away"), dict) else row.get("away")),
                            "start_time": row.get("start_time"),
                            "status": row.get("status"),
                            "competition": row.get("competition"),
                        }
                        for row in parsed[:6]
                    ],
                }
            )
        out[sport] = {
            "landing_status": int(getattr(landing, "http_status", 0) or 0),
            "landing_bytes": len(html.encode("utf-8")) if html else 0,
            "matches": found,
        }
    return out



def sportscore_team_schedule_probe() -> Dict[str, Any]:
    """Prove team/player recent+upcoming schedules using match-derived slugs."""
    from urllib.parse import urlparse
    from collector.adapters_sportscore import MATCHES_URL, TEAM_URL, _payload_matches
    from collector.http import fetch_url

    out: Dict[str, Any] = {}
    for sport in ("basketball", "tennis", "cricket"):
        board = fetch_url(MATCHES_URL.format(sport=sport, limit=10))
        rows = _payload_matches(board.payload) if getattr(board, "ok", False) else []
        first = rows[0] if rows else {}
        path = urlparse(str(first.get("url") or "")).path.rstrip("/")
        match_slug = path.rsplit("/", 1)[-1] if path else ""
        team_slugs = [part for part in match_slug.split("-vs-", 1) if part] if "-vs-" in match_slug else []
        probes = []
        for team_slug in team_slugs[:2]:
            result = fetch_url(TEAM_URL.format(sport=sport, slug=team_slug))
            payload = result.payload if getattr(result, "ok", False) else {}
            team_rows = _payload_matches(payload)
            probes.append(
                {
                    "slug": team_slug,
                    "status": int(getattr(result, "http_status", 0) or 0),
                    "ok": bool(getattr(result, "ok", False)),
                    "rows": len(team_rows),
                    "keys": sorted(str(key) for key in payload.keys())[:50] if isinstance(payload, dict) else [],
                    "first_time": team_rows[0].get("time") if team_rows else None,
                    "last_time": team_rows[-1].get("time") if team_rows else None,
                    "samples": [
                        {
                            "competition": row.get("competition"),
                            "home": row.get("home"),
                            "away": row.get("away"),
                            "time": row.get("time"),
                            "status": row.get("status"),
                            "url": row.get("url"),
                        }
                        for row in team_rows[:6]
                    ],
                }
            )
        out[sport] = {
            "board_status": int(getattr(board, "http_status", 0) or 0),
            "match_slug": match_slug,
            "probes": probes,
        }
    return out
