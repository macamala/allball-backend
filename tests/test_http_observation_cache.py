"""Actual HTTP-layer regressions: clocks advance but processes never restart."""
import json
from datetime import datetime,timedelta
import pytest
from collector.adapters import FetchResult
from collector import http

@pytest.fixture(autouse=True)
def isolated_http(monkeypatch):
    http.reset_http_stats()
    monkeypatch.setattr(http,'_pace_host',lambda _:None)
    monkeypatch.setattr(http,'_pace_family',lambda _:None)
    yield
    http.reset_http_stats()

class Response:
    status=200
    headers={}
    def __init__(self,payload):self.payload=payload
    def read(self):return json.dumps(self.payload).encode()
    def __enter__(self):return self
    def __exit__(self,*_):pass

@pytest.mark.parametrize('url',[
    'https://www.fotmob.com/api/data/matches?date=20260925',
    'https://api.openligadb.de/getmatchdata/bl1',
    'https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard',
])
def test_scoreboard_http_cache_expires_without_reset_or_redeploy(monkeypatch,url):
    clock=[100.0];calls=[]
    monkeypatch.setattr(http.time,'monotonic',lambda:clock[0])
    def get(*a,**k):
        calls.append(1)
        return Response({'status':('scheduled','live','finished')[len(calls)-1],'score':len(calls)-1})
    monkeypatch.setattr(http.urllib.request,'urlopen',get)
    first=http.fetch_url(url);stamp=first.fetched_at
    assert http.fetch_url(url) is first and first.fetched_at==stamp and len(calls)==1
    clock[0]+=6
    assert http.fetch_url(url).payload['status']=='live'
    clock[0]+=6
    assert http.fetch_url(url).payload['status']=='finished' and len(calls)==3


def test_board_ttl_cannot_be_undermined_by_immortal_http_cache(monkeypatch):
    from collector import adapters_fotmob as fm
    from collector.adapters import FetchRequest
    fm._BOARD.clear();fm._BOARD_AT.clear()
    clock=[100.0];calls=[]
    monkeypatch.setattr(http.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(fm,'board_dates',lambda **k:['20260925'])
    def get(*a,**k):
        calls.append(1)
        n=len(calls)-1
        return Response({'leagues':[{'id':53,'name':'Ligue 1','matches':[{'id':991,'home':{'name':'Alpha','score':n},'away':{'name':'Beta','score':0},'status':{'started':n>0,'finished':n==2,'utcTime':'2026-09-25T00:00:00Z'}}]}]})
    monkeypatch.setattr(http.urllib.request,'urlopen',get)
    adapter=fm.FotMobAdapter(getter=http.fetch_url);request=FetchRequest(capability='live_scores',competition_id='france-ligue-1')
    first=adapter.fetch(request).events[0];assert first['status']=='scheduled' and first['score']['home'] is None
    original=first['source_fetch_time'];assert original
    assert adapter.fetch(request).events[0]['source_fetch_time']==original and len(calls)==1
    clock[0]+=6
    second=adapter.fetch(request).events[0];assert second['status']=='live' and second['score']['home']==1
    clock[0]+=6
    third=adapter.fetch(request).events[0];assert third['status']=='finished' and third['score']['home']==2
    assert len(calls)==3
    fm._BOARD.clear();fm._BOARD_AT.clear()


def test_negative_cache_expires_but_host_backoff_does_not(monkeypatch):
    clock=[100.];monkeypatch.setattr(http.time,'monotonic',lambda:clock[0])
    key=http._cache_key('https://www.fotmob.com/test','json',None)
    http._store(key,FetchResult(ok=False,http_status=403,restricted=True))
    http._block_host('https://www.fotmob.com/test',900,'forbidden')
    monkeypatch.setattr(http.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Ignored active host backoff'))
    clock[0]+=6
    assert http._cached(key) is None
    assert not http.fetch_url('https://www.fotmob.com/test').ok
    assert http.host_is_blocked('https://www.fotmob.com/test')


def test_cache_size_is_bounded_and_json_bytes_do_not_collide(monkeypatch):
    monkeypatch.setattr(http,'HTTP_CACHE_MAX_ENTRIES',3)
    for n in range(5):http._store(str(n),FetchResult(ok=True,http_status=200,payload=n))
    assert len(http._CACHE)==len(http._CACHE_AT)==3
    assert http._cached('0') is None
    monkeypatch.setattr(http.urllib.request,'urlopen',lambda *a,**k:Response({'a':1}))
    assert isinstance(http.fetch_url('https://example.test/a').payload,dict)
    assert isinstance(http.fetch_bytes('https://example.test/a').payload,bytes)

@pytest.mark.parametrize('status',['live','halftime','break','ht','inplay','in_play'])
def test_confirmed_interval_states_stay_in_live_priority_lane(status):
    from collector.urgency import classify_event
    assert classify_event(status,datetime.utcnow()-timedelta(minutes=55))=='LIVE'

@pytest.mark.parametrize('code',[403,429,503])
def test_unavailable_board_is_not_reported_as_healthy_empty(code):
    from collector.adapters_fotmob import FotMobAdapter,_BOARD,_BOARD_AT
    from collector.adapters import FetchRequest
    _BOARD.clear();_BOARD_AT.clear()
    result=FotMobAdapter(getter=lambda _:FetchResult(ok=False,http_status=code,restricted=code==403,error='unavailable')).fetch(FetchRequest(capability='live_scores',competition_id='france-ligue-1'))
    assert not result.ok and result.http_status==code and not result.events


def test_empty_live_response_does_not_freshen_absent_match(monkeypatch):
    from tests.test_collector_architecture import _source,_competition,_map
    from collector.models import SportsEvent
    from collector.collect import _consume_result
    from collector.util import dump_json,load_json
    from database import SessionLocal
    with SessionLocal() as db:
        s=_source(db,'contact-test','fotmob');s.upstream_family='fotmob'
        c=_competition(db,'france-ligue-1','football');m=_map(db,c.competition_id,s.source_id,upstream_family='fotmob')
        old=(datetime.utcnow()-timedelta(minutes=30)).isoformat()+'Z'
        row=SportsEvent(event_id='absent-live',event_family='team_match',sport_id='football',competition_id=c.competition_id,status='live',live=True,display_eligible=True,extra_json=dump_json({'source_fetch_time':old,'last_contact_at':old}))
        db.add(row);db.commit()
        _consume_result(db,source=s,mapping=m,competition=c,capability='live_scores',result=FetchResult(ok=True,http_status=200,events=[]));db.commit()
        assert load_json(row.extra_json)['source_fetch_time']==old


def test_fresh_explicit_second_half_and_var_correction_beats_older_board():
    from collector.merge import merge_event_fields
    old={'sport':'football','source_family':'fotmob','source_status':'break','status':'break','score':{'home':2,'away':0},'source_fetch_time':'2026-09-25T00:10:00Z'}
    new={'sport':'football','source_family':'fotmob','source_status':'live','status':'live','score':{'home':1,'away':0},'source_fetch_time':'2026-09-25T00:11:00Z'}
    corrected=merge_event_fields(old,new,incoming_is_higher_priority=True)
    assert corrected['status']=='live' and corrected['source_status']=='live'
    assert corrected['score']['home']==1
    replay=merge_event_fields(corrected,old,incoming_is_higher_priority=True)
    assert replay['status']=='live' and replay['score']['home']==1
