"""Apply reviewed News-only edits. No network, DB, AI, deployment or main writes."""
from pathlib import Path


def patch(path, old, new):
    file=Path(path);text=file.read_text()
    if new in text:return
    if text.count(old)!=1:raise RuntimeError('Source drift: '+path)
    file.write_text(text.replace(old,new,1))


def append(path, text):
    file=Path(path)
    if text not in file.read_text():file.write_text(file.read_text()+text)


append('bot/news_football_sources.py', '\n# Official club desks share the existing writer, validation and freshness gates.\nfrom .news_football_club_intake_b import RSS_FEEDS as CLUB_B_RSS, HTML_INDEXES as CLUB_B_HTML\nRSS_FEEDS = RSS_FEEDS + CLUB_B_RSS\nHTML_INDEXES = HTML_INDEXES + CLUB_B_HTML\n')
append('bot/news_football_regional_desks.py', '\nfrom .news_football_club_intake_b import ARTICLE_PROFILES as CLUB_B_PROFILES\n_PROFILES.update(CLUB_B_PROFILES)\n')
patch('bot/extract.py', '    if regional_hero_scope(canonical):\n',
    '    from .news_football_club_intake_b import napredak_article_photos\n'
    '    verified_club_photos = napredak_article_photos(html, canonical)\n'
    '    if verified_club_photos is not None:\n        return verified_club_photos\n'
    '    if regional_hero_scope(canonical):\n')
patch('bot/extract.py', '    if body_class or body_id or body_tag:\n',
    '    from .news_football_club_intake_b import napredak_single_post\n'
    '    single_post = napredak_single_post(html, canonical)\n'
    '    if single_post is not None:\n        if not single_post:\n            return \'\'\n        html = single_post\n'
    '    if body_class or body_id or body_tag:\n')
patch('bot/extract.py', '    if text and source_category:\n',
    '    from .news_football_club_intake_b import source_youth_category, YOUTH_CONTEXT\n'
    '    if text and source_youth_category(canonical, \'\', text):\n        source_category = YOUTH_CONTEXT\n'
    '    if text and source_category:\n')
patch('bot/news_fact_guard.py', '        context_reason = preserve_women_qualifier_reason(source, draft)\n',
    '        from .news_football_club_intake_b import preserve_youth_qualifier_reason\n'
    '        context_reason = (preserve_women_qualifier_reason(source, draft)\n'
    '                          or preserve_youth_qualifier_reason(source, draft))\n')
patch('bot/news_football_sections.py', "    youth = bool(age_team or re.search(r'\bacademy\b', title))\n".replace('\b', '\\b'),
    "    youth = bool(age_team or re.search(r'\\b(?:academy|youth football|youth teams?|junior teams?|cadet teams?|pioneer teams?)\\b', lead))\n")
patch('bot/news_football_sections.py', "    country_fixture = headline_national_fixture(getattr(article, 'title', ''))\n",
    "    from .news_football_subject_context import national_primary_subject, general_football_governance\n"
    "    country_fixture = (headline_national_fixture(getattr(article, 'title', ''))\n"
    "                       or national_primary_subject(getattr(article, 'title', ''))\n"
    "                       or (national_primary_subject(getattr(article, 'summary', ''))\n"
    "                           and not _club_section(title, '', article, False, today)))\n")
patch('bot/news_football_sections.py', "    headline_club = _club_section(title, '', article, False, today)\n    national = country_fixture",
    "    headline_club = _club_section(title, '', article, False, today)\n"
    "    source_menu = source_menu_association(getattr(article, 'source_url', None) or getattr(article, 'external_id', None))\n"
    "    lead_national = national_primary_subject(getattr(article, 'summary', '')) and not headline_club\n"
    "    national = country_fixture or lead_national")
patch('bot/news_football_sections.py', '    if not national and not _club_section(title, summary, article, False, today):\n',
    "    if not national and source_menu and not re.search(r'\\b(?:cup|pokal|coppa|copa del rey)\\b', title):\n"
    '        # An admitted domestic article category beats incidental player biography.\n'
    '        # Explicit national, women and youth headline/lead subjects still win.\n'
    '        return source_menu\n'
    '    if not national and not _club_section(title, summary, article, False, today):\n')
patch('bot/news_football_sections.py', "    if re.search(r'\\b(?:fifa|uefa|european club association|world football clubs)\\b', lead) and re.search(",
    "    if general_football_governance(title, summary):\n        return 'football-international'\n"
    "    if re.search(r'\\b(?:fifa|uefa|european club association|world football clubs)\\b', lead) and re.search(")
