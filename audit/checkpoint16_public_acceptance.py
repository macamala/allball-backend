"""Actual public C16 acceptance. No mocked browser responses or database writes."""
import json,re,time,urllib.request,unicodedata
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c16-public');OUT.mkdir(parents=True,exist_ok=True)
API='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
SLIGO='ninko-evt-8ea488bb6f0bcf5038b7';BANGLADESH='ninko-evt-0f0c8b1216525d84d854'
report={'at':datetime.now(timezone.utc).isoformat(),'api':[],'browser':[]}
def name(s):return ''.join(c for c in unicodedata.normalize('NFKD',str(s or '')).casefold() if c.isalnum())
def at(s):return datetime.fromisoformat(str(s).replace('Z','+00:00')).replace(tzinfo=None)
def get(pair):
    key,url=pair;start=time.monotonic();d={'url':url,'started_at':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=45) as r:d.update(http=r.status,payload=json.load(r))
    except Exception as e:d['error']=str(e)
    d.update(at=datetime.now(timezone.utc).isoformat(),seconds=time.monotonic()-start)
    (OUT/(key+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2));return key,d
urls={}
for key,lid in [('england-league-one','108'),('ireland-premier-division','126')]:
    urls['hub-'+key]=API+'/sports-data/competitions/'+key+'/hub'
    urls['native-'+key]='https://www.fotmob.com/api/data/leagues?id='+lid
urls.update({'uefa-group':API+'/sports-data/competitions/uefa-nations-league/hub?'+urlencode({'group':'UEFA Nations League A Grp. 2'}),'uefa-all':API+'/sports-data/competitions/uefa-nations-league/hub','asean':API+'/sports-data/competitions/football-fifa-asean-cup-premier-division-grp-a/hub','archive':API+'/sports-data/competitions/ireland-premier-division/hub?season=1900','wrong-pair':API+'/sports-data/competitions/ireland-premier-division/comparison?match=unverified','sligo-comparison':API+'/sports-data/competitions/ireland-premier-division/comparison?'+urlencode({'match':SLIGO}),'bangladesh-comparison':API+'/sports-data/competitions/football-fifa-asean-cup-premier-division-grp-a/comparison?'+urlencode({'match':BANGLADESH})})
with ThreadPoolExecutor(max_workers=3) as pool:payloads=dict(pool.map(get,urls.items()))
def checked(key,action):
    row={'check':key,'pass':False}
    try:row.update(action() or {});row['pass']=True
    except Exception as e:row['error']=str(e)
    report['api'].append(row)
def season_check(key,minimum,teams):
    public=payloads['hub-'+key];source=payloads['native-'+key];assert public.get('http')==source.get('http')==200
    p=public['payload'];n=source['payload'];events=p.get('events') or [];native=n['fixtures']['allMatches'];byid={str(x['id']):x for x in native}
    assert len(events)>=minimum and len({x['key'] for x in events})==len(events)
    assert p['season']==n['details']['selectedSeason']
    assert len(p['table_views']['home'])==len(p['table_views']['away'])==teams
    differences=[]
    for e in events:
        if e['key'].startswith('reference:'):m=byid.get(e['key'].split(':',1)[1])
        else:
            matches=[m for m in native if name(m['home']['name'])==name(e['home']['name']) and name(m['away']['name'])==name(e['away']['name']) and abs((at(m['status']['utcTime'])-at(e['start_time'])).total_seconds())<=60]
            m=matches[0] if len(matches)==1 else None
        if not m:differences.append({'key':e['key'],'issue':'not uniquely source matched'});continue
        if e.get('status')=='finished':
            score=re.fullmatch(r'\s*(\d+)\s*[-–]\s*(\d+)\s*',m['status'].get('scoreStr',''))
            if not score or [int(score[1]),int(score[2])]!=[e['score']['home'],e['score']['away']]:differences.append({'key':e['key'],'issue':'score differs'})
        if e.get('id') is None:assert not e.get('details_available')
    assert not differences,differences[:5]
    assert not any(x in json.dumps(p) for x in ['_football_history','_source_match_id','_native_id'])
    return {'events':len(events),'native_events':len(native),'linked':sum(bool(e.get('id')) for e in events),'results':sum(e['status']=='finished' for e in events),'fixtures':sum(e['status'] in ('scheduled','live','in_progress','halftime','break') for e in events),'season':p['season'],'home_away_rows':teams,'cold_seconds':public['seconds']}
