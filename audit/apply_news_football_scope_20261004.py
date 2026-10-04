"""Bounded integration on the isolated audit branch; no network or deployment."""
from pathlib import Path


def replace(path, old, new):
    file = Path(path)
    text = file.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('Source drift in ' + path)
    file.write_text(text.replace(old, new, 1))


replace('bot/news_policy.py',
    "    value = str(title or '').casefold()\n    if RALLY_TITLE_RE.search(value):\n",
    "    from .news_football_scope_guard import other_sport_headline\n"
    "    observed = other_sport_headline(title)\n"
    "    if observed:\n        return observed\n"
    "    value = str(title or '').casefold()\n    if RALLY_TITLE_RE.search(value):\n")
replace('bot/news_policy.py',
    '    for expected_host, prefix, sport in _SOURCE_PATH_SPORTS:\n',
    '    from .news_football_scope_guard import reviewed_other_sport_path\n'
    '    observed = reviewed_other_sport_path(url)\n'
    '    if observed:\n        return observed\n'
    '    for expected_host, prefix, sport in _SOURCE_PATH_SPORTS:\n')
replace('bot/news_policy.py',
    "def source_path_conflict_reason(item, sport):\n    expected = source_path_sport_hint((item or {}).get('url'))\n",
    "def source_path_conflict_reason(item, sport):\n"
    "    from .news_football_scope_guard import football_scope_conflict\n"
    "    conflict = football_scope_conflict(item, sport)\n"
    "    if conflict:\n        return conflict\n"
    "    expected = source_path_sport_hint((item or {}).get('url'))\n")
replace('bot/news_policy.py',
    'def non_article_news_reason(item):\n',
    'def non_article_news_reason(item):\n'
    '    from .news_football_scope_guard import video_game_product_reason\n'
    '    product = video_game_product_reason(item)\n'
    '    if product:\n        return product\n')
replace('bot/news_league_index.py',
    'def repair_football_league_menus(db, limit=300):\n',
    'def repair_football_league_menus(db, limit=600):\n'
    '    # Cover the existing bounded recent archive, not just its newest half.\n'
    '    # The hard 600-row cap and all original public/date/sport gates remain.\n')
for path in ('bot/news_policy.py', 'bot/news_league_index.py'):
    compile(Path(path).read_text(), path, 'exec')
    print('NEWS_SCOPE_PATCH', path)
