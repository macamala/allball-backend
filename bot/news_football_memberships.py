"""News menu evidence from existing public standings/fixtures, never ingestion.

A read-only GET refreshes a short-lived club catalogue. It is menu metadata,
not a fact source for an AI article, and cannot publish or admit any story.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, date
import json
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)
ROOT = Path(__file__).parent
PUBLIC_API = 'https://allball-backend-production.up.railway.app'
CATALOG = json.loads((ROOT / 'news_football_leagues.json').read_text())
DOMESTIC = {row['league']: row for row in CATALOG
            if row['country'] != 'international' and (row['tier'] in (1, 2) or row['league'] in {'usa-nwsl', 'england-womens-super-league', 'australia-a-league-women'})}
# Explicit aliases verified against the public football competition registry.
ALIASES = {
    'japan-j1-league': 'japan-j1', 'south-korea-k-league-1': 'korea-k-league-1',
    'australia-a-league-men': 'australia-a-league', 'usa-mls': 'mls',
    'argentina-liga-profesional': 'argentina-primera', 'hungary-nb-1': 'hungary-nb-i',
    'romania-liga-1': 'romania-superliga', 'england-womens-super-league': 'womens-super-league',
}
FALLBACKS = {
    'italy-serie-b': 'football-ita-serie-b', 'france-ligue-2': 'football-fra-ligue-2',
    'netherlands-eerste-divisie': 'football-ned-eerste-divisie',
    'belgium-challenger-pro-league': 'football-bel-first-division-b',
    'scotland-championship': 'football-sco-championship', 'portugal-liga-2': 'football-por-liga-portugal-2',
    'turkey-first-league': 'football-tur-1-lig', 'greece-super-league-2': 'football-gre-super-league-2',
    'switzerland-challenge-league': 'football-sui-challenge-league', 'poland-first-league': 'football-pol-i-liga',
    'czech-second-league': 'football-cze-fnl', 'austria-second-league': 'football-aut-2-liga',
    'denmark-first-division': 'football-den-1-division', 'norway-first-division': 'football-nor-1-divisjon',
    'sweden-superettan': 'football-swe-superettan', 'finland-ykkosliiga': 'football-fin-ykk-sliiga',
    'romania-liga-2': 'football-rou-liga-ii', 'bulgaria-second-league': 'football-bul-second-professional-league',
    'hungary-nb-2': 'football-hun-nb-ii', 'brazil-serie-b': 'football-bra-s-rie-b',
    'argentina-primera-nacional': 'football-arg-primera-nacional', 'japan-j2-league': 'football-jpn-j-league-2',
    'south-korea-k-league-2': 'football-kor-k-league-2', 'saudi-first-division': 'football-ksa-saudi-first-division',
    'turkey-super-lig': 'football-tur-super-lig', 'greece-super-league': 'football-gre-super-league',
    'mexico-liga-expansion': 'football-mex-liga-de-expansion-mx-apertura',
}
_LOCK = threading.Lock()
_ENTRIES = {}
_LAST_REFRESH = float('-inf')
_RETRY_PENDING = {}
RETRY_SECONDS = 600
MAX_TRANSIENT_RETRIES = 3
TTL_SECONDS = 6 * 3600
MAX_AGE = timedelta(hours=72)


def parse_membership(league, data, *, now=None):
    """Reject wrong league/sport, stale/future records and non-current seasons."""
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError('Membership evidence requires a timezone-aware clock')
    if league not in DOMESTIC or not isinstance(data, dict):
        return None
    meta = data.get('competition')
    valid_keys = {league, ALIASES.get(league), FALLBACKS.get(league)} - {None}
    if not isinstance(meta, dict) or meta.get('id') not in valid_keys or meta.get('sport') != 'football':
        return None
    if data.get('stale') is not False or not data.get('available'):
        return None
    try:
        updated = datetime.fromisoformat(str(data.get('updated_at', '')).replace('Z', '+00:00'))
    except ValueError:
        return None
    if updated.tzinfo is None or not -timedelta(minutes=5) <= clock-updated <= MAX_AGE:
        return None
    season = str(data.get('season') or '')
    match = re.match(r'^(20\d{2})(?:[/\-](20\d{2}))?(?:\s+-\s+(?:Apertura|Clausura))?$', season)
    if not match:
        return None
    first, last = int(match[1]), int(match[2] or match[1])
    # A standings cache can continue to serve last season during summer. Do
    # not call those clubs current after the season, or extrapolate membership.
    current = clock.year == first if first == last else (
        last == first + 1 and date(first, 7, 1) <= clock.date() <= date(last, 6, 30))
    if not current:
        return None
    rows = data.get('rows')
    if not isinstance(rows, list):
        return None
    clubs = sorted({str(row.get('team') or '').strip() for row in rows if isinstance(row, dict)
                    and row.get('team_id') and str(row.get('team') or '').strip()})
    if not 4 <= len(clubs) <= 64:
        return None
    return {'clubs': clubs, 'season': season, 'data_key': meta['id'],
            'observed_at': updated.isoformat(), 'valid_from': (updated-timedelta(days=1)).date().isoformat(),
            'valid_until': (updated+MAX_AGE).date().isoformat(),
            'source': PUBLIC_API + '/sports-data/standings?' + urlencode({'league': meta['id']})}


def _public_get(league, key):
    # Fixed first-party host, no credentials, no redirects and no write routes.
    with httpx.Client(timeout=6.0, follow_redirects=False, trust_env=False) as client:
        response = client.get(PUBLIC_API + '/sports-data/standings', params={'league': key},
                              headers={'User-Agent': 'NinkoSports-News-Membership/1.0'})
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise ValueError('Membership response exceeds bounded size')
        return response.json()


def _transient_read_error(error):
    """Retry network errors, 429 and server failures, never invalid identities."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, (httpx.TimeoutException, httpx.NetworkError, ConnectionError, TimeoutError))


