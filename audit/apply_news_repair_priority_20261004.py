"""Repair selection only; same News tables, row limits and editorial validators."""
from pathlib import Path
file=Path('public_index.py')
text=file.read_text()
start=text.index('def repair_recent_gossip_news(')
end=text.index('\n    hidden = 0',start)
section=text[start:end]
old='    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))\n'
new=(old+'    import os\n'
     "    football_focus = os.environ.get('NEWS_FOOTBALL_ONLY') == '1'\n"
     '    ordering = [func.coalesce(Article.published_at, Article.created_at).desc(), Article.id.desc()]\n'
     '    if football_focus:\n'
     '        # Otherwise newer rows from other sports permanently starve older\n'
     '        # still-public football mistakes. Retain the SAME bounded budget.\n'
     "        ordering.insert(0, (ArticleTaxonomyResolution.resolved_sport == 'football').desc())\n")
if 'football_focus = ' not in section:
    assert section.count(old)==1
    section=section.replace(old,new,1)
    oldorder=('        .order_by(\n'
              '            func.coalesce(Article.published_at, Article.created_at).desc(),\n'
              '            Article.id.desc(),\n'
              '        )\n')
    assert section.count(oldorder)==1
    section=section.replace(oldorder,'        .order_by(*ordering)\n',1)
    section += "\n    logger.info('[public_index] News editorial repair scanned=%s football_focus=%s', len(rows), football_focus)"
    text=text[:start]+section+text[end:]
    file.write_text(text)
compile(file.read_text(),str(file),'exec')
print('NEWS_ONLY_PATCH public_index.py repair_recent_gossip_news selection priority; limits unchanged')
