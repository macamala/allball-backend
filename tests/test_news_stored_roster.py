from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from urllib.parse import parse_qs,urlsplit
import pytest
import httpx
from bot import news_football_memberships as m
from test_news_recent_fixture_memberships import hub, NOW, LEAGUE, NAMES


def snapshot():
    start,end=m._record_bounds(NOW)
    rows=hub()['events']
    return {'connected':True,'sport':'football','competition':LEAGUE,'status':None,'events':rows,
            'snapshot':{'complete':True,'count':len(rows),'date_from':start,'date_to':end}}


def test_independently_scoped_stored_records_can_supply_roster_while_hub_supplement_is_stale():
    old=hub();old['coverage']['stale']=True
    assert m.parse_fixture_membership(LEAGUE,old,now=NOW) is None
    data=snapshot();before=deepcopy(data)
    record=m.parse_stored_membership(LEAGUE,data,now=NOW)
    assert record['clubs']==sorted(NAMES) and record['season'] is None
    assert record['source_kind']=='confirmed_date_bounded_stored_roster'
    assert record['complete_roster'] is False and record['evidence_matches']==2
    assert record['observed_at']==data['events'][0]['updated_at']
    assert data==before and old['coverage']['stale'] is True
    query=parse_qs(urlsplit(record['source']).query)
    assert query['sport']==['football'] and query['competition']==[LEAGUE]
    assert not {'rows','points','score','goals'}.intersection(record)

@pytest.mark.parametrize('field,value',[
    ('connected',False),('connected',1),('sport','basketball'),('competition','spain-la-liga'),
    ('competition',{}),('snapshot',{}),('events',{}),('events',[]),('status','live'),
])
def test_wrong_or_unverified_snapshot_envelope_is_rejected(field,value):
    data=snapshot();data[field]=value
    assert m.parse_stored_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('field,value',[
    ('complete',False),('complete',1),('count',3),('count',True),('count','2'),
    ('date_from','2020-01-01T00:00:00Z'),('date_from',None),('date_to','2030-12-31T23:59:59Z'),
])
def test_incomplete_overbroad_or_wrong_count_response_does_not_supply_evidence(field,value):
    data=snapshot();data['snapshot'][field]=value
    assert m.parse_stored_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('field,value',[
    ('competition_key','spain-la-liga'),('sport','basketball'),
    ('start_time',None),('start_time','2020-01-01T00:00:00Z'),
    ('start_time','2027-01-01T00:00:00Z'),('start_time','2026-10-10T08:00:00'),
])
def test_a_broken_scope_contract_is_not_cherry_picked(field,value):
    data=snapshot();data['events'][0][field]=value
    assert m.parse_stored_membership(LEAGUE,data,now=NOW) is None

@pytest.mark.parametrize('field,value',[
    ('updated_at',(NOW-timedelta(days=4)).isoformat()),('updated_at',None),
    ('season','2025/2026'),('football_gender','women'),('status','postponed'),
])
def test_recent_api_response_cannot_freshen_old_or_wrong_individual_matches(field,value):
    data=snapshot()
    for event in data['events']:event[field]=value
    assert m.parse_stored_membership(LEAGUE,data,now=NOW) is None


def test_stored_reads_are_last_fallback_never_replace_valid_hub_or_table(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{LEAGUE:{}})
    monkeypatch.setattr(m,'_ENTRIES',{})
    monkeypatch.setattr(m,'_LAST_REFRESH',float('-inf'))
    call=Mock(return_value=snapshot())
    result=m.refresh_football_news_memberships(now=NOW,get=lambda *args:{},get_fixtures=lambda *args:hub(),get_records=call)
    assert result['fixture_rosters']==1
    call.assert_not_called()
    old=hub();old['coverage']['stale']=True
    result=m.refresh_football_news_memberships(now=NOW,get=lambda *args:{},get_fixtures=lambda *args:old,get_records=call,force=True)
    assert result['fixture_rosters']==1 and call.call_count==1
    assert m.memberships_for_news(NOW)[LEAGUE]['source_kind']=='confirmed_date_bounded_stored_roster'


def test_offline_injected_readers_do_not_enable_a_new_network_route(monkeypatch):
    monkeypatch.setattr(m,'DOMESTIC',{LEAGUE:{}})
    monkeypatch.setattr(m,'_ENTRIES',{})
    monkeypatch.setattr(m,'_LAST_REFRESH',float('-inf'))
    monkeypatch.setattr(m,'_public_stored_get',lambda *a,**k:pytest.fail('unexpected HTTP'))
    assert m.refresh_football_news_memberships(now=NOW,get=lambda *a:{},get_fixtures=lambda *a:{})['leagues']==0


def test_public_get_is_date_bounded_first_party_no_credentials_no_redirects(monkeypatch):
    calls=[]
    class Client:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            calls.append((url,kwargs))
            return httpx.Response(200,json=snapshot(),request=httpx.Request('GET',url))
    monkeypatch.setattr(m.httpx,'Client',Client)
    data=m._public_stored_get(LEAGUE,LEAGUE,now=NOW)
    assert data==snapshot() and len(calls)==1
    assert calls[0][0]==m.PUBLIC_API+'/sports-data/events'
    params=calls[0][1]['params']
    assert set(params)=={'sport','competition','date_from','date_to'}
    assert (params['date_from'],params['date_to'])==m._record_bounds(NOW)


def test_naive_date_cannot_be_treated_as_current_evidence():
    with pytest.raises(ValueError):m.parse_stored_membership(LEAGUE,snapshot(),now=NOW.replace(tzinfo=None))
