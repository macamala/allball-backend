"""Capability vs snapshot vs discovery family count."""

import json
import sys
from collections import Counter

from collector.registry import build_runtime_registry

payload = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "smoke_pass5.json", encoding="utf-8"))
runtime = build_runtime_registry()
print("A capability", payload.get("capability_totals"))
print("two", payload.get("capability_two_verified_families"), "one", payload.get("capability_one_verified_family"))
print("partial", payload.get("capability_partial_only"), "zero", payload.get("capability_zero"))
print("B snapshot", payload.get("totals"))
print("empty", payload.get("empty_reasons"))

zero = [row for row in payload["results"] if not row.get("verified_families") and not row.get("partial_families")]
print("\nZERO-OPERATIONAL", len(zero))
for row in zero:
    maps = row.get("mapping_results") or []
    brief = " | ".join(
        f"{item.get('family')} {item.get('capability')}/{item.get('label')} e={item.get('events')} {item.get('empty_reason') or item.get('error') or ''}"
        for item in maps
    )
    disc = runtime["competitions"].get(row["competition_id"]) or {}
    families = []
    seen = set()
    for src in disc.get("sources") or []:
        fam = src.get("source_family")
        if fam in seen:
            continue
        seen.add(fam)
        families.append(f"{fam}:en={src.get('enabled')}")
    print(f"  {row['competition_id']} class={row['classification']} cap={row['capability_status']} disc=[{', '.join(families)}] :: {brief}")

print("\nDISCOVERY >=2 FAMILIES BUT ZERO RUNTIME")
for row in zero:
    cid = row["competition_id"]
    spec = runtime["competitions"].get(cid) or {}
    enabled_fams = []
    seen = set()
    for src in spec.get("sources") or []:
        if not src.get("enabled"):
            continue
        fam = src.get("source_family")
        if fam in seen:
            continue
        seen.add(fam)
        enabled_fams.append(fam)
    if len(enabled_fams) >= 2:
        print(f"  {cid} mapped={enabled_fams}")

print("\nSNAPSHOT non-working")
counts = Counter()
for row in payload["results"]:
    if row["classification"] not in {"WORKING_PRIMARY", "WORKING_FALLBACK", "WORKING_PARTIAL"}:
        counts[row["classification"]] += 1
        if row["classification"] in {"NETWORK_FAILURE", "RATE_LIMITED", "SOURCE_CHANGED"} or (
            row["classification"] == "NO_CURRENT_EVENTS" and row.get("empty_reason") == "PARSER_COULD_NOT_EXTRACT"
        ):
            print(f"  {row['competition_id']} {row['classification']} {row.get('empty_reason')} cap={row.get('capability_status')} verified={row.get('verified_families')}")

print("\nHEALTHY EMPTY sample")
healthy = [
    row for row in payload["results"]
    if row["classification"] == "NO_CURRENT_EVENTS" and row.get("empty_reason") == "SOURCE_HEALTHY_NO_EVENTS"
]
print("count", len(healthy), "ids", [row["competition_id"] for row in healthy[:8]])
