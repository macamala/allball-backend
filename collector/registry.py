"""Canonical runtime competition/source registry.

Compiles discovery_inventory.COVERAGE (the research artifact) plus verified
competition IDs. Does not invent new providers or replace verified mappings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from collector.coverage import constraints_for
from collector.discovery_inventory import (
    COVERAGE,
    NON_OPERATIONAL_FAMILIES,
    _independent_family,
    _operational_family,
)
from collector.family_catalog import (
    CREDENTIAL_ENV,
    FAMILY_URLS,
    adapter_key_for,
    extra_config,
    infer_url,
    polling_class_for,
    source_type_for,
    verified_source_competition_id,
)
from collector.util import slugify
from sports_registry.competitions import all_competitions
from sports_registry.sports import get_sport

FEED_ONLY_FAMILIES: set = {"startgg"}

DEPRIORITIZE_FAMILIES = {
    "startgg",
    "afc-web",
    "plusliga-web",
    "nrl-web",
    "fortuna-liga-cz-web",
    "super-rugby-web",
    "lnr-web",
    "isl-web",
    "super-league-web",
    "a-league-web",
    "sackmann-tennis",
    "sanctioning-bodies",
    "usl-web",
    "nwsl-web",
    "denmark-superliga-web",
    "allsvenskan-web",
    "conmebol-web",
    "liga-mx-web",
    "caf-web",
}

PREFERRED_FALLBACK_PRIORITY = {
    "sportscore": 2,
    "wta-json": 2,
    "bbc-sport": 2,
    "openfootball": 2,
    "soccerway": 2,
    "aiff-web": 2,
    "rte-rugby": 2,
    "super-rugby-html": 2,
    "eliteprospects": 2,
    "volleyballworld": 2,
    "cev-competition-area": 2,
    "prod2-web": 2,
    "acb-web": 2,
    "formula-e-web": 2,
    "netballpass": 2,
    "world-netball-web": 2,
    "futsalplanet": 2,
    "gbgb-web": 2,
    "fis-web": 2,
    "eurohockey-web": 2,
    "ettu-web": 8,
    "nll-web": 2,
    "eurosport-volleyball": 2,
    "pcs-web": 2,
    "fcpro-web": 2,
    "gri-web": 2,
    "total-waterpolo": 2,
    "hbl-web": 2,
    "ibu-web": 2,
    "rte-cycling": 2,
    "world-athletics-web": 2,
    "nrl-draw-web": 2,
    "standardbred-canada-web": 2,
    "hrnsw-web": 2,
    "letrot-web": 2,
    "equidia-web": 2,
    "england-hockey-web": 2,
    "lacrosse-canada-web": 2,
    "fiaf2-web": 2,
    "fiaf3-web": 2,
    "fia-web": 3,
    "aso-letour": 2,
    "scottish-hockey-web": 3,
    "gpcqm-web": 3,
    "woodbine-mohawk-web": 3,
    "uefa-futsal-web": 2,
    "lnf-web": 2,
    "wikipedia-lnbp-web": 3,
    "diamond-league-pdf": 3,
    "tischtennislive": 2,
    "ttbl-web": 3,
    "wikipedia-all-england-web": 2,
    "wikipedia-uefa-futsal-web": 3,
    "wikipedia-lol-worlds-web": 3,
    "wikipedia-fifa-futsal-web": 2,
    "meadowlands-web": 2,
    "cetus-web": 3,
    "club-menangle-web": 3,
    "harrington-web": 3,
    "wikipedia-indonesia-open-web": 2,
    "kompas-web": 3,
    "cbf-fifa-futsal-web": 3,
    "afa-fifa-futsal-web": 4,
    "nordic-waterpolo-native": 2,
    "ettu-news-results": 2,
    "fftt-web": 3,
    "kpga-web": 2,
    "rocketleague-recaps": 2,
    "blizzard-owcs-recaps": 2,
    "world-aquatics-web": 2,
    "wikipedia-wa-wp-web": 3,
    "pgl-web": 2,
    "wikipedia-rlcs-web": 3,
    "wikipedia-vct-web": 3,
    "ewc-owcs-web": 3,
    "dttb-web": 3,
    "skidskytte-web": 3,
    "wikipedia-korean-tour-web": 3,
    "wikipedia-irish-greyhound-derby-web": 3,
    "wikipedia-owcs-world-finals-web": 3,
    "abc-sport": 2,
    "cue-tracker": 2,
    "sporting-life": 2,
    "opendota": 2,
    "lolesports-web": 2,
    "cdl-web": 2,
    "overwatch-esports-web": 2,
    "valorantesports-web": 2,
}


def _fit_source_id(value: str, limit: int = 80) -> str:
    from collector.ids import bound_source_key

    return bound_source_key("source", value, limit=limit)


def _source_id_original(family: str, source_name: str, competition_id: str, priority: int) -> str:
    label = slugify(source_name)[:48]
    family_slug = slugify(family)
    if label in {"", family_slug}:
        return f"{family_slug}:{competition_id}:{priority}"
    return f"{family_slug}:{label}:{competition_id}"


def _source_id(family: str, source_name: str, competition_id: str, priority: int) -> str:
    return _fit_source_id(_source_id_original(family, source_name, competition_id, priority))


def _enabled_row(row: dict) -> bool:
    if not row.get("technically_collectable"):
        return False
    if (row.get("independence_status") or "established") in {"unknown", "derived", "shared-upstream"}:
        if (row.get("coverage_scope") or "full") == "partial":
            return True
        if row.get("derived_from"):
            return False
    return True


def build_runtime_registry() -> Dict[str, Any]:
    catalog = all_competitions()
    competitions: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Dict[str, Any]] = {}
    mappings: List[Dict[str, Any]] = []

    for row in COVERAGE:
        if not row.get("technically_collectable"):
            continue
        competition_id = row["competition"]
        family = row["upstream_family"]
        sport_id = row["sport"]
        identity = catalog.get(competition_id) or {}
        sport = get_sport(sport_id) or {}
        competitions.setdefault(
            competition_id,
            {
                "competition_id": competition_id,
                "slug": identity.get("slug") or competition_id,
                "name": identity.get("name") or competition_id.replace("-", " ").title(),
                "official_name": identity.get("official_name") or identity.get("name") or competition_id,
                "sport": sport_id,
                "country_id": identity.get("country_id") or (row.get("country") if row.get("country") not in {"world", "europe"} else None),
                "region_id": identity.get("region_id") or row.get("country"),
                "gender": identity.get("gender"),
                "season": None,
                "event_model": sport.get("event_model") or "team_match",
                "enabled": True,
                "sources": [],
            },
        )
        orig = _source_id_original(family, row["source"], competition_id, int(row.get("priority_candidate") or 100))
        source_id = _fit_source_id(orig)
        coverage_scope = row.get("coverage_scope") or "full"
        constraints = constraints_for(competition_id, family)
        config = extra_config(family, competition_id)
        url = config.get("url") or infer_url(family, row["source"], row.get("probe") or "", sport_id)
        adapter_key = adapter_key_for(family, sport_id)
        family_url = FAMILY_URLS.get(family)
        if family_url and adapter_key == "generic-http":
            from urllib.parse import urlparse
            from collector.family_catalog import CANONICAL_HOST_FIX, _with_source_path

            inferred_host = (urlparse(url or "").netloc or "").lower().replace("www.", "")
            if inferred_host in CANONICAL_HOST_FIX:
                url = _with_source_path(CANONICAL_HOST_FIX[inferred_host], row.get("probe") or "", family)
            elif not url:
                url = _with_source_path(family_url, row.get("probe") or "", family)
        config["url"] = url
        if constraints:
            config["coverage_keywords"] = constraints.get("allow_keywords") or []
            config["deny_keywords"] = constraints.get("deny_keywords") or []
            config["coverage_notes"] = constraints.get("notes")
        cred_env = CREDENTIAL_ENV.get(family)
        operational = bool(_operational_family(row)) or (
            coverage_scope == "partial" and row.get("technically_collectable")
        )
        independent = bool(_independent_family(row))
        enabled_source = _enabled_row(row) and family not in NON_OPERATIONAL_FAMILIES and family not in FEED_ONLY_FAMILIES
        sources[source_id] = {
            "source_id": source_id,
            "source_id_original": orig,
            "display_name": row["source"],
            "kind": "registered",
            "enabled": enabled_source,
            "upstream_family": family,
            "source_type": source_type_for(row.get("collection_method") or "", family),
            "adapter_key": adapter_key,
            "requires_credentials": bool(cred_env),
            "credential_env": cred_env,
            "licensed": False,
            "attribution_required": True,
            "attribution_text": f"Sports data from {row['source']}.",
            "attribution_url": url,
            "license_name": f"reuse:{row.get('production_reuse_status') or 'unclear'}",
            "rate_limit_per_minute": 8 if polling_class_for(row) == "LIVE" else 4,
            "independence_status": row.get("independence_status") or "established",
            "derived_from": row.get("derived_from") or "",
            "sports_supported": [sport_id],
        }
        priority = int(row.get("priority_candidate") or 100)
        if family in DEPRIORITIZE_FAMILIES:
            priority = 90
        if family in PREFERRED_FALLBACK_PRIORITY:
            priority = min(priority, PREFERRED_FALLBACK_PRIORITY[family])
        mapping = {
            "competition_id": competition_id,
            "source_id": source_id,
            "priority": priority,
            "enabled": sources[source_id]["enabled"] and operational and family not in FEED_ONLY_FAMILIES,
            "coverage": coverage_scope,
            "coverage_notes": constraints.get("notes") or (row.get("probe") or "")[:400],
            "verification": row.get("probe") or "",
            "source_family": family,
            "source_type": sources[source_id]["source_type"],
            "adapter_key": adapter_key,
            "polling_class": polling_class_for(row),
            "source_competition_id": verified_source_competition_id(family, competition_id, row["source"])
            or competition_id,
            "source_config": config,
            "independence_status": row.get("independence_status") or "established",
            "derived_from": row.get("derived_from") or "",
            "independent": independent,
            "operational": operational,
            "reuse_status": row.get("production_reuse_status") or "unclear",
        }
        mappings.append(mapping)
        competitions[competition_id]["sources"].append(mapping)

    for item in competitions.values():
        item["sources"].sort(key=lambda row: (row["priority"], row["source_id"]))
        item["primary_source"] = next((row["source_id"] for row in item["sources"] if row["enabled"]), None)
        item["fallback_sources"] = [
            row["source_id"]
            for row in item["sources"]
            if row["enabled"] and row["source_id"] != item["primary_source"]
        ]

    return {
        "competitions": competitions,
        "sources": sources,
        "mappings": mappings,
        "counts": {
            "competitions": len(competitions),
            "sources": len(sources),
            "mappings": len(mappings),
            "enabled_mappings": sum(1 for row in mappings if row["enabled"]),
            "families": len({row["source_family"] for row in mappings}),
            "adapters": len({row["adapter_key"] for row in mappings}),
        },
    }


def competition_record(competition_id: str) -> Optional[Dict[str, Any]]:
    return build_runtime_registry()["competitions"].get(competition_id)


def validate_registry(registry: Optional[Dict[str, Any]] = None) -> List[str]:
    registry = registry or build_runtime_registry()
    errors: List[str] = []
    seen_maps = set()
    for mapping in registry["mappings"]:
        key = (mapping["competition_id"], mapping["source_id"])
        if key in seen_maps:
            errors.append(f"duplicate mapping {key}")
        seen_maps.add(key)
        if mapping["coverage"] not in {"full", "partial"}:
            errors.append(f"bad coverage {key}")
        if mapping["coverage"] == "partial" and mapping["source_family"] == "microplus-timing":
            notes = (mapping.get("coverage_notes") or "").lower()
            if "u20" not in notes and "world cup" not in notes:
                errors.append("microplus partial missing verified notes")
        source = registry["sources"].get(mapping["source_id"])
        if not source:
            errors.append(f"missing source {mapping['source_id']}")
            continue
        if not source.get("upstream_family"):
            errors.append(f"source missing family {mapping['source_id']}")
        if mapping["source_family"] != source["upstream_family"]:
            errors.append(f"family mismatch {mapping['source_id']}")
    if len(registry["competitions"]) < 180:
        errors.append("expected ~184 mapped competitions")
    return errors


def families_for_competition(competition_id: str) -> List[str]:
    record = competition_record(competition_id) or {}
    families = []
    seen = set()
    for row in record.get("sources") or []:
        if row.get("operational") and row["source_family"] not in seen:
            seen.add(row["source_family"])
            families.append(row["source_family"])
    return families
