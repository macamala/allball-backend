"""Additional News desks verified with public article probes on 2026-10-03.

Used by the EXISTING RSS intake and article extractor. Desk labels are discovery
metadata, never competition facts. No result ingestion, credentials or AI here.
"""
from __future__ import annotations
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

RSS_FEEDS = (
    {'url': 'https://www.football-espana.net/feed', 'publisher': 'Football Espana',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'article_path_re': r'^/20\d{2}/\d{2}/\d{2}/[^/]+/?$',
     'note': 'Exact offset RSS dates, article-body id and same-page social photo verified. No La Liga stamp; international and club reporting stay distinct.'},
    {'url': 'https://www.getfootballnewsgermany.com/feed/', 'publisher': 'Get German Football News',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'article_path_re': r'^/20\d{2}/[^/]+/?$', 'excluded_entry_categories': ('Opinion',),
     'note': 'Verified public entry-content and social photo; opinion category excluded before writing. No Bundesliga stamp.'},
    {'url': 'https://fotbolldirekt.se/feed', 'publisher': 'FotbollDirekt',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'article_path_re': r'^/[^/]+/[^/]+/?$', 'excluded_article_paths': ('/video/', '/videos/', '/spel/', '/betting/'),
     'note': 'Public entry-content only and explicit free NewsArticle metadata required. Paywalled reports fail closed. No Allsvenskan stamp.'},
    {'url': 'https://www.suomifutis.com/feed/', 'publisher': 'SuomiFutis',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'article_path_re': r'^/20\d{2}/\d{2}/[^/]+/?$',
     'note': 'Finnish football desk; scoped post-content and exact RSS dates verified. No Veikkausliiga stamp.'},
    {'url': 'https://liga2.prosport.ro/feed', 'publisher': 'Liga2 ProSport',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'allowed_article_paths': ('/seria-1/',), 'article_path_re': r'^/seria-1/[^/]+-\d+/?$',
     'excluded_entry_categories': ('LIVE-TEXT',),
     'note': 'Romanian second-tier reporting; exact RSS dates and single__content verified. Third-tier live score trackers excluded; club membership still establishes the News menu.'},
    {'url': 'https://www.blick.ch/sport/fussball/rss.xml', 'publisher': 'Blick Football',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'allowed_article_paths': ('/sport/fussball/',),
     'note': 'Football-only feed; scoped article body and explicit free NewsArticle required. No Swiss league stamp; paid articles remain unavailable.'},
    {'url': 'https://news.stv.tv/section/sport/feed', 'publisher': 'STV Sport',
     'kind': 'mixed', 'enabled': True, 'article_body_required': True,
     'allowed_article_paths': ('/sport/',),
     'note': 'Mixed sport desk. Independently classify every article; scoped post-body removes WhatsApp callouts. No football or Scottish league stamp.'},
    {'url': 'https://gong.bg/rss', 'publisher': 'Gong',
     'kind': 'mixed', 'enabled': True, 'article_body_required': True,
     'allowed_article_paths': ('/football-sviat/', '/bg-football/'),
     'excluded_article_paths': ('/multimedia/', '/video/', '/videos/', '/na-jivo/'),
     'note': 'Only explicitly bounded football article paths enter this desk. Article-content and same-page photos verified; video products excluded. Never stamp a Bulgarian league.'},
    {'url': 'https://equalizersoccer.com/feed/', 'publisher': 'Equalizer Soccer',
     'kind': 'league', 'sport': 'football', 'enabled': True, 'article_body_required': True,
     'article_path_re': r'^/20\d{2}/\d{2}/\d{2}/[^/]+/?$',
     'excluded_entry_categories': ('Extra', 'Player Feature'),
     'note': 'Public women football reports only. Exact mvp-content-main body excludes unrelated cards; visible paywall markers cause rejection, never RSS/JSON-LD body fallback. No blanket NWSL stamp.'},
)

