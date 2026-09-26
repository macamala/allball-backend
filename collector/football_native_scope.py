"""Narrow native scope witnesses; never authorize by a copied provider ID alone."""
from collector.source_ids import id_for_family
from collector.util import load_json


def owned_pair(row, event, sid):
    rich = load_json(row.extra_json, {}) or {}
    if (not isinstance(event, dict) or not isinstance(rich, dict)
            or event.get('source_family') != 'fotmob' or rich.get('source_family') != 'fotmob'
            or not isinstance(sid, str) or not sid.isdigit() or int(sid) <= 0
            or id_for_family(rich, 'fotmob') != sid):
        return False
    sides = load_json(row.participants_json, {}) or {}
    if not isinstance(sides, dict):
        return False
    for side in ('home', 'away'):
        stored, incoming = sides.get(side), event.get(side)
        if not isinstance(stored, dict) or not isinstance(incoming, dict):
            return False
        left, right = stored.get('id'), incoming.get('id')
        if (isinstance(left, bool) or isinstance(right, bool) or
                not str(left or '').isdigit() or not str(right or '').isdigit()
                or int(left) <= 0 or str(left) != str(right)):
            return False
    return True


def same_ungrouped_parent(row, event, scope, leaf, sid):
    """An explicit ungrouped parent and its leaf for one exact native match.

    Group tables, inherited IDs and arbitrary competition names cannot use this
    bridge. Existing lifecycle, final-score, kickoff and tree checks still apply.
    """
    node = event.get('source_competition_context') or {}
    if not isinstance(node, dict):
        return False
    parents = {str(node[k]) for k in ('parentLeagueId', 'primaryId')
               if node.get(k) not in (None, '') and str(node[k]) != leaf}
    if (node.get('isGroup') is not False or node.get('groupName')
            or str(node.get('id') or '') != leaf or len(parents) != 1
            or scope not in parents or scope == leaf or event.get('source_group_id')
            or row.competition_id != event.get('competition_key')
            or not owned_pair(row, event, sid)):
        return False
    for attr in ('extra_json', 'list_extra_json'):
        meta = load_json(getattr(row, attr, None), {}) or {}
        if not isinstance(meta, dict):
            return False
        context = meta.get('source_competition_context') or {}
        if not isinstance(context, dict):
            return False
        if (meta.get('source_group_id') or context.get('isGroup')
                or context.get('groupName')):
            return False
        if context and str(context.get('id') or '') not in ('', scope, leaf):
            return False
    return True


def proven_womens_legacy_bucket(row, event, leaf, sid):
    """Resolve a native women's event stored in a men's domestic bucket.

    Both exact oriented native participant IDs and the same leaf must prove that
    this is a classification error, not a men's event with a borrowed source ID.
    """
    from collector.football_category import native_gender, canonical_gender
    from collector.competition_identity import canonical_country_matches
    rich = load_json(row.extra_json, {}) or {}
    return bool(
        native_gender(event.get('source_competition_context') or {}) == 'women'
        and canonical_gender(row.competition_id) == 'men'
        and canonical_country_matches(row.competition_id, event.get('country_id') or '')
        and str(rich.get('source_group_id') or rich.get('source_competition_id') or '') == leaf
        and owned_pair(row, event, sid)
    )
