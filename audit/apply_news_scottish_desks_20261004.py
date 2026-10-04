"""Apply News-only Scottish desk integration; never deploy or change budgets."""
from pathlib import Path


def replace(path, old, new):
    p=Path(path); text=p.read_text()
    if new in text:return
    if text.count(old)!=1:raise RuntimeError('Source drift: '+path)
    p.write_text(text.replace(old,new,1))


def append(path, code):
    p=Path(path)
    if code not in p.read_text():p.write_text(p.read_text()+code)


append('bot/news_scottish_club_desks.py', '''

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
''')

replace('bot/extract.py',
    '    from .news_football_club_intake_b import napredak_article_photos\n',
    '    from .news_scottish_club_desks import motherwell_article_photos\n'
    '    scottish_photos = motherwell_article_photos(html, canonical)\n'
    '    if scottish_photos is not None:\n        return scottish_photos\n'
    '    from .news_football_club_intake_b import napredak_article_photos\n')
replace('bot/extract.py',
    '    from .news_football_club_intake_b import napredak_single_post\n',
    '    from .news_scottish_club_desks import motherwell_single_post, motherwell_women_category\n'
    '    scottish_post = motherwell_single_post(html, canonical)\n'
    '    if scottish_post is not None:\n'
    "        if not scottish_post:\n            return ''\n"
    '        if motherwell_women_category(scottish_post):\n            source_category = WOMEN_CONTEXT\n'
    '        html = scottish_post\n'
    '    from .news_football_club_intake_b import napredak_single_post\n')
replace('bot/extract.py',
    '    if not url or news_source_is_excluded(url):\n        return [],\n',
    '    if not url or news_source_is_excluded(url):\n        return [],\n') if False else None
replace('bot/extract.py',
    '    if not url or news_source_is_excluded(url):\n        return []\n    try:\n',
    '    if not url or news_source_is_excluded(url):\n        return []\n'
    '    from .news_scottish_club_desks import fetch_scottish_article\n'
    '    handled, scottish_html = fetch_scottish_article(url)\n'
    '    if handled:\n'
    '        return collect_page_image_candidates(scottish_html) if scottish_html else []\n'
    '    try:\n')
replace('bot/extract.py',
    '    if not url or news_source_is_excluded(url):\n        return "", None\n    try:\n',
    '    if not url or news_source_is_excluded(url):\n        return "", None\n'
    '    from .news_scottish_club_desks import fetch_scottish_article\n'
    '    handled, scottish_html = fetch_scottish_article(url)\n'
    '    if handled:\n'
    '        if not scottish_html:\n            return "", None\n'
    '        text = article_text_from_html(scottish_html)\n'
    '        if not text:\n            return "", None\n'
    '        from .news_image_http import pick_news_article_image\n'
    '        try:\n            image = pick_news_article_image(collect_page_image_candidates(scottish_html))\n'
    '        except Exception:\n            image = None\n'
    "        logger.info('[extract] verified Scottish article %s words=%s', url[:120], word_count(text))\n"
    '        return text, image\n'
    '    try:\n')
append('bot/news_football_sources.py', '''
# Official Scottish sources retain the same freshness and publication gates.
from .news_scottish_club_desks import RSS_FEEDS as SCOTTISH_RSS, SOURCE_DESKS as SCOTTISH_DESKS
RSS_FEEDS = RSS_FEEDS + SCOTTISH_RSS
SOURCE_DESKS.update(SCOTTISH_DESKS)
''')
append('bot/news_football_regional_desks.py', '''
from .news_scottish_club_desks import ARTICLE_PROFILES as SCOTTISH_CLUB_PROFILES
_PROFILES.update(SCOTTISH_CLUB_PROFILES)
''')
for path in ('bot/extract.py','bot/news_scottish_club_desks.py','bot/news_football_sources.py','bot/news_football_regional_desks.py'):
    compile(Path(path).read_text(),path,'exec')
    print('NEWS_SCOTTISH_INTEGRATION',path)
