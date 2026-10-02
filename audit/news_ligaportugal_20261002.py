"""Read one first-party article from its public, inert Nuxt JSON payload.

Only the object matching the /news/<id>/<slug> URL is considered. Recommended
stories, scores and page generation timestamps are never article evidence.
No JavaScript execution, private API, network request or database write occurs.
"""
import json
import re
from urllib.parse import urljoin, urlsplit

from .extract import _og, _parse_explicit_datetime, page_title_from_html, paragraphs_from_html
from .textutil import clean_text

MAX_HTML_BYTES = 2_000_000
MAX_NODES = 20_000


def read_ligaportugal_article(html, url):
    """Return verified same-article fields, or None on an ambiguous/changed CMS."""
    if not isinstance(html, str) or len(html.encode('utf8')) > MAX_HTML_BYTES:
        return None
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.ligaportugal.pt':
            return None
        route = re.fullmatch(r'/news/(\d+)/[^/]+/?', parsed.path)
        if not route or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        canonical = urlsplit(urljoin(url, _og(html, 'og:url') or ''))
        if not _og(html, 'og:url') or canonical.hostname != parsed.hostname or canonical.path.rstrip('/') != parsed.path.rstrip('/'):
            return None
        blocks = re.findall(r'<script\b[^>]*\bid=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
        if len(blocks) != 1:
            return None
        nodes = json.loads(blocks[0])
        if not isinstance(nodes, list) or not 0 < len(nodes) <= MAX_NODES:
            return None

        def ref(index, expected):
            if type(index) is not int or not 0 <= index < len(nodes):
                return None
            value = nodes[index]
            return value if type(value) is expected else None

        records = [row for row in nodes if type(row) is dict
                   and {'id', 'title', 'date', 'blocks'} <= row.keys()
                   and ref(row['id'], int) == int(route[1])]
        if len(records) != 1:
            return None
        record = records[0]
        title = clean_text(ref(record['title'], str) or '')
        published_at = _parse_explicit_datetime(ref(record['date'], str))
        if not title or title != page_title_from_html(html) or published_at is None:
            return None
        content = ref(record['blocks'], list)
        if not content or len(content) > 100:
            return None
        paragraphs = []
        for index in content:
            part = ref(index, dict)
            if not part:
                return None
            if ref(part.get('type'), str) != 'content-fields.text-content':
                continue
            text = ref(part.get('text'), str)
            if text is None or len(text) > 100_000:
                return None
            prose = paragraphs_from_html(text)
            if prose:
                paragraphs.append(prose)
        body = '\n\n'.join(paragraphs)
        if not body or len(body) > 200_000:
            return None
        # The social hero must also occur in this selected article object.
        image = _og(html, 'og:image')
        images = ref(record.get('images'), dict) or {}
        approved = {ref(index, str) for index in images.values()}
        banners = ref(record.get('banner'), list) or []
        for index in banners[:10]:
            banner = ref(index, dict) or {}
            approved.add(ref(banner.get('url'), str))
        if not image or image not in approved:
            return None
        image_url = urlsplit(image)
        if image_url.scheme != 'https' or image_url.hostname != parsed.hostname or not image_url.path.startswith('/backoffice/assets/'):
            return None
        return {'title': title, 'body': body, 'published_at': published_at,
                'image_candidates': [{'url': image, 'source': 'og', 'in_article': True}]}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return None
