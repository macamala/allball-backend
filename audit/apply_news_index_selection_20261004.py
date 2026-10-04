"""Apply one reviewed News-only integration; no network, AI or DB writes."""
from pathlib import Path

p = Path('bot/news_official_indexes.py')
text = p.read_text()


def change(old, new):
    global text
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('Source drift in news_official_indexes.py')
    text = text.replace(old, new, 1)


change('def _anchor_candidates(cfg: Dict) -> List[tuple[str, str]]:\n    try:\n',
       'def _anchor_candidates(cfg: Dict) -> List[tuple[str, str]]:\n'
       '    from .news_index_selection import excluded_index_link\n    try:\n')
change('            if not url or url in seen:\n                continue\n            seen.add(url)\n',
       '            if not url or url in seen or excluded_index_link(cfg, url):\n'
       '                continue\n            seen.add(url)\n')
change('        if not url or url in seen:\n            continue\n        text = clean_text(title)\n',
       '        if not url or url in seen or excluded_index_link(cfg, url):\n'
       '            continue\n        text = clean_text(title)\n')
change('def _sitemap_candidates(cfg: Dict, *, publication_times=None) -> List[tuple[str, str]]:\n    try:\n',
       'def _sitemap_candidates(cfg: Dict, *, publication_times=None) -> List[tuple[str, str]]:\n'
       '    from .news_index_selection import excluded_index_link\n    try:\n')
change('        if not (url_ok or title_ok) or loc in seen:\n',
       '        if not (url_ok or title_ok) or loc in seen or excluded_index_link(cfg, loc):\n')
change('    publication_times = {}\n    candidates = _sitemap_candidates(cfg, publication_times=publication_times) if sitemap else _anchor_candidates(cfg)\n',
       '    from .news_index_selection import discovery_config, record_stale_index_page\n'
       '    publication_times = {}\n'
       '    selected_cfg = discovery_config(cfg, known_urls)\n'
       '    candidates = (_sitemap_candidates(selected_cfg, publication_times=publication_times)\n'
       '                  if sitemap else _anchor_candidates(selected_cfg))\n')
change('        item = _hydrate(cfg, url, title, diagnostics=reasons, sitemap_published_at=publication_times.get(url))\n        if item is None:\n            continue\n',
       '        item_reasons = Counter()\n'
       '        item = _hydrate(cfg, url, title, diagnostics=item_reasons, sitemap_published_at=publication_times.get(url))\n'
       '        reasons.update(item_reasons)\n'
       '        if item is None:\n'
       '            record_stale_index_page(cfg, url, item_reasons)\n'
       '            continue\n')
compile(text, str(p), 'exec')
p.write_text(text)
print('NEWS_INDEX_SELECTION_INTEGRATED: eight-link read cap unchanged; no writer or publication bypass')
