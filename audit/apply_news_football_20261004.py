"""Apply reviewed News-only edits on the isolated audit branch, never deploy."""
from pathlib import Path


def replace_once(path, old, new):
    target = Path(path)
    text = target.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('Source drift: ' + path)
    target.write_text(text.replace(old, new, 1))


replace_once('bot/news_policy.py',
    '    # Source-only lexical equivalents, not calculations. Confirmed false hold:\n',
    '    # Explicit Portuguese thousand-person spellings; source-only, no new fact.\n'
    '    from .news_count_lexemes import portuguese_count_equivalents\n'
    '    tokens.update(portuguese_count_equivalents(text))\n'
    '    # Source-only lexical equivalents, not calculations. Confirmed false hold:\n')
replace_once('bot/news_policy.py',
    '    # Branded daily betting-slip roundups contain sports names and results,\n',
    '    # Audited BET INFO daily betting product: reject before AI calls, not\n'
    '    # ordinary reporting about betting investigations or league sponsors.\n'
    "    if (re.match(r'^\\s*bet[\\s-]+info\\s*[:|–—-]', title)\n"
    "            and re.search(r'\\b(?:najigranij\\w*|parov\\w*|tiket\\w*|kvot\\w*)\\b', title)):\n"
    "        return 'non_article_betting_product'\n"
    '    # Branded daily betting-slip roundups contain sports names and results,\n')

replace_once('bot/news_source_holds.py',
    '        for url, reason in _CJK_REPAIR_REASONS.items():\n',
    "        count_repair_url = 'https://ge.globo.com/futebol/futebol-internacional/noticia/2026/10/04/clube-suico-apresenta-projeto-de-estadio-com-montanha-russa-veja.ghtml'\n"
    '        if count_repair_url in hashes:\n'
    '            # Only the observed pre-fix Sion number-format hold may retry.\n'
    '            # A new attempt still passes every independent publication gate.\n'
    '            cursor.execute(\n'
    '                "UPDATE news_ai_source_holds SET expires_at=NOW(), "\n'
    '                "reason=\'audited-portuguese-count-spelling-repaired\', updated_at=NOW() "\n'
    '                "WHERE source_hash=%s AND expires_at > NOW() "\n'
    '                "AND reason=\'unsupported_number\' AND updated_at < %s::timestamptz",\n'
    "                (hashes[count_repair_url], '2026-10-04T05:22:00Z'),\n"
    '            )\n'
    '            if cursor.rowcount:\n'
    "                logger.info('[source_holds] expired audited pre-fix Portuguese count cooldown=%s', cursor.rowcount)\n"
    '        for url, reason in _CJK_REPAIR_REASONS.items():\n')

replace_once('bot/news_publisher_media.py',
    "        return host == 'soccernews.com' and bool(re.fullmatch(r'/og/og-image\\.(?:png|jpe?g|webp)', path))\n",
    "        if host == 'getfootballnewsbene.com' and path == '/wp-content/uploads/2023/02/gbenefnwhitesquare512.png':\n"
    '            return True\n'
    "        return host == 'soccernews.com' and bool(re.fullmatch(r'/og/og-image\\.(?:png|jpe?g|webp)', path))\n")

for path, content in {
    'bot/news_football_sources.py': '\n# Reviewed additional desks share this same intake and all publication gates.\nfrom .news_verified_desks import RSS_FEEDS as VERIFIED_RSS, SOURCE_DESKS as VERIFIED_DESKS\nRSS_FEEDS = RSS_FEEDS + VERIFIED_RSS\nSOURCE_DESKS.update(VERIFIED_DESKS)\n',
    'bot/news_football_regional_desks.py': '\n# Same visible-body and own-photo rules for additional reviewed publishers.\nfrom .news_verified_desks import ARTICLE_PROFILES as VERIFIED_DESK_PROFILES\n_PROFILES.update(VERIFIED_DESK_PROFILES)\n',
}.items():
    target = Path(path)
    if content not in target.read_text():
        target.write_text(target.read_text() + content)

for path in ('bot/news_policy.py', 'bot/news_source_holds.py', 'bot/news_publisher_media.py',
             'bot/news_football_sources.py', 'bot/news_football_regional_desks.py'):
    compile(Path(path).read_text(), path, 'exec')
    print('NEWS_PATCH', path)