# Coverage planning only, not evidence that a current story exists for a league.
SOURCE_DESKS = {
    'Football Espana': ('spain-la-liga', 'spain-la-liga-2'),
    'Get German Football News': ('germany-bundesliga', 'germany-2-bundesliga'),
    'FotbollDirekt': ('sweden-allsvenskan', 'sweden-superettan'),
    'SuomiFutis': ('finland-veikkausliiga', 'finland-ykkosliiga'),
    'Liga2 ProSport': ('romania-liga-2',),
    'Blick Football': ('switzerland-super-league', 'switzerland-challenge-league'),
    'STV Sport': ('scotland-premiership', 'scotland-championship'),
    'Gong': ('bulgaria-first-league', 'bulgaria-second-league'),
    'Equalizer Soccer': ('usa-nwsl', 'football-women'),
}

_PROFILES = {
    'www.football-espana.net': {'body_id': 'article-body'},
    'www.getfootballnewsgermany.com': {'body_class': 'entry-content'},
    'fotbolldirekt.se': {'body_class': 'entry-content', 'require_free': True},
    'www.suomifutis.com': {'body_class': 'post-content'},
    'liga2.prosport.ro': {'body_class': 'single__content'},
    'www.blick.ch': {'body_class_prefix': 'Body__StyledContainer-', 'body_tag': 'article', 'require_free': True,
                     'path_prefix': '/sport/fussball/'},
    'news.stv.tv': {'body_class': 'post-body', 'extra_chrome_classes': ('whatsapp-callout',)},
    'gong.bg': {'body_class': 'article-content'},
    'equalizersoccer.com': {'body_id': 'mvp-content-main'},
}
_BLOCKED_CLASSES = frozenset({'equalizer-paywall', 'paywall-block', 'subscriber-only', 'membership-required'})
_ARTICLE_TYPES = frozenset({'NewsArticle', 'Article', 'ReportageNewsArticle', 'SportsArticle'})


def regional_hero_scope(canonical: str) -> bool:
    """Only this article's OG/Twitter image; never recommendation-card photos."""
    try:
        parts = urlsplit(canonical or '')
        profile = _PROFILES.get(parts.hostname)
        return bool(profile and (not profile.get('path_prefix') or parts.path.startswith(profile['path_prefix'])))
    except ValueError:
        return False


class _Markers(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = False
        self.nodes = []
        self.blocks = []
        self.collecting = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = values.get('class', '').split()
        if _BLOCKED_CLASSES.intersection(classes):
            self.blocked = True
        if tag == 'article':
            self.nodes.extend((tag, value) for value in classes)
        if tag == 'script':
            self.collecting = str(values.get('type', '')).lower() == 'application/ld+json'
            self.parts = []

    def handle_data(self, value):
        if self.collecting:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == 'script' and self.collecting:
            self.blocks.append(''.join(self.parts))
            self.collecting = False
            self.parts = []


def regional_article_profile(html: str, canonical: str):
    """Resolve a reviewed body, rejecting paid or changed structures safely.

    No hidden articleBody is read. JSON-LD is used only for a free-access flag;
    actual prose must remain inside the visible, scoped HTML body.
    """
    if not regional_hero_scope(canonical):
        return None
    profile = dict(_PROFILES[urlsplit(canonical).hostname])
    markers = _Markers()
    try:
        markers.feed(html or '')
        markers.close()
    except Exception:
        return {'blocked': True}
    free = []
    for block in markers.blocks:
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
            if isinstance(kinds, list) and _ARTICLE_TYPES.intersection(k for k in kinds if isinstance(k, str)):
                if isinstance(node.get('isAccessibleForFree'), bool):
                    free.append(node['isAccessibleForFree'])
    if markers.blocked or False in free or (profile.get('require_free') and True not in free):
        return {'blocked': True}
    prefix = profile.pop('body_class_prefix', None)
    if prefix:
        matches = {cls for tag, cls in markers.nodes if tag == profile.get('body_tag') and cls.startswith(prefix)}
        if len(matches) != 1:
            return {'blocked': True}
        profile['body_class'] = next(iter(matches))
    return profile


def excluded_feed_entry(config, entry) -> bool:
    excluded = {str(value).strip().casefold() for value in config.get('excluded_entry_categories', ())}
    if not excluded:
        return False
    categories = {str(row.get('term', '')).strip().casefold()
                  for row in (entry.get('tags') or ()) if isinstance(row, dict)}
    return bool(excluded.intersection(categories))
