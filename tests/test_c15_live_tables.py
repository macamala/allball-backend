"""Regression shapes observed on a live match and seasonal league table API."""
from copy import deepcopy
from datetime import datetime,timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.models import Base,SportsEvent,SportsEventDetail,SportsCompetition,SportsSourceCompetition
from collector.util import dump_json,load_json
from collector.detail_enrich import _fresh,PARSER_REV,enrich_event_row
from collector.football_table_identity import resolve_context,scoped_table
from collector.standings_enrich import _fetch_fotmob_dynamic_standings
from tests.test_fotmob_match_centre import source,stored


def test_live_empty_answer_does_not_hide_new_lineup_for_fifteen_minutes(stored):
    db,row,record=stored;row.status='live';record.lineups_json=None
    meta=load_json(row.extra_json);meta.update(detail_empty=True,detail_negative=True,lineups_absent=True,
      detail_fetched_at=(datetime.utcnow()-timedelta(seconds=40)).isoformat(),fotmob_detail_checked_at=datetime.utcnow().isoformat())
    row.extra_json=dump_json(meta);db.commit();calls=[]
    def getter(url):calls.append(url);return SimpleNamespace(ok=True,payload=source())
    before=(row.score_json,row.fingerprint,row.canonical_event_id,row.display_eligible)
    enrich_event_row(db,row,getter=getter);db.commit()
    assert len(calls)==1 and load_json(record.lineups_json)['home']['start'][0]['name']=='First Player'
    assert (row.score_json,row.fingerprint,row.canonical_event_id,row.display_eligible)==before
    enrich_event_row(db,row,getter=getter);assert len(calls)==1

@pytest.mark.parametrize('status,age,expected',[('live',20,True),('live',40,False),('halftime',40,False),('break',20,True),('scheduled',40,True),('finished',40,True),('live',-100,False)])
def test_status_aware_negative_cache_keeps_backoff(status,age,expected):
    meta={'parser_rev':PARSER_REV,'detail_empty':True,'detail_fetched_at':(datetime.utcnow()-timedelta(seconds=age)).isoformat()}
    assert _fresh(meta,status) is expected

def test_transition_to_final_rechecks_details_instead_of_retaining_partial_for_week():
    meta={'parser_rev':PARSER_REV,'detail_empty':False,'detail_status_at_fetch':'live','detail_fetched_at':(datetime.utcnow()-timedelta(seconds=40)).isoformat()}
    assert not _fresh(meta,'finished')

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:yield db

def add_case(db):
    now=datetime.utcnow();cid='football-test-group-a'
    db.add(SportsCompetition(competition_id=cid,sport_id='football',name='Test Group A',slug=cid,event_model='team_match'))
    db.add(SportsSourceCompetition(competition_id=cid,source_id='fotmob-global',upstream_family='fotmob',source_competition_id='9001',enabled=True,priority=1))
    row=SportsEvent(event_id='match',sport_id='football',competition_id=cid,event_family='team_match',status='live',fingerprint='stable',start_time=now,display_eligible=True,
       participants_json=dump_json({'home':{'id':'1','name':'Alpha'},'away':{'id':'2','name':'Beta'}}),extra_json=dump_json({'source_event_ids':{'fotmob':'101'}}))
    db.add(row);db.commit()
    native={'general':{'matchId':'101','leagueId':9001,'parentLeagueId':900,'homeTeam':{'id':1,'name':'Alpha'},'awayTeam':{'id':2,'name':'Beta'},'matchTimeUTCDate':now.isoformat()}}
    def team(i,name):return {'id':i,'name':name,'pts':0,'played':0,'wins':0,'draws':0,'losses':0,'idx':i,'scoresStr':'0-0'}
    table={'details':{'id':900,'name':'Test Cup','selectedSeason':'2026'},'table':[{'data':{'leagueId':900,'composite':True,'leagueName':'Test Cup','tables':[
      {'leagueId':9001,'leagueName':'Group A','table':{'all':[team(1,'Alpha'),team(2,'Beta')]}},
      {'leagueId':9002,'leagueName':'Group B','table':{'all':[team(3,'Gamma'),team(4,'Delta')]}}]}}]}
    return cid,row,native,table

def test_native_match_proves_parent_and_only_requested_group_is_persistable(db):
    cid,row,native,table=add_case(db);before=(row.extra_json,row.score_json,row.fingerprint,row.competition_id);calls=[]
    def get(url):calls.append(url);return SimpleNamespace(ok=True,payload=native if 'matchDetails' in url else table)
    fetched=_fetch_fotmob_dynamic_standings(db,cid,getter=get)
    assert [r['team'] for r in fetched['rows']]==['Alpha','Beta']
    assert fetched['season']=='2026' and fetched['source_parent_id']=='900' and fetched['source_leaf_id']=='9001'
    assert all(r['points']==r['played']==0 and r.get('logo') for r in fetched['rows'])
    assert calls[-1].endswith('id=900')
    assert (row.extra_json,row.score_json,row.fingerprint,row.competition_id)==before