patch('bot/news_football_source_context.py', '_SOURCE_MENUS = (\n',
    '_SOURCE_MENUS = (\n'
    "    ('www.marca.com', r'^/futbol/primera-division/20\\d{2}/\\d{2}/\\d{2}/[^/]+\\.html$', 'spain-la-liga'),\n"
    "    ('www.marca.com', r'^/futbol/segunda-division/20\\d{2}/\\d{2}/\\d{2}/[^/]+\\.html$', 'spain-la-liga-2'),\n"
    "    ('www.record.pt', r'^/futebol/futebol-nacional/liga-betclic/[^/]+/detalhe/[^/]+$', 'portugal-primeira-liga'),\n"
    "    ('www.record.pt', r'^/futebol/futebol-nacional/2--liga/[^/]+/detalhe/[^/]+$', 'portugal-liga-2'),\n")
patch('bot/news_football_scope_guard.py', "('/modalidades/triatlo/', 'triathlon')):",
    "('/modalidades/triatlo/', 'triathlon'),\n                              ('/modalidades/golfe/', 'golf')):")
patch('bot/news_football_scope_guard.py', "    return 'taxonomy_football_scope_conflict' if expected else None\n",
    "    if not expected:\n"
    "        lead = plain(str((item or {}).get('title') or '') + ' ' + str((item or {}).get('summary') or ''))\n"
    "        body = plain((item or {}).get('body') or '')[:750]\n"
    "        football = re.search(r'\\b(?:football|soccer|futebol|fudbal)\\b', lead)\n"
    "        if (not football and re.search(r'\\b(?:golfer|golf|golfe)\\b', body)\n"
    "                and len(re.findall(r'\\b(?:birdies?|bogeys?|under[ -]par|strokes?|holes?)\\b', body)) >= 2):\n"
    "            expected = 'golf'\n"
    "        if (not football and re.search(r'comite olimpico de portugal', lead)\n"
    "                and re.search(r'\\b(?:research projects?|sports research)\\b', lead)\n"
    "                and re.search(r'\\b(?:grants?|funding)\\b', lead)):\n"
    "            expected = 'multisport-research'\n"
    "    return 'taxonomy_football_scope_conflict' if expected else None\n")
patch('bot/news_official_indexes.py',
    'def _hydrate_source(cfg: Dict, limit: int, *, sitemap: bool = False) -> List[Dict]:',
    'def _hydrate_source(cfg: Dict, limit: int, *, sitemap: bool = False, known_urls=()) -> List[Dict]:')
patch('bot/news_official_indexes.py', '    reasons = Counter()\n    for url, title in candidates:\n',
    '    reasons = Counter()\n    from .news_policy import news_source_identity\n'
    '    known = {news_source_identity(url) for url in known_urls if news_source_identity(url)}\n'
    '    for url, title in candidates:\n        if news_source_identity(url) in known:\n'
    "            reasons['already_ingested_before_hydration'] += 1\n            continue\n")
patch('bot/news_official_indexes.py', 'def fetch_official_index_entries(max_per_source: int = 3) -> List[Dict]:',
    'def fetch_official_index_entries(max_per_source: int = 3, *, known_urls=()) -> List[Dict]:')
patch('bot/news_official_indexes.py', '_hydrate_source(cfg, limit)]', '_hydrate_source(cfg, limit, known_urls=known_urls)]')
patch('bot/news_official_indexes.py', '_hydrate_source(cfg, limit, sitemap=True),', '_hydrate_source(cfg, limit, sitemap=True, known_urls=known_urls),')
patch('bot/fetch_sources.py', '                queued.extend(fetch_official_index_entries(per_feed))\n',
    '                # Same bounded source history as duplicate admission, before\n'
    '                # the per-source quota so known headlines do not starve new ones.\n'
    '                known_rows = db.query(Article.source_url, Article.external_id).filter(\n'
    '                    Article.source_url.isnot(None)).order_by(Article.id.desc()).limit(500).all()\n'
    '                known_urls = frozenset(value for pair in known_rows for value in pair if value)\n'
    '                queued.extend(fetch_official_index_entries(per_feed, known_urls=known_urls))\n')
for path in Path('bot').glob('*.py'):
    compile(path.read_text(), str(path), 'exec')
print('NEWS_FILL_B_APPLIED')
