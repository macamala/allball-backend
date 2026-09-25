"""Resolve retired football IDs before writes; never manufacture a replacement.

Public IDs are immutable while fingerprints can change after canonical repair.
An occupied deterministic ID is identity evidence to validate, not permission to
insert the same primary key again or to revive an observation-only row.
"""
from collector.keeper_revalidation import _same_pair
from collector.maintenance_policy import automatic_promotion_blocked
from collector.models import SportsEvent
from collector.normalize import fingerprint
from collector.public_keeper import public_keeper_for_alias
from collector.source_ids import id_for_family
from collector.util import load_json, parse_datetime, sha_id


class FootballIdentityConflict(ValueError):
    """Deterministic conflict, distinct from transient persistence failures."""


def _metadata(row):
    return [load_json(getattr(row, key, None), {}) or {}
            for key in ('extra_json', 'list_extra_json')]


def _pointers(row):
    values = {str(row.canonical_event_id)} if row.canonical_event_id else set()
    values.update(str(meta['canonical_event_id']) for meta in _metadata(row)
                  if meta.get('canonical_event_id'))
    if len(values) > 1:
        raise FootballIdentityConflict('contradictory_canonical_pointers')
    return next(iter(values), None)


def _manual(row):
    return any(meta.get('manual_hidden') or meta.get('do_not_restore') for meta in _metadata(row))


def _same_event(row, incoming):
    kickoff = parse_datetime(incoming.get('start_time'))
    return (row.sport_id == 'football'
            and row.competition_id == incoming.get('competition_key')
            and row.start_time is not None and kickoff is not None
            and abs((row.start_time - kickoff).total_seconds()) <= 180
            and _same_pair(row, incoming))


def football_write_target(db, incoming, existing):
    """Return the validated root, or explicitly quarantine an unresolved write.

    This does not edit any row, pointer, score, visibility flag or source ID.
    Non-football matching is unchanged. Ordinary already-matched public roots
    keep their existing matching policy; stricter proof applies to alias repair.
    """
    if incoming.get('sport') != 'football':
        return existing
    row = existing
    collision = row is None
    if collision:
        row = db.get(SportsEvent, sha_id('ninko-evt-', fingerprint(incoming)))
    if row is None:
        return None
    if _manual(row):
        raise FootballIdentityConflict('manual_visibility_policy')
    pointer = _pointers(row)
    retired = automatic_promotion_blocked(row)
    if not collision and not pointer and not retired:
        return row
    origin = row
    visited = set()
    while True:
        if row.event_id in visited or len(visited) >= 8:
            raise FootballIdentityConflict('cyclic_canonical_lineage')
        visited.add(row.event_id)
        if _manual(row) or not _same_event(row, incoming):
            raise FootballIdentityConflict('unsafe_canonical_identity')
        pointer = _pointers(row)
        if not pointer:
            break
        row = db.get(SportsEvent, pointer)
        if row is None:
            raise FootballIdentityConflict('missing_canonical_keeper')
    # Reverse collapsed_from lineage is already used by public legacy links.
    # It requires a unique visible keeper, same competition, ordered teams and
    # kickoff. Reuse it rather than inventing a second, less strict resolver.
    reverse = public_keeper_for_alias(db, row)
    if reverse is not row:
        if _manual(reverse) or not _same_event(reverse, incoming) or _pointers(reverse):
            raise FootballIdentityConflict('unsafe_reverse_lineage')
        row = reverse
    if automatic_promotion_blocked(row):
        raise FootballIdentityConflict('unresolved_retired_observation')
    if row is not origin and (row.display_eligible is False
                             or any(m.get('display_eligible') is False for m in _metadata(row))):
        raise FootballIdentityConflict('hidden_canonical_keeper')
    family = str(incoming.get('source_family') or '')
    sid = str(incoming.get('source_event_id') or '')
    known = id_for_family(load_json(row.extra_json, {}) or {}, family)
    if known and sid and str(known) != sid:
        raise FootballIdentityConflict('conflicting_family_event_id')
    return row
