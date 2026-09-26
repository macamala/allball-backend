"""Read-only, season-scoped goals leaderboard from the verified competition root."""
import re
import time
from threading import RLock
from collections import OrderedDict
_CACHE = OrderedDict()
_LOCK = RLock()
_INFLIGHT = set()
from collector.util import isoformat
from datetime import datetime


def _integer(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
        return int(n) if n >= 0 and n.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def scorer_spec(native):
    parent = str(native.get('parent') or '')
    for spec in native.get('_scorer_specs') or []:
        participant = spec.get('participant') or {}
        if (participant.get('stat') or {}).get('name') != 'goals':
            continue
        url = str(spec.get('fetchAllUrl') or '')
        if re.fullmatch(r'https://data\.fotmob\.com/stats/'+re.escape(parent)+r'/season/\d+(?:/(?:Apertura|Clausura))?/goals\.json', url):
            return spec
    return None


def parse_scorers(root, native, spec):
    if not isinstance(root, dict):
        return []
    lists = [x for x in root.get('TopLists', []) if isinstance(x, dict) and x.get('StatName') == 'goals']
    if len(lists) != 1:
        return []
    members = {str(t.get('team_id')) for t in native.get('table_rows') or []}
    out, seen = [], set()
    for row in lists[0].get('StatList') or []:
        pid = str(row.get('ParticiantId') or row.get('ParticipantId') or '')
        tid = str(row.get('TeamId') or '')
        goals, rank = _integer(row.get('StatValue')), _integer(row.get('Rank'))
        if not pid.isdigit() or tid not in members or not row.get('ParticipantName') or goals is None or not rank:
            continue
        if pid in seen:
            return []  # Contradictory duplicates must not be summed as extra goals.
        seen.add(pid)
        out.append({'player_id': pid, 'name': row['ParticipantName'], 'team_id': tid,
                    'team': row.get('TeamName') or '', 'goals': goals, 'rank': rank,
                    'penalties': _integer(row.get('SubStatValue')),
                    'appearances': _integer(row.get('MatchesPlayed')),
                    'photo': f'https://images.fotmob.com/image_resources/playerimages/{pid}.png',
                    'team_logo': f'https://images.fotmob.com/image_resources/logo/teamlogo/{tid}.png'})
    top = spec.get('participant') or {}
    # Bind this feed to the top scorer in the very same verified season response.
    expected = next((r for r in out if r['player_id'] == str(top.get('id'))), None)
    if not expected or expected['goals'] != _integer((top.get('stat') or {}).get('value')):
        return []
    return sorted(out, key=lambda r: (r['rank'], -r['goals'], r['name']))


def scorers(db, key, *, season='', group='', getter=None):
    from collector.competition_hub import _native
    empty = {'available': False, 'competition_key': key, 'season': season or None, 'rows': [],
             'reason': 'verified_scorers_not_available'}
    if group:
        return {**empty, 'reason': 'group_scorers_not_verified'}
    native = _native(db, key, season, getter=getter)
    spec = scorer_spec(native)
    if not spec:
        return empty
    cache_key = (key, native.get('season'), spec['fetchAllUrl'],
                 str(spec.get('participant')), tuple(sorted(str(r.get('team_id')) for r in native.get('table_rows') or [])))
    now = time.monotonic()
    if getter is None:
        with _LOCK:
            cached = _CACHE.get(cache_key)
            if cached and cached[0] > now:
                return cached[1]
            if cache_key in _INFLIGHT or len(_INFLIGHT) >= 4:
                return {**empty, 'reason': 'refresh_in_progress'}
            _INFLIGHT.add(cache_key)
    try:
        from collector.http import fetch_url
        response = getter(spec['fetchAllUrl']) if getter else fetch_url(spec['fetchAllUrl'], timeout=6)
        rows = parse_scorers(response.payload, native, spec) if getattr(response, 'ok', False) else []
        payload = {**empty, 'available': bool(rows), 'rows': rows, 'season': native.get('season') or season,
                   'football_gender': {'female': 'women', 'male': 'men'}.get(native.get('_gender'), 'unknown'),
                   'checked_at': isoformat(datetime.utcnow()), 'reason': None if rows else empty['reason']}
        if getter is None:
            with _LOCK:
                _CACHE[cache_key] = (now + (300 if rows else 60), payload)
                while len(_CACHE) > 64:
                    _CACHE.popitem(last=False)
        return payload
    finally:
        if getter is None:
            with _LOCK:
                _INFLIGHT.discard(cache_key)
