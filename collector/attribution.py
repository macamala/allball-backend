"""Discreet attribution records for legally required source credits.

Credits are never rendered as Live Scores branding. They are returned as a
flat list for a global Data Sources page/footer.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from collector.family_caps import family_caps
from collector.models import SportsEvent, SportsSource
from collector.util import load_json

# Public page: one row per provider family. Internal adapter/source rows stay in DB.
_PUBLIC_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "cricsheet": {
        "name": "Cricsheet",
        "description": "Ball-by-ball cricket data published under the Open Data Commons Attribution licence.",
        "url": "https://cricsheet.org/",
        "attribution_kind": "required",
    },
    "opendota": {
        "name": "OpenDota",
        "description": "Professional Dota 2 match data from the OpenDota API.",
        "url": "https://www.opendota.com/",
        "attribution_kind": "required",
    },
    "thesportsdb": {
        "name": "TheSportsDB",
        "description": "Community sports fixtures and results used under TheSportsDB terms.",
        "url": "https://www.thesportsdb.com/",
        "attribution_kind": "required",
    },
    "mlb-statsapi": {
        "name": "MLB",
        "description": "Official Major League Baseball public stats feed.",
        "url": "https://www.mlb.com/",
        "attribution_kind": "transparency",
    },
    "nhl-web": {
        "name": "NHL",
        "description": "Official National Hockey League public score feed.",
        "url": "https://www.nhl.com/",
        "attribution_kind": "transparency",
    },
    "sportscore": {
        "name": "SportScore",
        "description": "Live scores for selected competitions from SportScore public data.",
        "url": "https://sportscore.com/",
        "attribution_kind": "transparency",
    },
    "wta-json": {
        "name": "WTA",
        "description": "Women's Tennis Association public tournament data.",
        "url": "https://www.wtatennis.com/",
        "attribution_kind": "transparency",
    },
    "openligadb": {
        "name": "OpenLigaDB",
        "description": "Community football results from OpenLigaDB.",
        "url": "https://www.openligadb.de/",
        "attribution_kind": "transparency",
    },
    "fifa-digital": {
        "name": "FIFA",
        "description": "Public FIFA match calendar and live data.",
        "url": "https://www.fifa.com/",
        "attribution_kind": "transparency",
    },
}

_BLOCKED_PUBLIC_FAMILIES = {"espn-html"}
_AUDIT_MARKERS = (
    " json",
    " html",
    "reuse:",
    "widget",
    "scoreboard",
    "api v1",
    "standings+team",
    "parser",
    "adapter",
)


def _is_audit_copy(text: str) -> bool:
    blob = f" {text or ''}".lower()
    if blob.strip().startswith("sports data from"):
        return True
    return any(marker in blob for marker in _AUDIT_MARKERS)


def credits_for_sources(db: Session, source_ids: Iterable[str]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    items: List[Dict[str, Any]] = []
    for source_id in source_ids:
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        source = db.query(SportsSource).filter_by(source_id=source_id).first()
        if source is None or not source.attribution_required:
            continue
        items.append(
            {
                "source_id": source.source_id,
                "text": source.attribution_text or source.display_name,
                "url": source.attribution_url,
                "license_name": source.license_name,
            }
        )
    return items


def _family_for(source: SportsSource) -> str:
    return (source.upstream_family or source.source_id or "").strip()


def public_provider_items(db: Session) -> List[Dict[str, Any]]:
    """Deduplicated, human-readable providers for the public Data Sources page."""
    seen: Set[str] = set()
    items: List[Dict[str, Any]] = []
    sources = db.query(SportsSource).filter_by(enabled=True).all()
    sources.sort(key=lambda row: (_family_for(row), row.source_id))
    for source in sources:
        family = _family_for(source)
        if not family or family in seen:
            continue
        if family in _BLOCKED_PUBLIC_FAMILIES or family.startswith("wikipedia") or "wikipedia" in family:
            continue
        if family_caps(family).get("production_status") == "ACCESS_BLOCKED":
            continue
        spec = _PUBLIC_PROVIDERS.get(family)
        if spec is None:
            if not source.attribution_required:
                continue
            text = (source.attribution_text or source.display_name or "").strip()
            if not text or _is_audit_copy(text) or _is_audit_copy(source.display_name or ""):
                continue
            spec = {
                "name": text,
                "description": "",
                "url": source.attribution_url,
                "attribution_kind": "required",
            }
        seen.add(family)
        items.append(
            {
                "provider": spec["name"],
                "name": spec["name"],
                "text": spec["name"],
                "description": spec["description"],
                "url": spec["url"] or source.attribution_url,
                "attribution_kind": spec["attribution_kind"],
                "required": spec["attribution_kind"] == "required",
            }
        )
    kind_rank = {"required": 0, "transparency": 1}
    items.sort(key=lambda row: (kind_rank.get(row.get("attribution_kind") or "", 9), row.get("name") or ""))
    return items


def attribution_payload(db: Session, events: Optional[List[SportsEvent]] = None) -> Dict[str, Any]:
    catalog = public_provider_items(db)
    if events is not None:
        family_ids: Set[str] = set()
        for event in events:
            if event.primary_source_id:
                source = db.query(SportsSource).filter_by(source_id=event.primary_source_id).first()
                if source:
                    family_ids.add(_family_for(source))
            for source_id in load_json(event.contributing_sources_json, []) or []:
                source = db.query(SportsSource).filter_by(source_id=source_id).first()
                if source:
                    family_ids.add(_family_for(source))
        name_for = {fam: spec["name"] for fam, spec in _PUBLIC_PROVIDERS.items()}
        wanted = {name_for[fam] for fam in family_ids if fam in name_for}
        catalog = [row for row in catalog if row.get("name") in wanted]
    return {
        "items": catalog,
        "count": len(catalog),
        "message": (
            "NinkoSports combines sports information from multiple data providers and official public sources. "
            "Attribution is shown where required by the source."
            if catalog
            else "No third-party sports-data sources currently require credit."
        ),
    }
