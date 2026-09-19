"""Bounded smoke test across enabled mapped competitions.

Does not hammer upstreams: one snapshot capability per mapping, cached by
adapter+league+URL, per-mapping request budget.
"""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional

from collector.adapters import AdapterNotRegistered, FetchRequest, make_adapter
from collector.capability_ledger import merge_capability
from collector.adapters_generic import classify_http
from collector.coverage import constraints_for, filter_partial_events
from collector.adapters_thesportsdb import reset_thesportsdb_cache
from collector.http import begin_budget, end_budget, family_host_blocked, host_is_blocked, reset_http_stats
from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition
from collector.production import bootstrap_registry, register_production_adapters
from collector.util import load_json


CLASSIFICATIONS = (
    "WORKING_PRIMARY",
    "WORKING_FALLBACK",
    "WORKING_PARTIAL",
    "NO_CURRENT_EVENTS",
    "CONFIG_MISSING",
    "RATE_LIMITED",
    "PARSE_FAILURE",
    "NETWORK_FAILURE",
    "SOURCE_CHANGED",
    "NO_VALID_FALLBACK",
    "OTHER_ERROR",
)

CAPABILITY_RANKS = {
    "VERIFIED_OPERATIONAL": 3,
    "PARTIAL_OPERATIONAL": 2,
    "RATE_LIMITED": 1,
    "CONFIG_MISSING": 1,
    "BROKEN": 0,
}

_RESULT_CACHE: Dict[tuple, object] = {}


def _result_for_source(source: SportsSource, mapping: SportsSourceCompetition, competition: SportsCompetition, capability: str):
    config = load_json(mapping.source_config_json, {}) or {}
    url = config.get("url") or ""
    cache_key = (source.adapter_key, mapping.source_competition_id or "", url, capability)
    if cache_key in _RESULT_CACHE:
        return _RESULT_CACHE[cache_key]
    request = FetchRequest(
        capability=capability,
        sport_id=competition.sport_id,
        competition_id=competition.competition_id,
        source_competition_id=mapping.source_competition_id or competition.competition_id,
        source_config=config,
        coverage_scope=mapping.coverage_scope or "full",
        upstream_family=mapping.upstream_family or source.upstream_family,
    )
    adapter = make_adapter(source.adapter_key, source.source_id)
    result = adapter.fetch(request)
    _RESULT_CACHE[cache_key] = result
    return result


def _capability_for_mapping(result, events, coverage: str) -> str:
    if getattr(result, "config_missing", False):
        return "CONFIG_MISSING"
    label = classify_http(result)
    if label == "RATE_LIMITED":
        return "RATE_LIMITED"
    if label in {"NETWORK_FAILURE", "SOURCE_CHANGED", "PARSE_FAILURE", "OTHER_ERROR"}:
        return "BROKEN"
    if events:
        return "PARTIAL_OPERATIONAL" if coverage == "partial" else "VERIFIED_OPERATIONAL"
    if result.ok and (result.empty_reason or "") == "PARSER_COULD_NOT_EXTRACT":
        return "BROKEN"
    if result.ok:
        return "PARTIAL_OPERATIONAL"
    return "BROKEN"


