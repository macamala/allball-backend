"""Do not join men's and women's club histories by an ambiguous shared name."""
import re
from collector.football_category import category_for_event, label_gender
from collector.participant_text import fold_for_identity
from collector.util import load_json


def row_category(row):
    return category_for_event(load_json(row.extra_json, {}) or {}, row.competition_id) if row.sport_id == 'football' else None


def has_exact_side(row, entity_key):
    sides = load_json(row.participants_json, {}) or {}
    return bool(entity_key and any(isinstance(side, dict) and str(side.get('id') or '') == entity_key for side in sides.values()))


def football_profile_category(rows, entity_key, name):
    explicit = label_gender(name)
    anchors = set()
    exact_unknown = False
    for row in rows:
        category = row_category(row)
        if category not in ('men', 'women', 'unknown'):
            continue
        for side in (load_json(row.participants_json, {}) or {}).values():
            if not isinstance(side, dict) or not entity_key or str(side.get('id') or '') != entity_key:
                continue
            actual = str(side.get('display_name') or side.get('name') or '')
            # The already verified native team ID permits this one decoration.
            clean = lambda s: re.sub(r'\s*\(W\)\s*$', '', s, flags=re.I) if category == 'women' else s
            if name and fold_for_identity(clean(name)) != fold_for_identity(clean(actual)):
                continue
            if category == 'unknown':
                exact_unknown = True
            else:
                anchors.add(category)
    if len(anchors) > 1 or (explicit and anchors and explicit not in anchors):
        return 'conflict'
    return next(iter(anchors)) if anchors else explicit or ('unknown' if exact_unknown else None)


def allowed_category(row, category, entity_key):
    if category == 'conflict':
        return False
    if category == 'unknown' and row.sport_id == 'football':
        return has_exact_side(row, entity_key) and row_category(row) == 'unknown'
    if category not in ('men', 'women') or row.sport_id != 'football':
        return True
    actual = row_category(row)
    return actual == category or (actual == 'unknown' and has_exact_side(row, entity_key))
