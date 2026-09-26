"""Competition categories from explicit native identities, never guessed player sex.

The bounded catalog contains checked competition metadata, not result overrides.
Unknown categories remain unknown. Women's labels are also a negative safety
boundary: a substring such as 'FA Cup' cannot authorize the men's competition.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

_WOMEN = re.compile(r"(?:\b(?:women(?:['’]s|s)?|ladies|femenil|femenino|femenina|feminino|feminina|femminile|frauen|vrouwen|kvinner|wsl|nwsl)\b|\(w\))", re.I)
WOMEN_CANONICAL = {'australia-a-league-women', 'womens-super-league', 'usa-nwsl', 'football-friendlies-women'}


def label_gender(value):
    return 'women' if _WOMEN.search(str(value or '')) else None


def label_category_conflict(name, competition):
    # Called for known football canonicals only, not general sport categories.
    return bool(label_gender(name) and competition not in WOMEN_CANONICAL and not label_gender(competition))


@lru_cache(maxsize=1)
def _catalog():
    rows = json.loads(Path(__file__).with_name('football_category_catalog.json').read_text())['competitions']
    index = {}
    for parent, row in rows.items():
        for sid in [parent, *row.get('aliases', [])]:
            value = {**row, 'parent': parent}
            if sid in index and index[sid]['parent'] != parent:
                index[sid] = None
            else:
                index[sid] = value
    return index


def native_info(context):
    if not isinstance(context, dict):
        return None
    matches = [_catalog().get(str(context.get(k) or '')) for k in
               ('parentLeagueId', 'primaryId', 'source_parent_competition_id', 'id', 'source_competition_id', 'source_group_id')]
    matches = [m for m in matches if m]
    if not matches or len({m['parent'] for m in matches}) != 1:
        return None
    return matches[0]


def native_gender(context):
    row = native_info(context)
    return {'female': 'women', 'male': 'men'}.get((row or {}).get('gender'))


def category_for_event(extra, competition_key=''):
    family = str(extra.get('source_family') or '')
    if family == 'fotmob':
        supplied = native_gender(extra.get('source_competition_context') or extra)
        if supplied:
            return supplied
    return label_gender(extra.get('source_competition_name') or '') or label_gender(competition_key) or canonical_gender(competition_key) or 'unknown'


def public_category_projection(extra, country=''):
    """Keep an existing match visible while the normal worker repairs its bucket.
    Only a checked native female identity can leave a men's legacy bucket.
    No DB writes, replacement event IDs, or score mutations.
    """
    if extra.get('source_family') != 'fotmob':
        return None
    info = native_info(extra.get('source_competition_context') or extra)
    if not info or info['gender'] != 'female':
        return None
    from collector.fotmob_crosswalk import _fotmob_competition_identity
    name = str(extra.get('source_competition_name') or info['name'])
    context = {'id': extra.get('source_competition_id') or info['parent'],
               'parentLeagueId': info['parent'], 'name': name, 'ccode': info['country']}
    return _fotmob_competition_identity({'_league': context})[0]


def womens_marker_pair(actual, expected, *, female=False):
    """Allow the one observed '(W)' decoration only with equal native team IDs.
    Never ignore arbitrary team suffixes, age groups or reserve identities.
    """
    from collector.participant_alias import punctuation_identity_key
    for side in ('home', 'away'):
        a, b = actual.get(side) or {}, expected.get(side) or {}
        an, bn = str(a.get('name') or ''), str(b.get('name') or '')
        if not an or not bn:
            return False
        if punctuation_identity_key(an) == punctuation_identity_key(bn):
            continue
        ai, bi = str(a.get('id') or ''), str(b.get('id') or '')
        if not female or not ai.isdigit() or ai != bi:
            return False
        clean = lambda s: re.sub(r'\s*\(W\)\s*$', '', s, flags=re.I)
        if punctuation_identity_key(clean(an)) != punctuation_identity_key(clean(bn)):
            return False
    return True


@lru_cache(maxsize=256)
def canonical_gender(competition_key):
    """Alternate source IDs are not native IDs. Only an unambiguous, checked
    public competition identity may supply its category across source families.
    """
    if not competition_key:
        return None
    from collector.fotmob_crosswalk import _fotmob_competition_identity
    genders = set()
    for info in _catalog().values():
        if not info:
            continue
        context = {'id': info['parent'], 'name': info['name'], 'ccode': info['country']}
        key = _fotmob_competition_identity({'_league': context})[0]
        if key == competition_key:
            genders.add(info['gender'])
    return {'female': 'women', 'male': 'men'}.get(next(iter(genders))) if len(genders) == 1 else None


def competition_scope_candidates(db, competition_key):
    """Coarse SQL candidates for a public women's projection, NOT authorization.

    Legacy matches can still have a men's stored key until their ordinary worker
    update. Search the small list metadata for an exact competition label too.
    Every cross-key row must subsequently pass checked native projection and
    the existing visibility/source/season guards. No fuzzy names or DB writes.
    """
    from sqlalchemy import or_, and_
    from collector.models import SportsCompetition, SportsEvent
    direct = SportsEvent.competition_id == competition_key
    competition = db.get(SportsCompetition, competition_key)
    if (not competition or competition.sport_id != 'football' or
            not (label_gender(competition.name) or canonical_gender(competition_key) == 'women')):
        return direct
    literal = re.escape(json.dumps(str(competition.name)))
    pattern = r'"source_competition_name"\s*:\s*' + literal
    slim = SportsEvent.list_extra_json
    legacy = or_(slim.regexp_match(pattern),
        and_(or_(slim.is_(None), slim == '', slim == '{}'), SportsEvent.extra_json.regexp_match(pattern)))
    return or_(direct, legacy)
