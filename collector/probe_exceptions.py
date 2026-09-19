"""Bounded live proof for exception families only. Sequential, cached, no 180 burst."""

from __future__ import annotations

import json
from pathlib import Path

from collector.adapters import FetchRequest, make_adapter
from collector.family_catalog import extra_config, infer_url
from collector.http import begin_budget, end_budget, reset_http_stats
from collector.production import register_production_adapters
from collector.registry import build_runtime_registry
from collector.source_matrix import ROOT, _strict_working_sample

PROOF = ROOT / "collector" / "proof_ledger.json"

SKIP_STATUS = {"WORKING", "RESTRICTED", "PARTIAL_WORKING"}
SKIP_FAMILY = {"thesportsdb", "bbc-sport", "espn-html", "liquipedia", "startgg", "openfootball", "openligadb"}


def _plausible(event: dict) -> bool:
    home = str(((event.get("home") or {}) if isinstance(event.get("home"), dict) else {}).get("name") or "").strip()
    away = str(((event.get("away") or {}) if isinstance(event.get("away"), dict) else {}).get("name") or "").strip()
    blob = f"{home} {away}".lower()
    if any(token in blob for token in ("cookie", "subscribe", "arrow_drop", "like us", "follow us", "cheval/", "horse name")):
        return False
    if away.lower() in {"vs", "v", "sex", "team", "home", "away"}:
        return False
    if len(home) < 3:
        return False
    if away and len(away) < 2:
        return False
    return True


def main() -> None:
    register_production_adapters()
    reset_http_stats()
    matrix = json.loads((ROOT / "source_matrix_final.json").read_text(encoding="utf-8"))
    runtime = build_runtime_registry()
    by_comp = runtime["competitions"]
    pairs = {}
    if PROOF.exists():
        try:
            pairs = json.loads(PROOF.read_text(encoding="utf-8")).get("pairs") or {}
        except (OSError, ValueError):
            pairs = {}
    cleaned = {}
    for key, row in pairs.items():
        if (row or {}).get("status") == "WORKING":
            sample = (row or {}).get("sample") or ""
            if " vs " in sample:
                home, away = sample.split(" vs ", 1)
                if not _plausible({"home": {"name": home}, "away": {"name": away}}):
                    continue
        cleaned[key] = row
    pairs = cleaned
    requests = 0
    for exc in matrix.get("exceptions") or []:
        cid = exc["competition"]
        rec = by_comp.get(cid) or {}
        for mapping in rec.get("sources") or []:
            if not mapping.get("enabled"):
                continue
            family = mapping.get("source_family") or ""
            if family in SKIP_FAMILY:
                continue
            key = f"{cid}|{family}"
            existing = pairs.get(key) or {}
            if existing.get("status") in SKIP_STATUS:
                continue
            status_now = exc["a_status"] if exc.get("provider_a") == family else exc.get("b_status")
            if status_now in {"RESTRICTED"} and family in {"afc-web", "plusliga-web", "super-rugby-web", "startgg"}:
                pairs[key] = {"status": "RESTRICTED", "events": 0, "reason": status_now}
                continue
            adapter_key = mapping.get("adapter_key") or "generic-http"
            config = dict(mapping.get("source_config") or extra_config(family, cid))
            if not config.get("url"):
                config["url"] = infer_url(family, family, "", rec.get("sport") or "")
            begin_budget(max_requests=8, max_seconds=25)
            try:
                adapter = make_adapter(adapter_key, f"probe-{family}")
                result = adapter.fetch(
                    FetchRequest(
                        capability="snapshot",
                        sport_id=rec.get("sport"),
                        competition_id=cid,
                        source_config=config,
                        upstream_family=family,
                    )
                )
            except Exception as exc_err:  # noqa: BLE001
                pairs[key] = {"status": "UNAVAILABLE", "events": 0, "reason": str(exc_err)[:300]}
                end_budget()
                requests += 1
                continue
            end_budget()
            requests += 1
            events = [
                event
                for event in list(result.events or [])
                if _plausible(event)
                and _strict_working_sample(
                    f"{((event.get('home') or {}) if isinstance(event.get('home'), dict) else {}).get('name')} vs {((event.get('away') or {}) if isinstance(event.get('away'), dict) else {}).get('name')}"
                )
            ]
            error = result.error or ""
            http_status = result.http_status
            if events:
                sample = events[0]
                pairs[key] = {
                    "status": "WORKING",
                    "events": len(events),
                    "reason": "canonical events from mapped public path",
                    "sample": f"{(sample.get('home') or {}).get('name')} vs {(sample.get('away') or {}).get('name')}",
                    "url": config.get("url"),
                    "http_status": http_status,
                    "verified_at": __import__("datetime").date.today().isoformat(),
                }
            elif http_status in {401, 403} or result.restricted:
                pairs[key] = {"status": "RESTRICTED", "events": 0, "reason": error or f"http {http_status}", "http_status": http_status}
            elif http_status in {404, 410}:
                pairs[key] = {"status": "SOURCE_CHANGED", "events": 0, "reason": error or f"http {http_status}", "http_status": http_status}
            elif "certificate" in error.lower() or "ssl" in error.lower():
                pairs[key] = {"status": "NETWORK_UNAVAILABLE", "events": 0, "reason": error[:300], "http_status": http_status}
            elif "timeout" in error.lower() or "getaddrinfo" in error.lower() or http_status == 0:
                pairs[key] = {"status": "NETWORK_UNAVAILABLE", "events": 0, "reason": error[:300], "http_status": http_status}
            elif result.ok:
                pairs[key] = {
                    "status": "EMPTY_ARCHIVE",
                    "events": 0,
                    "reason": result.empty_reason or "reachable; no extractable events in fixtures/results path",
                    "http_status": http_status,
                    "url": config.get("url"),
                }
            else:
                pairs[key] = {"status": "UNAVAILABLE", "events": 0, "reason": error[:300], "http_status": http_status}
            if requests >= 45:
                break
        if requests >= 45:
            break
    PROOF.write_text(json.dumps({"pairs": pairs, "requests": requests}, indent=2), encoding="utf-8")
    working = sum(1 for row in pairs.values() if row.get("status") == "WORKING")
    print(f"requests={requests} pairs={len(pairs)} working={working}")
    for key, row in sorted(pairs.items()):
        if row.get("status") == "WORKING":
            print("WORKING", key, row.get("events"), row.get("sample"))


if __name__ == "__main__":
    main()
