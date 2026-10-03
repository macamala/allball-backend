from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import inspect
import pytest
from bot import news_football_memberships as m
from bot import news_football_sections as sections

NOW = datetime(2026, 10, 3, 8, tzinfo=timezone.utc)
LEAGUE = 'england-championship'
NAMES = ['Blackburn Rovers FC', 'Birmingham City FC', 'Burnley FC', 'Watford FC']

def hub():
    def match(index):
        return {'key':f'match-{index}', 'sport':'football', 'competition_key':LEAGUE,
                'status':'scheduled', 'football_gender':'unknown', 'season':None,
                'start_time':(NOW+timedelta(days=7)).isoformat(), 'updated_at':(NOW-timedelta(hours=1)).isoformat(),
                'home':{'name':NAMES[index*2], 'slug':f'home-{index}'},
                'away':{'name':NAMES[index*2+1], 'slug':f'away-{index}'}}
    return {'available':True,'competition':{'id':LEAGUE,'sport':'football'},
            'checked_at':NOW.isoformat(),'coverage':{'stale':False},'events':[match(0),match(1)]}

@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(m,'_ENTRIES',{})
    monkeypatch.setattr(m,'_LAST_REFRESH',float('-inf'))


def test_recent_confirmed_matches_provide_only_menu_metadata():
    data=hub();before=deepcopy(data)
    entry=m.parse_fixture_membership(LEAGUE,data,now=NOW)
    assert entry['clubs']==sorted(NAMES)
    assert entry['season'] is None and entry['complete_roster'] is False
    assert entry['source_kind']=='confirmed_recent_fixture_roster'
    assert entry['evidence_matches']==2 and '/hub' in entry['source']
    assert entry['observed_at']==data['events'][0]['updated_at']
    assert data==before
    assert not {'score','rows','points','goals','wins'}.intersection(entry)

@pytest.mark.parametrize('field,value',[
    ('available',False),('coverage',{'stale':True}),('coverage',{}),
    ('competition',{'id':'spain-la-liga','sport':'football'}),
    ('competition',{'id':LEAGUE,'sport':'basketball'}),
    ('checked_at',None),('checked_at','2026-10-03T08:00:00'),
    ('checked_at',(NOW-timedelta(hours=2)).isoformat()),
    ('checked_at',(NOW+timedelta(hours=1)).isoformat()),('events',{}),('events',[]),
])
def test_invalid_or_unverified_hub_never_proves_membership(field,value):
    data=hub();data[field]=value
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('field,value',[
    ('competition_key','spain-la-liga'),('sport','basketball'),('football_gender','women'),
    ('status','cancelled'),('status','postponed'),('status','awaiting_confirmation'),
    ('season','2025/2026'),('season','2027/2028'),('season','invented'),
    ('updated_at',None),('updated_at','2026-10-03T07:00:00'),
    ('updated_at',(NOW-timedelta(days=4)).isoformat()),
    ('updated_at',(NOW+timedelta(days=1)).isoformat()),
    ('start_time',(NOW-timedelta(days=30)).isoformat()),
    ('start_time',(NOW+timedelta(days=40)).isoformat()),
    ('start_time',(NOW-timedelta(hours=5)).isoformat()),
])
def test_each_fixture_needs_own_recent_scope_evidence(field,value):
    data=hub()
    for event in data['events']:event[field]=value
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('name',['Blackburn Rovers Women','Blackburn Rovers (W)','Blackburn U19','Blackburn Under-21','Blackburn Academy'])
def test_wrong_gender_and_youth_identities_cannot_enter_mens_roster(name):
    data=hub();data['events'][0]['home']['name']=name
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('changed',[{'name':'Real club without identity'},{'slug':'team'},{'name':'TBD','slug':None}])
def test_missing_identity_or_name_does_not_create_a_club(changed):
    data=hub();data['events'][0]['home']=changed
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None


def test_duplicate_or_reversed_partial_rows_do_not_fake_complete_roster():
    data=hub();data['events']=[data['events'][0]]*100
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None


def test_finished_recent_fixture_is_valid_but_source_age_does_not_reset_on_read():
    data=hub()
    for event in data['events']:
        event['status']='finished';event['start_time']=(NOW-timedelta(days=3)).isoformat()
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW)
    for event in data['events']:event['updated_at']=(NOW-timedelta(days=4)).isoformat()
    data['checked_at']=NOW.isoformat()
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW) is None


