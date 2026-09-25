"""Real public C14 data/UI checks; synthetic clock check isolated and labeled."""
import json,time,urllib.request,concurrent.futures
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c14-public');OUT.mkdir(exist_ok=True)
API='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
MATCH='ninko-evt-8ea488bb6f0bcf5038b7'
report={'checked_at':datetime.now(timezone.utc).isoformat(),'profiles':[],'ui':[],'errors':[]}
def get(name,url):
    start=time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=30) as r:p={'http':r.status,'payload':json.load(r)}
    except Exception as e:p={'error':str(e)}
    p.update(url=url,seconds=time.monotonic()-start,fetched_at=datetime.now(timezone.utc).isoformat());(OUT/(name+'.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2));return p
for pid,name in [(825815,'Aidan Keena'),(1234030,'Liam Hughes')]:
    native=get('native-'+str(pid),'https://www.fotmob.com/api/data/playerData?id='+str(pid))
    public=get('player-'+str(pid),API+'/sports-data/players/'+str(pid)+'?'+urlencode({'name':name,'event_id':MATCH}))
    p=public.get('payload',{}).get('player') or {};n=native.get('payload') or {};headline=next((r.get('value') for r in n.get('playerInformation',[]) if r.get('translationKey')=='transfer_value'),{}) or {}
    passed=bool(public.get('http')==native.get('http')==200 and p.get('current_club',{}).get('id')==str(n.get('primaryTeam',{}).get('teamId')) and p.get('market_value',{}).get('amount')==headline.get('numberValue') and p.get('market_value',{}).get('currency')=='EUR' and p.get('career') and p.get('season_summary',{}).get('stats') and 'profile_ref' not in p)
    report['profiles'].append({'id':pid,'pass':passed,'club':p.get('current_club'),'value':p.get('market_value'),'career_rows':len(p.get('career') or []),'season':p.get('season_summary')})
report['score_reads']=[]
for n in range(3):
    d=get('light-score-'+str(n),API+'/sports-data/matches/'+MATCH+'/score');e=d.get('payload',{}).get('event') or {}
    report['score_reads'].append({'pass':d.get('http')==200 and e.get('id')==MATCH and e.get('status')=='finished' and e.get('score',{}).get('away')==1,'seconds':d['seconds'],'observed_at':e.get('score_observed_at')})
get('andorra-light',API+'/sports-data/matches/ninko-evt-86345b6cb47a7c4b8524/score')
club=get('club',API+'/sports-data/teams/6361?'+urlencode({'sport':'football','name':'Sligo Rovers'}))
report['team_results']=len(club.get('payload',{}).get('results') or [])
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    for width in (1440,390,320):
        ctx=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney');page=ctx.new_page();errors=[];network=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:network.append({'url':r.url,'status':r.status}) if '/sports-data/' in r.url else None)
        try:
            page.goto(SITE,wait_until='domcontentloaded');page.locator('.page-home .hero-lead-link').wait_for(timeout=45000);page.wait_for_timeout(600)
            no_scores=page.locator('.page-home .score-row, .page-home .portal-rail, .page-home .live-scores-rail').count()==0 and not any('/sports-data/events' in r['url'] for r in network)
            report['ui'].append({'page':'home','width':width,'pass':no_scores and not page.evaluate('document.documentElement.scrollWidth>innerWidth+1') and not errors,'score_requests':network.copy()});page.screenshot(path=str(OUT/f'home-{width}.png'),full_page=False)
            page.goto(SITE+'/live-scores?sport=football&date=2026-09-25',wait_until='domcontentloaded');page.locator('.score-centre-main .score-row-link').first.wait_for(timeout=45000)
            heads=page.locator('.score-centre-main .score-comp-title').all_text_contents();indices=[i for i,x in enumerate(heads) if x.startswith('UEFA Nations League')]
            passed=bool(indices) and indices==list(range(min(indices),max(indices)+1)) and min(indices)==0
            report['ui'].append({'page':'football-order','width':width,'pass':passed and not page.evaluate('document.documentElement.scrollWidth>innerWidth+1') and not errors,'headings':heads});page.screenshot(path=str(OUT/f'football-{width}.png'))
            page.goto(SITE+'/players/825815?'+urlencode({'name':'Aidan Keena','event_id':MATCH}),wait_until='domcontentloaded');page.locator('.player-value-card').wait_for(timeout=45000)
            report['ui'].append({'page':'player','width':width,'pass':page.locator('.player-career li').count()>0 and page.locator('.player-season-grid dd').count()>0 and page.locator('.player-club-link').count()==1 and not page.evaluate('document.documentElement.scrollWidth>innerWidth+1') and not errors,'valuation_text':page.locator('.player-value-card').inner_text(),'club_text':page.locator('.player-club-link').inner_text(),'career_rows':page.locator('.player-career li').count()});page.screenshot(path=str(OUT/f'player-{width}.png'),full_page=True)
            report['bundle']=page.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)')
        except Exception as e:
            report['errors'].append({'width':width,'error':str(e)});page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
        report['errors'].extend(errors);ctx.close()
    # Controlled response data in a separate browser only: not source latency evidence.
    ctx=browser.new_context(viewport={'width':390,'height':1000},timezone_id='Australia/Sydney');page=ctx.new_page();light=[];initial=datetime.now(timezone.utc);base={'id':'c14-clock-probe','sport':'football','event_family':'team_match','competition_key':'qa','home':{'name':'Controlled Home'},'away':{'name':'Controlled Away'},'start_time':(initial-timedelta(hours=1)).isoformat(),'status':'live','live':True,'live_class':'CONFIRMED_LIVE','score_observed_at':initial.isoformat(),'score':{'home':0,'away':0,'minute':60}}
    def controlled(route):
        e=dict(base)
        if route.request.url.endswith('/score'):
            light.append(time.monotonic());e['score']={'home':0,'away':0,'minute':60+len(light)};e['score_observed_at']=datetime.now(timezone.utc).isoformat()
            if len(light)>=3:e.update(status='finished',live=False,live_class=None)
        route.fulfill(status=200,content_type='application/json',body=json.dumps({'id':'c14-clock-probe','connected':True,'event':e,'header':e}))
    page.route('**/sports-data/matches/c14-clock-probe**',controlled)
    try:
        page.goto(SITE+'/scores/event/c14-clock-probe',wait_until='domcontentloaded');page.locator('[role=timer]').wait_for();before=page.locator('[role=timer]').inner_text();page.wait_for_timeout(2100);after=page.locator('[role=timer]').inner_text();page.wait_for_timeout(15000)
        final=page.locator('.mc-clock-block').inner_text();count=len(light);page.wait_for_timeout(5500)
        report['controlled_clock']={'mode':'synthetic response smoke check, NOT a real fixture or latency measurement','pass':before!=after and len(light)>=3 and 'FT' in final and page.locator('[role=timer]').count()==0 and len(light)==count,'first':before,'second':after,'final':final,'light_intervals_s':[b-a for a,b in zip(light,light[1:])],'light_requests':len(light)}
    except Exception as e:report['controlled_clock']={'pass':False,'error':str(e)}
    ctx.close();browser.close()
(OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
assert not report['errors'] and all(x['pass'] for x in report['profiles']+report['score_reads']+report['ui']) and report['controlled_clock']['pass']
