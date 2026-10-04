"""Repair a source-admission false negative; no final publication gate changes."""
from pathlib import Path
p=Path('bot/quality.py');s=p.read_text()
old='''    if looks_like_garbage(title) or looks_like_garbage(body):
        return False, "garbage"
'''
new='''    title_garbage = looks_like_garbage(title)
    if title_garbage and not require_english:
        # Japanese/Chinese source headlines carry words without Latin spacing.
        # Observed J.LEAGUE headline: MF熊坂の負傷を発表【柏】 (11 letters).
        # This only repairs the short-headline length heuristic on intake;
        # body, sport, source, image, date, originality and fact checks remain.
        native = re.findall(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', title)
        if (6 <= len(native) < 40 and len(set(native)) >= 4
                and sum(c.isalpha() for c in title) >= 8
                and len(body) >= MIN_FACT_CHARS
                and not re.search(r'[<>]|function\\(|<!|\\[\\+|[\\x00-\\x08]', title, re.I)):
            title_garbage = False
    if title_garbage or looks_like_garbage(body):
        return False, "garbage"
'''
if new not in s:
    assert s.count(old)==1,'Source drift in quality.py'
    p.write_text(s.replace(old,new,1))
compile(p.read_text(),str(p),'exec')
print('NEWS_COMPACT_SOURCE_HEADLINE_REPAIRED; English output and all factual gates unchanged')