def test_named_current_season_is_kept_exactly_not_synthesized():
    data=hub()
    for e in data['events']:e['season']='2026-2027'
    assert m.parse_fixture_membership(LEAGUE,data,now=NOW)['season']=='2026-2027'


def test_rosters_are_fallback_only_and_expire(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{LEAGUE:{}})
    calls=[]
    result=m.refresh_football_news_memberships(now=NOW,get=lambda *a:{},get_fixtures=lambda *a:calls.append(a) or hub())
    assert result['fixture_rosters']==1 and result['leagues']==1
    assert calls==[(LEAGUE,LEAGUE)]
    copied=m.memberships_for_news(NOW);copied[LEAGUE]['clubs'].clear()
    assert m.memberships_for_news(NOW)[LEAGUE]['clubs']
    assert not m.memberships_for_news(NOW+timedelta(days=4))
    assert m.refresh_football_news_memberships(now=NOW,get=lambda *a:{},get_fixtures=lambda *a:pytest.fail('duplicate fetch'))['status']=='cached'


def test_injected_table_reader_cannot_trigger_implicit_network(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{LEAGUE:{}})
    monkeypatch.setattr(m,'_public_fixture_get',lambda *a:pytest.fail('unexpected network'))
    assert m.refresh_football_news_memberships(now=NOW,get=lambda *a:{})['leagues']==0


def test_available_table_wins_and_no_extra_fixture_request_occurs(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{LEAGUE:{}})
    data={'available':True,'stale':False,'competition':{'id':LEAGUE,'sport':'football'},
          'season':'2026/2027','updated_at':NOW.isoformat(),
          'rows':[{'team':n,'team_id':str(i)} for i,n in enumerate(NAMES)]}
    result=m.refresh_football_news_memberships(now=NOW,get=lambda *a:data,get_fixtures=lambda *a:pytest.fail('table already available'))
    assert result['leagues']==1 and result['fixture_rosters']==0


def test_current_club_alias_routes_article_without_rewriting_text(monkeypatch):
    entry=m.parse_fixture_membership(LEAGUE,hub(),now=NOW)
    monkeypatch.setattr(sections,'memberships_for_news',lambda:{LEAGUE:entry})
    a=SimpleNamespace(title='Blackburn Rovers confirm a new coaching appointment',summary='The football club confirmed the change.',content='The coach will lead training.',published_at=NOW)
    before=vars(a).copy()
    assert sections.football_news_section(a,today=NOW.date())==LEAGUE
    assert vars(a)==before
    a.title='Blackburn Rovers Women appoint a new coach'
    assert sections.football_news_section(a,today=NOW.date())=='football-women'
    a.title='Blackburn Rovers U21 appoint a new coach'
    assert sections.football_news_section(a,today=NOW.date())=='football-youth'


def test_verified_name_shortening_never_invents_nicknames_or_generic_clubs():
    names=['Blackburn Rovers FC','FC Copenhagen','Watford FC','FC United','AC Inter','New York City FC']
    result=m.verified_name_aliases(names)
    assert all(n in result for n in names)
    assert {'Blackburn Rovers','Copenhagen','Watford','New York City'} <= set(result)
    assert not {'United','Inter','Rovers','City','NYC','Blackburn'}.intersection(result)
    assert m.verified_name_aliases(['FC United','United FC'])==['FC United','United FC']
    assert 'Copenhagen' not in m.verified_name_aliases(['FC Copenhagen','Copenhagen FC'])


def test_mexico_apertura_fallback_is_exact_not_clausura():
    data=hub();key='football-mex-liga-de-expansion-mx-apertura'
    data['competition']['id']=key
    for e in data['events']:e['competition_key']=key
    assert m.parse_fixture_membership('mexico-liga-expansion',data,now=NOW)
    data['competition']['id']=key.replace('apertura','clausura')
    assert m.parse_fixture_membership('mexico-liga-expansion',data,now=NOW) is None


def test_naive_clock_and_write_paths_are_rejected():
    with pytest.raises(ValueError):m.parse_fixture_membership(LEAGUE,hub(),now=NOW.replace(tzinfo=None))
    for bad in ('SessionLocal','execute(','.post(','.put(','.delete(','.commit(', 'collector.run'):
        assert bad not in inspect.getsource(m)
