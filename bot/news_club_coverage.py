"""Read-only per-club News coverage and scheduling, not sporting fact evidence.

Every normal worker cycle reconstructs coverage from admitted published News.
Current roster identity is a menu aid only. No model, writer, score or source
publication date is changed; no source is created to satisfy a numerical quota.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from text_unidecode import unidecode

UTC = timezone.utc
HORIZON = timedelta(days=7)
_STATIC = json.loads((Path(__file__).parent / 'news_football_clubs.json').read_text())
_GENERIC = {'start', 'kapa', 'city', 'united', 'union', 'inter', 'nice', 'racing',
            'nacional', 'sporting', 'athletic', 'rangers', 'rovers'}
_WOMEN = re.compile(r'\b(?:women|womens|female|ladies|zfk|frauen|femminile|femenin\w*|zenska|zenski|wsl|nwsl|uwcl)\b')
_YOUTH = re.compile(r'\b(?:u ?(?:[6-9]|1[0-9]|2[0-3])|(?:under|sub) (?:[6-9]|1[0-9]|2[0-3])|academy|youth team)\b')
_ROLE = r'(?:s |fc\b|cf\b|coach\b|manager\b|goalkeeper\b|defender\b|midfielder\b|striker\b|forward\b|players?\b|sign\w*\b|appoint\w*\b|confirm\w*\b|announce\w*\b|beat\b|defeat\w*\b|draw\b|win\b|wins\b|lose\b|lost\b|host\w*\b|face\w*\b)'
# Alternate names activate ONLY with their canonical club in a current roster.
_NAMES = {
    'paris saint germain': ('PSG',),
    'bayern munchen': ('Bayern Munich',),
    'borussia monchengladbach': ('Borussia Moenchengladbach',),
    'athletic club': ('Athletic Bilbao',),
    'manchester united': ('Man Utd', 'Manchester Utd'),
    'brighton hove albion': ('Brighton',),
    'wolverhampton wanderers fc': ('Wolves',),
    'west bromwich albion fc': ('West Brom',),
    'fk crvena zvezda': ('Crvena Zvezda', 'Red Star Belgrade'),
    'partizan beograd': ('Partizan', 'Partizan Belgrade'),
}
_SERBIAN_CYRILLIC = dict(zip('абвгдђежзијклљмнњопрстћуфхцчџш',
    ['a','b','v','g','d','dj','e','z','z','i','j','k','l','lj','m','n','nj','o','p','r','s','t','c','u','f','h','c','c','dz','s']))


def normalize(value):
    text = str(value or '').casefold()
    text = ''.join(_SERBIAN_CYRILLIC.get(c, c) for c in text)
    return re.sub(r'[^\w]+', ' ', unidecode(text).casefold()).strip()


def _time(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


def _get(row, key, default=None):
    return row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)


def lead_text(row):
    body = _get(row, '_classification_text') or _get(row, '_extracted') or ''
    value = str(_get(row, 'summary') or body).strip()
    lead = re.split(r'\n\s*\n', value, maxsplit=1)[0]
    if len(lead) > 650:
        sentence = re.split(r'(?<=[.!?])\s+', lead, maxsplit=1)[0]
        lead = sentence if len(sentence) <= 650 else ''
    return lead


class ClubCoverage:
    """A bounded snapshot for one cycle. Constructing it performs no I/O."""
    def __init__(self, rosters, *, now=None):
        self.now = now or datetime.now(UTC)
        if self.now.tzinfo is None:
            raise ValueError('Club coverage requires an aware clock')
        self.now = self.now.astimezone(UTC)
        self.clubs, self.aliases = {}, {}
        self.count24, self.count7 = Counter(), Counter()
        self.latest, self.seen = {}, set()
        self.scanned = 0
        static_current = _STATIC['valid_from'] <= self.now.date().isoformat() <= _STATIC['valid_until']
        from .news_football_memberships import verified_name_aliases
        for league, entry in (rosters or {}).items():
            if not isinstance(entry, dict):
                continue
            if not entry.get('valid_from', '9999') <= self.now.date().isoformat() <= entry.get('valid_until', ''):
                continue
            observed = _time(entry.get('observed_at'))
            if not observed or not -timedelta(minutes=5) <= self.now - observed <= timedelta(hours=72):
                continue
            names = {normalize(n): n for n in entry.get('clubs', ()) if isinstance(n, str) and n.strip()}
            if not 4 <= len(names) <= 64:
                continue
            self.clubs[league] = names
            owners = defaultdict(set)
            for key, name in names.items():
                aliases = verified_name_aliases([name]) + list(_NAMES.get(key, ()))
                for alias in aliases:
                    normalized = normalize(alias)
                    if normalized:
                        owners[normalized].add(key)
            if static_current:
                for alias in _STATIC['leagues'].get(league, {}).get('clubs', ()):
                    short = normalize(alias)
                    matches = [key for key in names if (' '+short+' ') in (' '+key+' ') or (' '+key+' ') in (' '+short+' ')]
                    if len(matches) == 1:
                        owners[short].add(matches[0])
            self.aliases[league] = {alias: next(iter(keys)) for alias, keys in owners.items() if len(keys) == 1}

    def subjects(self, row, league):
        """Headline clubs, else explicit lead roles; never historical tail mentions."""
        if league not in self.clubs:
            return ()
        title, lead = normalize(_get(row, 'title')), normalize(lead_text(row))
        if _YOUTH.search(title) and league not in {'football-youth', 'uefa-under-21-euro'}:
            return ()
        women = 'women' in league or league == 'usa-nwsl'
        if not women and _WOMEN.search(title + ' ' + lead):
            return ()
        for text, summary_only in ((title, False), (lead, True)):
            matches = []
            for alias, key in self.aliases[league].items():
                for hit in re.finditer(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', text):
                    before, after = text[max(0, hit.start()-50):hit.start()], text[hit.end():]
                    if re.search(r'\b(?:former|ex|previously (?:at|with)|used to play for)\s*$', before):
                        continue
                    if re.search(r'\b(?:compared to|unlike|record set by)\s*$', before):
                        continue
                    if alias == 'start' and not re.search(
                            r'\b(?:ik start|start fc|start s (?:coach|manager|goalkeeper|defender|midfielder|striker|forward))\b', text):
                        continue
                    if alias == 'kapa':
                        raw = str(_get(row, 'summary') if summary_only else _get(row, 'title') or '')
                        if not (re.search(r'(?<!\w)KäPa(?!\w)', raw) or 'kapylan pallo' in text):
                            continue
                    if alias in _GENERIC or len(alias) < 4 or summary_only:
                        if not re.match(r'\s+' + _ROLE, after):
                            raw = str(_get(row, 'summary') if summary_only else _get(row, 'title') or '')
                            if alias not in {'psg'} or not re.search(r'(?<!\w)PSG(?!\w)', raw):
                                continue
                    matches.append((hit.start(), -len(alias), key, hit.end()))
            matches = [m for m in matches if not any(o[0] <= m[0] and o[3] >= m[3] and o[1] < m[1] for o in matches)]
            keys = tuple(dict.fromkeys(m[2] for m in sorted(matches)))
            if keys:
                return keys if len(keys) <= 2 else ()
        return ()

    def observe(self, row, league=None):
        """Count a public record supplied by the filtered loader, once per ID."""
        key = _get(row, 'id') or _get(row, 'url') or _get(row, 'slug')
        stamp = _time(_get(row, 'published_at') or _get(row, 'created_at'))
        if key is None or key in self.seen or not stamp or not self.now-HORIZON <= stamp <= self.now:
            return
        self.seen.add(key)
        self.scanned += 1
        league = league or _get(row, 'league')
        for club in self.subjects(row, league):
            pair = (league, club)
            self.count7[pair] += 1
            if stamp >= self.now - timedelta(hours=24):
                self.count24[pair] += 1
            self.latest[pair] = max(stamp, self.latest.get(pair, stamp))

    def bounded_priorities(self, items, priorities, *, identity, section):
        """Keep the first Zvezda priority slot; followups use their league lane."""
        from .news_football_priority import PRIMARY_COMPETITIONS
        result, first = dict(priorities), True
        for item in items:
            key = identity(item)
            if result.get(key, 0) < 2:
                continue
            if first:
                first = False
            else:
                result[key] = 1 if section(item) in PRIMARY_COMPETITIONS else 0
        return result

    def balance(self, items, *, section, priority):
        """Reorder only within an existing league/tier's slots; remove nothing."""
        output = list(items)
        groups = defaultdict(list)
        for index, item in enumerate(items):
            tier, league = priority(item), section(item)
            if tier < 2 and league in self.clubs:
                groups[(league, tier)].append(index)
        for (league, _), positions in groups.items():
            pending = [(i, items[i], self.subjects(items[i], league)) for i in positions]
            projected, previous = Counter(), set()
            for turn, position in enumerate(positions):
                known = [row for row in pending if row[2]]
                options = known if known and turn % 4 != 3 else pending
                different = [row for row in options if row[2] and not previous.intersection(row[2])]
                if different and turn % 4 != 3:
                    options = different
                def rank(row):
                    index, _, clubs = row
                    if not clubs:
                        return (-1 if turn % 4 == 3 else 1, 0, 0, 0, index)
                    pairs = [(league, c) for c in clubs]
                    return (max(projected[c] for c in clubs),
                            0 if min(self.count7[p] for p in pairs) == 0 else 1,
                            max(self.count24[p] for p in pairs),
                            min(self.count7[p] for p in pairs), index)
                chosen = min(options, key=rank)
                output[position] = chosen[1]
                pending.remove(chosen)
                previous = set(chosen[2])
                projected.update(chosen[2])
        return output

    def report(self, candidates=(), *, section=None):
        queued, publishers = Counter(), defaultdict(set)
        from urllib.parse import urlsplit
        for item in candidates:
            league = section(item) if section else _get(item, 'candidate_league') or _get(item, 'league')
            try:
                host = (urlsplit(str(_get(item, 'url') or '')).hostname or '').removeprefix('www.')
            except ValueError:
                host = ''
            for club in self.subjects(item, league):
                queued[(league, club)] += 1
                if host:
                    publishers[(league, club)].add(host)
        rows = []
        for league, names in sorted(self.clubs.items()):
            for key, name in sorted(names.items()):
                pair = (league, key)
                rows.append({'league': league, 'club': name, 'club_key': key,
                    'articles_24h': self.count24[pair], 'articles_7d': self.count7[pair],
                    'last_published_at': self.latest[pair].isoformat() if pair in self.latest else None,
                    'candidate_count': queued[pair], 'candidate_hosts': sorted(publishers[pair]),
                    'status': 'published_24h' if self.count24[pair] else 'candidate_waiting' if queued[pair]
                        else 'published_7d_no_current_candidate' if self.count7[pair] else 'no_current_candidate'})
        return {'checked_at': self.now.isoformat(), 'roster_leagues': len(self.clubs),
                'roster_clubs': len(rows), 'public_records_scanned': self.scanned,
                'clubs_with_24h_news': sum(r['articles_24h'] > 0 for r in rows),
                'clubs_with_7d_news': sum(r['articles_7d'] > 0 for r in rows),
                'clubs_with_candidates': sum(r['candidate_count'] > 0 for r in rows),
                'complete': False, 'rows': rows}


