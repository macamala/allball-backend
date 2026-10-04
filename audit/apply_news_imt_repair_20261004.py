"""Repair the observed Cyrillic acronym false hold, never skip factual checks."""
from pathlib import Path

def patch(path,old,new):
    p=Path(path);s=p.read_text()
    if new in s:return
    if s.count(old)!=1:raise RuntimeError('Source drift: '+path)
    p.write_text(s.replace(old,new,1))

patch('bot/news_fact_guard.py',
    '        src_acronyms.update(source_cjk_acronyms(source))\n',
    '        src_acronyms.update(source_cjk_acronyms(source))\n'
    '        # Official Crvena zvezda article, 2026-10-03: the literal club\n'
    '        # acronym ИМТ is IMT in Latin script. This adds no club, match,\n'
    '        # opponent, league or role absent from the source.\n'
    "        if re.search(r'(?<!\\w)ИМТ(?!\\w)', source or '', re.I):\n"
    "            src_acronyms.add('IMT')\n")
patch('bot/news_policy.py',
    '    if re.search(r"\\b(?:today[’\']?s papers|paper talk|newspaper round[- ]?up)\\b", title):\n',
    "    if re.match(r'^\\s*papers\\s*:', title):\n"
    "        return 'non_article_newspaper_roundup'\n"
    '    if re.search(r"\\b(?:today[’\']?s papers|paper talk|newspaper round[- ]?up)\\b", title):\n')
patch('bot/news_source_holds.py',
    '        for url, reason in _CJK_REPAIR_REASONS.items():\n',
    "        imt_url = 'https://www.crvenazvezdafk.com/vesti/dijeng-postigao-najlepsi-gol-u-septembru'\n"
    '        if imt_url in hashes:\n'
    '            cursor.execute(\n'
    '                "UPDATE news_ai_source_holds SET expires_at=NOW(), "\n'
    '                "reason=\'audited-source-imt-spelling-repaired\', updated_at=NOW() "\n'
    '                "WHERE source_hash=%s AND expires_at > NOW() "\n'
    '                "AND reason=\'unsupported_acronym:IMT\' AND updated_at < %s::timestamptz",\n'
    "                (hashes[imt_url], '2026-10-04T06:45:00Z'),\n"
    '            )\n'
    '            if cursor.rowcount:\n'
    "                logger.info('[source_holds] expired exact pre-fix IMT source hold=%s', cursor.rowcount)\n"
    '        for url, reason in _CJK_REPAIR_REASONS.items():\n')
for path in ('bot/news_fact_guard.py','bot/news_policy.py','bot/news_source_holds.py'):
    compile(Path(path).read_text(),path,'exec')
print('NEWS_IMT_REPAIR_APPLIED source token equivalence and one original retry only')
