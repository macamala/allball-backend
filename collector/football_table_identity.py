"""Resolve a native season/group leaf to its proven parent table, never by name.

Discovery only follows already stored numeric match identities. It cannot
change event IDs, groups, score, status, visibility or source permissions.
"""
from datetime import datetime, timedelta
import re
from collector.models import SportsEvent
from collector.source_ids import id_for_family
from collector.util import load_json, parse_datetime
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
        # A legacy mixed bucket may have a mapping left pointing at the other
        # category. The accepted native row, not the first mapping, owns scope.
        # Only checked native context resolving to THIS competition authorizes it.
        from collector.football_category import native_info
        from collector.fotmob_crosswalk import _fotmob_competition_identity
        info = native_info(meta)
        proved_scope = False
        if info and meta.get('source_competition_name'):
            native_key = _fotmob_competition_identity({'_league': {
                'id': row_leaf, 'parentLeagueId': parent or info['parent'],
                'name': meta['source_competition_name'], 'ccode': info['country']}})[0]
            if native_key != competition_key:
                continue
            proved_scope = True
        if parent and (row_leaf == leaf or (row_leaf and proved_scope)):
            leaf = row_leaf
            context = {**context, 'league_id': leaf}
            return {**context, 'parent_id': parent, 'leaf_id': leaf, 'teams': sides,
                    'match_id': mid, 'start_time': row.start_time.isoformat()}
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
                return {**context, 'parent_id': parent, 'leaf_id': actual_leaf, 'teams': teams,
                        'match_id': mid, 'start_time': row.start_time.isoformat()}
    return {**context, 'parent_id': leaf, 'leaf_id': leaf, 'teams': []}


def _current_fixture_witness(root, context):
    """A seasonal ID may use a stable single league table, but only when this
    response's selected season includes the exact known match and oriented IDs.
    Membership alone is not proof of a current season or a group.
    """
    details = root.get('details') or {}
    if not details.get('selectedSeason'):
        return False
    mid = numeric(context.get('match_id'))
    kickoff = parse_datetime(context.get('start_time'))
    teams = context.get('teams') or []
    if not mid or not kickoff or len(teams) != 2 or any(not numeric(t) for t in teams) or teams[0] == teams[1]:
        return False
    fixtures = root.get('fixtures') or {}
    matches = fixtures.get('allMatches') if isinstance(fixtures, dict) else None
    if not isinstance(matches, list):
        return False
    found = [m for m in matches if isinstance(m, dict) and numeric(m.get('id')) == mid]
    if len(found) != 1:
        return False
    match = found[0]
    actual = [numeric((match.get(side) or {}).get('id')) for side in ('home', 'away')]
    at = parse_datetime((match.get('status') or {}).get('utcTime'))
    return actual == [numeric(t) for t in teams] and at is not None and abs((at-kickoff).total_seconds()) <= 60


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
    if len(found) == 1:
        return {'details': details, 'table': [{'data': found[0]}]}
    if found:
        return None
    # Native daily boards use seasonal IDs (e.g. 938219); a plain league's
    # current table can carry its stable ID (108). Never apply this relaxation
    # to composite/multiple groups, playoffs, or an unproven season fixture.
    tables = root.get('table')
    if not isinstance(tables, list) or len(tables) != 1:
        return None
    entry = tables[0]
    node = entry.get('data') if isinstance(entry, dict) else None
    if (not isinstance(node, dict) or node.get('composite') or node.get('tables')
            or numeric(node.get('leagueId')) != parent
            or not isinstance(node.get('table'), dict)
            or not isinstance(node['table'].get('all'), list)
            or not _current_fixture_witness(root, context)):
        return None
    from collector.fotmob_tables import parse_tables
    members = {r.get('team_id') for r in parse_tables(root)}
    if not set(context['teams']).issubset(members):
        return None
    return root
