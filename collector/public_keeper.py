"""Read-only resolution of legacy football links from verified collapse lineage."""
from datetime import timedelta
from collector.enrichment import is_display_eligible
from collector.keeper_revalidation import _same_pair
from collector.models import SportsEvent
from collector.util import load_json


def public_keeper_for_alias(db, row):
    if row.sport_id != 'football' or row.start_time is None:
        return row
    extra = load_json(row.extra_json, {}) or {}
    if extra.get('manual_hidden') or extra.get('do_not_restore'):
        return row
    # Current canonical roots already carry their retired links. No extra query.
    if not row.canonical_event_id and extra.get('collapsed_from'):
        return row
    parts = load_json(row.participants_json, {}) or {}
    candidates = db.query(SportsEvent).filter(
        SportsEvent.event_id != row.event_id,
        SportsEvent.sport_id == row.sport_id,
        SportsEvent.competition_id == row.competition_id,
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
        SportsEvent.start_time >= row.start_time-timedelta(seconds=60),
        SportsEvent.start_time <= row.start_time+timedelta(seconds=60),
        SportsEvent.extra_json.contains(row.event_id),
    ).limit(8).all()
    valid = []
    for candidate in candidates:
        meta = load_json(candidate.extra_json, {}) or {}
        if row.event_id not in (meta.get('collapsed_from') or []):
            continue
        if meta.get('display_eligible') is False or meta.get('manual_hidden') or meta.get('do_not_restore'):
            continue
        cparts = load_json(candidate.participants_json, {}) or {}
        if not _same_pair(candidate, parts) or not is_display_eligible({**meta, **cparts, 'sport': candidate.sport_id, 'score':load_json(candidate.score_json, {}) or {}}):
            continue
        valid.append(candidate)
    # Ambiguous reverse links must never guess a different event.
    return valid[0] if len(valid) == 1 else row
