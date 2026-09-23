"""Build the coverage ledger from the production API.

The public list is evidence that a canonical event is stored. Match detail
is evidence of classification rows. This script does not increment counters.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.verification_ledger import recompute_ledger

BASE = "https://allball-backend-production.up.railway.app"
OUT_JSON = ROOT / "artifacts" / "coverage_audit_2026-09-22.json"
OUT_MD = ROOT / "artifacts" / "coverage_audit_2026-09-22.md"


def get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "NinkoSportsCoverageAudit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    week = get("/sports-data/events?date_from=2026-09-16T00:00:00Z&date_to=2026-09-22T23:59:59Z")
    events = week.get("events") or []
    by_comp = defaultdict(list)
    for event in events:
        by_comp[event.get("competition_key") or event.get("competition")].append(event)
    from collector.matrix_guard import frozen_competition_ids

    for key in sorted(frozen_competition_ids()):
        if by_comp.get(key):
            continue
        try:
            older = get(
                f"/sports-data/events?competition={key}&date_from=2024-01-01T00:00:00Z&date_to=2026-12-31T23:59:59Z"
            )
        except Exception:
            continue
        older_events = older.get("events") or []
        if older_events:
            by_comp[key] = older_events[:1]
            continue
        try:
            undated = get(f"/sports-data/events?competition={key}")
        except Exception:
            continue
        classified = []
        for event in (undated.get("events") or [])[:8]:
            if event.get("classification"):
                classified.append(event)
                break
            try:
                detail = get(f"/sports-data/matches/{event['id']}").get("event") or {}
            except Exception:
                continue
            if detail.get("classification"):
                event = dict(event)
                event["classification"] = detail["classification"]
                classified.append(event)
                break
        if classified:
            by_comp[key] = classified[:1]
    evidence = {}
    for key, rows in by_comp.items():
        sample = rows[0]
        detail = {}
        try:
            detail = get(f"/sports-data/matches/{sample['id']}").get("event") or {}
        except Exception:
            detail = {}
        merged = dict(sample)
        if detail.get("classification"):
            merged["classification"] = detail["classification"]
            detail_coverage = detail.get("coverage") or (detail.get("sport_detail") or {}).get("coverage")
            if detail_coverage:
                merged["coverage"] = detail_coverage
        if key == "wec":
            summary_events = []
            for proof_id in ("ninko-evt-0e17b32f56dcc249bdbe", "ninko-evt-df411624488b495f83bf"):
                try:
                    summary_events.append(get(f"/sports-data/matches/{proof_id}").get("event") or {})
                except Exception:
                    continue
            if summary_events:
                evidence_extra = summary_events
            else:
                evidence_extra = None
        else:
            evidence_extra = None
        if detail.get("source_event_id"):
            merged["source_event_id"] = detail["source_event_id"]
        standings = []
        applicable = bool(sample.get("standings_available"))
        if applicable:
            try:
                table = get(f"/sports-data/standings?league={key}")
                standings = table.get("rows") or []
            except Exception:
                standings = []
        if evidence_extra:
            merged = dict(evidence_extra[0])
        evidence[key] = {
            "event": merged,
            "summary_events": evidence_extra,
            "standings": standings,
            "standings_applicable": applicable or bool(standings),
            "proof_source_path": f"/sports-data/matches/{sample['id']}",
            "proof_retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
    ledger = recompute_ledger(evidence)
    known = {row["competition_key"] for row in ledger["rows"]}
    supplemental = []
    for key, item in sorted(evidence.items()):
        if key in known or not key:
            continue
        event = item.get("event") or {}
        supplemental.append(
            {
                "competition_key": key,
                "note": "Production competition outside the frozen 180. Not used to shrink the denominator.",
                "canonical_proof_event_id": event.get("id"),
                "classification_row_count": len(event.get("classification") or []),
                "standings_row_count": len(item.get("standings") or []),
            }
        )
    ledger["supplemental_production_competitions"] = supplemental
    ledger["production_window"] = {
        "from": "2026-09-16",
        "to": "2026-09-22",
        "event_count": len(events),
        "duplicate_canonical_ids": len(events) - len({row.get("id") for row in events}),
    }
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    lines = [
        "# Coverage audit 2026-09-22",
        "",
        f"Competitions: {ledger['competition_count']}",
        f"Legacy overlay production_verified: {ledger['legacy']['production_verified']}",
        f"Legacy overlay standings PROVEN: {ledger['legacy']['standings_proven']}",
        "",
        "## Totals",
        "",
    ]
    for key, value in ledger["totals"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Rows", ""])
    for row in ledger["rows"]:
        lines.append(
            f"- {row['sport']} | {row['competition_key']} | {row['provider_independence']} | "
            f"{row['terms_status']} | event {row['production_event_status']} | "
            f"class {row['classification_status']} | standings {row['standings_status']} | "
            f"proof {row['canonical_proof_event_id'] or '-'} | blocker {row['blocker_code']}"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"window": ledger["production_window"], "totals": ledger["totals"], "legacy": ledger["legacy"]}, indent=2))


if __name__ == "__main__":
    main()
