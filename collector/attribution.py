"""Discreet attribution records for legally required source credits.

Credits are never rendered as Live Scores branding. They are returned as a
flat list for a global Data Sources page/footer.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from collector.models import SportsEvent, SportsSource
from collector.util import load_json


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


def attribution_payload(db: Session, events: Optional[List[SportsEvent]] = None) -> Dict[str, Any]:
    source_ids: List[str] = []
    if events is None:
        items = [
            {
                "source_id": source.source_id,
                "text": source.attribution_text or source.display_name,
                "url": source.attribution_url,
                "license_name": source.license_name,
            }
            for source in db.query(SportsSource).filter_by(attribution_required=True).all()
        ]
    else:
        for event in events:
            if event.primary_source_id:
                source_ids.append(event.primary_source_id)
            source_ids.extend(load_json(event.contributing_sources_json, []) or [])
        items = credits_for_sources(db, source_ids)
    return {
        "items": items,
        "count": len(items),
        "message": (
            "Third-party data sources are credited here when legally required. "
            "NinkoSports does not display provider logos on Live Scores."
            if items
            else "No third-party sports-data sources currently require credit."
        ),
    }
