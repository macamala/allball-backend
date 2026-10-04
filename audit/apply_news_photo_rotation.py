"""News-only photo health integration; never touch main, scores or AI limits."""
from pathlib import Path
p=Path('public_index.py');text=p.read_text()
start=text.index('def repair_recent_news_images(')
end=text.index('\ndef _correct_confirmed_deadline_copy',start)
s=text[start:end]
if 'rotate: bool = False' not in s:
    s=s.replace('    recover_limit: int = 8,\n','    recover_limit: int = 8,\n    rotate: bool = False,\n',1)
    s=s.replace('    rows = (\n','    query = (\n',1)
    old='''        .order_by(
            Article.image_url.ilike("%soccernews.com/og/og-image.%").desc(),
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 160)))
        .all()
    )
'''
    new='''    )
    rotation_scope = rotation_cursor = None
    if rotate:
        import os
        from bot.news_image_rotation import next_image_health_rows
        rows, rotation_scope, rotation_cursor = next_image_health_rows(
            query, limit=limit, football_only=os.environ.get('NEWS_FOOTBALL_ONLY') == '1',
            window=max_age_hours,
        )
    else:
        rows = query.order_by(
            Article.image_url.ilike("%soccernews.com/og/og-image.%").desc(),
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        ).limit(max(1, min(int(limit), 160))).all()
'''
    assert s.count(old)==1
    s=s.replace(old,new,1)
    old='''    for article, tax in rows:
        if not tax.public_ok or int(article.id) in touched_ids or not article.source_url:
'''
    new='''    # A transient CDN failure is never grounds to hide an article. Prefer
    # its own source-page photo check within the EXISTING six-check allowance.
    alignment_rows = sorted(rows, key=lambda row: bool(
        probes.get(str(row[0].image_url or '').strip(), (False, 'missing'))[0]))
    for article, tax in alignment_rows:
        if not tax.public_ok or int(article.id) in touched_ids or not article.source_url:
'''
    assert s.count(old)==1;s=s.replace(old,new,1)
    old='''    return changed
'''
    new='''    if rotate:
        from bot.news_image_rotation import finish_image_health_rows
        finish_image_health_rows(rotation_scope, rotation_cursor)
        logger.info('[public_index] News rotating photo check scope=%s checked=%s failed=%s next_id=%s source_checks=%s',
                    rotation_scope, len(rows), dict(reasons), rotation_cursor, checks)
    return changed
'''
    assert s.count(old)==1;s=s.replace(old,new,1)
    text=text[:start]+s+text[end:];p.write_text(text)
p=Path('bot/scheduler.py');text=p.read_text()
old='''            limit=160,
            max_age_hours=72,
            recover_limit=16,
'''
new=old+'            rotate=True,\n'
if new not in text:
    assert text.count(old)==1;p.write_text(text.replace(old,new,1))
for path in ('public_index.py','bot/scheduler.py'):
    compile(Path(path).read_text(),path,'exec')
print('NEWS_PHOTO_ROTATION_APPLIED same 160-photo and 6-source-check limits; no destructive transient repair')
