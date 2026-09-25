"""Regressions from the three user screenshots; never infer FT or LIVE by time."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest
from collector.models import SportsEvent, SportsCompetition
from collector.provider import NinkoCollectedSportsDataProvider
from collector.live_state import reconcile_live_status, public_live_visible
from collector.adapters_openligadb import _to_event
from collector.status_delta import status_delta_page
from collector.util import dump_json
from database import SessionLocal


def row(eid='match', **kw):
    at=datetime.utcnow()
    values=dict(event_id=eid,fingerprint=eid,sport_id='football',event_family='team_match',
        competition_id='germany-3-liga',start_time=at-timedelta(hours=3),updated_at=at,
        status='finished',live=False,display_eligible=True,
        score_json=dump_json({'home':0,'away':0,'minute':'95’'}),
        participants_json=dump_json({'home':{'name':'Cayman Islands'},'away':{'name':'Dominica'}}),
        extra_json=dump_json({'source_family':'fotmob','source_status':'finished','display_eligible':True,
            'live_class':'CONFIRMED_LIVE','source_fetch_time':at.isoformat()+'Z',
            'source_competition_id':'208','source_competition_name':'3. Liga'}))
    values.update(kw);return SportsEvent(**values)


@pytest.fixture
def db():
    db=SessionLocal()
    db.add(SportsCompetition(competition_id='germany-3-liga',sport_id='football',name='3. Liga',slug='germany-3-liga',event_model='team_match'))
    db.commit()
    yield db
    db.close()


def test_final_status_delta_clears_legacy_live_flag_and_preserves_zero_final(db):
    db.add(row());db.commit()
    page=status_delta_page(db,NinkoCollectedSportsDataProvider(),since=(datetime.utcnow()-timedelta(minutes=1)).isoformat())
    e=page['events'][0]
    assert e['status']=='finished' and e['live'] is False and e['live_class'] is None
    assert e['score']['home']==e['score']['away']==0
    assert 'source_family' not in e and 'source_event_ids' not in e


@pytest.mark.parametrize('field,value',[
    ('canonical_event_id','keeper'),('display_eligible',False),
    ('extra_json',dump_json({'manual_hidden':True})),
    ('list_extra_json',dump_json({'do_not_restore':True})),
    ('extra_json',dump_json({'display_eligible':False})),
    ('list_extra_json',dump_json({'canonical_event_id':'keeper'})),
    ('extra_json',dump_json({'collapse_role':'observation_only'})),
])
def test_status_delta_returns_retirement_not_hidden_fixture(db,field,value):
    db.add(row('retired',**{field:value}));db.commit()
    page=status_delta_page(db,NinkoCollectedSportsDataProvider())
    e=page['events'][0]
    assert e['id']=='retired' and e['removed'] is True
    assert set(e)=={'id','removed','updated_at'}


def test_delta_cursor_does_not_lose_rows_sharing_a_timestamp(db,monkeypatch):
    import collector.status_delta as mod
    monkeypatch.setattr(mod,'PAGE_SIZE',2)
    at=datetime.utcnow().replace(microsecond=123456)
    for i in range(5):db.add(row(f'event-{i}',updated_at=at))
    db.commit();p=NinkoCollectedSportsDataProvider()
    one=status_delta_page(db,p);two=status_delta_page(db,p,cursor=one['next_cursor']);three=status_delta_page(db,p,cursor=two['next_cursor'])
    assert one['has_more'] and two['has_more'] and not three['has_more']
    assert [e['id'] for page in (one,two,three)for e in page['events']]==[f'event-{i}'for i in range(5)]
    assert status_delta_page(db,p,cursor=three['next_cursor'])['events']==[]
    assert '.123456Z' in one['events'][0]['updated_at']


@pytest.mark.parametrize('cursor',['bad-cursor', '!!!!!', 'a'*600])
def test_bad_cursor_falls_back_without_crash_or_unfiltered_history(db,cursor):
    db.add(row());db.commit()
    assert len(status_delta_page(db,NinkoCollectedSportsDataProvider(),cursor=cursor)['events'])==1


@pytest.mark.parametrize('status',['live','break','halftime','stale'])
def test_future_football_progress_cannot_create_public_live(status):
    now=datetime.now(timezone.utc)
    original={'sport':'football','status':status,'start_time':(now+timedelta(hours=13)).isoformat(),
        'start_precision':'EXACT_TIME','source_family':'openligadb','source_status':status,
        'source_fetch_time':now.isoformat(),'live':True,'live_class':'CONFIRMED_LIVE',
        'score':{'home':0,'away':0,'minute':45},'periods':[{'code':'HT','home':0,'away':0}]}
    before=deepcopy(original);e=reconcile_live_status(original,now=now)
    assert e['status']=='scheduled' and e['live'] is False and not public_live_visible(e,now=now)
    assert e['score']['home'] is None and e['periods']==[] and original==before


def test_live_future_guard_keeps_real_recent_live():
    now=datetime.now(timezone.utc)
    e=reconcile_live_status({'sport':'football','status':'live','start_time':(now-timedelta(minutes=25)).isoformat(),
        'source_family':'fotmob','source_status':'live','source_fetch_time':now.isoformat(),
        'score':{'home':0,'away':0,'minute':25}},now=now)
    assert e['live'] is True and e['status']=='live'


def openliga(future=True,finished=False,goals=None):
    return {'matchID':84813,'matchDateTimeUTC':(datetime.utcnow()+timedelta(hours=13) if future else datetime.utcnow()-timedelta(hours=1)).isoformat()+'Z',
        'matchIsFinished':finished,'team1':{'teamName':'TSV Havelse'},'team2':{'teamName':'Fortuna Köln'},
        'lastUpdateDateTime':'2026-09-19T22:18:22.65','goals':goals or [],
        'matchResults':[{'resultName':'Halbzeit','resultTypeID':1,'resultTypeKind':'HalfTime','pointsTeam1':0,'pointsTeam2':0},
                        {'resultName':'Endergebnis','resultTypeID':2,'resultTypeKind':'After90Minutes','pointsTeam1':0,'pointsTeam2':0}]}


@pytest.mark.parametrize('future',[True,False])
def test_precreated_openliga_result_slots_are_not_live_proof_even_after_kickoff(future):
    e=_to_event(openliga(future=future),{'competition_id':'germany-3-liga'})
    assert e['status']=='scheduled' and e['score']=={'home':None,'away':None}
    assert e['periods']==[] and e['incidents']==[]


def test_openliga_explicit_finished_zero_zero_is_retained():
    e=_to_event(openliga(future=False,finished=True),{'competition_id':'germany-3-liga'})
    assert e['status']=='finished' and e['score']=={'home':0,'away':0}


def test_future_legacy_ht_is_sanitized_in_status_delta(db):
    r=row(status='break',live=True,start_time=datetime.utcnow()+timedelta(hours=13),
        extra_json=dump_json({'source_family':'openligadb','source_status':'break','display_eligible':True,
            'source_competition_name':'3. Liga','source_competition_id':'bl3',
            'live_class':'CONFIRMED_LIVE','periods':[{'code':'HT','home':0,'away':0}]}))
    db.add(r);db.commit();e=status_delta_page(db,NinkoCollectedSportsDataProvider())['events'][0]
    assert e['status']=='scheduled' and e['live'] is False
    assert e['score'].get('home') is None


def test_date_bounded_api_marks_only_a_completed_public_snapshot(monkeypatch):
    import app as app_module
    from fastapi.testclient import TestClient
    class Provider:
        def status(self):return {'connected':True}
        def get_events(self,**kwargs):return []
    monkeypatch.setattr(app_module,'get_active_provider',lambda:Provider())
    client=TestClient(app_module.app)
    full=client.get('/sports-data/events',params={'date':'2026-09-25'}).json()
    assert full['snapshot']=={'complete':True,'count':0,'date_from':'2026-09-25T00:00:00Z','date_to':'2026-09-25T23:59:59Z'}
    assert client.get('/sports-data/events').json()['snapshot']['complete'] is False
    assert client.get('/sports-data/events',params={'date':'2026-09-25','status':'live'}).json()['snapshot']['complete'] is False


def test_status_api_passes_exact_paging_cursor_without_changing_it(monkeypatch):
    import app as app_module
    from fastapi.testclient import TestClient
    calls=[]
    class Provider:
        def status(self):return {'connected':True}
        def get_status_delta_page(self,**kwargs):
            calls.append(kwargs)
            return {'events':[{'id':'old','removed':True}],'has_more':True,'next_cursor':'next-proof'}
    monkeypatch.setattr(app_module,'get_active_provider',lambda:Provider())
    body=TestClient(app_module.app).get('/sports-data/status-delta',params={'cursor':'page-proof','sport':'football'}).json()
    assert calls==[{'since':None,'sport':'football','cursor':'page-proof'}]
    assert body['events']==[{'id':'old','removed':True}] and body['next_cursor']=='next-proof'