def refresh_football_news_memberships(*, now=None, get=None, get_fixtures=None, force=False):
    """Six-hour full refresh; bounded retries of failed leagues on normal cycles.

    Quiet/stale/wrong-scope sources do not trigger retries. A transient failure
    retries only the failed league (at 10, 20, 40 minute delays), up to three
    times before the next full refresh. Good current evidence remains intact.
    """
    global _ENTRIES, _LAST_REFRESH, _RETRY_PENDING
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError('Membership refresh requires a timezone-aware clock')
    if not _LOCK.acquire(blocking=False):
        return {'status': 'already_refreshing'}
    try:
        tick = time.monotonic()
        full = force or tick-_LAST_REFRESH >= TTL_SECONDS
        if full:
            targets = list(DOMESTIC)
            _LAST_REFRESH = tick
            _RETRY_PENDING = {}
        else:
            targets = [league for league, retry in _RETRY_PENDING.items()
                       if league in DOMESTIC and retry['due'] <= tick]
            if not targets:
                return {'status': 'cached', 'leagues': len(memberships_for_news(clock)),
                        'retry_pending': sorted(_RETRY_PENDING)}
        reader = get or _public_get
        # Injected offline table readers never cause implicit network I/O.
        fixture_reader = get_fixtures or (_public_fixture_get if get is None else None)
        def load(league):
            transient = None
            for key in dict.fromkeys([ALIASES.get(league, league), FALLBACKS.get(league)]):
                if not key:
                    continue
                try:
                    item = parse_membership(league, reader(league, key), now=clock)
                    if item:
                        return league, item, None
                except Exception as exc:
                    if _transient_read_error(exc):
                        transient = type(exc).__name__
                    log.debug('News membership read held league=%s error=%s', league, type(exc).__name__)
            if fixture_reader is not None:
                for key in dict.fromkeys([ALIASES.get(league, league), FALLBACKS.get(league)]):
                    if not key:
                        continue
                    try:
                        item = parse_fixture_membership(league, fixture_reader(league, key), now=clock)
                        if item:
                            return league, item, None
                    except Exception as exc:
                        if _transient_read_error(exc):
                            transient = type(exc).__name__
                        log.debug('News fixture membership held league=%s error=%s', league, type(exc).__name__)
            return league, None, transient
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix='news-membership') as pool:
            loaded = list(pool.map(load, targets))
        fresh, failures = {}, []
        for league, entry, transient in loaded:
            previous = _RETRY_PENDING.pop(league, None)
            if entry:
                fresh[league] = entry
                continue
            if transient:
                attempts = 0 if full else int((previous or {}).get('attempts', 0)) + 1
                if attempts < MAX_TRANSIENT_RETRIES:
                    _RETRY_PENDING[league] = {'attempts': attempts,
                                             'due': tick + RETRY_SECONDS * (2 ** attempts)}
                failures.append({'league': league, 'error': transient,
                                 'retry_scheduled': league in _RETRY_PENDING})
        # A brief outage preserves still-current evidence, never an unlimited stale roster.
        _ENTRIES = {**memberships_for_news(clock), **fresh}
        result = {'status': 'refreshed' if full else 'retried',
                  'leagues': len(_ENTRIES), 'fresh': len(fresh),
                  'clubs': sum(len(e['clubs']) for e in _ENTRIES.values()),
                  'fixture_rosters': sum(e.get('source_kind') == 'confirmed_recent_fixture_roster' for e in _ENTRIES.values()),
                  'fixture_roster_leagues': sorted(k for k, v in _ENTRIES.items()
                                                  if v.get('source_kind') == 'confirmed_recent_fixture_roster'),
                  'retry_pending': sorted(_RETRY_PENDING), 'read_failures': failures}
        log.info('News read-only football membership %s', result)
        return result
    finally:
        _LOCK.release()


