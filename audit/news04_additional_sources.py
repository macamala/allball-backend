"""Second bounded metadata pass. New sources only; no AI/DB/publishing."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from audit import news04_source_probe as base

ROWS = [
 ('handball','IHF','https://www.ihf.info/news/rss.xml'),
 ('futsal','Liga Nacional de Futsal','https://lnfoficial.com.br/feed/'),
 ('water-polo','USA Water Polo','https://usawaterpolo.org/rss.aspx?path=general'),
 ('water-polo','SwimSwam','https://swimswam.com/category/water-polo/feed/'),
 ('winter-sports','Etusuora','https://etusuora.com/rss/en/rss_winter_sports.xml'),
 ('winter-sports','FasterSkier','https://fasterskier.com/feed/'),
 ('lacrosse','Inside Lacrosse','https://www.insidelacrosse.com/rss.php'),
 ('darts','Dartsnews','https://dartsnews.com/rss'),
 ('esports','Esports.gg','https://esports.gg/feed/'),
 ('league-of-legends','Esports.gg','https://esports.gg/games/league-of-legends/feed/'),
 ('valorant','Esports.gg','https://esports.gg/games/valorant/feed/'),
 ('overwatch','Esports.gg','https://esports.gg/games/overwatch/feed/'),
 ('call-of-duty','Esports.gg','https://esports.gg/games/call-of-duty/feed/'),
 ('rocket-league','Esports.gg','https://esports.gg/games/rocket-league/feed/'),
 ('dota-2','Esports.gg','https://esports.gg/games/dota-2/feed/'),
 ('esports','Esports.net','https://www.esports.net/feed/'),
 ('league-of-legends','Esports.net','https://www.esports.net/news/lol/feed/'),
 ('valorant','Esports.net','https://www.esports.net/news/valorant/feed/'),
 ('overwatch','Esports.net','https://www.esports.net/news/overwatch/feed/'),
 ('call-of-duty','Esports.net','https://www.esports.net/news/call-of-duty/feed/'),
 ('rocket-league','Esports.net','https://www.esports.net/news/rocket-league/feed/'),
 ('ea-sports-fc','Esports.net','https://www.esports.net/news/fifa/feed/'),
 ('ea-sports-fc','RealSport101','https://realsport101.com/feed.xml'),
]
if __name__=='__main__':
 base.LOCKS.update({urlsplit(row[2]).hostname:threading.Lock() for row in ROWS})
 with ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(base.probe,ROWS))
 report={'observed_at':base.NOW.isoformat(),'mode':'new bounded GET metadata and one eligible page per feed; no AI/DB/publishing',
         'rows':rows,'states':dict(Counter(r['state'] for r in rows)),
         'limitations':['Not a production/news completeness or rights claim.','Category URLs are candidates, not assumed successful feeds.','No blocked DotEsports/TotalWaterpolo/ITTF endpoint is retried or bypassed.']}
 Path('evidence').mkdir(exist_ok=True)
 Path('evidence/news04-additional-sources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