def classify_competition(db, competition: SportsCompetition, capability: str = "snapshot") -> Dict:
    mappings = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition.competition_id, enabled=True)
        .order_by(SportsSourceCompetition.priority.asc())
        .all()
    )
    if not mappings:
        return {
            "competition_id": competition.competition_id,
            "sport": competition.sport_id,
            "classification": "NO_VALID_FALLBACK",
            "events": 0,
            "capability_status": "BROKEN",
            "window_status": "NO_EVENTS",
            "operational_families": [],
            "mapping_results": [],
        }
    families_tried = []
    primary_family = mappings[0].upstream_family
    last_class = "NO_VALID_FALLBACK"
    events_count = 0
    used = None
    last_error = None
    empty_reason = None
    snapshot_locked = False
    mapping_results = []
    operational = {}
    ordered = list(mappings)
    if host_is_blocked("https://www.thesportsdb.com/"):
        ordered = sorted(ordered, key=lambda row: 1 if (row.upstream_family or "") == "thesportsdb" else 0)

    for mapping in ordered:
        source = db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
        if source is None or not source.enabled:
            continue
        family = mapping.upstream_family or source.upstream_family
        coverage = mapping.coverage_scope or "full"
        if family_host_blocked(family or ""):
            cap = merge_capability("RATE_LIMITED", competition_id=competition.competition_id, family=family or "", events=0)
            mapping_results.append(
                {
                    "family": family,
                    "source_id": source.source_id,
                    "capability": cap,
                    "events": 0,
                    "label": "RATE_LIMITED",
                    "empty_reason": None,
                    "error": "host cooldown",
                    "http_status": 429,
                }
            )
            operational[family] = cap
            families_tried.append(family)
            continue
        begin_budget(max_requests=8, max_seconds=18)
        try:
            result = _result_for_source(source, mapping, competition, capability)
        except AdapterNotRegistered:
            families_tried.append(family)
            mapping_results.append({"family": family, "capability": "BROKEN", "events": 0, "label": "OTHER_ERROR"})
            end_budget()
            continue
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            families_tried.append(family)
            mapping_results.append({"family": family, "capability": "BROKEN", "events": 0, "label": "OTHER_ERROR", "error": last_error})
            used = source.source_id
            end_budget()
            continue
        end_budget()
        events = list(result.events or [])
        if coverage == "partial":
            events = filter_partial_events(events, constraints_for(competition.competition_id, family or ""))
        label = classify_http(result)
        cap = _capability_for_mapping(result, events, coverage)
        cap = merge_capability(cap, competition_id=competition.competition_id, family=family or "", events=len(events))
        mapping_results.append(
            {
                "family": family,
                "source_id": source.source_id,
                "capability": cap,
                "events": len(events),
                "label": label,
                "empty_reason": result.empty_reason,
                "error": result.error,
                "http_status": result.http_status,
            }
        )
        best = operational.get(family)
        if best is None or CAPABILITY_RANKS.get(cap, 0) > CAPABILITY_RANKS.get(best, 0):
            operational[family] = cap
        families_tried.append(family)
        used = source.source_id
        if snapshot_locked:
            continue
        if result.ok and events:
            events_count = len(events)
            empty_reason = None
            if coverage == "partial":
                last_class = "WORKING_PARTIAL"
            elif family == primary_family:
                last_class = "WORKING_PRIMARY"
            else:
                last_class = "WORKING_FALLBACK"
            snapshot_locked = True
            continue
        if result.ok and not events:
            last_class = "NO_CURRENT_EVENTS"
            empty_reason = result.empty_reason or "SOURCE_HEALTHY_NO_EVENTS"
            continue
        last_class = label if label != "WORKING" else "OTHER_ERROR"
        last_error = result.error or last_error

    verified = [family for family, cap in operational.items() if cap == "VERIFIED_OPERATIONAL"]
    partial = [family for family, cap in operational.items() if cap == "PARTIAL_OPERATIONAL"]
    if verified:
        capability_status = "VERIFIED_OPERATIONAL"
    elif partial:
        capability_status = "PARTIAL_OPERATIONAL"
    elif operational and all(cap == "RATE_LIMITED" for cap in operational.values()):
        capability_status = "RATE_LIMITED"
    elif operational and all(cap == "CONFIG_MISSING" for cap in operational.values()):
        capability_status = "CONFIG_MISSING"
    else:
        capability_status = "BROKEN"

    return {
        "competition_id": competition.competition_id,
        "sport": competition.sport_id,
        "classification": last_class,
        "events": events_count,
        "active_source": used,
        "error": last_error,
        "empty_reason": empty_reason,
        "families_tried": families_tried,
        "capability_status": capability_status,
        "window_status": "HAS_EVENTS" if events_count else "NO_EVENTS",
        "operational_families": verified + partial,
        "verified_families": verified,
        "partial_families": partial,
        "mapping_results": mapping_results,
    }


