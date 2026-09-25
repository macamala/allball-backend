from datetime import datetime,timedelta
from types import SimpleNamespace
import pytest
from collector.player_enrichment import parse_profile,enriched_profile,_CACHE
from collector.football_board_priority import changed_result_signature,priority_plan,record_priority_attempt
from tests.test_football_board_priority import candidate
from collector.util import dump_json


def root():
    return {'id':123,'name':'Verified Player','primaryTeam':{'teamId':4,'teamName':'Actual Club','onLoan':False},'birthDate':{'utcTime':'1999-01-02T00:00:00Z'},'positionDescription':{'primaryPosition':{'label':'Striker'}},
      'playerInformation':[{'translationKey':'transfer_value','value':{'numberValue':0,'fallback':'€0'}}],
      'marketValues':{'values':[{'value':100000,'currency':'EUR','date':'2026-08-01T00:00:00Z'}]},
      'careerHistory':{'careerItems':{'senior':{'teamEntries':[{'teamId':4,'team':'Actual Club','startDate':'2025-01-01','active':True,'appearances':'0','goals':'0','assists':'undefined','transferType':{'text':'free transfer'}}]}}},
      'mainLeague':{'leagueName':'Premier','season':'2026','stats':[{'title':'Goals','value':0}]}}


def test_player_real_club_valuation_zero_career_and_scoped_season():
    out=parse_profile(root(),123,'Verified Player')
    assert out['current_club']['name']=='Actual Club'
    assert out['market_value']=={'amount':0,'currency':'EUR','as_of':None,'estimated':True}
    assert out['career'][0]['goals']=='0' and out['career'][0]['assists'] is None
    assert out['season_summary']['stats'][0]['value']==0
    assert 'source' not in out and 'transfer_fee' not in out

@pytest.mark.parametrize('id,name',[(124,'Verified Player'),(123,'Other Player'),(123,'')])
def test_wrong_player_payload_is_rejected(id,name):assert parse_profile(root(),id,name)=={}

def test_unknown_currency_or_future_value_does_not_become_euros():
    r=root();r['playerInformation']=[];r['marketValues']['values']=[{'value':5,'date':'2099-01-01','currency':'EUR'},{'value':5,'date':'2026-01-01','currency':None}]
    assert 'market_value' not in parse_profile(r,123,'Verified Player')

def test_profile_cache_coalesces_and_returns_independent_copies():
    _CACHE.clear();calls=[]
    def getter(url):calls.append(url);return SimpleNamespace(ok=True,payload=root())
    a=enriched_profile(123,'Verified Player',getter);a['current_club']['name']='Mutated'
    b=enriched_profile(123,'Verified Player',getter)
    assert len(calls)==1 and b['current_club']['name']=='Actual Club'
    assert enriched_profile('../bad','Verified Player',getter)=={} and len(calls)==1

def test_clock_only_update_is_prioritized_without_whole_board_cursor_wait():
    now=datetime.utcnow();raw,row=candidate(now=now,stored='live',actual=(2,1),upstream='live')
    raw['status']['liveTime']={'short':"64'"};row.score_json=dump_json({'home':2,'away':1,'minute':"60'"})
    first=priority_plan({'900':raw},{'900':[row]},{},now,100);assert '900' in first
    receipts={};record_priority_attempt(receipts,'900',first['900'],now)
    assert not priority_plan({'900':raw},{'900':[row]},receipts,now,100)
    raw['status']['liveTime']['short']="65'"
    assert priority_plan({'900':raw},{'900':[row]},receipts,now,100)

def test_clock_does_not_bypass_hidden_conflict_backoff():
    now=datetime.utcnow();raw,row=candidate(now=now,stored='live',actual=(2,1),upstream='live');row.display_eligible=False
    raw['status']['liveTime']={'short':"64'"};before=changed_result_signature(raw,[row],now)
    raw['status']['liveTime']['short']="65'"
    assert changed_result_signature(raw,[row],now)==before

def test_hot_refresh_precedes_slow_lanes_and_preserves_shared_lease(monkeypatch):
    import collector.priority_cycle as pc
    calls=[]
    db=SimpleNamespace(commit=lambda:None,rollback=lambda:None)
    monkeypatch.setattr('collector.football_board_refresh.run_football_board_refresh',lambda *a,**kw:calls.append(('board',kw)) or {})
    monkeypatch.setattr(pc,'run_incremental_tick',lambda *a,**kw:calls.append(('tick',kw)) or {})
    monkeypatch.setattr(pc,'heartbeat_scheduler_lock',lambda *a,**kw:True)
    monkeypatch.setattr(pc,'has_priority_events',lambda *a:False)
    assert pc.run_priority_cycle(db,owner='same-lease') is False
    assert calls[0]==('board',{'owner':'same-lease','hot_only':True})
    assert sum(kind=='tick' for kind,_ in calls)==2
    assert calls[-1]==('board',{'owner':'same-lease'})

from tests.test_keeper_revalidation import case
from tests.test_public_keeper_alias import ready

def test_light_score_view_uses_canonical_visibility_without_enrichment_or_history(case,monkeypatch):
    from collector.provider import NinkoCollectedSportsDataProvider
    from database import SessionLocal
    c=case;ready(c)
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda *_:pytest.fail('Network detail on score lane'))
    monkeypatch.setattr('collector.provider._history_context',lambda *_:pytest.fail('History on score lane'))
    p=NinkoCollectedSportsDataProvider(session_factory=SessionLocal)
    value=p.get_event(c.child.event_id,lightweight=True)
    assert value['id']==c.root.event_id and value['status']=='finished'
    assert value['score']['home']==1 and value['score']['away']==2
    assert p.get_event('unknown',lightweight=True) is None

def test_public_clock_anchor_does_not_leak_provider(case):
    from collector.provider import NinkoCollectedSportsDataProvider
    from database import SessionLocal
    from collector.util import load_json
    c=case;ready(c);meta=load_json(c.root.extra_json);meta['source_fetch_time']='2026-09-25T08:00:00Z';c.root.extra_json=dump_json(meta);c.db.commit()
    value=NinkoCollectedSportsDataProvider(session_factory=SessionLocal).get_event(c.root.event_id,lightweight=True)
    assert value['score_observed_at']=='2026-09-25T08:00:00Z'
    assert 'source_family' not in value

from tests.test_entity_profile_navigation import db

def test_player_enrichment_never_uses_a_namesake_or_exposes_linkage(db,monkeypatch):
    from collector.models import SportsEventDetail
    from collector.entity_profiles import player_profile
    detail=db.get(SportsEventDetail,'match')
    detail.lineups_json=dump_json({'home':{'start':[
      {'id':825815,'name':'Aidan Keena','profile_ref':{'family':'fotmob','id':'825815'}},
      {'id':999,'name':'Aidan Keena','profile_ref':{'family':'fotmob','id':'999'},'goals':99}]}})
    db.commit();called=[]
    monkeypatch.setattr('collector.player_enrichment.enriched_profile',lambda pid,name:called.append(pid) or {'current_club':{'id':'4','name':'Correct'}})
    result=player_profile(db,player_key='825815',name='Aidan Keena',event_id='match')
    assert called==['825815'] and 'profile_ref' not in result['player'] and result['player'].get('goals')!=99
    from collector.provider import _public_value
    assert 'profile_ref' not in _public_value({'profile_ref':{'family':'fotmob','id':'825815'},'name':'Aidan'})
