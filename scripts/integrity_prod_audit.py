"""One-shot production public-API integrity probe. Read-only."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://allball-backend-production.up.railway.app"
MARKERS = [
    "Kristiansund",
    "Rosenborg",
    "Molde",
    "Aalesund",
    "Elgin City",
    "Alloa",
    "Salford",
    "Woking",
    "Leyton Orient",
    "Zeleznicar",
    "Železničar",
    "Montevideo City",
    "18.09.2026",
    "LouviÃ",
    "GB AFC",
    "FlamengoBR",
]


def fetch(path: str, params: dict | None = None, timeout: int = 90):
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = BASE + path + query
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"User-Agent": "ninko-integrity-audit"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        elapsed = time.perf_counter() - started
        return response.status, len(body), json.loads(body), elapsed, url


def js_bounds(date_key: str) -> tuple[str, str]:
    year, month, day = map(int, date_key.split("-"))
    start = datetime(year, month, day, 0, 0, 0, 0)
    end = datetime(year, month, day, 23, 59, 59, 999000)
    offset = datetime.now().astimezone().utcoffset()
    start_utc = (start - offset).replace(tzinfo=timezone.utc)
    end_utc = (end - offset).replace(tzinfo=timezone.utc)
    return (
        start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        end_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{end_utc.microsecond // 1000:03d}Z",
    )


def sides(event: dict) -> tuple[str, str, str]:
    home = (event.get("home") or {}).get("name") or event.get("home_name") or ""
    away = (event.get("away") or {}).get("name") or event.get("away_name") or ""
    competition = (
        event.get("competition_id")
        or event.get("competition_key")
        or event.get("competition")
        or ""
    )
    if isinstance(competition, dict):
        competition = competition.get("id") or competition.get("name") or ""
    return str(home), str(away), str(competition)


def scan(events: list) -> dict:
    issues = []
    midnight = 0
    date_only = 0
    comps: dict[str, int] = {}
    sports: dict[str, int] = {}
    for event in events:
        home, away, competition = sides(event)
        comps[competition] = comps.get(competition, 0) + 1
        sport = event.get("sport") or event.get("sport_id") or ""
        sports[str(sport)] = sports.get(str(sport), 0) + 1
        blob = f"{home} {away}"
        if event.get("start_precision") == "DATE_ONLY":
            date_only += 1
        start = event.get("start_time") or ""
        if "T00:00" in start and event.get("start_precision") != "DATE_ONLY":
            midnight += 1
        if competition in {"brazil-serie-a"} and any(
            token in blob
            for token in ("Kristiansund", "Rosenborg", "Molde", "Aalesund", "Roma", "Venezia", "Lazio", "Inter Milan")
        ):
            issues.append({"class": "brazil_contamination", "home": home, "away": away, "competition": competition})
        if "a-league" in competition and any(
            token in blob for token in ("Elgin", "Alloa", "Salford", "Woking", "Leyton Orient", "Reading")
        ):
            issues.append({"class": "aleague_contamination", "home": home, "away": away, "competition": competition})
        if "18.09.2026" in blob:
            issues.append({"class": "date_participant", "home": home, "away": away, "competition": competition})
        if home.startswith(("GB ", "CZ ", "BR ")) or away.startswith(("GB ", "CZ ", "BR ")):
            issues.append({"class": "country_prefix", "home": home, "away": away, "competition": competition})
        if home.endswith(("GB", "CZ", "BR")) or away.endswith(("GB", "CZ", "BR")):
            if home not in {"SGB", "MCB"}:
                issues.append({"class": "country_suffix", "home": home, "away": away, "competition": competition})
        if "Ã" in blob or "Â" in blob:
            issues.append({"class": "mojibake", "home": home, "away": away, "competition": competition})
    return {
        "count": len(events),
        "issues": issues[:40],
        "issue_count": len(issues),
        "midnight_shown": midnight,
        "date_only": date_only,
        "top_competitions": sorted(comps.items(), key=lambda item: -item[1])[:15],
        "by_sport": sports,
        "markers": {
            marker: [
                {"home": home, "away": away, "competition": competition}
                for event in events
                for home, away, competition in [sides(event)]
                if marker.lower() in f"{home} {away}".lower()
            ][:8]
            for marker in MARKERS
        },
    }


def main() -> None:
    report: dict = {"generated_at": datetime.utcnow().isoformat() + "Z"}
    _, _, health, elapsed, _ = fetch("/health")
    report["health"] = {"ms": round(elapsed * 1000), "body": health}
    report["bounds_today"] = list(js_bounds("2026-09-19"))
    for label, date_key in (
        ("yesterday", "2026-09-18"),
        ("today", "2026-09-19"),
        ("tomorrow", "2026-09-20"),
    ):
        date_from, date_to = js_bounds(date_key)
        _, nbytes, payload, elapsed, _ = fetch(
            "/sports-data/events",
            {"sport": "football", "date_from": date_from, "date_to": date_to},
        )
        scanned = scan(payload.get("events") or [])
        scanned["bytes"] = nbytes
        scanned["ms"] = round(elapsed * 1000)
        for status in ("live", "upcoming", "finished"):
            _, _, status_payload, status_ms, _ = fetch(
                "/sports-data/events",
                {
                    "sport": "football",
                    "status": status,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            )
            scanned[f"status_{status}"] = {
                "count": len(status_payload.get("events") or []),
                "ms": round(status_ms * 1000),
            }
        report[label] = scanned
    _, nbytes, payload, elapsed, _ = fetch("/sports-data/events", {"sport": "football"})
    report["unfiltered_football"] = {
        "count": len(payload.get("events") or []),
        "bytes": nbytes,
        "ms": round(elapsed * 1000),
        "issue_count": scan(payload.get("events") or []).get("issue_count"),
        "issues": scan(payload.get("events") or []).get("issues"),
        "markers": scan(payload.get("events") or []).get("markers"),
        "top_competitions": scan(payload.get("events") or []).get("top_competitions"),
    }
    date_from, date_to = js_bounds("2026-09-19")
    for competition in ("brazil-serie-a", "australia-a-league", "norway-eliteserien"):
        _, _, payload, elapsed, _ = fetch(
            "/sports-data/events",
            {
                "sport": "football",
                "competition": competition,
                "date_from": date_from,
                "date_to": date_to,
            },
        )
        events = payload.get("events") or []
        report[competition] = {
            "count": len(events),
            "ms": round(elapsed * 1000),
            "names": [sides(event)[:2] for event in events[:30]],
        }
    sports = [
        "football",
        "basketball",
        "tennis",
        "ice-hockey",
        "baseball",
        "american-football",
        "rugby",
        "cricket",
        "golf",
        "motorsport",
        "mma",
        "boxing",
        "volleyball",
        "handball",
        "snooker",
        "cycling",
        "australian-rules",
        "horse-racing",
        "darts",
        "formula-e",
    ]
    sport_counts = {}
    for sport in sports:
        _, _, payload, elapsed, _ = fetch(
            "/sports-data/events",
            {"sport": sport, "date_from": date_from, "date_to": date_to},
        )
        events = payload.get("events") or []
        sport_counts[sport] = {"count": len(events), "ms": round(elapsed * 1000), "issues": scan(events)["issue_count"]}
    report["multi_sport_today"] = sport_counts
    out = Path(__file__).resolve().parents[1] / "audit" / "integrity_prod_after.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "unfiltered_football"}, indent=2, ensure_ascii=False)[:12000])
    print("---unfiltered---")
    print(json.dumps(report["unfiltered_football"], indent=2, ensure_ascii=False)[:8000])
    print("wrote", out)


if __name__ == "__main__":
    main()
