"""Read-only public event-detail consistency audit.

Flags contradictions. Does not repair.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.integrity import audit_event_detail_consistency

BASE = "https://allball-backend-production.up.railway.app"


def fetch(path: str, params: dict | None = None, timeout: int = 90):
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = BASE + path + query
    request = urllib.request.Request(url, headers={"User-Agent": "ninko-event-detail-audit"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def collect_event_ids(limit: int = 400) -> list[str]:
    ids: list[str] = []
    seen = set()
    for sport in ("tennis", "football", "basketball", "ice-hockey", "baseball"):
        payload = fetch("/sports-data/events", {"sport": sport, "limit": 120})
        for event in payload.get("events") or []:
            event_id = event.get("id") or event.get("event_id")
            if event_id and event_id not in seen:
                seen.add(event_id)
                ids.append(event_id)
            if len(ids) >= limit:
                return ids
    return ids


def main() -> None:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checked": 0,
        "flagged": 0,
        "tennis_checked": 0,
        "issues": [],
        "singles_sample": None,
        "doubles_sample": None,
    }
    started = time.perf_counter()
    ids = collect_event_ids()
    for event_id in ids:
        payload = fetch(f"/sports-data/matches/{urllib.parse.quote(event_id)}")
        event = payload.get("event") or payload.get("header") or {}
        flags = audit_event_detail_consistency(event, route_id=event_id)
        report["checked"] += 1
        if (event.get("sport") or "") == "tennis":
            report["tennis_checked"] += 1
            home = ((event.get("home") or {}).get("name") or "")
            if " / " not in home and not report["singles_sample"]:
                report["singles_sample"] = {
                    "id": event.get("id"),
                    "home": home,
                    "away": ((event.get("away") or {}).get("name") or ""),
                    "score": event.get("score"),
                    "periods": event.get("periods"),
                    "flags": flags,
                }
            if " / " in home and not report["doubles_sample"]:
                report["doubles_sample"] = {
                    "id": event.get("id"),
                    "home": home,
                    "away": ((event.get("away") or {}).get("name") or ""),
                    "score": event.get("score"),
                    "periods": event.get("periods"),
                    "flags": flags,
                }
        if flags:
            report["flagged"] += 1
            if len(report["issues"]) < 80:
                report["issues"].append({"id": event_id, "flags": flags})
    report["elapsed_s"] = round(time.perf_counter() - started, 2)
    out = Path(__file__).resolve().parents[1] / "audit" / "event_detail_consistency.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("checked", "flagged", "tennis_checked", "elapsed_s")}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
