"""Source registry helpers: collectability, credentials, family-aware fallbacks."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.coverage import constraints_for, context_matches_partial
from collector.limits import is_rate_limited
from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition
from collector.util import load_json
from collector.http import family_host_blocked, host_is_blocked
from sports_registry.providers import CAPABILITY_KEYS


def credentials_configured(source_id: str, credential_env: Optional[str] = None) -> bool:
    env_name = credential_env or f"NINKO_SOURCE_{source_id.upper().replace('-', '_')}_CREDENTIALS"
    return bool((os.getenv(env_name) or "").strip())


def source_collectable(source: SportsSource) -> bool:
    if not source.enabled:
        return False
    if source.public_branding_required:
        return False
    if source.licensed or source.requires_credentials:
        env_name = getattr(source, "credential_env", None)
        if not credentials_configured(source.source_id, env_name):
            return False
    return True


def source_config_missing(source: SportsSource) -> bool:
    if source.licensed or source.requires_credentials:
        env_name = getattr(source, "credential_env", None)
        return not credentials_configured(source.source_id, env_name)
    return False


def source_has_capability(source: SportsSource, mapping: SportsSourceCompetition, capability: str) -> bool:
    override = load_json(mapping.capabilities_json, None)
    caps = override if isinstance(override, dict) else load_json(source.capabilities_json, {}) or {}
    if not caps:
        return True
    return bool(caps.get(capability))


def source_supports_sport(source: SportsSource, sport_id: Optional[str]) -> bool:
    sports = load_json(source.sports_supported_json, None)
    if not sports or not sport_id:
        return True
    return sport_id in sports


def mapping_family(mapping: SportsSourceCompetition, source: SportsSource) -> str:
    return mapping.upstream_family or source.upstream_family or source.source_id


def independent_enough(mapping: SportsSourceCompetition) -> bool:
    if mapping.derived_from:
        return False
    status = (mapping.independence_status or "established").strip()
    if status in {"unknown", "derived", "shared-upstream"}:
        return (mapping.coverage_scope or "full") == "partial"
    return True


def partial_fallback_allowed(mapping: SportsSourceCompetition, source: SportsSource, context: Optional[str]) -> bool:
    scope = mapping.coverage_scope or "full"
    if scope != "partial":
        return True
    family = mapping_family(mapping, source)
    constraints = constraints_for(mapping.competition_id, family)
    config = load_json(mapping.source_config_json, {}) or {}
    if not constraints and not config.get("coverage_keywords"):
        return False
    if constraints:
        return context_matches_partial(context, constraints)
    blob = (context or "").lower()
    return any(str(item).lower() in blob for item in config.get("coverage_keywords") or [])


def ordered_sources(
    db: Session,
    competition_id: str,
    capability: str,
    *,
    now: Optional[datetime] = None,
    coverage_context: Optional[str] = None,
):
    mappings = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, enabled=True)
        .order_by(SportsSourceCompetition.priority.asc(), SportsSourceCompetition.id.asc())
        .all()
    )
    ready: List[Tuple[SportsSourceCompetition, SportsSource]] = []
    for mapping in mappings:
        source = db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
        if source is None:
            continue
        if source_config_missing(source):
            continue
        if not source_collectable(source):
            continue
        if not source_has_capability(source, mapping, capability):
            continue
        competition = db.query(SportsCompetition).filter_by(competition_id=competition_id).first()
        sport_id = competition.sport_id if competition else None
        if not source_supports_sport(source, sport_id):
            continue
        if is_rate_limited(db, source.source_id, now=now):
            continue
        family = mapping_family(mapping, source)
        if family_host_blocked(family):
            continue
        attr = source.attribution_url or ""
        if attr and host_is_blocked(attr):
            continue
        if not independent_enough(mapping) and (mapping.coverage_scope or "full") != "partial":
            continue
        ready.append((mapping, source))

    if not ready:
        return [], []

    primary_family = mapping_family(ready[0][0], ready[0][1])
    primary = [(m, s) for m, s in ready if mapping_family(m, s) == primary_family]
    fallback = []
    seen_families = {primary_family}
    for mapping, source in ready:
        family = mapping_family(mapping, source)
        if family == primary_family:
            continue
        if family in seen_families:
            continue
        if mapping.derived_from and mapping.derived_from in seen_families:
            continue
        if (mapping.coverage_scope or "full") == "partial":
            if not partial_fallback_allowed(mapping, source, coverage_context):
                continue
        fallback.append((mapping, source))
        seen_families.add(family)
    return primary, fallback


def plan_sources(
    db: Session,
    competition_id: str,
    capability: str,
    *,
    now: Optional[datetime] = None,
    coverage_context: Optional[str] = None,
) -> Dict[str, List[Tuple[SportsSourceCompetition, SportsSource]]]:
    primary, fallback = ordered_sources(
        db, competition_id, capability, now=now, coverage_context=coverage_context
    )
    return {"primary": primary, "fallback": fallback}


def empty_capability_map() -> Dict[str, bool]:
    return {key: False for key in CAPABILITY_KEYS}
