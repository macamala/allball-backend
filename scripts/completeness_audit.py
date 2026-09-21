"""CLI for the 180-competition scoreboard completeness auditor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.completeness_audit import audit_production, freeze_state, write_artifact
from collector.matrix_guard import matrix_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://allball-backend-production.up.railway.app")
    parser.add_argument("--tz-offset", type=int, default=10)
    parser.add_argument("--upstream", action="store_true")
    parser.add_argument("--out", default="audit/completeness_180.json")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.freeze_only:
        payload = {"freeze": freeze_state(args.base), "matrix": matrix_status()}
        path = root / "audit" / "completeness_freeze.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(path)
        print(json.dumps(payload["matrix"], indent=2))
        return
    payload = audit_production(args.base, tz_offset_hours=args.tz_offset, fetch_upstream=args.upstream)
    out = root / args.out
    write_artifact(payload, out)
    print(out)
    print(json.dumps({"totals": payload.get("totals"), "errors": payload.get("errors"), "dates": payload.get("dates_checked")}, indent=2))


if __name__ == "__main__":
    main()
