"""All source-native football identities, not a hard-coded Nations League subset."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
from collector.adapters import FetchResult
from collector.adapters_fotmob import _BOARD, _BOARD_AT, match_to_event
from collector.football_board_refresh import (consume_board_match, refresh_day, _identity_index,
    run_football_board_refresh, rolling_dates, JOB_PREFIX)
from collector.models import SportsEvent, SportsSource, SportsSourceCompetition, SportsCollectorJob
from collector.util import dump_json, load_json, isoformat
from database import SessionLocal

RECORDED=json.loads((Path(__file__).parent/'fixtures/fotmob_all_competitions_20260925.json').read_text())['matches']

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('RESULTS_COLLECTION_ENABLED','true')
    monkeypatch.setenv('RESULTS_WRITE_ENABLED','true')
    monkeypatch.setenv('RESULTS_SCHEDULER_ENABLED','true')
    _BOARD.clear();_BOARD_AT.clear()
    from collector.http import reset_http_stats
    reset_http_stats()
    db=SessionLocal()
    source=SportsSource(source_id='fotmob-global',display_name='FotMob',kind='test',adapter_key='fotmob',enabled=True,
        upstream_family='fotmob',capabilities_json=dump_json({'fixtures':True,'results':True,'live_scores':True}))
    db.add(source);db.commit()
    yield db,source
    db.close();_BOARD.clear();_BOARD_AT.clear();reset_http_stats()


def fresh(raw):
    raw=deepcopy(raw)
    raw['_source_fetched_at']=isoformat(datetime.utcnow())
    return raw

@pytest.mark.parametrize('recorded',RECORDED,ids=lambda x:str(x['_league'].get('name'))+'-'+str(x['id']))
def test_every_recorded_league_ingests_and_keeps_stable_identity(setup,recorded):
    db,source=setup;raw=fresh(recorded)
    expected=match_to_event(raw,'test')
    out=consume_board_match(db,raw,source,{})
    db.commit()
    assert not out.get('rejected'),out
    row=db.query(SportsEvent).one()
    original_id=row.event_id
    assert row.status==expected['status'] or (expected['status']=='live' and row.status in ('live','halftime','break'))
    for side in ('home','away'):
        assert (load_json(row.score_json)or{}).get(side)==expected['score'][side]
    mapping=db.query(SportsSourceCompetition).filter_by(competition_id=row.competition_id,source_id=source.source_id).one()
    assert str(raw['_league']['id']) in load_json(mapping.source_config_json)['fotmob_league_ids']
    consume_board_match(db,raw,source,{str(raw['id']):[row]});db.commit()
    assert db.query(SportsEvent).count()==1 and row.event_id==original_id


def board(raws):
    return {'leagues':[dict(r['_league'],matches=[{k:v for k,v in r.items() if not k.startswith('_')}]) for r in raws]}


def test_cursor_resumes_after_reopened_session_and_new_league_is_not_starved(setup):
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    raws=[fresh(x) for x in RECORDED[:3]]
    for r in raws:r['status']['utcTime']=isoformat(now-timedelta(hours=1))
    getter=lambda _:FetchResult(ok=True,http_status=200,payload=board(raws),fetched_at=isoformat(now))
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=1)
    db.commit();assert result['processed']==1 and not result['complete']
    checkpoint=load_json(db.get(SportsCollectorJob,JOB_PREFIX+day).last_error)['after_id']
    assert checkpoint
    with SessionLocal() as second:
        result=refresh_day(second,day,second.get(SportsSource,'fotmob-global'),now=now,getter=getter,max_events=10)
        second.commit();assert result['processed']==2 and result['complete']
        assert second.query(SportsEvent).count()==3
        assert load_json(second.get(SportsCollectorJob,JOB_PREFIX+day).last_error)['after_id']==''


def test_failed_board_keeps_cursor_and_does_not_acknowledge_empty_success(setup):
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    job=SportsCollectorJob(job_key=JOB_PREFIX+day,last_error=dump_json({'after_id':'123'}))
    db.add(job);db.commit()
    result=refresh_day(db,day,source,now=now,getter=lambda _:FetchResult(ok=False,http_status=503,error='source unavailable'))
    db.commit()
    assert not result['complete'] and result.get('error')
    assert load_json(job.last_error)['after_id']=='123'
    assert job.last_status=='failed'
    assert db.query(SportsEvent).count()==0


def test_db_failure_does_not_advance_past_failed_observation(setup,monkeypatch):
    import collector.football_board_refresh as mod
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    monkeypatch.setattr(mod,'consume_board_match',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('db failed')))
    result=refresh_day(db,day,source,now=now,getter=lambda _:FetchResult(ok=True,http_status=200,payload=board([RECORDED[0]])))
    db.commit();state=load_json(db.get(SportsCollectorJob,JOB_PREFIX+day).last_error)
    assert not result['complete'] and state['after_id']=='' and not state.get('last_success_at')


@pytest.mark.parametrize('policy',[{'manual_hidden':True},{'do_not_restore':True},{'collapse_role':'observation_only'}])
def test_global_result_refresh_never_resurrects_policy_blocked_rows(setup,policy):
    db,source=setup;raw=fresh(RECORDED[0]);consume_board_match(db,raw,source,{});db.commit()
    row=db.query(SportsEvent).one();original=load_json(row.extra_json)
    row.extra_json=dump_json({**original,**policy,'display_eligible':False});row.display_eligible=False;db.commit()
    out=consume_board_match(db,raw,source,{str(raw['id']):[row]});db.commit()
    assert out['reason']=='visibility_policy' and row.display_eligible is False


def test_original_retired_link_stays_retired_while_keeper_updates(setup):
    db,source=setup;raw=fresh(RECORDED[0]);consume_board_match(db,raw,source,{});db.commit()
    root=db.query(SportsEvent).one()
    child=SportsEvent(event_id='old-link',fingerprint='old-link',event_family='team_match',sport_id='football',
        competition_id=root.competition_id,start_time=root.start_time,participants_json=root.participants_json,
        canonical_event_id=root.event_id,display_eligible=False,extra_json=dump_json({'canonical_event_id':root.event_id,'collapse_role':'observation_only'}))
    db.add(child);db.commit()
    out=consume_board_match(db,raw,source,{str(raw['id']):[child,root]});db.commit()
    assert not out.get('rejected') and db.query(SportsEvent).count()==2
    assert child.canonical_event_id==root.event_id and child.display_eligible is False


def test_no_new_scheduler_or_unowned_write(setup):
    db,_=setup
    assert run_football_board_refresh(db,owner='not-owner')['skipped']=='not_scheduler_owner'
    assert db.query(SportsEvent).count()==0


def test_rolling_window_advances_after_midnight_instead_of_being_frozen_to_saved_dates():
    first=datetime(2026,9,25,23,59);next_day=first+timedelta(minutes=2)
    a,b=rolling_dates(first);c,d=rolling_dates(next_day)
    assert a==['20260925','20260924'] and c==['20260926','20260925']
    assert len(set(a+b))==11 and len(set(c+d))==11
    assert '20260929' in d and '20260918' not in c+d


def test_correct_group_badge_replaces_only_same_node_group_url():
    from collector.fotmob_crosswalk import _corrected_competition_logo
    prefix='https://images.fotmob.com/image_resources/logo/leaguelogo/'
    parsed={'competition_logo':prefix+'533.png','source_badge_group_id':'943368','source_badge_parent_id':'533'}
    assert _corrected_competition_logo(prefix+'943368.png',parsed)==prefix+'533.png'
    assert _corrected_competition_logo('https://official.example/logo.png',parsed)=='https://official.example/logo.png'
    assert _corrected_competition_logo(prefix+'99999.png',parsed)==prefix+'99999.png'

@pytest.mark.parametrize('change',['wrong-sport','wrong-target','wrong-source-id','wrong-country','wrong-source-name','wrong-context-country'])
def test_positive_source_context_never_authorizes_a_contradictory_mapping(change):
    from collector.competition_identity import event_accepted_for_mapping
    raw=fresh(next(x for x in RECORDED if x['_league'].get('id')==47))
    parsed=match_to_event(raw,'england-premier-league');target='england-premier-league'
    if change=='wrong-sport':parsed['sport']='basketball'
    if change=='wrong-target':target='france-ligue-1'
    if change=='wrong-source-id':parsed['source_competition_id']='53'
    if change=='wrong-country':parsed['country_id']='FRA'
    if change=='wrong-source-name':parsed['source_competition_name']='Ligue 1'
    if change=='wrong-context-country':parsed['source_competition_context']['ccode']='CHN'
    assert not event_accepted_for_mapping(parsed,target)[0]


def test_identically_named_domestic_cups_keep_their_country():
    from collector.fotmob_crosswalk import _fotmob_competition_identity
    from collector.competition_identity import correct_public_competition_id
    cid,*_= _fotmob_competition_identity({'_league':{'id':999555,'name':'FA Cup','ccode':'CHN'}})
    assert cid=='football-chn-fa-cup'
    assert correct_public_competition_id(stored_competition_id=cid,source_competition_name='FA Cup',sport_id='football',source_family='fotmob')==cid


def test_full_lifecycle_preserves_score_identity_and_never_reverts_final(setup):
    db,source=setup;raw=fresh(RECORDED[0]);raw['status']['utcTime']=isoformat(datetime.utcnow()-timedelta(minutes=70))
    original_id=None
    for index,(status,score) in enumerate([('scheduled',(0,0)),('live',(1,0)),('halftime',(1,1)),('finished',(2,1)),('scheduled',(0,0))]):
        raw['_source_fetched_at']=isoformat(datetime.utcnow()+timedelta(seconds=index))
        raw['status'].update(started=status!='scheduled',finished=status=='finished',reason={'short':'HT' if status=='halftime' else 'FT' if status=='finished' else ''},scoreStr=f'{score[0]}-{score[1]}')
        raw['home']['score'],raw['away']['score']=score
        existing=db.query(SportsEvent).first()
        result=consume_board_match(db,raw,source,{str(raw['id']):[existing]} if existing else {});db.commit()
        assert not result.get('rejected')
        row=db.query(SportsEvent).one();original_id=original_id or row.event_id
        assert row.event_id==original_id
        if index==0:assert load_json(row.score_json)['home'] is None and row.status=='scheduled'
        if index==1:assert row.status=='live' and load_json(row.score_json)['home']==1
        if index==2:assert row.status in ('halftime','break')
        if index>=3:assert row.status=='finished' and load_json(row.score_json)['home']==2
