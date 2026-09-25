"""Bounded source-proven duplicate linking; no rehashing or fixture deletion."""
from datetime import datetime, timedelta
from collector.maintenance_policy import automatic_promotion_blocked
from collector.models import SportsEvent
from collector.participant_alias import punctuation_identity_key
from collector.source_ids import as_family_map, id_for_family
from collector.util import load_json, parse_datetime

LINKAGE_REVISION = 1


def fresh_evidence(event):
    at = parse_datetime(event.get('source_fetch_time'))
    return bool(at and -30 <= (datetime.utcnow()-at).total_seconds() <= 300)


def _visible(row):
    return (row.display_eligible is True and not automatic_promotion_blocked(row)
            and all((load_json(getattr(row, field, None), {}) or {}).get('display_eligible') is not False
                    for field in ('extra_json', 'list_extra_json')))


def compatible_peer(keeper, other, event):
    """Names are literal apart from punctuation, case and accent, not fuzzy."""
    if (keeper.event_id == other.event_id or not fresh_evidence(event)
            or not _visible(keeper) or not _visible(other)
            or keeper.sport_id != 'football' or other.sport_id != 'football'
            or keeper.competition_id != other.competition_id
            or keeper.competition_id != event.get('competition_key')
            or keeper.event_family != 'team_match' or other.event_family != 'team_match'):
        return False
    kickoff = parse_datetime(event.get('start_time'))
    if not kickoff or any(not row.start_time or abs((row.start_time-kickoff).total_seconds()) > 60
                          for row in (keeper, other)):
        return False
    for field in ('season', 'stage'):
        values = {str(getattr(row, field)).strip().casefold() for row in (keeper, other)
                  if getattr(row, field, None)}
        if len(values) > 1:
            return False
    parts = [load_json(row.participants_json, {}) or {} for row in (keeper, other)]
    for side in ('home', 'away'):
        keys = [punctuation_identity_key((p.get(side) or {}).get('name', '')) for p in parts]
        incoming_key = punctuation_identity_key((event.get(side) or {}).get('name', ''))
        if not all(keys) or keys[0] != keys[1] or keys[0] != incoming_key:
            return False
    meta = [load_json(row.extra_json, {}) or {} for row in (keeper, other)]
    sid = str(event.get('source_event_id') or '')
    if not sid or id_for_family(meta[0], 'fotmob') != sid:
        return False
    if id_for_family(meta[1], 'fotmob') not in (None, sid):
        return False
    maps = [as_family_map(m.get('source_event_ids')) for m in meta]
    if any(maps[0][family] != maps[1][family] for family in maps[0].keys() & maps[1].keys()
           if family != '_untyped'):
        return False
    # A contradictory completed result is evidence to review, not to hide.
    from collector.live_state import canonical_status
    for row in (keeper, other):
        score = load_json(row.score_json, {}) or {}
        if canonical_status(row.status) in {'finished', 'walkover', 'awarded'}:
            incoming_score = event.get('score') or {}
            if any(score.get(side) is not None and incoming_score.get(side) is not None
                   and score[side] != incoming_score[side] for side in ('home', 'away')):
                return False
    return True


def choose_indexed_keeper(rows, event):
    """Read-only plan for multiple exact source-ID roots, never a name guess."""
    if not 1 < len(rows) <= 4 or not fresh_evidence(event):
        return None
    sid = str(event.get('source_event_id') or '')
    if any(id_for_family(load_json(r.extra_json, {}) or {}, 'fotmob') != sid for r in rows):
        return None
    anchored = [r for r in rows if (load_json(r.extra_json, {}) or {}).get('collapsed_from')]
    if len(anchored) > 1:
        return None
    keeper = anchored[0] if anchored else min(rows, key=lambda r: r.event_id)
    return keeper if all(r is keeper or compatible_peer(keeper, r, event) for r in rows) else None


def link_accepted_duplicates(db, keeper, event):
    """Only after accepted ingestion, attach proven peers to the same stable ID."""
    if not fresh_evidence(event) or not _visible(keeper):
        return 0
    rows = db.query(SportsEvent).filter(
        SportsEvent.sport_id == 'football',
        SportsEvent.competition_id == keeper.competition_id,
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
        SportsEvent.start_time >= keeper.start_time-timedelta(seconds=60),
        SportsEvent.start_time <= keeper.start_time+timedelta(seconds=60),
        SportsEvent.event_id != keeper.event_id,
    ).order_by(SportsEvent.event_id).limit(9).all()
    if len(rows) > 8:
        return 0  # Bound work; never interpret a truncated peer set as complete.
    from collector.canonical_collapse import _collapse_pair
    from collector.cache import note_list_invalidation
    from collector.maintenance_policy import sync_public_visibility
    linked = []
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        if (extra.get('collapsed_from') or not compatible_peer(keeper, row, event)
                or db.query(SportsEvent.event_id).filter(SportsEvent.canonical_event_id == row.event_id).first()):
            continue  # Do not combine independent established canonical trees.
        if not _collapse_pair(db, keeper.event_id, row.event_id):
            raise RuntimeError('Verified fixture linking failed; retain observation transaction')
        linked.append(row.event_id)
    if linked:
        extra = load_json(keeper.extra_json, {}) or {}
        proofs = extra.get('fixture_linkage_proofs') or []
        proofs.append({'source_family': 'fotmob', 'source_event_id': event['source_event_id'],
                       'source_fetch_time': event.get('source_fetch_time'), 'linked_ids': linked})
        extra['fixture_linkage_proofs'] = proofs[-8:]
        sync_public_visibility(keeper, extra, True)
        for key in ('events_by_id', 'events_by_fp', 'events_by_comp', 'event_details'):
            db.info.pop(key, None)
        note_list_invalidation(db, sport='football', competition=keeper.competition_id,
                               start_time=keeper.start_time, scoreboard_visible=True)
        db.flush()
        import logging
        logging.getLogger(__name__).info('FOOTBALL_VERIFIED_LINK keeper=%s source_id=%s aliases=%s',
                                        keeper.event_id, event['source_event_id'], linked)
    return len(linked)
