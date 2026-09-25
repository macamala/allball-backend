"""Changed known results cannot wait behind an entire historical date crawl."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from collector.adapters import FetchResult
from collector.football_board_priority import (changed_result_signature, priority_plan,
    record_priority_attempt, MAX_PRIORITY_RECEIPTS, conflict_evidence)
from collector.football_board_refresh import refresh_day, JOB_PREFIX, POLICY_REVISION
from collector.models import SportsEvent, SportsCollectorJob
from collector.util import dump_json, load_json, isoformat
from tests.test_football_global_refresh import setup, fresh, RECORDED, board


def candidate(sid='900', *, now=None, stored='scheduled', actual=(None,None), upstream='finished'):
    now=now or datetime.utcnow()
    raw=fresh(RECORDED[0]);raw['id']=int(sid)
    raw['status'].update(utcTime=isoformat(now-timedelta(hours=2)),started=True,
                         finished=upstream=='finished',scoreStr='2-1')
    raw['home']['score']=2;raw['away']['score']=1
    raw['status']['reason']={'short':'FT' if upstream=='finished' else 'LIVE'}
    parts={s:{'name':raw[s]['name']} for s in ('home','away')}
    row=SportsEvent(event_id='evt-'+sid,fingerprint='fp-'+sid,sport_id='football',competition_id='test',
        event_family='team_match',start_time=now-timedelta(hours=2),status=stored,
        score_json=dump_json(dict(zip(('home','away'),actual))),participants_json=dump_json(parts),
        display_eligible=True,extra_json=dump_json({'source_family':'fotmob','source_event_ids':{'fotmob':sid}}))
    return raw,row


@pytest.mark.parametrize('stored,score',[('scheduled',(None,None)),('live',(1,0)),('finished',(1,1)),('finished',('1','0'))])
def test_actual_fresh_correction_is_selected(stored,score):
    now=datetime.utcnow();raw,row=candidate(now=now,stored=stored,actual=score)
    assert priority_plan({'900':raw},{'900':[row]}, {}, now, 100).keys()=={'900'}


@pytest.mark.parametrize('case',['equal','old','future-fetch','future-kickoff','pregame','no-root','wrong-pair','wrong-time','manual','retired','slim-policy'])
def test_priority_is_not_a_freshness_identity_or_visibility_override(case):
    now=datetime.utcnow();raw,row=candidate(now=now)
    index={'900':[row]}
    if case=='equal':row.status='finished';row.score_json=dump_json({'home':'2','away':1})
    if case=='old':raw['_source_fetched_at']=isoformat(now-timedelta(minutes=6))
    if case=='future-fetch':raw['_source_fetched_at']=isoformat(now+timedelta(minutes=2))
    if case=='future-kickoff':raw['status']['utcTime']=isoformat(now+timedelta(hours=2));row.start_time=now+timedelta(hours=2)
    if case=='pregame':raw['status'].update(started=False,finished=False);raw['status']['reason']={}
    if case=='no-root':index={}
    if case=='wrong-pair':raw['home']['name']='Different Team'
    if case=='wrong-time':row.start_time-=timedelta(hours=1)
    if case=='manual':row.extra_json=dump_json({'manual_hidden':True})
    if case=='retired':row.canonical_event_id='other-root'
    if case=='slim-policy':row.list_extra_json=dump_json({'do_not_restore':True})
    assert not priority_plan({'900':raw},index,{},now,100)


def test_identical_fetch_does_not_defeat_retry_cooldown_but_changed_evidence_does():
    now=datetime.utcnow();raw,row=candidate(now=now);matches={'900':raw};index={'900':[row]};receipts={}
    selected=priority_plan(matches,index,receipts,now,100)
    record_priority_attempt(receipts,'900',selected['900'],now)
    raw['_source_fetched_at']=isoformat(now+timedelta(seconds=10))
    assert not priority_plan(matches,index,receipts,now+timedelta(seconds=10),100)
    row.score_json=dump_json({'home':1,'away':1})
    assert priority_plan(matches,index,receipts,now+timedelta(seconds=10),100)
    assert priority_plan(matches,index,receipts,now+timedelta(seconds=301),100)


def test_priority_is_bounded_fair_and_survives_receipt_serialization():
    now=datetime.utcnow();matches={};index={};receipts={}
    for sid in range(900,920):
        raw,row=candidate(str(sid),now=now);matches[str(sid)]=raw;index[str(sid)]=[row]
    first=priority_plan(matches,index,receipts,now,100);assert len(first)==8
    for sid,sig in first.items():record_priority_attempt(receipts,sid,sig,now)
    second=priority_plan(matches,index,load_json(dump_json(receipts)),now,100)
    assert len(second)==8 and not (first.keys()&second.keys())
    assert not priority_plan(matches,index,{},now,1)
    assert len(priority_plan(matches,index,{},now,2))==1
    for sid in range(150):record_priority_attempt(receipts,str(sid),'x',now)
    assert len(receipts)==MAX_PRIORITY_RECEIPTS


def schedule_case(setup,monkeypatch,*,after='',failure=None):
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    raws=[]
    for sid in ('100','200','900'):
        raw,row=candidate(sid,now=now);raws.append(raw)
        if sid=='900':db.add(row)
    job=SportsCollectorJob(job_key=JOB_PREFIX+day,last_error=dump_json({'policy_revision':POLICY_REVISION,'after_id':after}))
    db.add(job);db.commit();seen=[]
    def consume(db,raw,*_):
        sid=str(raw['id']);seen.append(sid)
        if sid==failure:raise RuntimeError('transient database failure')
        return {'written':1}
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match',consume)
    getter=lambda _:FetchResult(ok=True,http_status=200,payload=board(raws),fetched_at=isoformat(now))
    return db,source,now,day,job,getter,seen


def test_known_late_id_updates_without_acknowledging_unseen_coverage(setup,monkeypatch):
    db,source,now,day,job,getter,seen=schedule_case(setup,monkeypatch)
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=2);db.commit()
    assert seen==['100','900'] and result['priority_processed']==1
    assert load_json(job.last_error)['after_id']=='100' and not result['complete']
    # Reopen session, using the persisted receipt/cursor rather than process memory.
    from database import SessionLocal
    with SessionLocal() as second:
        result=refresh_day(second,day,second.get(type(source),source.source_id),now=now,getter=getter,max_events=10);second.commit()
    assert seen==['100','900','200','900'] and result['complete']


def test_priority_duplicate_acknowledgement_does_not_reprocess_same_page(setup,monkeypatch):
    db,source,now,day,job,getter,seen=schedule_case(setup,monkeypatch)
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=3);db.commit()
    assert seen==['100','900','200'] and result['complete']
    assert result['processed']==3 and load_json(job.last_error)['after_id']==''


def test_priority_behind_coverage_cursor_never_rewinds_it(setup,monkeypatch):
    db,source,now,day,job,getter,seen=schedule_case(setup,monkeypatch,after='950')
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=2);db.commit()
    assert seen==['900'] and result['complete']


def test_transient_failure_retains_only_acknowledged_coverage(setup,monkeypatch):
    db,source,now,day,job,getter,seen=schedule_case(setup,monkeypatch,failure='900')
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=5);db.commit()
    state=load_json(job.last_error)
    assert seen==['100','900'] and state['after_id']=='100'
    assert not result['complete'] and not state['priority_receipts']


def test_changed_result_priority_does_not_add_an_upstream_request(setup,monkeypatch):
    db,source,now,day,job,getter,seen=schedule_case(setup,monkeypatch)
    urls=[]
    def fetch(url):urls.append(url);return getter(url)
    refresh_day(db,day,source,now=now,getter=fetch,max_events=3);db.commit()
    assert len(urls)==1 and seen==['100','900','200']


def test_failed_source_preserves_priority_receipts_and_cursor(setup):
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    before={'policy_revision':POLICY_REVISION,'after_id':'500','priority_receipts':{'900':{'signature':'x'}}}
    job=SportsCollectorJob(job_key=JOB_PREFIX+day,last_error=dump_json(before));db.add(job);db.commit()
    result=refresh_day(db,day,source,now=now,getter=lambda _:FetchResult(ok=False,http_status=503));db.commit()
    state=load_json(job.last_error)
    assert not result['complete'] and state['after_id']=='500' and state['priority_receipts']==before['priority_receipts']


def test_internal_conflict_evidence_is_bounded_and_does_not_edit_rows():
    now=datetime.utcnow();raw,row=candidate(now=now)
    from collector.adapters_fotmob import match_to_event
    rows={}
    for n in range(10):
        _,r=candidate(str(900+n),now=now);rows[r.event_id]=r
    evidence=conflict_evidence(rows,match_to_event(raw,''))
    assert evidence['root_count']==10 and len(evidence['roots'])==4
    assert all(r.canonical_event_id is None and r.status=='scheduled' for r in rows.values())