def load_club_coverage(db, *, now=None):
    """Same public admission gates as league inventory; SELECT only, no writes."""
    from sqlalchemy import func
    from models import Article, ArticleTaxonomyResolution as Tax
    from taxonomy_resolver import RESOLVER_VERSION
    from .news_football_memberships import memberships_for_news
    clock = now or datetime.now(UTC)
    snapshot = ClubCoverage(memberships_for_news(clock), now=clock)
    stamp = func.coalesce(Article.published_at, Article.created_at)
    end = clock.astimezone(UTC).replace(tzinfo=None)
    rows = (db.query(Article.id, Article.title, Article.summary, Article.published_at,
                     Article.created_at, Tax.resolved_competition.label('league'))
        .join(Tax, Tax.article_id == Article.id)
        .filter(Article.ai_generated.is_(True), Tax.public_ok.is_(True),
                Tax.resolved_sport == 'football', Tax.resolver_version == RESOLVER_VERSION,
                Tax.hero_media_kind.in_(('EDITORIAL_PHOTO', 'UNKNOWN')),
                Article.image_url.isnot(None), Article.image_url != '',
                Tax.resolved_competition.isnot(None), stamp >= end-HORIZON, stamp <= end)
        .yield_per(500))
    for row in rows:
        snapshot.observe(row)
    return snapshot
