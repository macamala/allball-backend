"""Extend final public QA after c17_final_acceptance_prepare.py categories."""
from pathlib import Path
p=Path('audit/c17_public_acceptance.py');s=p.read_text()
def one(old,new):
    global s
    assert s.count(old)==1,(old[:90],s.count(old))
    s=s.replace(old,new)
one('PROFILES={}','PROFILES={}\nTEAMS={}')
needle="        if (native.get('birthDate') or {}).get('utcTime'):assert facts['birth_date']==native['birthDate']['utcTime'][:10]"
one(needle,needle+'''
        team_id=facts['current_club']['id']
        team_public=get('new-profile-team-'+team_id,API+'/sports-data/teams/'+team_id+'?'+urlencode({'sport':'football','name':facts['current_club']['name']}))
        team_native=get('new-profile-native-team-'+team_id,'https://www.fotmob.com/api/data/teams?id='+team_id)
        assert team_public.get('http')==team_native.get('http')==200
        club_data=team_public['payload'];native_club=team_native['payload']['details'];TEAMS[key]=club_data
        assert club_data['available'] and str(club_data['team']['id'])==str(native_club['id'])==team_id
        assert club_data['name']==native_club['name']
        gender={'female':'women','male':'men'}[native_club['gender']]
        assert gender==board['football_gender']==club_data['football_gender']
        for event in club_data['fixtures']+club_data['results']:
            if event['football_gender']!=gender:
                assert event['football_gender']=='unknown' and any(str(event[side].get('id'))==team_id for side in ('home','away'))
        if team_id=='4500':
            assert club_data['competition_keys']==['football-nor-toppserien']
            assert {event['id'] for event in club_data['fixtures']+club_data['results']}=={'ninko-evt-502d99d773c36f1850cd','ninko-evt-99b63e4a2de717c9139b'}
            assert len(facts['career'])==3 and facts['career'][0]['start']=='2025-01-01'
''')
one("return {'player_id':pid,'name':public['name'],'current_club':facts['current_club']['name'],'career_rows':len(facts.get('career') or []),'recorded_matches':len(public.get('appearances') or [])}","return {'player_id':pid,'player_name':public['name'],'current_club':facts['current_club']['name'],'club_identity':club_data['name'],'club_category':gender,'club_events':len(club_data['fixtures'])+len(club_data['results']),'career_rows':len(facts.get('career') or []),'recorded_matches':len(public.get('appearances') or [])}")
one("                assert page.locator('.entity-hero h1').inner_text()==club['name']", "                assert urlparse(page.url).path=='/teams/'+club['id']\n                assert page.locator('.entity-hero h1').inner_text()==TEAMS[key]['name']")
one("            assert women_links and all(BYID[i]['football_gender']=='women' and BYID[i]['competition_key']==MXW for i in women_links)", "            women_by_id={e['id']:e for e in HUBS[MXW]['payload']['events'] if e.get('id')}\n            assert women_links and all(women_by_id[i]['football_gender']=='women' and women_by_id[i]['competition_key']==MXW for i in women_links)")
needle="            page.screenshot(path=str(OUT/f'mx-women-fixtures-{width}.png'),full_page=True)"
one(needle,needle+'''
            target_id=women_links[0];target=women_by_id[target_id]
            page.locator('.hub-fixture-pair[href]').first.click();page.locator('.mc-score').wait_for(timeout=45000)
            assert urlparse(page.url).path=='/scores/event/'+target_id
            detail_text=page.locator('.match-centre').inner_text()
            assert target['home']['name'] in detail_text and target['away']['name'] in detail_text
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(OUT/f'mx-women-match-{width}.png'),full_page=True)
''')
compile(s,str(p),'exec');p.write_text(s)
Path('/tmp/c17-public/executed_acceptance.py').write_text(s)
