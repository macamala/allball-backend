"""News source context: exact article identity, not sporting-data ingestion.

Category evidence is anchored to the fetched article, never site navigation,
recommendations, a club's geography, or a guessed participant gender.
"""
from __future__ import annotations
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit

WOMEN_CONTEXT = "Verified article category: women's football."
_WOMEN_OUTPUT = re.compile(r"\b(?:women(?:['’]s)?|female|ladies|wsl|nwsl|uwcl|uswnt)\b", re.I)
_AUDITED_WOMEN_PATH = '/regional/wdr/wdr-leverkusen-feiert-comeback-sieg-gegen-bremen-100.html'
_AUDITED_WOMEN_TITLE = 'Bayer Leverkusen overcomes two-goal deficit to defeat Werder Bremen in football'

HTML_INDEXES = (
    {'id': 'gazzetta-greece-top-flight', 'publisher': 'Gazzetta', 'sport': 'football',
     'verified_official': False, 'url': 'https://www.gazzetta.gr/football/superleague',
     'host': 'www.gazzetta.gr', 'paths': ('/football/superleague/',),
     'article_path_re': r'^/football/superleague/\d+/[^/]+/?$'},
    {'id': 'gazzetta-greece-second-tier', 'publisher': 'Gazzetta', 'sport': 'football',
     'verified_official': False, 'url': 'https://www.gazzetta.gr/football/superleague-2',
     'host': 'www.gazzetta.gr', 'paths': ('/football/superleague-2/',),
     'article_path_re': r'^/football/superleague-2/\d+/[^/]+/?$'},
    {'id': 'laola-austria-top-flight', 'publisher': 'LAOLA1', 'sport': 'football',
     'verified_official': False, 'url': 'https://www.laola1.at/de/', 'host': 'www.laola1.at',
     'paths': ('/de/red/fussball/bundesliga/news/',),
     'article_path_re': r'^/de/red/fussball/bundesliga/news/[^/]+/?$'},
    {'id': 'laola-austria-second-tier', 'publisher': 'LAOLA1', 'sport': 'football',
     'verified_official': False, 'url': 'https://www.laola1.at/de/', 'host': 'www.laola1.at',
     'paths': ('/de/red/fussball/2--liga/news/',),
     'article_path_re': r'^/de/red/fussball/2--liga/news/[^/]+/?$'},
)
_SOURCE_MENUS = (
    ('www.gazzetta.gr', r'^/football/superleague/\d+/[^/]+/?$', 'greece-super-league'),
    ('www.gazzetta.gr', r'^/football/superleague-2/\d+/[^/]+/?$', 'greece-super-league-2'),
    ('www.laola1.at', r'^/de/red/fussball/bundesliga/news/[^/]+/?$', 'austria-bundesliga'),
    ('www.laola1.at', r'^/de/red/fussball/2--liga/news/[^/]+/?$', 'austria-second-league'),
)


def _identity(url):
    if not isinstance(url, str):
        return None
    try:
        value = urlsplit(url or '')
        if value.scheme != 'https' or value.username or value.password or value.port not in (None, 443):
            return None
        if not value.hostname or not value.path.startswith('/'):
            return None
        return value.hostname, value.path.rstrip('/')
    except (TypeError, ValueError):
        return None


class _ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.blocks = []
        self.size = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.active = dict(attrs).get('type', '').lower() == 'application/ld+json'
            self.parts = []
            self.size = 0

    def handle_data(self, text):
        if self.active:
            self.size += len(text)
            if self.size <= 500000:
                self.parts.append(text)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active:
            if self.size <= 500000 and len(self.blocks) < 64:
                self.blocks.append(''.join(self.parts))
            self.active = False
            self.parts = []


def _norm(value):
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ''.join(c for c in text if not unicodedata.combining(c)).strip()


def verified_women_article_category(html, canonical):
    """Read ONLY an exact NewsArticle's keywords, never its articleBody."""
    identity = _identity(canonical)
    if not identity or identity[0] != 'www.sportschau.de' or not identity[1].endswith('.html'):
        return False
    parser = _ArticleMetadata()
    try:
        parser.feed(html or '')
        parser.close()
    except Exception:
        return False
    for block in parser.blocks:
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get('@graph'), list):
            nodes = data['@graph']
        for node in nodes:
            if not isinstance(node, dict):
                continue
            kinds = node.get('@type', [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if not isinstance(kinds, list) or 'NewsArticle' not in kinds:
                continue
            target = node.get('mainEntityOfPage')
            if isinstance(target, dict):
                target = target.get('@id')
            if _identity(target) != identity:
                continue
            values = node.get('keywords', [])
            if isinstance(values, str):
                values = values.split(',')
            if not isinstance(values, list):
                continue
            tags = {_norm(value) for value in values if isinstance(value, str)}
            if 'frauen' in tags and tags.intersection({'fussball', 'football', 'soccer'}):
                return True
    return False


def preserve_women_qualifier_reason(source, draft):
    if WOMEN_CONTEXT not in (source or ''):
        return None
    lead = str(draft.get('title') or '') + '\n' + str(draft.get('summary') or '')
    return None if _WOMEN_OUTPUT.search(lead) else 'source_subject_qualifier_missing:women'


def audited_women_article(article):
    """Idempotent menu-only repair of the verified Sportschau publication.

    Verified 2026-10-03: exact NewsArticle mainEntityOfPage, keywords Fussball /
    Frauen and publication 2026-10-02T19:15:07.452Z. No prose/date alteration.
    """
    identity = _identity(getattr(article, 'source_url', None) or getattr(article, 'external_id', None))
    exact_source = identity == ('www.sportschau.de', _AUDITED_WOMEN_PATH)
    exact_legacy = (getattr(article, 'id', None) == 22719 and
                    getattr(article, 'title', None) == _AUDITED_WOMEN_TITLE)
    stamp = str(getattr(article, 'published_at', None) or '')[:10]
    return stamp == '2026-10-02' and (exact_source or exact_legacy)


def source_menu_association(url):
    """Editorial fallback only, after admitted football's primary subject.

    A publisher's explicit league category associates its club reporting with
    a News menu. It does NOT establish a match, score or a competition claim.
    """
    identity = _identity(url)
    if identity:
        host, path = identity
        for expected, pattern, menu in _SOURCE_MENUS:
            if host == expected and re.fullmatch(pattern, path):
                return menu
    return None
