"""Restore a hidden canonical keeper only after a matching current observation.

No broad visibility reset. Child observations stay hidden and retain their links.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict
from sqlalchemy.orm import Session
from collector.models import SportsEvent
from collector.util import dump_json, load_json, parse_datetime
from collector.enrichment import is_display_eligible, quality_flags_for_event
from collector.identity import mapped_ninko_id
from collector.participant_alias import names_equivalent
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra


def _same_pair(row: SportsEvent, incoming: Dict[str, Any]) -> bool:
    parts = load_json(row.participants_json, {}) or {}
    return all(
        names_equivalent(str((parts.get(side) or {}).get('name') or ''),
                         str((incoming.get(side) or {}).get('name') or ''))
        for side in ('home', 'away')
    )


def revalidate_current_keeper(db: Session, row: SportsEvent, incoming: Dict[str, Any], *, source_id: str) -> bool:
    """An accepted, exact-time scored observation can validate its existing root."""
    if row is None or row.canonical_event_id or row.sport_id != 'football':
        return False
    extra = load_json(row.extra_json, {}) or {}
    if row.display_eligible is not False and extra.get('display_eligible') is not False:
        return False
    if incoming.get('accepted') is not True or incoming.get('source_family') != 'fotmob':
        return False
    if incoming.get('sport') != row.sport_id or incoming.get('competition_key') != row.competition_id:
        return False
    if not is_display_eligible(incoming) or quality_flags_for_event(incoming):
        return False
    flags = set(extra.get('quality_flags') or [])
    if flags - {'duplicate_or_contaminated'} or extra.get('manual_hidden') or extra.get('do_not_restore'):
        return False
    if incoming.get('status') not in {'live', 'halftime', 'break', 'finished'}:
        return False
    score = incoming.get('score') or {}
    if any(type(score.get(side)) is not int or not 0 <= score[side] <= 15 for side in ('home', 'away')):
        return False
    now = datetime.utcnow()
    fetched = parse_datetime(incoming.get('source_fetch_time') or incoming.get('fetch_completed_at'))
    if fetched is None or not -60 <= (now-fetched).total_seconds() <= 180:
        return False
    kickoff = parse_datetime(incoming.get('start_time'))
    if kickoff is None or row.start_time is None or abs((kickoff-row.start_time).total_seconds()) > 60:
        return False
    if not timedelta(hours=-2) <= now-kickoff <= timedelta(hours=48):
        return False
    if not _same_pair(row, incoming):
        return False
    children = db.query(SportsEvent).filter_by(canonical_event_id=row.event_id).limit(16).all()
    lineage = {str(x) for x in extra.get('collapsed_from') or []}
    valid_children = [x for x in children if x.event_id in lineage and x.sport_id == row.sport_id
                      and x.competition_id == row.competition_id and _same_pair(x,incoming)
                      and x.start_time is not None and abs((x.start_time-kickoff).total_seconds()) <= 60]
    if not valid_children:
        return False
    mapped = mapped_ninko_id(db, 'event', source_id, incoming.get('source_event_id'))
    if mapped not in {row.event_id, *(x.event_id for x in valid_children)}:
        return False
    others = db.query(SportsEvent).filter(
        SportsEvent.competition_id == row.competition_id,
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.isnot(False),
        SportsEvent.start_time >= kickoff-timedelta(minutes=2),
        SportsEvent.start_time <= kickoff+timedelta(minutes=2),
    ).all()
    if any(x.event_id != row.event_id and _same_pair(x,incoming) for x in others):
        return False
    extra['quality_flags'] = []
    extra['display_eligible'] = True
    extra['quarantine_disposition'] = 'RESTORED_VERIFIED_CANONICAL'
    extra['keeper_revalidated_at'] = datetime.utcnow().isoformat()+'Z'
    row.display_eligible = True
    row.extra_json = dump_json(extra)
    store_list_extra(row,extra)
    note_list_invalidation(db,sport=row.sport_id,competition=row.competition_id,start_time=row.start_time)
    logging.getLogger(__name__).info('VERIFIED_CANONICAL_RESTORED event=%s source=%s', row.event_id, source_id)
    return True
