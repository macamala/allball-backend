"""Legacy league repairs preserve the same fixture and old links, not score hacks."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from tests.test_football_global_refresh import setup, fresh, RECORDED
from collector.football_board_refresh import consume_board_match
from collector.fotmob_crosswalk import _fotmob_competition_identity
from collector.integrity import _fingerprint_for
from collector.models import SportsCompetition, SportsEvent, SportsSourceCompetition
from collector.util import dump_json, load_json, isoformat


def historical_case(db, source, *, country='THA', name='FA Cup - 1st Round', league=1000001670):
    raw=fresh(RECORDED[0])
    raw['_league']={'id':league,'primaryId':league,'name':name,'ccode':country}
    raw['status'].update(started=True,finished=True,scoreStr='2-1')
    raw['home']['score']=2;raw['away']['score']=1
    out=consume_board_match(db,raw,source,{});db.commit();assert not out.get('rejected'),out
    root=db.query(SportsEvent).one();correct=root.competition_id
    if not db.get(SportsCompetition,'fa-cup'):
        db.add(SportsCompetition(competition_id='fa-cup',sport_id='football',name='FA Cup',slug='fa-cup',event_model='team_match'))
    extra=load_json(root.extra_json)
    extra.update({'public_competition_key':'fa-cup','canonical_competition_id':'fa-cup','collapsed_from':['legacy-alias']})
    root.extra_json=dump_json(extra);root.competition_id='fa-cup';root.fingerprint=_fingerprint_for(root,'fa-cup')
    root.status='scheduled';root.score_json=dump_json({'home':None,'away':None})
    child=SportsEvent(event_id='legacy-alias',fingerprint='legacy-alias',event_family='team_match',sport_id='football',competition_id='fa-cup',
        start_time=root.start_time,participants_json=root.participants_json,canonical_event_id=root.event_id,display_eligible=False,
        extra_json=dump_json({'canonical_event_id':root.event_id,'collapse_role':'observation_only'}))
    db.add(child);db.commit()
    return raw,root,child,correct


@pytest.mark.parametrize('country,name,league',[('THA','FA Cup - 1st Round',1000001670),('SVK','FA Cup',177),('CHN','FA Cup',131)])
def test_wrong_country_cup_corrected_in_place_through_normal_result_ingestion(setup,country,name,league):
    db,source=setup;raw,root,child,target=historical_case(db,source,country=country,name=name,league=league)
    eid=root.event_id
    for _ in range(2):
        out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[root]});db.commit()
        assert not out.get('rejected'),out
        assert root.competition_id==target and root.event_id==eid
        assert db.query(SportsEvent).count()==2
        assert root.status=='finished' and load_json(root.score_json)=={'home':2,'away':1}
        assert child.canonical_event_id==eid and child.display_eligible is False
    extra=load_json(root.extra_json)
    assert len(extra['competition_identity_repairs'])==1
    assert extra['public_competition_key']==target
    assert load_json(root.list_extra_json)['public_competition_key']==target
    assert root.fingerprint==_fingerprint_for(root,target)


@pytest.mark.parametrize('change',['no-fetch','stale-fetch','future-fetch','wrong-source-id','manual-hidden','wrong-kickoff','wrong-home','disabled-target','collision'])
def test_legacy_repair_fails_closed_without_full_proof(setup,change):
    db,source=setup;raw,root,child,target=historical_case(db,source)
    if change=='no-fetch':raw.pop('_source_fetched_at',None)
    if change=='stale-fetch':raw['_source_fetched_at']=isoformat(datetime.utcnow()-timedelta(hours=1))
    if change=='future-fetch':raw['_source_fetched_at']=isoformat(datetime.utcnow()+timedelta(hours=1))
    if change=='wrong-source-id':raw['id']='unmapped-id'
    if change=='manual-hidden':root.extra_json=dump_json({**load_json(root.extra_json),'manual_hidden':True});root.display_eligible=False
    if change=='wrong-kickoff':raw['status']['utcTime']=isoformat(root.start_time+timedelta(hours=1))
    if change=='wrong-home':raw['home']['name']='Another team'
    if change=='disabled-target':db.query(SportsSourceCompetition).filter_by(competition_id=target,source_id=source.source_id).one().enabled=False
    if change=='collision':db.add(SportsEvent(event_id='other-root',fingerprint=_fingerprint_for(root,target),sport_id='football',competition_id=target,event_family='team_match',display_eligible=True))
    db.commit();before=(root.competition_id,root.fingerprint,root.score_json,child.canonical_event_id)
    out=consume_board_match(db,raw,source,{str(raw['id']):[root]});db.commit()
    assert out.get('rejected'),out
    assert (root.competition_id,root.fingerprint,root.score_json,child.canonical_event_id)==before
    assert not load_json(root.extra_json).get('competition_identity_repairs')


@pytest.mark.parametrize('league,primary,name,country,expected',[(126,126,'Premier Division','IRL','ireland-premier-division'),(937650,64,'Premiership','SCO','scotland-premiership')])
def test_verified_domestic_leagues_keep_existing_canonical_ids(league,primary,name,country,expected):
    assert _fotmob_competition_identity({'_league':{'id':league,'primaryId':primary,'parentLeagueId':primary,'name':name,'ccode':country}})[0]==expected


def test_source_native_group_name_drift_preserves_event_and_alias(setup):
    db,source=setup
    raw,root,child,_=historical_case(db,source,country='INT',name='FIFA ASEAN Cup Challenge Division Grp. A',league=943311)
    root.competition_id='football-asean-cup-challenge-division-grp-a'
    root.fingerprint=_fingerprint_for(root,root.competition_id);db.commit()
    out=consume_board_match(db,raw,source,{str(raw['id']):[root]});db.commit()
    assert not out.get('rejected'),out
    assert root.competition_id=='football-fifa-asean-cup-challenge-division-grp-a'
    assert child.canonical_event_id==root.event_id and child.display_eligible is False
    assert root.status=='finished'


def test_partial_historical_cursor_is_revalidated_after_identity_policy_revision(setup):
    from collector.football_board_refresh import _select_day, refresh_day, JOB_PREFIX, POLICY_REVISION
    from collector.models import SportsCollectorJob
    from collector.adapters import FetchResult
    from tests.test_football_global_refresh import board
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    raw=fresh(RECORDED[0]);raw['status']['utcTime']=isoformat(now-timedelta(hours=1))
    db.add(SportsCollectorJob(job_key=JOB_PREFIX+day,last_run_at=now,last_error=dump_json({'policy_revision':1,'after_id':'999999999999','complete':True,'next_due_at':isoformat(now+timedelta(hours=6))})));db.commit()
    assert _select_day(db,[day],now) is not None
    result=refresh_day(db,day,source,now=now,getter=lambda _:FetchResult(ok=True,http_status=200,payload=board([raw]),fetched_at=isoformat(now)))
    db.commit();assert result['processed']==1 and result['complete']
    assert load_json(db.get(SportsCollectorJob,JOB_PREFIX+day).last_error)['policy_revision']==POLICY_REVISION
    assert db.query(SportsEvent).count()==1


@pytest.mark.parametrize('physical_change',['status','score'])
def test_cached_observation_signature_cannot_hide_changed_canonical_state(setup,physical_change):
    from collector.dirty import event_unchanged
    from collector.adapters_fotmob import match_to_event
    db,source=setup;raw=fresh(RECORDED[0]);raw['status'].update(started=True,finished=True,scoreStr='2-1')
    raw['home']['score']=2;raw['away']['score']=1
    consume_board_match(db,raw,source,{});db.commit();row=db.query(SportsEvent).one()
    # Reconstruct the stored signature itself to isolate the state safeguard.
    incoming=load_json(load_json(row.extra_json)['obs_signature'])
    incoming['home']={'name':incoming['home']}
    incoming['away']={'name':incoming['away']}
    assert event_unchanged(row,incoming)
    if physical_change=='status':row.status='stale'
    else:row.score_json=dump_json({'home':1,'away':1})
    db.commit();assert not event_unchanged(row,incoming)
    raw['_source_fetched_at']=isoformat(datetime.utcnow()+timedelta(seconds=2))
    consume_board_match(db,raw,source,{str(raw['id']):[row]});db.commit()
    assert row.status=='finished' and load_json(row.score_json)['home']==2


def test_terminal_reconciliation_does_not_restore_older_cached_score_after_fresh_merge():
    from collector.live_state import reconcile_live_status
    now=datetime.utcnow();old={'status':'finished','sport':'football','source_family':'fotmob','score':{'home':1,'away':1},'source_fetch_time':isoformat(now-timedelta(minutes=3))}
    new={**old,'score':{'home':2,'away':1},'source_fetch_time':isoformat(now)}
    assert reconcile_live_status(new,counterparts=[old,new])['score']==new['score']
    assert reconcile_live_status(new,counterparts=[old])['score']==new['score']
