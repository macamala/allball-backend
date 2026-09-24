"""Verify public score consistency and group-table navigation without admin access."""
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as daytime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

OUT = Path('/tmp/football-release-check'); OUT.mkdir(exist_ok=True)
BASE = 'https://allball-backend-production.up.railway.app'
SYDNEY = ZoneInfo('Australia/Sydney')
now = datetime.now(timezone.utc)
day = now.astimezone(SYDNEY).date()
start = datetime.combine(day, daytime(), tzinfo=SYDNEY)
params = {'date_from':start.astimezone(timezone.utc).isoformat(), 'date_to':(start+timedelta(days=1,microseconds=-1)).astimezone(timezone.utc).isoformat()}
expected = {
 'ninko-evt-010ca31ce1e357f39eb6':[1,2],
 'ninko-evt-f4b4059af69d194fa8fa':[1,1],
 'ninko-evt-db356fd40b6f7266298f':[3,2],
 'ninko-evt-6f490b6e1d15a68d06e3':[1,0],
 'ninko-evt-e65b8b18fa540b5cc323':[3,1],
 'ninko-evt-7c872242ee6c70b9f0d4':[1,0],
 'ninko-evt-1f42f1c78ecce9019169':[0,2],
 'ninko-evt-86345b6cb47a7c4b8524':[1,2],
}

def read(target):
 name,url=target
 try:
  with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-release-QA/1.0'}),timeout=35) as r:
   record={'url':url,'http_status':r.status,'fetched_at':datetime.now(timezone.utc).isoformat(),'payload':json.loads(r.read())}
 except Exception as e:
  record={'url':url,'error':str(e)[:300]}
 (OUT/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False))
 return name,record

def events(record):
 data=record.get('payload') or {}
 return data.get('events') or data.get('matches') or []

targets=[('football',BASE+'/sports-data/events?'+urlencode({**params,'sport':'football'})),
 ('all-sports',BASE+'/sports-data/events?'+urlencode(params)),
 ('standings',BASE+'/sports-data/standings?league=uefa-nations-league'),
 ('live',BASE+'/sports-data/live?sport=football')]
with ThreadPoolExecutor(max_workers=3) as pool: data=dict(pool.map(read,targets))
football=events(data['football'])
all_football=[r for r in events(data['all-sports']) if r.get('sport')=='football']
checks={'checked_at':now.isoformat(),'football_count':len(football),'all_sport_football_count':len(all_football),'score_checks':{},'status_counts':dict(Counter(r.get('status') for r in football))}
for key,want in expected.items():
 row=next((r for r in football if r.get('id')==key),{})
 ar=next((r for r in all_football if r.get('id')==key),{})
 score=row.get('score') or {}; asc=ar.get('score') or {}
 checks['score_checks'][key]={'expected':want,'score':[score.get('home'),score.get('away')],'status':row.get('status'),'group':row.get('group'),'all_sports_score':[asc.get('home'),asc.get('away')],'all_sports_status':ar.get('status'),'pass':row.get('status')=='finished' and [score.get('home'),score.get('away')]==want and [asc.get('home'),asc.get('away')]==want}
for eid in ('ninko-evt-010ca31ce1e357f39eb6','ninko-evt-86345b6cb47a7c4b8524'):
 read(('detail-'+eid,BASE+'/sports-data/matches/'+eid))

browser_results=[]
with sync_playwright() as p:
 browser=p.chromium.launch()
 for name,width,height in [('desktop',1440,1050),('mobile',390,844)]:
  context=browser.new_context(viewport={'width':width,'height':height},timezone_id='Australia/Sydney')
  page=context.new_page(); errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  rec={'viewport':name}
  try:
   page.goto('https://ninkosports.com/live-scores?sport=football&date='+str(day),wait_until='domcontentloaded',timeout=35000)
   page.wait_for_selector('.score-row',timeout=35000)
   page.wait_for_timeout(1500)
   rec['main_rows']=page.locator('.score-centre-main .score-row').count()
   rec['body']=page.locator('body').inner_text()
   rec['overflow']=page.evaluate('document.documentElement.scrollWidth > innerWidth')
   rec['groups']=page.locator('.score-centre-main .score-comp-title').all_text_contents()
   rec['missing_assets']=page.locator('.score-centre-main [data-asset-missing]').evaluate_all('(xs)=>xs.map(x=>({type:x.getAttribute("data-asset-missing"),row:x.closest(".score-row,.score-comp-head")?.innerText}))')
   rec['broken_images']=page.locator('img').evaluate_all('(xs)=>xs.filter(x=>x.complete&&!x.naturalWidth).map(x=>x.src)')
   page.screenshot(path=str(OUT/(name+'-board.png')),full_page=True)
   section=page.locator('.score-centre-main .score-comp').filter(has=page.locator('.score-name',has_text='Serbia')).first
   rec['serbia_group']=section.locator('.score-comp-title').inner_text()
   table_link=section.locator('.score-comp-standings')
   rec['table_link']=table_link.get_attribute('href')
   table_link.click()
   page.wait_for_selector('#mc-panel-standings:not([hidden]) table',timeout=60000)
   rec['table_visible']=page.locator('#mc-panel-standings').is_visible()
   rec['selected_group']=page.locator('select[aria-label="Standings group"] option:checked').inner_text()
   rec['group_options']=page.locator('select[aria-label="Standings group"] option').all_text_contents()
   rec['table_teams']=page.locator('#mc-panel-standings .standings-team').all_text_contents()
   rec['table_body']=page.locator('#mc-panel-standings').inner_text()
   rec['match_overflow']=page.evaluate('document.documentElement.scrollWidth > innerWidth')
   page.screenshot(path=str(OUT/(name+'-table.png')),full_page=True)
   selector=page.locator('select[aria-label="Standings group"]')
   target=selector.locator('option',has_text='UEFA Nations League B Grp. 3').first
   selector.select_option(target.get_attribute('value'))
   rec['switched_teams']=page.locator('#mc-panel-standings .standings-team').all_text_contents()
   rec['group_table_pass']=len(rec['group_options'])==14 and set(rec['table_teams'])=={'Serbia','Greece','Netherlands','Germany'} and len(rec['switched_teams'])==4
  except Exception as e:
   rec['error']=str(e)
   page.screenshot(path=str(OUT/(name+'-error.png')),full_page=True)
  rec['errors']=errors
  browser_results.append(rec)
  context.close()
 browser.close()
(OUT/'browser.json').write_text(json.dumps(browser_results,ensure_ascii=False,indent=2))
# A fresh second read verifies persistence after the browser requests and polling.
_, second=read(('football-second',targets[0][1]))
checks['second_count']=len(events(second))
checks['persistent_scores']={r['id']:[(r.get('score')or{}).get('home'),(r.get('score')or{}).get('away')] for r in events(second) if r.get('id') in expected}
checks['browser_summary']=[{k:v for k,v in r.items() if k not in ('body','table_body')} for r in browser_results]
(OUT/'summary.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False))