def memberships_for_news(now=None):
    """No I/O in classification: return a bounded, non-mutable catalogue copy."""
    clock = now or datetime.now(timezone.utc)
    output = {}
    for league, entry in _ENTRIES.items():
        try:
            stamp = datetime.fromisoformat(entry['observed_at'])
            if -timedelta(minutes=5) <= clock-stamp <= MAX_AGE:
                output[league] = {**entry, 'clubs': list(entry['clubs'])}
        except (KeyError, ValueError, TypeError):
            pass
    return output


def _aware_stamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _current_named_season(value, clock):
    """Unknown season is not silently renamed; dated fixtures have a separate gate."""
    if value is None or value == '':
        return True
    match = re.fullmatch(r'(20\d{2})(?:[/\-](20\d{2}))?(?:\s+-\s+(?:Apertura|Clausura))?', str(value))
    if not match:
        return False
    first, last = int(match[1]), int(match[2] or match[1])
    return clock.year == first if first == last else (
        last == first + 1 and date(first, 7, 1) <= clock.date() <= date(last, 6, 30))


def parse_fixture_membership(league, data, *, now=None):
    """News-menu roster from recently updated, nearby confirmed public matches.

    NOT a standings table, complete season roster, result calculation or AI fact
    input. An absent season remains absent. Each retained match supplies its own
    exact competition, nearby kick-off and recent update evidence. A freshly
    served hub timestamp alone is never enough to freshen old sporting records.
    """
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError('Fixture membership requires a timezone-aware clock')
    if league not in DOMESTIC or not isinstance(data, dict):
        return None
    meta, coverage = data.get('competition'), data.get('coverage')
    valid_keys = {league, ALIASES.get(league), FALLBACKS.get(league)} - {None}
    if (not isinstance(meta, dict) or meta.get('id') not in valid_keys
            or meta.get('sport') != 'football' or data.get('available') is not True
            or not isinstance(coverage, dict) or coverage.get('stale') is not False):
        return None
    checked = _aware_stamp(data.get('checked_at'))
    if checked is None or not -timedelta(minutes=5) <= clock-checked <= timedelta(hours=1):
        return None
    rows = data.get('events')
    if not isinstance(rows, list) or len(rows) > 2500:
        return None
    women = league in {'england-womens-super-league', 'australia-a-league-women', 'usa-nwsl'}
    names, stamps, keys, seasons = set(), [], set(), set()
    for event in rows:
        if not isinstance(event, dict) or event.get('sport') != 'football' or event.get('competition_key') != meta['id']:
            continue
        key = event.get('key') or event.get('id')
        if not isinstance(key, str) or not key or key in keys:
            continue
        status = str(event.get('status') or '').lower()
        if status not in {'finished','complete','final','ft','ended','live','in_progress','halftime','scheduled','upcoming','not_started'}:
            continue
        start, updated = _aware_stamp(event.get('start_time')), _aware_stamp(event.get('updated_at'))
        if start is None or updated is None:
            continue
        if not clock-timedelta(days=21) <= start <= clock+timedelta(days=35):
            continue
        if not -timedelta(minutes=5) <= clock-updated <= MAX_AGE:
            continue
        if status in {'scheduled','upcoming','not_started'} and start < clock-timedelta(hours=3):
            continue
        if not _current_named_season(event.get('season'), clock):
            continue
        gender = event.get('football_gender')
        if gender not in (None, '', 'unknown', 'unclassified', 'women' if women else 'men'):
            continue
        pair = []
        for side in ('home', 'away'):
            team = event.get(side)
            if not isinstance(team, dict):
                break
            name = str(team.get('name') or '').strip()
            identity = team.get('id') or team.get('slug')
            if not identity or not 3 <= len(name) <= 160:
                break
            if re.search(r'(?i)\b(?:under[- ]?(?:16|17|18|19|20|21|23)|u[- ]?(?:16|17|18|19|20|21|23)|academy|youth)\b', name):
                break
            if not women and re.search(r'(?i)\b(?:women|womens|ladies|frauen)\b|\(W\)', name):
                break
            pair.append(name)
        if len(pair) != 2 or pair[0].casefold() == pair[1].casefold():
            continue
        names.update(pair); stamps.append(updated); keys.add(key)
        if event.get('season'):
            seasons.add(str(event['season']))
    if not 4 <= len(names) <= 64 or len(keys) < 2:
        return None
    observed = min(stamps)
    return {'clubs': sorted(names), 'season': next(iter(seasons)) if len(seasons) == 1 else None,
            'data_key': meta['id'], 'source_kind': 'confirmed_recent_fixture_roster',
            'observed_at': observed.isoformat(),
            'valid_from': (observed-timedelta(days=1)).date().isoformat(),
            'valid_until': (observed+MAX_AGE).date().isoformat(),
            'evidence_matches': len(keys), 'complete_roster': False,
            'source': PUBLIC_API + '/sports-data/competitions/' + meta['id'] + '/hub'}


