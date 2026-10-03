"""Visible, article-bound J.LEAGUE news in Japanese; no scores or AI here.

The English edition can lag behind the native publisher. The same existing
index intake uses this reader; navicode and site-wide keywords are NOT proof
of an article's competition. Only its own title-module category qualifies.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

NATIVE_INDEXES = tuple({
    'id': f'jleague-native-j{tier}', 'publisher': 'J.LEAGUE', 'sport': 'football',
    'url': f'https://www.jleague.jp/j{tier}/news/', 'host': 'www.jleague.jp',
    'paths': ('/news/article/',), 'article_path_re': r'^/news/article/\d+/?$',
} for tier in (1, 2))
_NATIVE_IDS = {row['id'] for row in NATIVE_INDEXES}
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
# Broadcast advertisements, shopping, voting and preview/analysis products are
# not straight reporting; never turn them into fabricated news developments.
_NON_NEWS = re.compile(r'放送告知|放送追加|チケット|キャンペーン|プレゼント|投票|プレビュー|マンスリーレポート|達成間近の記録')


def article_identity(url):
    if not isinstance(url, str):
        return None
    try:
        part = urlsplit(url)
        if (part.scheme != 'https' or part.hostname != 'www.jleague.jp'
                or part.username or part.password or part.port not in (None, 443)
                or not re.fullmatch(r'/news/article/\d+/', part.path)):
            return None
        return 'https://www.jleague.jp' + part.path
    except ValueError:
        return None


class _VisibleArticle(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.fields = {k: [] for k in ('title', 'category', 'date', 'body')}
        self.active = []
        self.meta = {}
        self.hero = []
        self.roots = 0

    def handle_starttag(self, tag, attrs):
        values = {str(k).lower(): str(v or '') for k, v in attrs}
        classes = set(values.get('class', '').split())
        inside = any('p-news-details__content' in c for _, c, _ in self.stack)
        blocked = any(b for _, _, b in self.stack)
        hidden = ('hidden' in values or values.get('aria-hidden') == 'true'
                  or bool(re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', values.get('style', ''), re.I)))
        blocked = blocked or hidden or tag in {'script', 'style', 'noscript', 'aside', 'nav', 'footer'}
        if tag == 'meta':
            key = values.get('property') or values.get('name')
            if key:
                self.meta.setdefault(key, []).append(values.get('content', ''))
        if 'p-news-details__content' in classes and not blocked:
            self.roots += 1
        in_header = any('p-news-details__title-module' in c for _, c, _ in self.stack)
        field = None
        if inside and not blocked:
            if tag == 'h1' and in_header and 'm-article-module__title' in classes:
                field = 'title'
            elif tag == 'span' and in_header and 'm-article-module__category-title' in classes:
                field = 'category'
            elif tag == 'p' and in_header and 'm-article-module__date' in classes:
                field = 'date'
            elif tag == 'div' and 'lexical-content' in classes:
                field = 'body'
            if field:
                chunk = []
                self.fields[field].append(chunk)
                self.active.append((len(self.stack) + 1, field, chunk))
            if tag in {'br', 'p', 'li'}:
                for _, name, chunk in self.active:
                    if name == 'body':
                        chunk.append('\n')
            if tag == 'img' and 'm-article-module__image' in classes:
                self.hero.append(values.get('src', ''))
        if tag not in _VOID:
            self.stack.append((tag, classes, blocked))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for idx in range(len(self.stack)-1, -1, -1):
            if self.stack[idx][0] == tag:
                for depth, field, chunk in self.active:
                    if field == 'body' and tag in {'p', 'li'}:
                        chunk.append('\n')
                self.stack = self.stack[:idx]
                self.active = [a for a in self.active if a[0] <= idx]
                break

    def handle_data(self, data):
        if any(blocked for _, _, blocked in self.stack):
            return
        for _, _, chunk in self.active:
            chunk.append(data)


def read_jleague_article(html, url, *, expected_tier=None):
    """Return only a same-page J1/J2 report with visible time/body/hero.

    It supplies existing writer/validator inputs, never an accepted article.
    Japanese text is kept intact; translation must pass the existing gates.
    """
    canonical = article_identity(url)
    if not canonical or not isinstance(html, str) or len(html) > 2_000_000:
        return None
    parser = _VisibleArticle()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return None
    if parser.roots != 1 or parser.meta.get('og:type') != ['article']:
        return None
    identities = parser.meta.get('og:url', [])
    if len(identities) != 1 or article_identity(identities[0]) != canonical:
        return None
    if any(len(parser.fields[k]) != 1 for k in parser.fields):
        return None
    values = {k: ''.join(v[0]).strip() for k, v in parser.fields.items()}
    title = re.sub(r'\s+', ' ', values['title'])
    category = unicodedata.normalize('NFKC', values['category'])
    tier = {'明治安田J1リーグ': 1, '明治安田J2リーグ': 2}.get(category)
    if not tier or (expected_tier is not None and tier != expected_tier) or _NON_NEWS.search(title):
        return None
    date_text = unicodedata.normalize('NFKC', values['date'])
    matched = re.fullmatch(r'(20\d{2})/(\d{1,2})/(\d{1,2})\s*\([月火水木金土日]\)\s*(\d{1,2}):(\d{2})', date_text)
    if not matched:
        return None
    try:
        stamp = datetime(*map(int, matched.groups()), tzinfo=ZoneInfo('Asia/Tokyo')).astimezone(timezone.utc)
    except ValueError:
        return None
    from .extract import page_published_at_from_html
    machine_stamp = page_published_at_from_html(html)
    if machine_stamp and abs((machine_stamp-stamp).total_seconds()) > 60:
        return None
    body = '\n\n'.join(re.sub(r'\s+', ' ', line).strip() for line in re.split(r'\n+', values['body']) if line.strip())
    if len(title) < 8 or len(body) < 80 or sum(c.isalpha() for c in body) < 50:
        return None
    images = parser.meta.get('og:image', [])
    if len(images) != 1 or len(parser.hero) != 1:
        return None
    photo = urljoin(canonical, parser.hero[0])
    if photo != urljoin(canonical, images[0]):
        return None
    part = urlsplit(photo)
    if part.scheme != 'https' or part.hostname != 'www.jleague.jp' or not part.path.startswith('/images/media/'):
        return None
    return {'url': canonical, 'title': title, 'published_at': stamp,
            'body': f'Source article category: J{tier} League.\n\n' + body,
            'source_category': f'japan-j{tier}-league',
            'image_candidates': [{'url': photo, 'source': 'og', 'in_article': True}]}
