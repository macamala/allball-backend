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



def tomorrow_public_multisport_snapshot() -> Dict[str, Any]:
    """Sydney-local canary for all public sports. Diagnostics only, never business logic."""
    from collector.provider import NinkoCollectedSportsDataProvider

    now_local = datetime.now(timezone.utc).astimezone(SYDNEY)
    day = now_local.date() + timedelta(days=1)
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
    competition_counts: Dict[str, int] = {}
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for row in events:
        sport = str(row.get("sport") or "unknown")
        competition_counts[sport] = competition_counts.get(sport, 0) + 1
        bucket = samples.setdefault(sport, [])
        if len(bucket) < 8:
            bucket.append(
                {
                    "competition": row.get("competition_name") or row.get("competition"),
                    "competition_key": row.get("competition_key"),
                    "home": (row.get("home") or {}).get("name"),
                    "away": (row.get("away") or {}).get("name"),
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
        "local_date": day.isoformat(),
        "utc_from": utc_start.isoformat().replace("+00:00", "Z"),
        "utc_to": utc_end.isoformat().replace("+00:00", "Z"),
        "total": len(events),
        "sports": dict(sport_counts.most_common()),
        "competitions_by_sport": distinct_competitions,
        "samples": samples,
    }



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