def run_smoke(
    db,
    *,
    concurrency: int = 1,
    capability: str = "snapshot",
    limit: Optional[int] = None,
    competition_ids: Optional[Iterable[str]] = None,
) -> Dict:
    register_production_adapters()
    bootstrap_registry(db)
    db.commit()
    reset_http_stats()
    reset_thesportsdb_cache()
    _RESULT_CACHE.clear()
    competitions = (
        db.query(SportsCompetition)
        .filter_by(active=True, identity_only=False)
        .order_by(SportsCompetition.competition_id.asc())
        .all()
    )
    mapped = {
        row.competition_id
        for row in db.query(SportsSourceCompetition).filter_by(enabled=True).all()
    }
    competitions = [row for row in competitions if row.competition_id in mapped]
    if competition_ids is not None:
        wanted = set(competition_ids)
        competitions = [row for row in competitions if row.competition_id in wanted]
    if limit:
        competitions = competitions[:limit]
    rows: List[Dict] = []
    if concurrency <= 1:
        for competition in competitions:
            rows.append(classify_competition(db, competition, capability))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(classify_competition, db, competition, capability): competition.competition_id
                for competition in competitions
            }
            for future in as_completed(futures):
                try:
                    rows.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "competition_id": futures[future],
                            "classification": "OTHER_ERROR",
                            "error": str(exc),
                            "events": 0,
                            "capability_status": "BROKEN",
                            "window_status": "NO_EVENTS",
                        }
                    )
    totals = Counter(row["classification"] for row in rows)
    for key in CLASSIFICATIONS:
        totals.setdefault(key, 0)
    empty_reasons = Counter(row.get("empty_reason") for row in rows if row["classification"] == "NO_CURRENT_EVENTS")
    capability_totals = Counter(row.get("capability_status") for row in rows)
    two_ops = sum(1 for row in rows if len(row.get("verified_families") or []) >= 2)
    one_ops = sum(1 for row in rows if len(row.get("verified_families") or []) == 1)
    payload = {
        "competitions": len(rows),
        "totals": dict(totals),
        "empty_reasons": dict(empty_reasons),
        "capability_totals": dict(capability_totals),
        "capability_two_verified_families": two_ops,
        "capability_one_verified_family": one_ops,
        "capability_partial_only": sum(1 for row in rows if not row.get("verified_families") and row.get("partial_families")),
        "capability_zero": sum(1 for row in rows if not row.get("verified_families") and not row.get("partial_families")),
        "results": sorted(rows, key=lambda row: row["competition_id"]),
    }
    return payload


def main() -> None:
    from database import SessionLocal, engine
    from models import Base
    import collector.models  # noqa: F401
    import collector.http as httpmod
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="")
    parser.add_argument("--out", default="smoke_pass4.json")
    args = parser.parse_args()
    httpmod.DEFAULT_TIMEOUT = 12
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ids = [item.strip() for item in args.ids.split(",") if item.strip()] or None
        payload = run_smoke(db, concurrency=1, competition_ids=ids)
        print(
            json.dumps(
                {
                    "competitions": payload["competitions"],
                    "totals": payload["totals"],
                    "empty_reasons": payload["empty_reasons"],
                    "capability_totals": payload["capability_totals"],
                    "capability_two_verified_families": payload["capability_two_verified_families"],
                    "capability_one_verified_family": payload["capability_one_verified_family"],
                    "capability_partial_only": payload["capability_partial_only"],
                    "capability_zero": payload["capability_zero"],
                },
                indent=2,
            )
        )
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    finally:
        db.close()


if __name__ == "__main__":
    main()