checked('League One native season',lambda:season_check('england-league-one',500,24))
checked('Ireland native season',lambda:season_check('ireland-premier-division',150,10))
def scope_check():
    for k in ('uefa-group','uefa-all','asean','archive','wrong-pair'):assert payloads[k].get('http')==200,(k,payloads[k])
    group=payloads['uefa-group']['payload']['events'];allrows=payloads['uefa-all']['payload']['events'];asean=payloads['asean']['payload']['events']
    assert group and all(e.get('group')=='UEFA Nations League A Grp. 2' for e in group)
    assert len(allrows)>=len(group) and len(asean)>=4
    assert not payloads['archive']['payload']['events'] and not payloads['archive']['payload']['table_views']
    assert payloads['wrong-pair']['payload']['event'] is None
    return {'uefa_selected':len(group),'uefa_available':len(allrows),'asean_available':len(asean),'empty_archive_not_substituted':True}
checked('Group and archive isolation',scope_check)
def history_check(key,expected,mid):
    d=payloads[key];assert d.get('http')==200,d
    p=d['payload'];assert p['available'] and p['event']['id']==mid
    h=p.get('h2h') or [];f=p.get('form') or {};assert len(h)==expected,(len(h),expected)
    assert len(f['home']['results'])==len(f['away']['results'])==5
    pair={name(p['event']['home']['name']),name(p['event']['away']['name'])}
    assert all({name(r['home']['name']),name(r['away']['name'])}==pair and at(r['start_time'])<at(p['event']['start_time']) and r['status']=='finished' for r in h)
    assert not any(x in json.dumps(p) for x in ['_source_match_id','_football_history','_native_id'])
    return {'history':len(h),'home_form':5,'away_form':5,'event':mid}
checked('Sligo mutual history',lambda:history_check('sligo-comparison',57,SLIGO))
checked('Bangladesh mutual history',lambda:history_check('bangladesh-comparison',1,BANGLADESH))
# Preserve the exact previously observed canonical set; a native read-only season
# supplement must not replace or erase the main live-score database identities.
def retention():
    old=json.loads(Path('/tmp/c15-baseline/public-cohort.json').read_text());new=get(('main-board-after',old['url']))[1];assert new.get('http')==200
    a={e['id'] for e in old['payload']['events']};b={e['id'] for e in new['payload']['events']};assert not a-b,sorted(a-b)
    return {'before':len(a),'after':len(b),'removed':0,'added':len(b-a)}
