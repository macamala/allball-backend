"""Scheduling new results does not bypass the existing ingestion authority."""
from datetime import datetime,timedelta
import pytest
from collector.football_board_priority import board_priority_plan,unseen_played_plan,record_priority_attempt
from collector.football_board_refresh import refresh_day,JOB_PREFIX
from collector.adapters import FetchResult
from collector.models import SportsCollectorJob
from collector.util import dump_json,load_json,isoformat
from tests.test_football_board_priority import candidate
from tests.test_football_global_refresh import setup,board


def test_new_finished_and_live_event_dont_wait_for_full_day_cursor(setup,monkeypatch):
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    scheduled,_=candidate('100',now=now,upstream='scheduled')
    scheduled['status'].update(started=False,finished=False,reason={},utcTime=isoformat(now+timedelta(hours=2)))
    played,_=candidate('999',now=now);seen=[];requests=[]
    def consume(db,raw,*_):seen.append(str(raw['id']));return {'written':1}
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match',consume)
    def get(url):requests.append(url);return FetchResult(ok=True,http_status=200,payload=board([scheduled,played]),fetched_at=isoformat(now))
    out=refresh_day(db,day,source,now=now,getter=get,max_events=2);db.commit()
    assert seen==['100','999'] and out['priority_processed']==1 and len(requests)==1
    assert out['complete'] and db.query(SportsCollectorJob).count()==1


@pytest.mark.parametrize('case',['future','stale','future-fetch','too-old','scheduled','indexed','policy-indexed','wrong-id','missing-league'])
def test_new_discovery_lane_is_not_an_identity_or_freshness_override(case):
    now=datetime.utcnow();raw,row=candidate('999',now=now);index={}
    if case=='future':raw['status']['utcTime']=isoformat(now+timedelta(hours=1))
    if case=='stale':raw['_source_fetched_at']=isoformat(now-timedelta(minutes=6))
    if case=='future-fetch':raw['_source_fetched_at']=isoformat(now+timedelta(minutes=2))
    if case=='too-old':raw['status']['utcTime']=isoformat(now-timedelta(days=3))
    if case=='scheduled':raw['status'].update(started=False,finished=False,reason={})
    if case in ('indexed','policy-indexed'):
        index['999']=[row]
        if case=='policy-indexed':row.extra_json=dump_json({'manual_hidden':True})
    if case=='wrong-id':raw['id']=1000
    if case=='missing-league':raw['_league']={}
    assert not unseen_played_plan({'999':raw},index,{},now,2)


def test_known_and_new_results_each_get_slots_and_retry_state_survives_restart():
    now=datetime.utcnow();matches={};index={};receipts={}
    for sid in range(900,924):
        raw,row=candidate(str(sid),now=now);matches[str(sid)]=raw
        if sid<912:index[str(sid)]=[row]
    first=board_priority_plan(matches,index,receipts,now,100)
    assert len(first)==8 and len(first.keys() & index.keys())==6
    for sid,signature in first.items():record_priority_attempt(receipts,sid,signature,now)
    second=board_priority_plan(matches,index,load_json(dump_json(receipts)),now,100)
    assert len(second)==8 and not first.keys()&second.keys()
    assert not board_priority_plan(matches,index,{},now,1)
    tiny=board_priority_plan(matches,index,{},now,2)
    assert len(tiny)==1 and set(tiny)<=set(index)
