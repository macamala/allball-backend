"""Public read-only acceptance. No mocks, scores or database writes."""
import json, time, urllib.request, concurrent.futures
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c15-final');OUT.mkdir(parents=True,exist_ok=True)
API='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
EID='ninko-evt-0f0c8b1216525d84d854';LEAGUE='football-fifa-asean-cup-premier-division-grp-a'
def get(name,url):
    start=time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=35) as r:
        d={'http':r.status,'payload':json.load(r),'url':url,'at':datetime.now(timezone.utc).isoformat(),'seconds':time.monotonic()-start}
    (OUT/(name+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2));return d['payload']
def main():
    report={'at':datetime.now(timezone.utc).isoformat(),'checks':[],'network':[],'errors':[]}
    sources=[('native-detail','https://www.fotmob.com/api/data/matchDetails?matchId=6232978'),('public-detail',API+'/sports-data/matches/'+EID),('asean-table',API+'/sports-data/standings?'+urlencode({'league':LEAGUE}))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool: responses=dict(zip([s[0] for s in sources],pool.map(lambda x:get(*x),sources)))
    native=responses['native-detail'];event=responses['public-detail'].get('event') or {}
    report['detail']={k:event.get(k) for k in ['id','home','away','status','score','lineups','statistics','incidents','score_observed_at']}
    table=responses['asean-table'];report['asean_table']=table
    native_lineup=(native.get('content') or {}).get('lineup') or {}
    report['native_lineup_counts']={s:len((native_lineup.get(s+'Team') or {}).get('starters') or []) for s in ['home','away']}
    assert event.get('id')==EID
    assert event.get('lineups'),'Native lineups must be exposed in the public match'
    assert {str(r.get('team_id')) for r in table.get('rows',[])}=={'95797','5823','6324','5825'},'Wrong or missing ASEAN group membership'
    with sync_playwright() as p:
        browser=p.chromium.launch()
        for width in (1440,390,320):
            ctx=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney')
            page=ctx.new_page();errors=[];network=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('response',lambda r:network.append({'url':r.url,'status':r.status,'at':datetime.now(timezone.utc).isoformat()}) if '/sports-data/' in r.url else None)
            row={'width':width,'table_checks':[]}
            try:
                for title,team in [('UEFA Nations League A Grp. 2','Serbia'),('FIFA ASEAN Cup Premier Division Grp. A','Bangladesh')]:
                    page.goto(SITE+'/live-scores?sport=football&date=2026-09-25',wait_until='domcontentloaded')
                    group=page.locator('section.score-comp').filter(has=page.get_by_role('heading',name=title,exact=True))
                    group.locator('a.score-comp-standings').wait_for(timeout=60000)
                    href=group.locator('a.score-comp-standings').get_attribute('href');assert '/scores/competition/' in href and '/scores/event/' not in href
                    before=len(network);group.locator('a.score-comp-standings').click()
                    page.locator('.competition-standings-page .standings-responsive tbody').wait_for(timeout=60000)
                    page.wait_for_timeout(500)
                    teams=page.locator('.competition-standings-page .standings-team').all_text_contents()
                    assert any(team in t for t in teams),(title,teams)
                    assert page.locator('.mc-hero').count()==0
                    assert '/scores/competition/' in page.url and '/standings' in page.url
                    assert not any('/sports-data/matches/' in r['url'] for r in network[before:]),'A league table fetched an arbitrary match'
                    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                    if title.startswith('UEFA'):
                        select=page.get_by_role('combobox',name='Standings group')
                        option=select.locator('option').filter(has_text='UEFA Nations League B Grp. 3').first
                        select.select_option(option.get_attribute('value'))
                        assert 'Austria' in page.locator('tbody').inner_text() and 'Serbia' not in page.locator('tbody').inner_text()
                        saved=page.url;page.reload(wait_until='domcontentloaded');page.locator('.standings-team').first.wait_for(timeout=45000)
                        assert page.url==saved and 'Austria' in page.locator('tbody').inner_text()
                    else:
                        assert len(teams)==4,teams
                    page.screenshot(path=str(OUT/f'table-{team}-{width}.png'),full_page=True)
                    row['table_checks'].append({'title':title,'href':href,'teams':teams,'url':page.url,'no_match_requests':True,'pass':True})
                page.goto(SITE+'/scores/event/'+EID+'#mc-lineups',wait_until='domcontentloaded')
                page.locator('.mc-pitch-player').first.wait_for(timeout=60000)
                row['pitch_players']=page.locator('.mc-pitch-player').count();assert row['pitch_players']==22
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                page.screenshot(path=str(OUT/f'bangladesh-lineups-{width}.png'),full_page=True)
                row['pass']=not errors
            except Exception as e:
                row['pass']=False;row['error']=str(e);page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
            row['errors']=errors.copy();row['network']=network.copy();report['checks'].append(row);ctx.close()
        page=browser.new_page(viewport={'width':1440,'height':1000},timezone_id='Australia/Sydney')
        def capture(response):
            if '/sports-data/matches/'+EID not in response.url:return
            sample={'url':response.url,'status':response.status,'at':datetime.now(timezone.utc).isoformat()}
            try:
                e=response.json().get('event') or {};sample.update({k:e.get(k) for k in ['id','status','score','score_observed_at']})
            except Exception as e:sample['error']=str(e)
            report['network'].append(sample)
        page.on('response',capture);page.on('pageerror',lambda e:report['errors'].append(str(e)))
        page.goto(SITE+'/scores/event/'+EID,wait_until='domcontentloaded');page.locator('.mc-hero').wait_for(timeout=45000)
        report['live_samples']=[]
        for i in range(14):
            if i:page.wait_for_timeout(5000)
            report['live_samples'].append({'at':datetime.now(timezone.utc).isoformat(),'hero':page.locator('.mc-hero').inner_text()})
        page.screenshot(path=str(OUT/'bangladesh-live-final.png'));browser.close()
    (OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2));assert all(r['pass'] for r in report['checks']) and not report['errors']
if __name__=='__main__':main()
