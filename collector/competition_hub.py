"""Competition-owned schedule/results and explicit match comparisons.

Canonical rows stay authoritative. Native season records are a read-only,
identity-checked supplement, never an importer or a way to revive hidden rows.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import re
import threading
import time
from sqlalchemy import or_
from collector.models import SportsCompetition, SportsEvent, SportsEventObservation
from collector.util import load_json, dump_json, parse_datetime, isoformat
from collector.source_ids import id_for_family
from collector.maintenance_policy import automatic_promotion_blocked
from collector.participant_alias import punctuation_identity_key
from collector.football_history import parse_history, public_history, known_native_rows, _score

_CACHE = OrderedDict()
_LOCK = threading.RLock()
_INFLIGHT = set()
MAX_ROWS = 2500
FINALS = {'finished', 'complete', 'final', 'ft', 'ended', 'aet', 'pen'}
LIVE = {'live', 'halftime', 'break'}


def label(value):
    return re.sub(r'\s+', ' ', str(value or '').strip().casefold())


def _numeric(value):
    text = str(value or '')
    return text if re.fullmatch(r'\d{1,12}', text) else None


def _pair_time(native, canonical, *, female=False):
    a, b = parse_datetime(native.get('start_time')), parse_datetime(canonical.get('start_time'))
    if not a or not b or abs((a-b).total_seconds()) > 60:
        return False
    from collector.football_category import womens_marker_pair
    return womens_marker_pair(native, canonical, female=female)


def _table_variant(root, venue):
    """Only supplied split tables; never synthesize standings from partial scores."""
    result = deepcopy(root)
    found = False
    def walk(node):
        nonlocal found
        if isinstance(node, list):
            for item in node: walk(item)
        elif isinstance(node, dict):
            table = node.get('table')
            if isinstance(table, dict) and isinstance(table.get('all'), list):
                split = table.get(venue)
                table['all'] = split if isinstance(split, list) else []
                found |= bool(split)
                return
            for key in ('table', 'tables', 'data'):
                if key in node: walk(node[key])
    walk(result.get('table'))
    if not found:
        return []
    from collector.fotmob_tables import parse_tables
    return parse_tables(result)


def _fetch_native(db, key, season, getter):
    from collector.standings_enrich import fotmob_standings_context, FOTMOB_LEAGUE
    from collector.football_table_identity import resolve_context, scoped_table, _current_fixture_witness
    from collector.fotmob_rich import verified_detail_identity
    from collector.fotmob_tables import parse_tables
    context = fotmob_standings_context(db, key)
    if not context:
        return {}
    context = resolve_context(db, key, context, getter)
    if not context:
        return {}
    response = getter(FOTMOB_LEAGUE.format(league_id=context['parent_id']))
    root = response.payload if getattr(response, 'ok', False) else None
    if not isinstance(root, dict):
        return {}
    details = root.get('details') or {}
    selected = str(details.get('selectedSeason') or '')
    if str(details.get('id') or '') != context['parent_id'] or not selected or (season and season != selected):
        return {}
    # Static catalog IDs and seasonal board IDs differ. Bind the returned
    # season to an actual stored numeric match, oriented names and kickoff.
    # No logo hint, guessed group or fuzzy name can authorize this witness.
    from collector.provider import _blocked_public_sources, _row_public_source_allowed
    blocked, blocked_families = _blocked_public_sources(db)
    matches = (root.get('fixtures') or {}).get('allMatches') or []
    indexed = {}
    for match in matches:
        if isinstance(match, dict) and _numeric(match.get('id')):
            indexed.setdefault(str(match['id']), []).append(match)
    witness = False
    candidates = db.query(SportsEvent).filter(SportsEvent.competition_id == key,
        SportsEvent.canonical_event_id.is_(None), SportsEvent.display_eligible.isnot(False),
        SportsEvent.start_time >= datetime.utcnow()-timedelta(days=7),
        SportsEvent.start_time <= datetime.utcnow()+timedelta(days=14)).order_by(SportsEvent.start_time).limit(80).all()
    for row in candidates:
        meta = load_json(row.extra_json, {}) or {}
        slim = load_json(row.list_extra_json, {}) or {}
        if (automatic_promotion_blocked(row) or meta.get('display_eligible') is False
                or slim.get('display_eligible') is False or not _row_public_source_allowed(row, blocked, blocked_families)):
            continue
        mid = id_for_family(meta, 'fotmob')
        found = indexed.get(mid, [])
        if len(found) != 1:
            continue
        match = found[0]
        source_parent = _numeric(meta.get('source_parent_competition_id'))
        source_leaf = _numeric(meta.get('source_group_id') or meta.get('source_competition_id'))
        if source_parent and source_parent != context['parent_id']:
            continue
        if context['parent_id'] != context['leaf_id'] and source_leaf and source_leaf != context['leaf_id']:
            continue
        native_event = {**{s: match.get(s) or {} for s in ('home','away')},
                        'start_time': (match.get('status') or {}).get('utcTime')}
        stored_event = {**(load_json(row.participants_json, {}) or {}), 'start_time': isoformat(row.start_time)}
        if not _pair_time(native_event, stored_event, female=details.get("gender") == "female"):
            continue
        candidate = {**context, 'match_id': mid, 'start_time': isoformat(row.start_time),
                     'teams': [str((match.get(s) or {}).get('id') or '') for s in ('home','away')]}
        if _current_fixture_witness(root, candidate):
            context, witness = candidate, True
            break
    scoped = scoped_table(root, context)
    if not witness or not scoped:
        return {}
    table_rows = parse_tables(scoped)
    if not table_rows:
        return {}
    members = {str(r.get('team_id')) for r in table_rows}
    table_labels = {label(r.get('group')) for r in table_rows if r.get('group')}
    tables = scoped.get('table') or []
    plain = len(tables) == 1 and isinstance(tables[0], dict) and isinstance(tables[0].get('data'), dict)
    data = tables[0].get('data') if plain else {}
    plain = plain and not data.get('composite') and not data.get('tables') and context['parent_id'] == str(data.get('leagueId'))
    # Composite parent tournaments need a supplied per-fixture group ID/label.
    # Team membership by itself cannot distinguish group play from a knockout.
    rows = []
    for match in ((root.get('fixtures') or {}).get('allMatches') or [])[:MAX_ROWS]:
        if not isinstance(match, dict) or not _numeric(match.get('id')):
            continue
        a, b = match.get('home') or {}, match.get('away') or {}
        if not all(_numeric(s.get('id')) and str(s.get('name') or '').strip() for s in (a, b)):
            continue
        if str(a['id']) == str(b['id']) or not {str(a['id']), str(b['id'])}.issubset(members):
            continue
        own_leaf = str(match.get('leagueId') or (match.get('league') or {}).get('id') or '')
        supplied_group = label(match.get('group') or match.get('groupName'))
        if not plain and not (own_leaf == context['leaf_id'] or (supplied_group and supplied_group in table_labels)):
            continue
        status = match.get('status') or {}
        at = parse_datetime(status.get('utcTime'))
        if not at:
            continue
        if status.get('awarded'):
            continue  # An awarded score is not a normally played historical result.
        if status.get('cancelled'):
            state, score = 'cancelled', None
        elif status.get('finished') is True:
            state, score = 'finished', _score(status.get('scoreStr'))
            if score is None:
                continue
        elif str((status.get('reason') or {}).get('short') or '').upper() in ('POSTP', 'PP', 'POSTPONED'):
            state, score = 'postponed', None
        elif status.get('started') is True:
            state, score = 'in_progress', _score(status.get('scoreStr'))
        else:
            state, score = 'scheduled', None
        sides = {s: {'id': str(match[s]['id']), 'name': str(match[s]['name']),
                      'logo': f"https://images.fotmob.com/image_resources/logo/teamlogo/{match[s]['id']}.png"}
                 for s in ('home', 'away')}
        rows.append({'id': None, 'key': 'reference:'+str(match['id']), '_native_id': str(match['id']),
                     'sport': 'football', 'competition_key': key, 'competition': details.get('name'),
                     'season': selected, 'event_family': 'team_match', **sides,
                     'start_time': isoformat(at), 'status': state, 'live': False,
                     'score': score or {'home': None, 'away': None}, 'round': str(match.get('round') or ''),
                     'group': match.get('group') or match.get('groupName'), 'details_available': False})
    duplicate_ids = {r['_native_id'] for r in rows if sum(x['_native_id'] == r['_native_id'] for x in rows) > 1}
    rows = [r for r in rows if r['_native_id'] not in duplicate_ids]
    if not rows:
        # A partial tournament parent must not impose its season on unrelated
        # already accepted groups. Without a verified schedule, retain the
        # canonical competition view rather than filtering it to an empty page.
        return {}
    return {'events': rows, 'season': selected, 'table_views': {v: _table_variant(scoped, v) for v in ('home', 'away')},
            'table_rows': table_rows, 'checked_at': isoformat(datetime.utcnow()), 'parent': context['parent_id'],
            '_scorer_specs': (root.get('stats') or {}).get('players') or [] if plain else [],
            '_gender': details.get('gender')}


def _native(db, key, season, getter=None):
    from collector.provider import _blocked_public_sources
    blocked, families = _blocked_public_sources(db)
    if 'fotmob' in families:
        return {}
    from collector.models import SportsSourceCompetition, SportsSource
    mappings = db.query(SportsSourceCompetition).filter_by(competition_id=key, enabled=True, upstream_family='fotmob').all()
    sources = {r.source_id: r for r in db.query(SportsSource).filter(SportsSource.source_id.in_([m.source_id for m in mappings])).all()}
    if not mappings or any(m.source_id in blocked or (m.source_id in sources and sources[m.source_id].enabled is False) for m in mappings):
        return {}
    cache_key = (key, season or '', tuple((m.source_id, m.source_competition_id) for m in mappings))
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(cache_key)
        if entry and now < entry['until']:
            return deepcopy(entry['value'])
        if cache_key in _INFLIGHT:
            return deepcopy(entry['value']) if entry and now-entry['at'] < 3600 else {}
        if len(_INFLIGHT) >= 4:
            return {}
        _INFLIGHT.add(cache_key)
    value = {}
    try:
        deadline = time.monotonic()+9
        from collector.http import fetch_url
        from collector.adapters import FetchResult
        def bounded(url):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return FetchResult(ok=False, error='competition read budget reached')
            return getter(url) if getter else fetch_url(url, timeout=min(4, remaining))
        value = _fetch_native(db, key, season, bounded)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Competition native read failed key=%s', key)
    finally:
        with _LOCK:
            _INFLIGHT.discard(cache_key)
            if not value and entry and now-entry['at'] < 3600:
                value = {**entry['value'], 'stale': True}
            _CACHE[cache_key] = {'at': now if value and not value.get('stale') else (entry['at'] if entry else now),
                                 'until': now+(120 if value and not value.get('stale') else 60), 'value': deepcopy(value)}
            _CACHE.move_to_end(cache_key)
            while len(_CACHE) > 48:
                _CACHE.popitem(last=False)
    return value


def hub(db, provider, key, *, group='', season='', getter=None):
    from collector.provider import _blocked_public_sources, _row_public_source_allowed, _list_public_event, _dedupe_public_fixture_rows
    competition = db.get(SportsCompetition, key)
    empty = {'available': False, 'competition': {'id': key}, 'events': [], 'teams': [], 'groups': [], 'table_views': {}}
    if competition is None or competition.sport_id != 'football':
        return empty
    empty['competition'].update(name=competition.name, sport='football', country_id=competition.country_id)
    blocked, families = _blocked_public_sources(db)
    # Preserve hidden/canonical metadata for source-supplement denial; public
    # payloads are still serialized through the existing canonical read policy.
    rows = db.query(SportsEvent).filter(SportsEvent.competition_id == key, SportsEvent.sport_id == 'football').order_by(
        SportsEvent.start_time.desc(), SportsEvent.event_id).limit(MAX_ROWS+1).all()
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    native = _native(db, key, season, getter)
    native_rows = native.get('events') or []
    mids = {r['_native_id'] for r in native_rows}
    known = known_native_rows(db, mids)
    public = []
    by_mid = {}
    native_by_id = {r['_native_id']: r for r in native_rows}
    # Stored native keys may normalize to the requested canonical competition.
    # Use the already checked global identity lookup, never a name-only search.
    # A matching record still must pass every visibility/source/group guard and
    # the existing public competition resolver below before entering this view.
    included = {row.event_id for row in rows}
    for mid, candidates in known.items():
        reference = native_by_id.get(mid)
        for candidate in candidates:
            if candidate.event_id in included or not reference:
                continue
            stored = {**(load_json(candidate.participants_json, {}) or {}),
                      'start_time': isoformat(candidate.start_time)}
            if not _pair_time(reference, stored, female=native.get('_gender') == 'female'):
                continue
            if len(rows) >= MAX_ROWS:
                truncated = True
                break
            rows.append(candidate)
            included.add(candidate.event_id)
    for row in rows:
        meta, slim = load_json(row.extra_json, {}) or {}, load_json(row.list_extra_json, {}) or {}
        if (row.canonical_event_id or row.display_eligible is False or automatic_promotion_blocked(row)
                or meta.get('display_eligible') is False or slim.get('display_eligible') is False
                or not _row_public_source_allowed(row, blocked, families)):
            continue
        payload = provider._to_normalized(row, include_detail=False, list_mode=True)
        if not payload:
            continue
        event = _list_public_event(payload)
        if event.get('competition_key') != key:
            continue
        mid = id_for_family(meta, 'fotmob')
        witness = native_by_id.get(mid)
        supplied_season = str(row.season or meta.get('source_season_name') or '')
        if witness and _pair_time(witness, event, female=native.get('_gender') == 'female'):
            supplied_season = witness['season']
            event['round'] = event.get('round') or witness.get('round')
        desired_season = season or native.get('season')
        if desired_season and supplied_season != desired_season:
            continue  # Missing season is not permission to use current games for an archive.
        event.update(key=row.event_id, season=supplied_season or None, details_available=True)
        public.append(event)
        if mid:
            by_mid[mid] = event
    public = _dedupe_public_fixture_rows(public, {key})
    for event in native_rows:
        mid = event['_native_id']
        if mid in by_mid:
            continue
        # A previously observed hidden/conflicting/wrong-scope native fixture
        # may NOT reappear through this read-only source supplement.
        if known.get(mid):
            continue
        if any(_pair_time(event, p, female=native.get('_gender') == 'female') for p in public):
            continue
        view = {k: v for k, v in event.items() if not k.startswith('_')}
        if native.get('stale') and view['status'] == 'in_progress':
            view.update(status='awaiting_confirmation', score={'home': None, 'away': None})
        public.append(view)
    groups = sorted({str(e.get('group') or '').strip() for e in public if e.get('group')})
    for row in native.get('table_rows') or []:
        if row.get('group') and row['group'] not in groups:
            groups.append(row['group'])
    if group:
        exact = label(group)
        public = [e for e in public if label(e.get('group')) == exact or
                  (not e.get('group') and label(competition.name) == exact)]
    public.sort(key=lambda e: (e.get('start_time') or '', e['key']))
    teams = {}
    for event in public:
        for side in ('home', 'away'):
            t = event.get(side) or {}
            if t.get('name'):
                tkey = str(t.get('id') or t.get('slug') or t['name'])
                teams[tkey] = {**t, 'key': tkey}
    return {**empty, 'available': True, 'events': public, 'teams': sorted(teams.values(), key=lambda t: t['name']),
            'groups': sorted(set(groups)), 'season': native.get('season') or season or None,
            'table_views': native.get('table_views') or {},
            'checked_at': native.get('checked_at') or isoformat(datetime.utcnow()),
            'coverage': {'listed': len(public), 'linked_match_details': sum(bool(r.get('id')) for r in public),
                         'native_season_schedule': bool(native_rows), 'truncated': truncated,
                         'stale': bool(native.get('stale')), 'scope': 'available_confirmed_records'}}


def comparison(db, provider, key, match_key, *, group='', season='', getter=None):
    board = hub(db, provider, key, group=group, season=season, getter=getter)
    selected = next((e for e in board['events'] if e['key'] == match_key), None)
    if not selected:
        return {'available': False, 'event': None, 'h2h': [], 'form': {}, 'reason': 'match_not_in_scope'}
    if selected.get('id'):
        event = provider.get_event(selected['id'])
        if not event or event.get('competition_key') != key:
            return {'available': False, 'event': None, 'h2h': [], 'form': {}}
        return {'available': True, 'event': selected, 'h2h': event.get('h2h') or [], 'form': event.get('form') or {}}
    mid = match_key.removeprefix('reference:')
    if not match_key.startswith('reference:') or not _numeric(mid):
        return {'available': False, 'event': None, 'h2h': [], 'form': {}}
    from collector.http import fetch_url
    from collector.fotmob_rich import verified_detail_identity
    result = getter('https://www.fotmob.com/api/data/matchDetails?matchId='+mid) if getter else fetch_url(
        'https://www.fotmob.com/api/data/matchDetails?matchId='+mid, timeout=6)
    root = result.payload if getattr(result, 'ok', False) else None
    if (not isinstance(root, dict) or not verified_detail_identity(root, mid, selected)
            or any(str((root.get('general', {}).get(s+'Team') or {}).get('id') or '') != str((selected.get(s) or {}).get('id') or '') for s in ('home', 'away'))):
        return {'available': True, 'event': selected, 'h2h': [], 'form': {}, 'reason': 'history_not_verified'}
    history = parse_history(root)
    ephemeral = SimpleNamespace(event_id=None, competition_id=key, start_time=parse_datetime(selected['start_time']),
        participants_json=dump_json({s: selected[s] for s in ('home', 'away')}),
        extra_json=dump_json({'source_event_ids': {'fotmob': mid}}))
    h2h, form = public_history(db, ephemeral, history)
    return {'available': True, 'event': selected, 'h2h': h2h, 'form': form}