def _public_fixture_get(league, key):
    # Existing first-party GET only. No result ingestion or score/table mutation.
    with httpx.Client(timeout=8.0, follow_redirects=False, trust_env=False) as client:
        response = client.get(PUBLIC_API + '/sports-data/competitions/' + key + '/hub',
                              headers={'User-Agent': 'NinkoSports-News-Membership/1.0'})
        response.raise_for_status()
        if len(response.content) > 6_000_000:
            raise ValueError('Fixture roster response exceeds bounded size')
        return response.json()


def verified_name_aliases(names):
    """Drop only explicit club-type prefixes/suffixes, never city/identity words.

    A shortened name must identify exactly one full name in this roster and
    cannot be a known ambiguous generic club word. No nickname is invented.
    """
    import unicodedata
    def norm(value):
        value = unicodedata.normalize('NFKD', value).casefold()
        return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())
    originals = list(dict.fromkeys(str(name).strip() for name in names if isinstance(name, str) and name.strip()))
    generic = {'united','city','athletic','rangers','rovers','inter','nacional','sporting','start','dynamo','dinamo','union','olympic','olympiakos','racing','wanderers'}
    proposed = {}
    for name in originals:
        short = re.sub(r'^(?:(?:FC|FK|SC|CF|AC|AFC|SK|NK)\s+)+', '', name)
        short = re.sub(r'(?:\s+(?:FC|FK|SC|CF|AC|AFC|SK|NK))+$', '', short).strip()
        canonical = norm(short)
        if (short == name or len(short) < 6 or canonical in generic
                or re.search(r'(?i)\b(?:under[- ]?\d+|u[- ]?\d+|women|ladies|frauen)\b|\([Ww]\)', short)):
            continue
        proposed.setdefault(canonical, []).append((name, short))
    output = list(originals)
    normalized = [norm(name) for name in originals]
    for canonical, matches in proposed.items():
        # Duplicate normalized full names are the same identity; genuine
        # homonyms stay full-length rather than leaking into another club.
        owners = {norm(name) for name, _ in matches}
        if len(owners) == 1 and sum(canonical == name for name in normalized) == 0:
            output.append(matches[0][1])
    return list(dict.fromkeys(output))
