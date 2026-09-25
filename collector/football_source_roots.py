"""Consolidate strict same-source roots split by a competition label change.

Planning is read-only. Apply only after normal ingestion accepts fresh evidence;
never reuse this for unrelated names, unknown quarantine or independent trees.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from collector.football_fixture_linkage import fresh_evidence
from collector.maintenance_policy import automatic_promotion_blocked, sync_public_visibility
from collector.models import SportsEvent
from collector.participant_alias import punctuation_identity_key
from collector.source_ids import as_family_map, id_for_family
from collector.util import load_json, parse_datetime

AUTO_FLAGS = frozenset({'duplicate_or_contaminated', 'competition_attribution_mismatch'})
SAFE_DISPOSITIONS = frozenset({'', 'RECOVERABLE_BY_LABELLED_RECRAWL', 'RECOVERED_REMAPPED',
                              'RECOVERED_LABEL_MATCH', 'RESTORED_VERIFIED_CANONICAL'})


@dataclass(frozen=True)
class SourceRootPlan:
    keeper_id: str
    peer_ids: tuple[str, ...]
    source_id: str
    leaf_id: str
    target: str
    typed_ids: tuple[str, ...]


def _metas(row):
    values = [load_json(getattr(row, key, None), {}) or {}
              for key in ('extra_json', 'list_extra_json')]
    return values if all(isinstance(m, dict) for m in values) else None


def _native_identity_proven(row, rich, event, leaf, sid):
    """Resolve only automatic ambiguity backed by the same provider's IDs.

    Historical source_event_ids can be inherited from another provider. Require
    native ownership and both oriented participant IDs as well as the match and
    exact competition leaf; a copied match ID alone is not fresh identity proof.
    """
    if (not fresh_evidence(event) or event.get('source_family') != 'fotmob'
            or rich.get('source_family') != 'fotmob'
            or id_for_family(rich, 'fotmob') != sid
            or str(rich.get('source_group_id') or rich.get('source_competition_id') or '') != leaf):
        return False
    parts = load_json(row.participants_json, {}) or {}
    if not isinstance(parts, dict):
        return False
    for side in ('home', 'away'):
        stored, incoming = parts.get(side) or {}, event.get(side) or {}
        if not isinstance(stored, dict) or not isinstance(incoming, dict):
            return False
        known, supplied = stored.get('id'), incoming.get('id')
        if (known in (None, '') or supplied in (None, '') or isinstance(known, bool)
                or isinstance(supplied, bool) or str(known) != str(supplied)):
            return False
    return True


def _safe_root(row, event, leaf, sid, *, require_typed=True):
    metas = _metas(row)
    if (not metas or automatic_promotion_blocked(row) or row.sport_id != 'football'
            or row.event_family != 'team_match'):
        return False
    for meta in metas:
        flags = meta.get('quality_flags') or []
        if (not isinstance(flags, list) or not all(isinstance(f, str) for f in flags) or set(flags)-AUTO_FLAGS or meta.get('collapsed_from')
                or meta.get('provider_conflicts')
                or (str(meta.get('quarantine_disposition') or '') not in SAFE_DISPOSITIONS
                    and not (meta.get('quarantine_disposition') == 'AMBIGUOUS'
                             and require_typed
                             and _native_identity_proven(row, metas[0], event, leaf, sid)))):
            return False
        known = id_for_family(meta, 'fotmob')
        if known and known != sid:
            return False
        group = str(meta.get('source_group_id') or '')
        if group and group != leaf:
            return False
    # Rich metadata must carry both the typed match ID and same leaf/group ID.
    # Merely sharing a parent league ID does not prove the same table/group.
    rich = metas[0]
    if require_typed and id_for_family(rich, 'fotmob') != sid:
        return False
    if not require_typed and (row.competition_id != event.get('competition_key')
            or row.display_eligible is not True or any(m.get('display_eligible') is False for m in metas)):
        return False
    scope = str(rich.get('source_group_id') or rich.get('source_competition_id') or '')
    if require_typed and scope != leaf:
        return False
    for meta in metas:
        # Source IDs belonging to another provider are not a contradictory
        # FotMob league ID, but also cannot authorize the required rich proof.
        if meta.get('source_family') == 'fotmob':
            mscope = str(meta.get('source_group_id') or meta.get('source_competition_id') or '')
            if mscope and mscope != leaf:
                return False
    kickoff = parse_datetime(event.get('start_time'))
    if not kickoff or not row.start_time or abs((row.start_time-kickoff).total_seconds()) > 60:
        return False
    parts = load_json(row.participants_json, {}) or {}
    for side in ('home', 'away'):
        key = punctuation_identity_key((event.get(side) or {}).get('name', ''))
        if not key or punctuation_identity_key((parts.get(side) or {}).get('name', '')) != key:
            return False
    # Do not merge a contradictory final, or a played match into a new fixture.
    from collector.live_state import canonical_status
    status = canonical_status(row.status)
    incoming = canonical_status(event.get('status'))
    if status not in {'scheduled', 'finished', 'live', 'halftime', 'break', 'stale'}:
        return False
    if incoming == 'scheduled' and status not in {'scheduled', 'stale'}:
        return False
    if status == 'finished':
        actual = load_json(row.score_json, {}) or {}
        supplied = event.get('score') or {}
        if any(actual.get(s) is not None and actual[s] != supplied.get(s) for s in ('home', 'away')):
            return False
    return True


def plan_source_roots(db, roots, event, *, public_peers=()):
    """Exact typed source identity plus same node, not fuzzy competition labels."""
    from collector.competition_identity import event_accepted_for_mapping
    from collector.live_state import canonical_status
    if not roots or not fresh_evidence(event):
        return None
    typed_ids = tuple(r.event_id for r in roots)
    roots = list(roots) + list(public_peers)
    if not 1 <= len(roots) <= 4 or len({r.event_id for r in roots}) != len(roots):
        return None
    if len(roots) == 1 and roots[0].display_eligible is not False:
        return None  # No promotion/link work for an already public singleton.
    node = event.get('source_competition_context') or {}
    sid, leaf = str(event.get('source_event_id') or ''), str(node.get('id') or '')
    target = str(event.get('competition_key') or '')
    if (event.get('source_family') != 'fotmob' or not sid or not leaf or not target
            or not event_accepted_for_mapping({**event, 'sport': 'football'}, target)[0]):
        return None
    status = canonical_status(event.get('status'))
    kickoff = parse_datetime(event.get('start_time'))
    if status == 'finished':
        scores = event.get('score') or {}
        if not kickoff or kickoff > datetime.utcnow() or any(type(scores.get(s)) is not int or not 0 <= scores[s] <= 15 for s in ('home', 'away')):
            return None
    elif status != 'scheduled' or not kickoff or kickoff <= datetime.utcnow():
        return None
    if any(not _safe_root(row, event, leaf, sid, require_typed=row.event_id in typed_ids) for row in roots):
        return None
    for key in ('season', 'stage'):
        values = {str(getattr(r, key)).strip().casefold() for r in roots if getattr(r, key, None)}
        if len(values) > 1:
            return None
    candidates = [r for r in roots if r.competition_id == target]
    if not candidates or any(r.competition_id != target and not r.competition_id.startswith('football-') for r in roots):
        return None  # Never replace an independent known domestic competition.
    maps = [as_family_map((_metas(r)[0]).get('source_event_ids')) for r in roots]
    for i, left in enumerate(maps):
        for right in maps[i+1:]:
            if any(left[k] != right[k] for k in left.keys() & right.keys() if k != '_untyped'):
                return None
    ids = [r.event_id for r in roots]
    if db.query(SportsEvent.event_id).filter(SportsEvent.canonical_event_id.in_(ids)).first():
        return None  # Independent child trees require a separate migration.
    keeper = min(candidates, key=lambda r: (r.display_eligible is not True, r.event_id))
    # Do not publish an additional representation when a same-pair public row
    # outside this proven set would remain unresolved (e.g. a parent-only row).
    candidates = _public_pair_rows(db, event)
    if candidates is None or any(r.event_id not in ids for r in candidates):
        return None
    return SourceRootPlan(keeper.event_id, tuple(sorted(r.event_id for r in roots if r is not keeper)), sid, leaf, target, typed_ids)


def _public_pair_rows(db, event):
    kickoff = parse_datetime(event.get('start_time'))
    if not kickoff:
        return None
    rows = db.query(SportsEvent).filter(
        SportsEvent.sport_id == 'football', SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.is_(True),
        SportsEvent.start_time >= kickoff-timedelta(seconds=60),
        SportsEvent.start_time <= kickoff+timedelta(seconds=60),
    ).order_by(SportsEvent.event_id).limit(129).all()
    if len(rows) > 128:
        return None  # Never treat a truncated candidate scan as complete.
    out = []
    for row in rows:
        parts = load_json(row.participants_json, {}) or {}
        if all(punctuation_identity_key((parts.get(side) or {}).get('name','')) ==
               punctuation_identity_key((event.get(side) or {}).get('name','')) for side in ('home','away')):
            out.append(row)
    return out


def plan_hidden_source_with_public_peer(db, roots, event):
    """Revalidate a hidden exact source root, retaining a proven public peer ID."""
    if len(roots) != 1 or roots[0].display_eligible is not False or not fresh_evidence(event):
        return None
    rows = _public_pair_rows(db, event)
    if rows is None:
        return None
    peers = [r for r in rows if r.event_id != roots[0].event_id]
    if any(r.competition_id != event.get('competition_key') for r in peers):
        return None
    return plan_source_roots(db, roots, event, public_peers=peers)


def apply_accepted_source_roots(db, plan, event):
    """Same transaction as accepted normal ingestion; old IDs become aliases."""
    from collector.flags import writes_enabled
    from collector.cache import note_list_invalidation
    from collector.canonical_collapse import _collapse_pair
    from collector.live_state import canonical_status
    if not writes_enabled() or not fresh_evidence(event):
        raise RuntimeError('Source root proof expired or writes disabled')
    keeper = db.get(SportsEvent, plan.keeper_id)
    rows = [keeper] + [db.get(SportsEvent, eid) for eid in plan.peer_ids]
    if any(row is None or not _safe_root(row, event, plan.leaf_id, plan.source_id, require_typed=row.event_id in plan.typed_ids) for row in rows):
        raise RuntimeError('Source roots changed after acceptance')
    expected = event.get('score') or {}
    def result_matches():
        score = load_json(keeper.score_json, {}) or {}
        return (canonical_status(keeper.status) == canonical_status(event.get('status'))
                and all(score.get(s) == expected.get(s) for s in ('home', 'away')))
    if not result_matches():
        raise RuntimeError('Normal ingestion did not retain the verified source result')
    for row in rows[1:]:
        if not _collapse_pair(db, keeper.event_id, row.event_id):
            raise RuntimeError('Source root alias link failed')
    if not result_matches():
        raise RuntimeError('Source root merge altered the accepted result')
    meta = load_json(keeper.extra_json, {}) or {}
    proofs = meta.get('source_root_proofs') or []
    proofs.append({'source_family': 'fotmob', 'source_event_id': plan.source_id,
                   'source_leaf_id': plan.leaf_id, 'source_fetch_time': event.get('source_fetch_time'),
                   'linked_ids': list(plan.peer_ids), 'target': plan.target})
    meta['source_root_proofs'] = proofs[-8:]
    meta['quality_flags'] = [f for f in meta.get('quality_flags', []) if f not in AUTO_FLAGS]
    meta['quarantine_disposition'] = 'RESTORED_VERIFIED_CANONICAL'
    sync_public_visibility(keeper, meta, True)
    for row in rows:
        note_list_invalidation(db, sport='football', competition=row.competition_id,
                               start_time=row.start_time, scoreboard_visible=True)
    for key in ('events_by_id', 'events_by_fp', 'events_by_comp', 'event_details'):
        db.info.pop(key, None)
    db.flush()
    logging.getLogger(__name__).info('FOOTBALL_SOURCE_ROOT_LINK keeper=%s source=%s aliases=%s',
                                    keeper.event_id, plan.source_id, list(plan.peer_ids))
    return len(plan.peer_ids)
