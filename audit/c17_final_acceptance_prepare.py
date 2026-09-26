"""Prepare only QA scripts. Never changes app, stored events or production scores."""
import sys
from pathlib import Path
mode=sys.argv[1]

def replace_once(s,old,new):
    assert s.count(old)==1,(old[:90],s.count(old))
    return s.replace(old,new)

if mode=='categories':
    p=Path('audit/c17_public_acceptance.py');s=p.read_text()
    s=replace_once(s,"',label)","',arg=label)")
    extra='''
from urllib.parse import urlencode,urlparse,parse_qs
PROFILES={}
for key in ('ireland-premier-division',TOP):
    def profile_check(key=key):
        board=SCORERS[key];leader=board['rows'][0];pid=leader['player_id']
        native=get('native-profile-'+pid,'https://www.fotmob.com/api/data/playerData?id='+pid)
        assert native.get('http')==200;native=native['payload']
        query=urlencode({'name':leader['name'],'competition_key':key,'season':board['season']})
        public=get('profile-'+pid,API+'/sports-data/players/'+pid+'?'+query)
        assert public.get('http')==200;public=public['payload'];PROFILES[key]=public
        assert public['available'] and str(native['id'])==pid and native['name']==public['name']==leader['name']
        facts=public['player'];team=native.get('primaryTeam') or {}
        assert facts.get('current_club',{}).get('id')==str(team['teamId'])
        assert facts['current_club']['name']==team['teamName']
        if (native.get('birthDate') or {}).get('utcTime'):assert facts['birth_date']==native['birthDate']['utcTime'][:10]
        # A source-only scorer is not assigned fabricated match appearances.
        assert 'goals' not in facts or public.get('appearances')
        return {'player_id':pid,'name':public['name'],'current_club':facts['current_club']['name'],'career_rows':len(facts.get('career') or []),'recorded_matches':len(public.get('appearances') or [])}
    checked('New scorer profile source identity '+key,profile_check)
'''
    s=replace_once(s,'with sync_playwright() as pw:',extra+'\nwith sync_playwright() as pw:')
    old="                page.go_back(wait_until='domcontentloaded');page.locator('.scorer-row').first.wait_for(timeout=45000)"
    new='''                assert parse_qs(urlparse(page.url).query)['competition_key']==[key]
                assert parse_qs(urlparse(page.url).query)['season']==[data['season']]
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(OUT/f'new-player-{key}-{width}.png'),full_page=True)
                club=PROFILES[key]['player']['current_club'];page.locator('.player-club-link').click()
                page.locator('.entity-hero h1').wait_for(timeout=45000)
                assert page.locator('.entity-hero h1').inner_text()==club['name']
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.go_back(wait_until='domcontentloaded');page.locator('.entity-hero h1').wait_for(timeout=45000)
                page.get_by_role('link',name='← Back',exact=True).click();page.locator('.scorer-row').first.wait_for(timeout=45000)
                q=parse_qs(urlparse(page.url).query)
                assert '/scores/competition/'+key+'/standings' in page.url and q['tab']==['scorers'] and q['season']==[data['season']]
            page.goto(SITE+'/scores/competition/'+MXW+'/standings?sport=football&tab=fixtures',wait_until='domcontentloaded')
            page.locator('.hub-fixture-pair[href]').first.wait_for(timeout=45000)
            women_links=page.locator('.hub-fixture-pair[href]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href").split("/").pop())')
            assert women_links and all(BYID[i]['football_gender']=='women' and BYID[i]['competition_key']==MXW for i in women_links)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(OUT/f'mx-women-fixtures-{width}.png'),full_page=True)'''
    s=replace_once(s,old,new)
    compile(s,str(p),'exec');p.write_text(s)
    out=Path('/tmp/c17-public');out.mkdir(exist_ok=True);(out/'executed_acceptance.py').write_text(s)
elif mode=='live':
    p=Path('prior/audit/screenshot_production_acceptance.py');s=p.read_text()
    old=".score-row').first.wait_for(";assert s.count(old)==2
    s=s.replace(old,".score-row-link[href]').first.wait_for(")
    # This known match became final before C17. Verify actual source and the
    # pre-release snapshot; do not restore an obsolete scheduled expectation.
    extra='''
 native=fetch('havelse-native','https://www.fotmob.com/api/data/matches?date=20260925')
 assert native.get('http')==200,native
 candidates=[m for l in native['payload']['leagues'] for m in l.get('matches',[]) if str(m.get('id'))=='5905914']
 assert len(candidates)==1;witness=candidates[0]
 assert witness['home']['id']==89338 and witness['away']['id']==7786 and witness['status']['finished'] is True
 expected_score=(witness['home']['score'],witness['away']['score']);assert expected_score==(1,3)
 before=json.loads(Path('/tmp/c17-before/cohort.json').read_text())
 prior=next(e for e in before['payload']['events'] if e['id']==HAV)
 def verify_havelse(r):
  assert r['status']=='finished' and not r.get('live')
  assert (r['score']['home'],r['score']['away'])==expected_score
  assert r['home']['name']==witness['home']['name'] and r['away']['name']==witness['away']['name']
  assert datetime.fromisoformat(r['start_time'].replace('Z','+00:00'))==datetime.fromisoformat(witness['status']['utcTime'].replace('Z','+00:00'))
 verify_havelse(prior)
 REPORT['havelse_witness']={'native_id':'5905914','pre_release_at':before['at'],'unchanged_final_score':expected_score,'kickoff':witness['status']['utcTime']}
'''
    marker=" for r in ([r for r in results['sat26-football']['payload']['events'] if r['id']==HAV][0],results['havelse-detail']['payload']['event']):"
    s=replace_once(s,marker,extra+marker)
    old="  assert r['status']=='scheduled' and not r.get('live') and r['score']['home'] is None and r['score']['away'] is None,r"
    s=replace_once(s,old,'  verify_havelse(r)')
    s=replace_once(s,"'havelse_scheduled':True","'havelse_source_verified_final':True")
    s=replace_once(s,"    assert row.locator('.score-status-text').inner_text()=='03:00',row.inner_text()","    assert row.locator('.score-status-text').inner_text()=='FT',row.inner_text()\n    assert row.locator('.score-mid').all_text_contents()==[str(v) for v in expected_score]")
    needle="   REPORT['browser'][-1]['poll_responses']=requests[before:]"
    s=replace_once(s,needle,needle+"\n   successful=[r['url'] for r in requests[before:] if r['status']==200]\n   assert any('/sports-data/status-delta?' in u for u in successful)\n   assert any('/sports-data/events?' in u for u in successful)")
    compile(s,str(p),'exec');p.write_text(s)
    out=Path('/tmp/screenshot-after');out.mkdir(exist_ok=True);(out/'executed_acceptance.py').write_text(s)
else:raise ValueError(mode)
