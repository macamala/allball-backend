"""Nine alternative metadata endpoints; does not repeat the prior59 reads."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from news03_source_probe import probe, NOW

EXTRA = [
    ('basketball','BBC Sport','https://feeds.bbci.co.uk/sport/basketball/rss.xml','rss'),
    ('american-football','BBC Sport','https://feeds.bbci.co.uk/sport/american-football/rss.xml','rss'),
    ('ice-hockey','BBC Sport','https://feeds.bbci.co.uk/sport/ice-hockey/rss.xml','rss'),
    ('baseball','BBC Sport','https://feeds.bbci.co.uk/sport/baseball/rss.xml','rss'),
    ('mma','BBC Sport','https://feeds.bbci.co.uk/sport/mixed-martial-arts/rss.xml','rss'),
    ('darts','BBC Sport','https://feeds.bbci.co.uk/sport/darts/rss.xml','rss'),
    ('handball','IHF','https://www.ihf.info/news/rss.xml','rss'),
    ('dota-2','Valve','https://store.steampowered.com/feeds/news/app/570/?l=english','rss'),
    ('harness-racing','USTA','https://ustrottingnews.com/feed/','rss'),
]
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool: rows=list(pool.map(probe,EXTRA))
    report={'observed_at':NOW.isoformat(),'mode':'incremental source metadata only; no AI/DB/production/rights claim','sources':rows}
    out=Path('evidence');out.mkdir(exist_ok=True)
    (out/'news03-extra-sources.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('NEWS03_EXTRA_SOURCES '+json.dumps(report,ensure_ascii=False))
