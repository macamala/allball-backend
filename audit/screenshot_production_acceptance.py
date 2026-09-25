"""Read-only screenshot acceptance: public API, real desktop/mobile and polling."""
import json, os, urllib.request, concurrent.futures
from urllib.parse import urlencode
from pathlib import Path
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
OUT=Path(os.environ.get('SCORE_QA_OUT','/tmp/screenshot-after'));OUT.mkdir(parents=True,exist_ok=True)
BASE='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
FINALS={
 'ninko-evt-ae423ceaf0d151d8f046':('Everton CD',0,1),
 'ninko-evt-7b5307d620b565fb4693':('Dominican Republic',3,2),
 'ninko-evt-b5aaa116a9c33e3bf553':('Cayman Islands',0,0),
 'ninko-evt-e0f2b3e422fd470e7c79':('Haiti',3,2),
 'ninko-evt-865a1be627176358a4d7':('Atlético Nacional',1,1),
 'ninko-evt-b8b01381a0ceaddbde37':('Alebrijes Oaxaca',1,3),
 'ninko-evt-ae14c2ad24e67fc46d15':('Mineros de Zacatecas',3,0),
 'ninko-evt-9a50af5145a247bf857b':('Costa Rica',3,4),
 'ninko-evt-6d8bf3121dc158b647e1':('Andorra',1,2),
 'ninko-evt-7c872242ee6c70b9f0d4':('Kosovo',1,0)}
HAV='ninko-evt-d0203f3635ffe7d1db45'
REPORT={'checked_at':datetime.now(timezone.utc).isoformat(),'api':{},'browser':[],'errors':[]}
def fetch(name,url):
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=30) as r:
   d={'http':r.status,'url':url,'fetched_at':datetime.now(timezone.utc).isoformat(),'payload':json.load(r)}
 except Exception as e:d={'url':url,'error':str(e)}
 (OUT/(name+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2));return d
urls={}
for day,lo,hi in [('fri25','2026-09-24T14:00:00Z','2026-09-25T13:59:59Z'),('sat26','2026-09-25T14:00:00Z','2026-09-26T13:59:59Z')]:
 for sport in ('football','all'):
  q={'date_from':lo,'date_to':hi}
  if sport=='football':q['sport']=sport
  urls[day+'-'+sport]=BASE+'/sports-data/events?'+urlencode(q)
urls['live']=BASE+'/sports-data/live'
urls['andorra-old']=BASE+'/sports-data/matches/ninko-evt-86345b6cb47a7c4b8524'
urls['havelse-detail']=BASE+'/sports-data/matches/'+HAV
for eid in FINALS:urls['detail-'+eid]=BASE+'/sports-data/matches/'+eid
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=dict(zip(urls,pool.map(lambda p:fetch(*p),urls.items())))
try:
 for name,d in results.items():assert d.get('http')==200,(name,d.get('error'))
 rows=results['fri25-football']['payload']['events'];mapping={r['id']:r for r in rows}
 for eid,(_,h,a) in FINALS.items():
  for r in (mapping[eid],results['detail-'+eid]['payload']['event']):
   assert r['status']=='finished' and not r.get('live'),(eid,r['status'])
   assert (r['score']['home'],r['score']['away'])==(h,a),(eid,r['score'])
 assert len([r for r in rows if 'Andorra'==(r.get('home')or{}).get('name') and 'Malta'==(r.get('away')or{}).get('name')])==1
 old=results['andorra-old']['payload']['event'];assert old['status']=='finished' and old['score']['home']==1 and old['score']['away']==2
 for day in ('fri25','sat26'):
  one=results[day+'-football']['payload'];allp=results[day+'-all']['payload']
  assert {r['id'] for r in one['events']}=={r['id'] for r in allp['events'] if r['sport']=='football'}
  assert allp['snapshot']['complete'] and allp['snapshot']['count']==len(allp['events'])
 for r in ([r for r in results['sat26-football']['payload']['events'] if r['id']==HAV][0],results['havelse-detail']['payload']['event']):
  assert r['status']=='scheduled' and not r.get('live') and r['score']['home'] is None and r['score']['away'] is None,r
 liveids={r['id'] for r in results['live']['payload']['events']};assert not liveids.intersection(set(FINALS)|{HAV})
 since=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat();cursor=None;seen=[]
 for number in range(4):
  q={'since':since,'sport':'football'}
  if cursor:q['cursor']=cursor
  d=fetch('status-delta-'+str(number),BASE+'/sports-data/status-delta?'+urlencode(q))
  assert d.get('http')==200,d
  p=d['payload'];assert 'has_more' in p and 'next_since' in p
  seen.extend(p.get('events',[]));cursor=p.get('next_cursor')
  if not p['has_more']:break
 REPORT['api']={'pass':True,'friday_football':len(rows),'saturday_football':len(results['sat26-football']['payload']['events']),'checked_finals':len(FINALS),'andorra_old_link_pass':True,'havelse_scheduled':True,'delta_rows':len(seen),'delta_pages':number+1,'delta_truncated':p['has_more'],'retirements':sum(bool(r.get('removed')) for r in seen)}
