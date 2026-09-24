"""Bounded public-HTTP audit. No credentials and no production writes."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import json

BASE = "https://allball-backend-production.up.railway.app"
OUT = Path("/tmp/score-public-audit")
OUT.mkdir(parents=True, exist_ok=True)
now = datetime.now(timezone.utc)
local = now.astimezone(ZoneInfo("Australia/Sydney"))
targets = [("live", BASE + "/sports-data/live?sport=football"),
           ("nations-standings", BASE + "/sports-data/standings?league=uefa-nations-league")]
for offset in (-1, 0):
    day = local.date() + timedelta(days=offset)
    start = datetime.combine(day, time(), tzinfo=local.tzinfo)
    end = start + timedelta(days=1, microseconds=-1)
    params = {"sport": "football", "date_from": start.astimezone(timezone.utc).isoformat(),
              "date_to": end.astimezone(timezone.utc).isoformat()}
    targets.append((str(day), BASE + "/sports-data/events?" + urlencode(params)))
for offset in (-1, 0):
    day = (now + timedelta(days=offset)).strftime("%Y%m%d")
    targets.append(("fotmob-" + day, "https://www.fotmob.com/api/data/matches?date=" + day))

def read(target):
    name, url = target
    started = datetime.now(timezone.utc)
    try:
        with urlopen(Request(url, headers={"User-Agent": "NinkoSports-Recovery-QA/1.0", "Accept": "application/json"}), timeout=25) as response:
            payload = json.loads(response.read())
            status = response.status
        record = {"url": url, "http_status": status, "fetched_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
    except Exception as exc:
        record = {"url": url, "error": type(exc).__name__, "message": str(exc)[:250]}
    record["elapsed_seconds"] = round((datetime.now(timezone.utc)-started).total_seconds(), 2)
    (OUT / (name + ".json")).write_text(json.dumps(record, ensure_ascii=False))
    return name, record

with ThreadPoolExecutor(max_workers=3) as pool:
    results = dict(pool.map(read, targets))
summary = {"checked_at": now.isoformat(), "sydney_date": str(local.date()), "responses": {}}
for name, record in results.items():
    data = record.get("payload")
    rows = (data.get("events") or data.get("matches") or []) if isinstance(data, dict) else []
    item = {k: record[k] for k in ("http_status", "elapsed_seconds", "error", "message") if k in record}
    if not name.startswith("fotmob") and "standings" not in name:
        item["events"] = len(rows)
        item["status_counts"] = dict(Counter(row.get("status") for row in rows))
        item["with_score"] = sum((row.get("score") or {}).get("home") is not None and (row.get("score") or {}).get("away") is not None for row in rows)
        item["samples"] = [{"id": row.get("id"), "home": row.get("home"), "away": row.get("away"), "status": row.get("status"), "score": row.get("score"), "start_time": row.get("start_time"), "updated_at": row.get("updated_at"), "competition": row.get("competition_key")} for row in rows[:10]]
    elif "standings" in name:
        item["payload_keys"] = list(data) if isinstance(data,dict) else type(data).__name__
    summary["responses"][name] = item
(OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False))
