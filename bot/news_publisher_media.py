"""Known News publisher fallback images; no content or sports-data writes."""
import re
from urllib.parse import unquote, urlsplit


def is_publisher_branding(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        url = urlsplit(value.strip())
        host = (url.hostname or '').lower().removeprefix('www.')
        path = unquote(url.path).rstrip('/').lower()
        return host == 'soccernews.com' and bool(re.fullmatch(r'/og/og-image\.(?:png|jpe?g|webp)', path))
    except (ValueError, TypeError):
        return False


def soccernews_article_images(canonical, title, candidates):
    """Reviewed publisher's title-matched lead photo, not its shared OG logo.

    Return None for other sites; on this article pattern the DOM alt text must
    match the page's own headline. Unrelated cards/avatars and hidden schema
    image references do not establish a story photograph.
    """
    import html
    import unicodedata
    if not isinstance(canonical, str):
        return None
    try:
        parsed = urlsplit(canonical)
        if ((parsed.hostname or '').lower().removeprefix('www.') != 'soccernews.com'
                or not re.fullmatch(r'/[^/]+/\d+/?', parsed.path)):
            return None
    except ValueError:
        return None
    def norm(value):
        text = unicodedata.normalize('NFKD', html.unescape(str(value or ''))).casefold()
        text = re.sub(r'\s*[-|–—]\s*soccer\s*news\s*$', '', text)
        return ' '.join(re.sub(r'[^\w]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())
    headline = norm(title)
    if len(headline.split()) < 4:
        return []
    matched = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get('source') != 'body':
            continue
        url = candidate.get('url')
        if not isinstance(url, str) or is_publisher_branding(url):
            continue
        if norm(candidate.get('alt')) != headline:
            continue
        try:
            photo = urlsplit(url)
            if photo.scheme != 'https' or photo.username or photo.password:
                continue
            if photo.hostname not in {'images.performgroup.com', 'www.soccernews.com', 'soccernews.com'}:
                continue
            if re.search(r'(?:avatar|logo|icon|gravatar)', photo.path, re.I):
                continue
        except ValueError:
            continue
        matched.append({**candidate, 'in_article': True})
    return matched[:3]