except Exception as e:REPORT['api']={'pass':False,'error':str(e)}
with sync_playwright() as pw:
 browser=pw.chromium.launch()
 context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Australia/Sydney')
 page=context.new_page();errors=[];requests=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('response',lambda r:requests.append({'url':r.url,'status':r.status}) if '/sports-data/' in r.url else None)
 def checks(day,width,phase):
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(400)
  r={'day':day,'width':width,'phase':phase,'checked_at':datetime.now(timezone.utc).isoformat()}
  try:
   main=page.locator('.score-centre-main');main.locator('.score-row').first.wait_for(timeout=40000)
   if day=='2026-09-25':
    for eid,(name,h,a) in FINALS.items():
     row=main.locator('.score-row').filter(has=page.locator('a[href="/scores/event/'+eid+'"]'))
     assert row.count()==1,(name,row.count())
     assert 'is-live' not in (row.get_attribute('class') or ''),name
     assert row.locator('.score-status-text').inner_text()=='FT',(name,row.inner_text())
     assert row.locator('.score-mid').all_text_contents()==[str(h),str(a)],name
    assert main.locator('.score-name').filter(has_text='Andorra').count()==1
   else:
    row=main.locator('.score-row').filter(has=page.locator('a[href="/scores/event/'+HAV+'"]'))
    assert row.count()==1
    assert 'is-live' not in (row.get_attribute('class') or '')
    assert row.locator('.score-status-text').inner_text()=='03:00',row.inner_text()
    assert not page.locator('.score-centre-aside .score-row').filter(has_text='TSV Havelse').count()
   assert not page.evaluate('document.documentElement.scrollWidth > innerWidth+1'),'page overflow'
   assert not errors,errors
   r.update(pass_=True,row_count=main.locator('.score-row').count(),live_rows=main.locator('.score-row.is-live').count())
  except Exception as e:r.update(pass_=False,error=str(e))
  page.screenshot(path=str(OUT/(day+'-'+str(width)+'-'+phase+'.png')),full_page=True)
  REPORT['browser'].append(r)
 for day in ('2026-09-25','2026-09-26'):
  try:
   page.goto(SITE+'/live-scores?sport=football&date='+day,wait_until='domcontentloaded',timeout=60000)
   page.locator('.score-centre-main .score-row').first.wait_for(timeout=45000)
   page.wait_for_timeout(1000)
   checks(day,1440,'initial')
   before=len(requests);page.wait_for_timeout(55000)
   checks(day,1440,'after-poll')
   REPORT['browser'][-1]['poll_responses']=requests[before:]
   for width in (390,320):checks(day,width,'responsive')
  except Exception as e:REPORT['errors'].append({'day':day,'error':str(e)})
 REPORT['assets']=page.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)')
 REPORT['network']=requests;REPORT['javascript_errors']=errors
 context.close();browser.close()
(OUT/'acceptance.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2))
print(json.dumps(REPORT,ensure_ascii=False,indent=2))
assert REPORT['api'].get('pass') and not REPORT['errors'] and all(r.get('pass_') for r in REPORT['browser']), 'Screenshot production acceptance FAILED'
