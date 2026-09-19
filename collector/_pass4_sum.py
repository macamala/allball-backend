"""Summarize a smoke JSON without printing event payloads."""

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "smoke_pass4_targeted.json"
payload = json.load(open(path, encoding="utf-8"))
print("totals", payload.get("totals"))
print("empty", payload.get("empty_reasons"))
print("capability", payload.get("capability_totals"))
print("two", payload.get("capability_two_verified_families"), "one", payload.get("capability_one_verified_family"), "zero", payload.get("capability_zero"))
for row in payload.get("results") or []:
    if row.get("classification") not in {"WORKING_PRIMARY", "WORKING_FALLBACK", "WORKING_PARTIAL"} or row.get("capability_status") != "VERIFIED_OPERATIONAL":
        maps = row.get("mapping_results") or []
        brief = "; ".join(
            f"{item.get('family')} cap={item.get('capability')} label={item.get('label')} events={item.get('events')} empty={item.get('empty_reason')} err={item.get('error')}"
            for item in maps
        )
        print(
            f"{row.get('competition_id')} class={row.get('classification')} cap={row.get('capability_status')} window={row.get('window_status')} verified={row.get('verified_families')} {brief}"
        )
