"""Production-wide Score Centre status/time/score audit. Read-only. No repairs."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sports_registry.sports import SPORTS

BASE = "https://allball-backend-production.up.railway.app"

REGRESSION_PAIRS = (
    ("Kaiserslautern", "Braunschweig"),
    ("Holstein Kiel", "Osnabrück"),
    ("Karlsruhe", "Nürnberg"),
    ("Viktoria Köln", "Ingolstadt"),
    ("Aachen", "Düsseldorf"),
    ("Stuttgart II", "Regensburg"),
    ("Havelse", "Fortuna Köln"),
    ("Hoffenheim II", "Meppen"),
)


def fetch(path: str, params: dict | None = None, timeout: int = 90):
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = BASE + path + query
    request = urllib.request.Request(url, headers={"User-Agent": "ninko-score-centre-audit"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _name(side) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "")
    return str(side or "")


def _score_pair(event):
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    return score.get("home"), score.get("away")


def collect_events() -> list[dict]:
    seen = {}
    days = []
    today = datetime.now(timezone.utc).date()
    for offset in range(-2, 4):
        days.append((today + timedelta(days=offset)).isoformat())
    for sport in [row["slug"] for row in SPORTS]:
        for day in days:
            try:
                payload = fetch("/sports-data/events", {"sport": sport, "date": day})
            except Exception:
                continue
            for event in payload.get("events") or []:
                event_id = event.get("id")
                if event_id:
                    seen[event_id] = event
        try:
            payload = fetch("/sports-data/live", {"sport": sport})
            for event in payload.get("events") or []:
                event_id = event.get("id")
                if event_id:
                    seen[event_id] = event
        except Exception:
            continue
    return list(seen.values())


def classify(event: dict, now: datetime) -> dict:
    status = str(event.get("status") or "").lower()
    live = status in {"live", "break", "halftime"}
    home, away = _score_pair(event)
    precision = event.get("start_precision") or ""
    start = event.get("start_time") or ""
    flags = []
    live_class = event.get("live_class") or ""
    if live and live_class == "UNPROVEN_LIVE":
        flags.append("UNPROVEN_LIVE")
    elif live and live_class == "STALE_LIVE":
        flags.append("STALE_LIVE")
    elif live and live_class == "STATUS_CONFLICT":
        flags.append("STATUS_CONFLICT")
    elif live and live_class == "CONFIRMED_LIVE":
        flags.append("CONFIRMED_LIVE")
    elif live:
        flags.append("PUBLIC_LIVE")
    if live and home is None and away is None:
        flags.append("LIVE_UNKNOWN_SCORE")
    if live and home == 0 and away == 0:
        flags.append("LIVE_EXACT_00")
    if status == "finished" and home is None and away is None:
        flags.append("FINISHED_MISSING_SCORE")
    if precision == "EXACT_TIME" and not start:
        flags.append("EXACT_TIME_MISSING_START")
    if precision in {"DATE_ONLY", "UNKNOWN"} and start and "T00:00" in str(start) and event.get("_rendered_clock"):
        flags.append("FAKE_TIME")
    if event.get("conflicts"):
        flags.append("STATUS_CONFLICT")
    return {
        "id": event.get("id"),
        "sport": event.get("sport"),
        "competition": event.get("competition") or event.get("competition_key"),
        "status": status,
        "precision": precision,
        "live_class": live_class,
        "source_family": event.get("source_family"),
        "home": _name(event.get("home")),
        "away": _name(event.get("away")),
        "score": {"home": home, "away": away},
        "flags": flags,
    }


def pair_match(event, left, right) -> bool:
    home = _name(event.get("home"))
    away = _name(event.get("away"))
    blob = f"{home} {away}".lower()
    return left.lower() in blob and right.lower() in blob


def main() -> None:
    now = datetime.now(timezone.utc)
    events = collect_events()
    rows = [classify(event, now) for event in events]
    by_sport = Counter(row["sport"] or "" for row in rows)
    by_status = Counter(row["status"] for row in rows)
    by_provider = Counter(row["source_family"] or "unknown" for row in rows)
    by_precision = Counter(row["precision"] or "missing" for row in rows)
    flag_counts = Counter(flag for row in rows for flag in row["flags"])
    sport_status = defaultdict(Counter)
    for row in rows:
        sport_status[row["sport"] or ""][row["status"]] += 1
    samples = {f"{a}-{b}": None for a, b in REGRESSION_PAIRS}
    for event in events:
        for a, b in REGRESSION_PAIRS:
            key = f"{a}-{b}"
            if samples[key] is None and pair_match(event, a, b):
                samples[key] = {
                    "id": event.get("id"),
                    "status": event.get("status"),
                    "live_class": event.get("live_class"),
                    "score": event.get("score"),
                    "start_time": event.get("start_time"),
                    "start_precision": event.get("start_precision"),
                }
    sports_audited = sorted({row["sport"] for row in rows if row["sport"]})
    missing_sports = [row["slug"] for row in SPORTS if row["slug"] not in sports_audited]
    report = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "total_public_events_audited": len(rows),
        "sports_with_samples": sports_audited,
        "sports_no_current_sample": missing_sports,
        "status_counts": dict(by_status),
        "status_counts_by_sport": {sport: dict(counts) for sport, counts in sport_status.items()},
        "status_counts_by_provider": dict(by_provider),
        "start_precision_counts": dict(by_precision),
        "confirmed_live": flag_counts.get("CONFIRMED_LIVE", 0) + flag_counts.get("PUBLIC_LIVE", 0),
        "unproven_live": flag_counts.get("UNPROVEN_LIVE", 0),
        "stale_live": flag_counts.get("STALE_LIVE", 0),
        "status_conflict": flag_counts.get("STATUS_CONFLICT", 0),
        "real_0_0": sum(1 for row in rows if row["score"]["home"] == 0 and row["score"]["away"] == 0),
        "live_unknown_score": flag_counts.get("LIVE_UNKNOWN_SCORE", 0),
        "finished_missing_score": flag_counts.get("FINISHED_MISSING_SCORE", 0),
        "exact_time_missing_start": flag_counts.get("EXACT_TIME_MISSING_START", 0),
        "regression_examples": samples,
        "flag_counts": dict(flag_counts),
        "elapsed_ms": None,
    }
    started = time.perf_counter()
    report["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    out = ROOT / "audit" / "score_centre_semantics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("total_public_events_audited", "confirmed_live", "unproven_live", "stale_live", "sports_no_current_sample")}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
