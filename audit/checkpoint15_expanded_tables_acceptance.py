"""Real deployed league tables and source rows, not invented table fixtures."""
import json, urllib.request, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c15-expanded-tables');OUT.mkdir(exist_ok=True)
API='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
CASES=[('england-league-one','108'),('england-league-two','109'),('football-eng-national-league','117'),('football-isr-leumit-league','128'),('football-nga-npfl','533'),('football-den-2-division','239'),('football-nor-toppserien','331'),('football-irl-first-division','218')]
def get(pair):
    key,url=pair
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=30) as r:data={'url':url,'http':r.status,'payload':json.load(r),'at':datetime.now(timezone.utc).isoformat()}
    except Exception as e:data={'url':url,'error':str(e)}
    (OUT/(key+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2));return key,data
report={'checked_at':datetime.now(timezone.utc).isoformat(),'tables':[],'browser':[]}
urls=[pair for key,lid in CASES for pair in [('public-'+key,API+'/sports-data/standings?'+urlencode({'league':key})),('native-'+key,'https://www.fotmob.com/api/data/leagues?id='+lid)]]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:data=dict(pool.map(get,urls))
for key,lid in CASES:
    public=data['public-'+key];native=data['native-'+key];p=public.get('payload') or {};n=native.get('payload') or {}
    entries=n.get('table') or [];source=entries[0].get('data',{}).get('table',{}).get('all',[]) if len(entries)==1 else []
    rows=p.get('rows') or [];lookup={str(r.get('team_id')):r for r in rows};diff=[]
    for r in source:
        q=lookup.get(str(r.get('id')))
        if not q:diff.append({'id':r.get('id'),'error':'missing team'});continue
        for ours,theirs in [('position','idx'),('points','pts'),('played','played'),('wins','wins'),('draws','draws'),('losses','losses'),('goal_difference','goalConDiff')]:
            if r.get(theirs) is not None and str(q.get(ours))!=str(r.get(theirs)):diff.append({'id':r.get('id'),'field':ours,'public':q.get(ours),'native':r.get(theirs)})
    passed=public.get('http')==native.get('http')==200 and bool(source) and len(rows)==len(source) and not diff and p.get('season')==n.get('details',{}).get('selectedSeason') and str(n.get('details',{}).get('id'))==lid
    report['tables'].append({'competition':key,'pass':passed,'public_rows':len(rows),'native_rows':len(source),'season':p.get('season'),'diff':diff,'has_team_logos':all(r.get('logo') for r in rows)})
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    for width in (1440,390,320):
        for key,lid in CASES[:3]:
            ctx=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney');page=ctx.new_page();errors=[];network=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:network.append({'url':r.url,'http':r.status}) if '/sports-data/' in r.url else None)
            result={'width':width,'competition':key,'pass':False}
            try:
                page.goto(SITE+'/scores/competition/'+key+'/standings?sport=football',wait_until='domcontentloaded')
                page.locator('.standings-team').first.wait_for(timeout=45000)
                count=page.locator('.standings-team').count();expected=next(r['public_rows'] for r in report['tables'] if r['competition']==key)
                overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                result.update(rows=count,overflow=overflow,no_match_requests=not any('/sports-data/matches/' in r['url'] for r in network),no_match_hero=page.locator('.mc-hero').count()==0)
                result['pass']=count==expected and count>=10 and not overflow and result['no_match_requests'] and result['no_match_hero'] and not errors
                page.screenshot(path=str(OUT/(key+'-'+str(width)+'.png')),full_page=True)
            except Exception as e:result['error']=str(e)
            result.update(errors=errors.copy(),network=network.copy());report['browser'].append(result);ctx.close()
    browser.close()
(OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
assert all(r['pass'] for r in report['tables']+report['browser'])
