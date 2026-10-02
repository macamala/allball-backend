"""News menu evidence from existing public standings; never sports ingestion.

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
}
_LOCK = threading.Lock()
_ENTRIES = {}
_LAST_REFRESH = float('-inf')
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


def refresh_football_news_memberships(*, now=None, get=None, force=False):
    """Called by the existing News cycle, at most once every six hours."""
    global _ENTRIES, _LAST_REFRESH
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError('Membership refresh requires a timezone-aware clock')
    if not _LOCK.acquire(blocking=False):
        return {'status': 'already_refreshing'}
    try:
        tick = time.monotonic()
        if not force and tick-_LAST_REFRESH < TTL_SECONDS:
            return {'status': 'cached', 'leagues': len(memberships_for_news(clock))}
        _LAST_REFRESH = tick
        reader = get or _public_get
        def load(league):
            for key in dict.fromkeys([ALIASES.get(league, league), FALLBACKS.get(league)]):
                if not key:
                    continue
                try:
                    item = parse_membership(league, reader(league, key), now=clock)
                    if item:
                        return league, item
                except Exception as exc:
                    log.debug('News membership read held league=%s error=%s', league, type(exc).__name__)
            return league, None
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix='news-membership') as pool:
            fresh = {league: entry for league, entry in pool.map(load, DOMESTIC) if entry}
        # A brief outage preserves still-current evidence, not unlimited stale data.
        _ENTRIES = {**memberships_for_news(clock), **fresh}
        result = {'status': 'refreshed', 'leagues': len(_ENTRIES), 'fresh': len(fresh),
                  'clubs': sum(len(e['clubs']) for e in _ENTRIES.values())}
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
