"""Resolve a native season/group leaf to its proven parent table, never by name.

Discovery only follows already stored numeric match identities. It cannot
change event IDs, groups, score, status, visibility or source permissions.
"""
from datetime import datetime, timedelta
import re
from collector.models import SportsEvent
from collector.source_ids import id_for_family
from collector.util import load_json
from collector.maintenance_policy import automatic_promotion_blocked
from collector.fotmob_rich import verified_detail_identity


def numeric(value):
    value = str(value or '')
    return value if re.fullmatch(r'\d{1,10}', value) else None


def resolve_context(db, competition_key, context, getter):
    leaf = numeric(context.get('league_id'))
    if not leaf:
        return None
    # IDs may be seasonal, not addressable league IDs. Use recent canonical
    # native evidence; never pull a table for an unrelated same-name league.
    now = datetime.utcnow()
    candidates = db.query(SportsEvent).filter(
        SportsEvent.competition_id == competition_key,
        SportsEvent.sport_id == 'football',
        SportsEvent.canonical_event_id.is_(None),
        SportsEvent.display_eligible.isnot(False),
        SportsEvent.start_time >= now-timedelta(days=7),
        SportsEvent.start_time <= now+timedelta(days=14),
    ).order_by(SportsEvent.updated_at.desc()).limit(12).all()
    fallback = None
    for row in candidates:
        meta = load_json(row.extra_json, {}) or {}
        if automatic_promotion_blocked(row) or any(
            (load_json(getattr(row, f, None), {}) or {}).get('display_eligible') is False
            for f in ('extra_json', 'list_extra_json')
        ):
            continue
        mid = numeric(id_for_family(meta, 'fotmob'))
        if not mid:
            continue
        parts = load_json(row.participants_json, {}) or {}
        sides = [numeric((parts.get(s) or {}).get('id')) for s in ('home','away')]
        parent = numeric(meta.get('source_parent_competition_id'))
        row_leaf = numeric(meta.get('source_group_id') or meta.get('source_competition_id'))
        if parent and row_leaf == leaf:
            return {**context, 'parent_id': parent, 'leaf_id': leaf, 'teams': sides}
        if fallback is None:
            fallback = (row, parts, mid)
    if fallback:
        row, parts, mid = fallback
        result = getter('https://www.fotmob.com/api/data/matchDetails?matchId='+mid)
        root = result.payload if getattr(result, 'ok', False) else None
        identity = {**parts, 'start_time': row.start_time.isoformat()}
        if isinstance(root, dict) and verified_detail_identity(root, mid, identity):
            general = root.get('general') or {}
            # The same match ID alone cannot authorize a different competition.
            actual_leaf = numeric(general.get('leagueId'))
            parent = numeric(general.get('parentLeagueId')) or actual_leaf
            if actual_leaf == leaf and parent:
                teams = [numeric((general.get(s+'Team') or {}).get('id')) for s in ('home','away')]
                return {**context, 'parent_id': parent, 'leaf_id': actual_leaf, 'teams': teams}
    return {**context, 'parent_id': leaf, 'leaf_id': leaf, 'teams': []}


def scoped_table(root, context):
    """Select the exact group subtree; a parent response is not a single table."""
    if not isinstance(root, dict):
        return None
    details = root.get('details') or {}
    parent, leaf = context['parent_id'], context['leaf_id']
    supplied = numeric(details.get('id'))
    if supplied and supplied != parent:
        return None
    # Existing plain-league contexts may have old payloads without details.id.
    if parent == leaf:
        return root
    if supplied != parent:
        return None
    found = []
    def walk(node):
        if isinstance(node, list):
            for item in node: walk(item)
        elif isinstance(node, dict):
            if numeric(node.get('leagueId')) == leaf and isinstance(node.get('table'), (dict,list)):
                found.append(node)
                return
            for key in ('data','table','tables'):
                if key in node: walk(node[key])
    walk(root.get('table'))
    if len(found) != 1:
        return None
    return {'details': details, 'table': [{'data': found[0]}]}
