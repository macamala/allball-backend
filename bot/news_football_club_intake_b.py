"""Reviewed official club article bodies in the existing News pipeline.

Reviewed 2026-10-04: Napredak's own single-post Elementor widgets, Roma's
visible article content, Juventus' article body. A publisher is not a league.
No changes to Live Scores, source freshness, spending or publication gates.
"""
from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

YOUTH_CONTEXT = 'Verified article category: youth football.'
ARTICLE_PROFILES = {
    'fknapredak.rs': {'body_class': 'elementor-widget-theme-post-content'},
    'www.asroma.com': {'body_class': 'asr-article-main-content', 'path_prefix': '/en/news/'},
    'www.juventus.com': {'body_class': 'oc-c-article__body', 'path_prefix': '/en/news/articles/'},
}
RSS_FEEDS = ({
    'url': 'https://fknapredak.rs/feed/', 'publisher': 'FK Napredak',
    'kind': 'league', 'sport': 'football', 'enabled': True,
    'verified_official': True, 'article_body_required': True,
    'article_https_host': 'fknapredak.rs', 'article_path_re': r'^/[^/]+/?$',
    'excluded_article_paths': ('/category/', '/tag/', '/wp-', '/feed/', '/shop/', '/page/'),
    'note': 'Same canonical single-post visible body and exact featured-image widget only. Retain aware RSS publication date; no inferred senior league or age band.',
},)
HTML_INDEXES = ({
    'id': 'roma-official-football-news', 'publisher': 'AS Roma', 'sport': 'football',
    'verified_official': True, 'url': 'https://www.asroma.com/en/news',
    'host': 'www.asroma.com', 'paths': ('/en/news/',),
    'article_path_re': r'^/en/news/\d+/[^/]+/?$',
    'exclude_article_fragments': ('gallery-', 'buy-tickets', 'ticket-information', 'vote-for-'),
}, {
    'id': 'juventus-official-football-news', 'publisher': 'Juventus', 'sport': 'football',
    'verified_official': True, 'url': 'https://www.juventus.com/en/news/articles/',
    'host': 'www.juventus.com', 'paths': ('/en/news/articles/',),
    'article_path_re': r'^/en/news/articles/[^/]+/?$',
    'exclude_article_fragments': ('starting-xi', 'buy-tickets', 'ticket-information', 'vote-for-'),
},)


def _napredak_identity(canonical):
    try:
        p = urlsplit(str(canonical or ''))
        return (p.scheme == 'https' and p.hostname == 'fknapredak.rs'
                and not p.username and not p.password and p.port in (None, 443)
                and bool(re.fullmatch(r'/[^/]+/?', p.path))
                and p.path.rstrip('/') not in {'/feed','/shop','/page','/category'})
    except ValueError:
        return False


def napredak_single_post(html, canonical):
    """None means not this publisher. Empty means this publisher failed identity."""
    try:
        host = urlsplit(str(canonical or '')).hostname
    except ValueError:
        return ''
    if host != 'fknapredak.rs':
        return None
    if not _napredak_identity(canonical):
        return ''
    from .extract import _ScopedNewsBody
    root = _ScopedNewsBody('elementor-location-single')
    try:
        root.feed(html or '')
    except Exception:
        return ''
    classes = str(root.root_attrs.get('class') or '').split()
    if (not root.finished or not {'type-post','status-publish'} <= set(classes)
            or not any(re.fullmatch(r'post-\d+', c) for c in classes)):
        return ''
    return ''.join(root.parts)


class _FeaturedPhoto(HTMLParser):
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
            width, height = int(a.get('width') or 0), int(a.get('height') or 0)
            if (p.scheme != 'https' or p.hostname != 'fknapredak.rs'
                    or p.username or p.password or p.port not in (None,443)
                    or not re.fullmatch(r'/wp-content/uploads/20\d{2}/\d{2}/[^/]+\.(?:jpe?g|png|webp)', p.path, re.I)
                    or width < 600 or height < 250):
                return
        except (TypeError, ValueError):
            return
        self.photos.append({'url':url,'source':'article','in_article':True,
                            'width':width,'height':height})

    handle_startendtag = handle_starttag


def napredak_article_photos(html, canonical):
    single = napredak_single_post(html, canonical)
    if single is None:
        return None
    if not single:
        return []
    from .extract import _ScopedNewsBody, paragraphs_from_html
    from .news_football_regional_desks import regional_article_profile
    if (regional_article_profile(html, canonical) or {}).get('blocked'):
        return []
    own_body = _ScopedNewsBody('elementor-widget-theme-post-content')
    own_body.feed(single)
    photo = _ScopedNewsBody('elementor-widget-theme-post-featured-image')
    photo.feed(single)
    if not own_body.finished or not photo.finished or not paragraphs_from_html(''.join(own_body.parts)):
        return []
    parser = _FeaturedPhoto()
    parser.feed(''.join(photo.parts))
    photos = {p['url']:p for p in parser.photos}
    return list(photos.values()) if len(photos) == 1 else []


def source_youth_category(canonical, title, visible_body):
    """Use only this article's visible prose, never links or site navigation."""
    if not _napredak_identity(canonical):
        return False
    opening = str(visible_body or '').split('\n\n')[0]
    return bool(re.search(r'(?<!\w)(?:pioniri|pionira|kadeti|kadeta|omladinci|omladinaca|пионири|кадети|омладинци)(?!\w)', opening, re.I))


def preserve_youth_qualifier_reason(source, draft):
    if YOUTH_CONTEXT not in str(source or ''):
        return None
    lead = str(draft.get('title') or '') + '\n' + str(draft.get('summary') or '')
    return None if re.search(r'\b(?:youth|academy|junior|cadet|pioneer|under[ -]?\d+|u[ -]?\d+)\b', lead, re.I) else 'source_subject_qualifier_missing:youth'