checked('Canonical board retention',retention)
def summary(event,rows):
    h=a=d=hg=ag=0
    for r in rows:
        x,y=r['score']['home'],r['score']['away']
        if name(r['home']['name'])!=name(event['home']['name']):x,y=y,x
        h+=x>y;a+=x<y;d+=x==y;hg+=x;ag+=y
    return [str(h),str(d),str(a)],len(rows)
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    for width in (1440,390,320):
        ctx=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney',locale='en-AU');page=ctx.new_page();errors=[];network=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:network.append({'url':r.url,'http':r.status}) if '/sports-data/' in r.url else None)
        result={'width':width,'pass':False}
        try:
            page.goto(SITE+'/scores/competition/ireland-premier-division/standings?sport=football',wait_until='domcontentloaded')
            page.locator('.standings-team').first.wait_for(timeout=45000);page.locator('.hub-coverage-note').wait_for(timeout=45000)
            assert page.locator('.hub-preview-grid .hub-match-card').count()==2
            assert page.locator('.hub-preview-grid .hub-fixture-row').count()>=4
            assert page.locator('.mc-hero').count()==0 and not any('/comparison?' in r['url'] or '/sports-data/matches/' in r['url'] for r in network)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            result['standings_no_implicit_match']=True
            page.screenshot(path=str(OUT/f'overview-{width}.png'),full_page=True)
            page.get_by_role('button',name='Home',exact=True).click();assert page.get_by_role('button',name='Home',exact=True).get_attribute('aria-pressed')=='true'
            assert page.locator('.standings-team').count()==10
            result['home_split_rows']=10
            page.get_by_role('tab',name=re.compile('^Fixtures')).click();page.get_by_label('Filter team',exact=True).select_option('sligo rovers')
            page.wait_for_timeout(200);fixture_text=page.locator('.hub-fixture-list .hub-fixture-row').all_text_contents();assert fixture_text and all('Sligo Rovers' in t for t in fixture_text)
            result['filtered_fixtures']=len(fixture_text)
            round_options=page.get_by_label('Filter round',exact=True).locator('option').count();assert round_options>2
            upcoming=[e for e in payloads['hub-ireland-premier-division']['payload']['events'] if e['status']=='scheduled' and any(s.get('name')=='Sligo Rovers' for s in [e['home'],e['away']])]
            if upcoming and upcoming[0].get('round'):
                page.get_by_label('Filter round',exact=True).select_option(str(upcoming[0]['round']));assert page.locator('.hub-fixture-row').count()>=1;result['round_filter']=str(upcoming[0]['round']);page.get_by_label('Filter round',exact=True).select_option('')
            page.screenshot(path=str(OUT/f'fixtures-{width}.png'),full_page=True)
            page.get_by_role('tab',name=re.compile('^Results')).click();page.wait_for_timeout(200)
            assert page.locator('.hub-fixture-row').count()>0
            assert all('Sligo Rovers' in s for s in page.locator('.hub-fixture-row').all_text_contents())
            target=page.locator(f'.hub-fixture-row[data-match-key="{SLIGO}"]');target.wait_for(timeout=15000)
            target.locator('.hub-compare-button').click();page.locator('.h2h-summary-card').wait_for(timeout=45000)
            comparison=payloads['sligo-comparison']['payload'];expected,total=summary(comparison['event'],comparison['h2h'])
            values=page.locator('.h2h-summary-grid strong').all_text_contents();assert values==expected,(values,expected)
            assert page.locator('.h2h-form-card .h2h-history-list > li').count()==10
            assert page.locator('.h2h-meetings-card .h2h-history-list > li').count()==10
            page.locator('.h2h-meetings-card .hub-load-more').click();assert page.locator('.h2h-meetings-card .h2h-history-list > li').count()==25
            page.get_by_label('Head-to-head venue').select_option('home')
            home=[r for r in comparison['h2h'] if name(r['home']['name'])==name(comparison['event']['home']['name'])]
            assert page.locator('.h2h-summary-grid strong').all_text_contents()==summary(comparison['event'],home)[0]
            page.get_by_label('Head-to-head venue').select_option('all')
            page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(OUT/f'h2h-{width}.png'),full_page=True)
            assert 'tab=h2h' in page.url and SLIGO in page.url
            page.reload(wait_until='domcontentloaded');page.locator('.h2h-summary-card').wait_for(timeout=45000)
            assert page.locator('.h2h-summary-grid strong').all_text_contents()==expected
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            result.update(h2h_count=total,h2h_summary=values,form_rows=10,venue_and_reload=True)
            page.goto(SITE+'/scores/event/'+SLIGO+'#mc-h2h',wait_until='domcontentloaded')
            page.locator('.mc-hero').wait_for(timeout=45000)
            page.locator('[data-tab="h2h"]').click() if page.locator('[data-tab="h2h"]').count() else None
            page.locator('.football-comparison .h2h-summary-card').wait_for(timeout=45000)
            assert page.locator('.h2h-summary-grid strong').all_text_contents()==expected
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            result.update(match_h2h_retained=True,pass_value=True)
            result['pass']=not errors
        except Exception as e:
            result['error']=str(e);page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
        result.update(errors=errors.copy(),network=network.copy());report['browser'].append(result);ctx.close()
    browser.close()
(OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({**report,'browser':[{k:v for k,v in r.items() if k!='network'} for r in report['browser']]},ensure_ascii=False,indent=2))
assert all(r['pass'] for r in report['api']+report['browser'])
