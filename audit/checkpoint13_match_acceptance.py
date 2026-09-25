"""Actual production-only C13 checks. No mocks or manual score writes."""
import json, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c13-public');OUT.mkdir(parents=True,exist_ok=True)
API='https://allball-backend-production.up.railway.app'; SITE='https://ninkosports.com'
SLIGO='ninko-evt-8ea488bb6f0bcf5038b7';ANDORRA='ninko-evt-86345b6cb47a7c4b8524'

def get(url,name):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json'}),timeout=45) as r:
        data=json.load(r);assert r.status==200
    (OUT/(name+'.json')).write_text(json.dumps(data,indent=2,ensure_ascii=False));return data

def main():
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'api':{},'browser':[]}
    raw=get('https://www.fotmob.com/api/data/matchDetails?matchId=5100971','native-sligo')
    p=get(API+'/sports-data/matches/'+SLIGO,'public-sligo');e=p['event'];timeline=e['timeline'];shots=e['sport_detail']['shots']
    native_events=raw['content']['matchFacts']['events']['events']
    native_subs=[x for x in native_events if x.get('type')=='Substitution']
    subs=[x for x in timeline if x.get('family')=='substitution']
    assert len(subs)==len(native_subs) and len(subs)>0
    assert [(x.get('player_in'),x.get('player_out')) for x in subs]==[(x['swap'][0]['name'],x['swap'][1]['name']) for x in native_subs]
    native_goals=[x for x in native_events if x.get('type')=='Goal']
    goals=[x for x in timeline if x.get('family')=='goal']
    assert [x['score_after'] for x in goals]==[dict(zip(('home','away'),x['newScore'])) for x in native_goals]
    assert isinstance(shots,list) and len(shots)==len(raw['content']['shotmap']['shots'])
    lineups=p['lineups'];starters=lineups['home']['start']+lineups['away']['start']
    assert len(starters)==22 and all(x.get('pitch_position') for x in starters)
    assert all(not isinstance(x.get('position'),(int,float)) for x in starters)
    stats=p['statistics']; assert len({x.get('label') for x in stats})==len(stats)
    assert all(x.get('home') is not None or x.get('away') is not None for x in stats)
    assert e['status']=='finished' and e['score']['home']==0 and e['score']['away']==1
    after=get(API+'/sports-data/matches/'+SLIGO,'public-sligo-repeat')['event']
    assert after['score']==e['score'] and after['id']==e['id']
    result['api']={'substitutions':len(subs),'statistics':len(stats),'shots':len(shots),'positions':len(starters),'goal_after':[x['score_after'] for x in goals],'repeat_score_preserved':True,'pass':True}
    for label,eid in [('andorra-old',ANDORRA),('sligo-old','ninko-evt-bb4071086c3ea042f6e9'),('myanmar','ninko-evt-d807549bf94203765dd7')]:
        data=get(API+'/sports-data/matches/'+eid,label);ev=data.get('event')or{}
        result[label]={k:ev.get(k) for k in ['id','home','away','status','score']}
    with sync_playwright() as browser_api:
        browser=browser_api.chromium.launch()
        for width in (1440,390,320):
            context=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney',locale='en-AU');page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)));row={'width':width}
            try:
                page.goto(SITE+'/scores/event/'+SLIGO,wait_until='domcontentloaded',timeout=60000)
                page.locator('.mc-match-story').wait_for(timeout=45000)
                assert page.locator('.mc-sub-in').count()==len(subs)
                assert page.locator('.mc-sub-out').count()==len(subs)
                assert page.locator('.mc-tl-score').all_text_contents()==[str(x['score_after']['home'])+'–'+str(x['score_after']['away']) for x in goals]
                assert '90+4’' in page.locator('.mc-match-story').inner_text()
                page.get_by_role('button',name='Key events',exact=True).click();assert page.locator('.mc-sub-in').count()==0
                page.get_by_role('button',name='All events',exact=True).click();assert page.locator('.mc-sub-in').count()==len(subs)
                page.screenshot(path=str(OUT/f'overview-{width}.png'),full_page=True)
                page.locator('#mc-tab-stats').click();assert page.url.endswith('#mc-stats')
                page.locator('#mc-panel-stats').wait_for(state='visible')
                assert page.locator('#mc-panel-stats .mc-stats > li').count()==len(stats)
                periods=page.locator('.mc-stat-periods button');assert periods.count()==3
                period_sizes=[]
                for i,key in enumerate(('all','first_half','second_half')):
                    periods.nth(i).click();expected=e['sport_detail']['statistics_periods'][key]
                    period_sizes.append(page.locator('#mc-panel-stats .mc-stats > li').count());assert period_sizes[-1]==len(expected)
                page.screenshot(path=str(OUT/f'statistics-{width}.png'),full_page=True)
                page.reload(wait_until='domcontentloaded');page.locator('#mc-tab-stats[aria-selected="true"]').wait_for(timeout=45000)
                page.locator('#mc-tab-lineups').click();page.locator('.mc-pitch').wait_for(state='visible')
                assert page.locator('.mc-pitch-player').count()==22
                page.screenshot(path=str(OUT/f'lineups-{width}.png'),full_page=True)
                page.locator('#mc-tab-shots').click();assert page.locator('.mc-shot-list li').count()==len(shots)
                away_count=sum(s['side']=='away' for s in shots)
                page.locator('.mc-shot-teams button').nth(2).click();assert page.locator('.mc-shot-list li').count()==away_count
                page.get_by_role('button',name='Goals only',exact=True).click()
                expected_goals=[s for s in shots if s['side']=='away' and s['type']=='Goal'];assert page.locator('.mc-shot-list li').count()==len(expected_goals)
                page.screenshot(path=str(OUT/f'shots-{width}.png'),full_page=True)
                if width==1440:
                    page.locator('.mc-shot-list .mc-event-person').first.click();page.locator('.entity-back').wait_for(timeout=45000)
                    row['player_url']=page.url;row['player_available']=page.locator('.entity-hero h1').count()>0
                    assert row['player_available'] and page.locator('.entity-hero h1').inner_text()==expected_goals[0]['player']
                    assert page.locator('.entity-back').get_attribute('href').endswith('#mc-shots')
                    page.locator('.entity-back').click();page.locator('#mc-tab-shots[aria-selected="true"]').wait_for(timeout=45000)
                    row['player_return']=True
                row['period_sizes']=period_sizes
                row['overflow']=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                assert not row['overflow'] and not errors,errors
                row['pass']=True
            except Exception as error:
                row.update({'pass':False,'error':str(error)});page.screenshot(path=str(OUT/f'failed-{width}.png'),full_page=True)
            row['errors']=errors;result['browser'].append(row);context.close()
        context=browser.new_context(viewport={'width':390,'height':1000},timezone_id='Australia/Sydney');page=context.new_page()
        try:
            page.goto(SITE+'/scores/event/'+ANDORRA,wait_until='domcontentloaded',timeout=60000)
            page.locator('.mc-score').wait_for(timeout=45000)
            result['old_link_ui']={'score':page.locator('.mc-score').inner_text(),'body':page.locator('.match-centre').inner_text()[:500]}
            assert '1' in result['old_link_ui']['score'] and '2' in result['old_link_ui']['score']
            assert 'Andorra' in result['old_link_ui']['body'] and 'Malta' in result['old_link_ui']['body']
            result['old_link_ui']['pass']=True
        except Exception as error:result['old_link_ui']={'pass':False,'error':str(error)}
        page.screenshot(path=str(OUT/'andorra-old-mobile.png'),full_page=True)
        result['bundle']=page.evaluate("[...document.scripts].map(s=>s.src).filter(s=>s.includes('/assets/'))")
        browser.close()
    (OUT/'acceptance.json').write_text(json.dumps(result,indent=2,ensure_ascii=False));print(json.dumps(result,indent=2,ensure_ascii=False))
    assert result['old_link_ui']['pass'] and all(x['pass'] for x in result['browser'])
if __name__=='__main__':main()
