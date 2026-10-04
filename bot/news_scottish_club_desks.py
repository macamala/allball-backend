"""Official Scottish club discovery in the existing News intake.

Audited 2026-10-04. Motherwell embeds ten different articles on one URL, so
only the item whose data-href equals the canonical URL can provide prose,
category or a photograph. Quiet feeds keep their original publication dates.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

MOTHERWELL = 'www.motherwellfc.co.uk'
ARTICLE_PROFILES = {
    MOTHERWELL: {'body_class': 'postContent'},
    'kilmarnockfc.co.uk': {'body_class': 'article__body', 'path_prefix': '/news/'},
}
RSS_FEEDS = (
    {'url': 'https://www.motherwellfc.co.uk/feed/', 'publisher': 'Motherwell FC',
     'kind': 'league', 'sport': 'football', 'verified_official': True, 'enabled': True,
     'article_body_required': True, 'article_https_host': MOTHERWELL,
     'article_path_re': r'^/20\d{2}/\d{2}/\d{2}/[^/]+/?$',
     'excluded_entry_categories': ('Tickets', 'Commercial', 'Hospitality'),
     'note': 'Exact data-href item, postContent and that item imageWrap only. Own Women category retained. Original RSS dates; no domestic league or senior-team stamp.'},
    {'url': 'https://kilmarnockfc.co.uk/feed/', 'publisher': 'Kilmarnock FC',
     'kind': 'league', 'sport': 'football', 'verified_official': True, 'enabled': True,
     'article_body_required': True, 'article_https_host': 'kilmarnockfc.co.uk',
     'article_path_re': r'^/news/(?![^/]*(?:ticket-information|tickets-on-sale|hospitality|vote-for))[^/]+/?$',
     'excluded_entry_categories': ('Tickets', 'Commercial', 'Hospitality'),
     'note': 'Verified article__body and own social photograph. Ticket products excluded before AI; women, first team and league identities remain independently checked.'},
)
SOURCE_DESKS = {
    'Motherwell FC': ('scotland-premiership', 'football-women'),
    'Kilmarnock FC': ('scotland-premiership', 'football-women'),
}


def _identity(value):
    try:
        p = urlsplit(str(value or ''))
        if (p.scheme == 'https' and p.hostname == MOTHERWELL
                and not p.username and not p.password and p.port in (None, 443)
                and not p.query and re.fullmatch(r'/20\d{2}/\d{2}/\d{2}/[^/]+/?', p.path)):
            return p.path.rstrip('/')
    except ValueError:
        pass
    return None


class _ArticleItem(HTMLParser):
    def __init__(self, identity):
        super().__init__(convert_charrefs=False)
        self.identity = identity
        self.matches = 0
        self.depth = 0
        self.finished = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if not self.depth:
            if (tag == 'li' and 'infinite-item' in str(a.get('class') or '').split()
                    and _identity(a.get('data-href')) == self.identity
                    and re.fullmatch(r'[1-9]\d*', str(a.get('data-article-id') or ''))):
                self.matches += 1
                self.depth = 1
                self.finished = False
            return
        if tag == 'li':
            self.depth += 1
        self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == 'li':
            self.depth -= 1
        if self.depth:
            self.parts.append('</' + tag + '>')
        else:
            self.finished = True

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data('&' + name + ';')

    def handle_charref(self, name):
        self.handle_data('&#' + name + ';')


def motherwell_single_post(html, canonical):
    """None is another publisher; empty means this publisher failed identity."""
    try:
        if urlsplit(str(canonical or '')).hostname != MOTHERWELL:
            return None
    except ValueError:
        return ''
    identity = _identity(canonical)
    if not identity:
        return ''
    parser = _ArticleItem(identity)
    try:
        parser.feed(html or '')
        parser.close()
    except Exception:
        return ''
    return ''.join(parser.parts) if parser.matches == 1 and parser.finished and not parser.depth else ''


def motherwell_women_category(single):
    from .extract import _ScopedNewsBody, clean_text
    scoped = _ScopedNewsBody('primaryCategory')
    scoped.feed(single or '')
    return scoped.finished and clean_text(''.join(scoped.parts)).casefold() == 'women'


class _HeroPhoto(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.photos = []

    def handle_starttag(self, tag, attrs):
        if tag != 'img':
            return
        a = dict(attrs)
        try:
            url = str(a.get('src') or '')
            p = urlsplit(url)
            if (p.scheme != 'https' or p.hostname != MOTHERWELL or p.username
                    or p.password or p.port not in (None, 443)
                    or not re.fullmatch(r'/wp-content/uploads/20\d{2}/\d{2}/[^/]+\.(?:jpe?g|png|webp)', p.path, re.I)):
                return
        except ValueError:
            return
        self.photos.append({'url': url, 'source': 'article', 'in_article': True,
                            'alt': str(a.get('alt') or '')})

    handle_startendtag = handle_starttag


def motherwell_article_photos(html, canonical):
    single = motherwell_single_post(html, canonical)
    if single is None:
        return None
    if not single:
        return []
    from .extract import _ScopedNewsBody, paragraphs_from_html
    from .news_football_regional_desks import regional_article_profile
    if (regional_article_profile(html, canonical) or {}).get('blocked'):
        return []
    body, hero = _ScopedNewsBody('postContent'), _ScopedNewsBody('imageWrap')
    body.feed(single)
    hero.feed(single)
    if not body.finished or not hero.finished or not paragraphs_from_html(''.join(body.parts)):
        return []
    parser = _HeroPhoto()
    parser.feed(''.join(hero.parts))
    photos = {row['url']: row for row in parser.photos}
    return list(photos.values()) if len(photos) == 1 else []


def fetch_scottish_article(url):
    """Return (handled, HTML), using the existing robots-aware safe transport.

    A missing/wrong canonical or changed structure does not authorize generic
    whole-page or RSS fallback. Other publishers retain their existing path.
    """
    try:
        p = urlsplit(str(url or ''))
        if p.hostname not in ARTICLE_PROFILES:
            return False, ''
        valid_path = (_identity(url) is not None if p.hostname == MOTHERWELL
                      else bool(re.fullmatch(r'/news/[^/]+/?', p.path)))
        if (not valid_path or p.scheme != 'https' or p.username or p.password
                or p.port not in (None, 443)):
            return True, ''
        from .news_feed_http import read_news_feed
        from .extract import _og, _metadata
        raw = read_news_feed(url)
        if len(raw) > 2_000_000:
            return True, ''
        html = raw.decode('utf-8', 'replace')
        canonical = _og(html, 'og:url') or _metadata(html, 'canonical') or ''
        cp = urlsplit(canonical)
        if (cp.scheme != 'https' or cp.hostname != p.hostname or cp.username
                or cp.password or cp.port not in (None, 443) or cp.query
                or cp.path.rstrip('/') != p.path.rstrip('/')):
            return True, ''
        return True, html
    except Exception:
        # Includes robots denial, throttling, wrong redirects and parse errors.
        return True, ''