@pytest.mark.parametrize('wrong',['match','home','kickoff','league','parent','table-group','members'])
def test_table_identity_refuses_namesakes_wrong_group_and_wrong_season_evidence(db,wrong):
    cid,row,native,table=add_case(db)
    if wrong=='match':native['general']['matchId']='102'
    if wrong=='home':native['general']['homeTeam']['name']='Gamma'
    if wrong=='kickoff':native['general']['matchTimeUTCDate']=(datetime.utcnow()-timedelta(days=1)).isoformat()
    if wrong=='league':native['general']['leagueId']=5555
    if wrong=='parent':table['details']['id']=5555
    if wrong=='table-group':table['table'][0]['data']['tables'][0]['leagueId']=9999
    if wrong=='members':table['table'][0]['data']['tables'][0]['table']['all'][0]['id']=9999
    def get(url):return SimpleNamespace(ok=True,payload=native if 'matchDetails' in url else (table if url.endswith('id=900') else None))
    assert _fetch_fotmob_dynamic_standings(db,cid,getter=get)=={}

def test_stored_parent_context_avoids_an_extra_match_detail_request(db):
    cid,row,native,table=add_case(db);meta=load_json(row.extra_json);meta.update(source_group_id='9001',source_parent_competition_id='900');row.extra_json=dump_json(meta);db.commit();calls=[]
    def get(url):calls.append(url);return SimpleNamespace(ok=True,payload=table)
    assert len(_fetch_fotmob_dynamic_standings(db,cid,getter=get)['rows'])==2
    assert len(calls)==1 and 'leagues?id=900' in calls[0]


def test_seconds_update_is_prioritized_but_hidden_conflict_cooldown_is_unchanged():
    from collector.football_board_priority import priority_plan, changed_result_signature
    from tests.test_football_board_priority import candidate
    now=datetime.utcnow();raw,row=candidate(now=now,stored='live',actual=(0,0),upstream='live')
    raw['status']['liveTime']={'short':'11\u200e’\u200e','long':'10:28'}
    row.score_json=dump_json({'home':0,'away':0,'minute':'11\u200e’\u200e','clock':'10:04'})
    assert '900' in priority_plan({'900':raw},{'900':[row]},{},now,100)
    row.display_eligible=False;a=changed_result_signature(raw,[row],now)
    raw['status']['liveTime']['long']='10:40'
    assert changed_result_signature(raw,[row],now)==a

@pytest.mark.parametrize('status,clock,expected', [('live','10:28','10:28'),('live','10:88',None),('live','garbage',None),('finished','10:28',None),('scheduled','10:28',None)])
def test_only_valid_running_source_seconds_become_public_clock(status,clock,expected):
    from collector.adapters_fotmob import match_to_event
    raw={'id':1,'home':{'name':'Alpha'},'away':{'name':'Beta'},'status':{'started':status!='scheduled','finished':status=='finished','liveTime':{'long':clock}}}
    assert match_to_event(raw,'test')['score'].get('clock')==expected


def test_competition_table_view_selects_season_without_changing_any_match(db,monkeypatch):
    from collector.standings_enrich import standings_view
    from collector.models import SportsStandingSnapshot
    cid,row,native,table=add_case(db)
    for season,team in [('2025','Previous Team'),('2026','Current Team')]:
        db.add(SportsStandingSnapshot(competition_id=cid,sport_id='football',season=season,captured_at=datetime.utcnow(),rows_json=dump_json({'sport':'football','rows':[{'team':team,'points':3}]})))
    db.commit()
    monkeypatch.setattr('collector.standings_enrich.load_standings',lambda *_:None)
    old=standings_view(db,cid,'2025');assert old['rows'][0]['team']=='Previous Team'
    assert old['competition']['id']==cid and old['season']=='2025' and old['seasons']==['2026','2025']
    assert standings_view(db,cid,'1999')['rows']==[]
    assert standings_view(db,cid)['rows'][0]['team']=='Current Team'
    assert row.status=='live' and row.fingerprint=='stable'


def test_current_enrichment_never_runs_without_the_existing_owner(db,monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football
    monkeypatch.setattr('collector.football_enrichment_cycle.writes_enabled',lambda:True)
    assert warm_current_football(db,owner='wrong')['skipped']=='not_scheduler_owner'


def test_current_enrichment_preserves_results_and_progress_after_restart(db,monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football, JOB_KEY
    from collector.lock import acquire_scheduler_lock
    from collector.models import SportsCollectorJob
    cid,row,native,table=add_case(db)
    monkeypatch.setattr('collector.football_enrichment_cycle.writes_enabled',lambda:True)
    monkeypatch.setattr('collector.provider._blocked_public_sources',lambda _: (set(),set()))
    monkeypatch.setattr('collector.provider._row_public_source_allowed',lambda *_:True)
    calls=[]
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda db,row,**kw:calls.append(('detail',row.event_id)))
    monkeypatch.setattr('collector.standings_enrich.load_standings',lambda db,cid,**kw:calls.append(('table',cid)) or [{'team':'Alpha'}])
    acquire_scheduler_lock(db,owner='owner');db.commit()
    before=(row.event_id,row.score_json,row.fingerprint,row.canonical_event_id,row.display_eligible)
    result=warm_current_football(db,owner='owner');db.commit()
    assert result['detail_attempts']==1 and result['table_rows']==1
    assert warm_current_football(db,owner='owner')['skipped']=='not_due'
    job=db.get(SportsCollectorJob,JOB_KEY);job.last_run_at-=timedelta(seconds=31);db.commit()
    warm_current_football(db,owner='owner');db.commit()
    assert load_json(job.last_error)['cycle']==2
    assert load_json(job.last_error)['after_competition']==cid
    assert (row.event_id,row.score_json,row.fingerprint,row.canonical_event_id,row.display_eligible)==before
