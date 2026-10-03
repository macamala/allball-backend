from copy import deepcopy
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from bot import news_football_memberships as m

NOW=datetime(2026,10,3,3,tzinfo=timezone.utc)
GOOD='poland-ekstraklasa'
FAILED='england-championship'


def table(league):
    return {'competition':{'id':league,'sport':'football'},'stale':False,'available':True,
        'season':'2026/2027','updated_at':NOW.isoformat(),
        'rows':[{'team':f'Football Team {i}','team_id':str(i)} for i in range(1,5)]}

@pytest.fixture
def clock(monkeypatch):
    state=[1000.0]
    monkeypatch.setattr(m,'_ENTRIES',{})
    monkeypatch.setattr(m,'_LAST_REFRESH',float('-inf'))
    monkeypatch.setattr(m,'_RETRY_PENDING',{})
    monkeypatch.setattr(m,'DOMESTIC',{GOOD:{},FAILED:{}})
    monkeypatch.setattr(m.time,'monotonic',lambda:state[0])
    return state


def test_network_outage_retries_only_failed_league_and_retains_current_good_evidence(clock):
    calls=[]
    fail=[True]
    def get(league,key):
        calls.append(league)
        if league==FAILED and fail[0]:raise httpx.ReadTimeout('private details must not appear')
        return table(league)
    first=m.refresh_football_news_memberships(now=NOW,get=get)
    assert first['leagues']==1 and first['retry_pending']==[FAILED]
    assert 'private' not in str(first)
    good=deepcopy(m.memberships_for_news(NOW)[GOOD])
    clock[0]+=599
    assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='cached'
    assert len(calls)==2
    clock[0]+=1;fail[0]=False
    recovered=m.refresh_football_news_memberships(now=NOW,get=get)
    assert recovered['status']=='retried' and recovered['leagues']==2
    assert recovered['retry_pending']==[]
    assert calls.count(GOOD)==1 and calls.count(FAILED)==2
    assert m.memberships_for_news(NOW)[GOOD]==good
    assert m._LAST_REFRESH==1000


def test_retry_backoff_is_bounded_and_does_not_run_more_often_than_a_normal_cycle(clock):
    calls=[]
    def get(league,key):
        calls.append(league)
        if league==FAILED:raise httpx.ConnectError('offline')
        return table(league)
    m.refresh_football_news_memberships(now=NOW,get=get)
    for interval in [600,1200,2400]:
        clock[0]+=interval-1
        assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='cached'
        clock[0]+=1
        assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='retried'
    assert calls.count(FAILED)==4 and calls.count(GOOD)==1
    assert m._RETRY_PENDING=={}
    clock[0]+=600
    assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='cached'
    clock[0]=1000+m.TTL_SECONDS
    assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='refreshed'
    assert calls.count(GOOD)==2 and m._RETRY_PENDING

@pytest.mark.parametrize('kind',['missing','stale','wrong-scope','malformed'])
def test_invalid_or_quiet_source_is_not_retried_as_a_network_outage(clock,kind):
    def get(league,key):
        if league==GOOD:return table(league)
        if kind=='missing':return {}
        if kind=='malformed':raise ValueError('Invalid JSON data')
        data=table(league)
        if kind=='stale':data['stale']=True
        else:data['competition']['id']=GOOD
        return data
    result=m.refresh_football_news_memberships(now=NOW,get=get)
    assert result['leagues']==1 and result['retry_pending']==[]
    clock[0]+=1200
    assert m.refresh_football_news_memberships(now=NOW,get=get)['status']=='cached'

@pytest.mark.parametrize('status,retry',[(429,True),(500,True),(502,True),(503,True),(400,False),(401,False),(403,False),(404,False)])
def test_status_retries_respect_access_denials_and_missing_routes(clock,status,retry):
    response=httpx.Response(status,request=httpx.Request('GET','https://firstparty.invalid/public'))
    def get(league,key):
        if league==GOOD:return table(league)
        response.raise_for_status()
    result=m.refresh_football_news_memberships(now=NOW,get=get)
    assert bool(result['retry_pending'])==retry


def test_a_valid_fixture_fallback_cancels_failed_table_retry(clock,monkeypatch):
    from test_news_recent_fixture_memberships import hub, NOW as FIXTURE_NOW
    monkeypatch.setattr(m,'DOMESTIC',{FAILED:{}})
    def get(*args):raise httpx.ReadTimeout('timeout')
    fixture=hub()
    result=m.refresh_football_news_memberships(now=FIXTURE_NOW,get=get,get_fixtures=lambda *args:fixture)
    assert result['leagues']==1 and result['retry_pending']==[]
    assert result['fixture_roster_leagues']==[FAILED]


def test_valid_old_evidence_is_retained_but_not_retimestamped_or_resurrected(clock):
    m.refresh_football_news_memberships(now=NOW,get=lambda league,key:table(league))
    previous=deepcopy(m.memberships_for_news(NOW))
    def get(*args):raise httpx.ReadTimeout('offline')
    m.refresh_football_news_memberships(now=NOW,get=get,force=True)
    assert m.memberships_for_news(NOW)==previous
    clock[0]+=600
    m.refresh_football_news_memberships(now=NOW+timedelta(days=4),get=get)
    assert not m.memberships_for_news(NOW+timedelta(days=4))


def test_injected_readers_never_trigger_network_when_retrying(clock,monkeypatch):
    monkeypatch.setattr(m,'_public_get',lambda *args:pytest.fail('external table request'))
    monkeypatch.setattr(m,'_public_fixture_get',lambda *args:pytest.fail('external fixture request'))
    def failure(*args):raise httpx.ConnectError('offline')
    m.refresh_football_news_memberships(now=NOW,get=failure)
    clock[0]+=600
    assert m.refresh_football_news_memberships(now=NOW,get=failure)['status']=='retried'
