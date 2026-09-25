"""A retired deterministic ID must not block the rest of a football date."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from collector.adapters import FetchResult
from collector.football_board_refresh import consume_board_match, refresh_day, JOB_PREFIX
from collector.models import SportsEvent, SportsCollectorJob, SportsEventObservation
from collector.util import dump_json, load_json, isoformat
from database import SessionLocal
from tests.test_football_global_refresh import setup, fresh, RECORDED, board


def collision_case(db, source, *, mode='reverse', manual=False):
    raw=fresh(RECORDED[0]);raw['status']['utcTime']=isoformat(datetime.utcnow()-timedelta(hours=1))
    raw['status'].update(started=True,finished=True,scoreStr='2-1')
    raw['home']['score']=2;raw['away']['score']=1
    consume_board_match(db,raw,source,{});db.commit()
    child=db.query(SportsEvent).one();old_id=child.event_id
    # Historical canonical collapse can change the stored fingerprint while an
    # immutable public ID and a reverse collapsed_from link remain in use.
    child.fingerprint='historical-fingerprint'
    child.stage='historical-round'
    meta=load_json(child.extra_json)
    meta.pop('source_event_ids',None);meta.pop('source_event_id',None)
    meta['display_eligible']=False;meta['collapse_role']='observation_only'
    child.extra_json=dump_json(meta);child.display_eligible=False
    if mode=='dangling':
        child.canonical_event_id='not-present'
        root=None
    else:
        root=SportsEvent(event_id='verified-root',fingerprint='verified-root',sport_id=child.sport_id,
            competition_id=child.competition_id,event_family=child.event_family,
            start_time=child.start_time,status='scheduled',stage='different-stage-label',
            participants_json=child.participants_json,score_json=dump_json({'home':None,'away':None}),
            display_eligible=True,extra_json=dump_json({'display_eligible':True,'collapsed_from':[old_id],**({'manual_hidden':True} if manual else {})}))
        db.add(root)
        if mode=='forward':child.canonical_event_id=root.event_id
    # Old mappings can be absent or be rejected because their child spelling
    # has changed. No test bypasses the production identity/score pipeline.
    from collector.models import SportsIdMap
    db.query(SportsIdMap).filter(SportsIdMap.entity_kind=='event').delete(synchronize_session=False)
    db.info.clear();db.commit()
    return raw,child,root


@pytest.mark.parametrize('mode',['reverse','forward'])
def test_occupied_retired_id_routes_to_proven_keeper_without_new_row(setup,mode):
    db,source=setup;raw,child,root=collision_case(db,source,mode=mode)
    before_child=(child.event_id,child.canonical_event_id,child.display_eligible,child.score_json)
    for _ in range(2):
        outcome=consume_board_match(db,fresh(raw),source,{})
        db.commit()
        assert not outcome.get('rejected'),outcome
        assert db.query(SportsEvent).count()==2
        assert root.status=='finished' and load_json(root.score_json)['home']==2
        assert (child.event_id,child.canonical_event_id,child.display_eligible,child.score_json)==before_child
        assert db.query(SportsEventObservation).order_by(SportsEventObservation.id.desc()).first().event_id==root.event_id


def test_unresolved_collision_does_not_block_later_matches_and_is_retained_for_retry(setup):
    db,source=setup;raw,child,_=collision_case(db,source,mode='dangling')
    raw['id']=1000001
    other=fresh(RECORDED[1]);other['id']=9000001
    now=datetime.utcnow();day=now.strftime('%Y%m%d')
    other['status']['utcTime']=isoformat(now-timedelta(hours=1))
    getter=lambda _:FetchResult(ok=True,http_status=200,payload=board([raw,other]),fetched_at=isoformat(now))
    out=refresh_day(db,day,source,now=now,getter=getter,max_events=10,budget_seconds=20)
    db.commit()
    assert out['processed']==2 and out['written']==1 and out['rejected']==1,out
    assert out['complete'] and not out['data_complete']
    assert db.query(SportsEvent).count()==2
    state=load_json(db.get(SportsCollectorJob,JOB_PREFIX+day).last_error)
    assert state['deferred']['1000001']['reason']=='event_identity_conflict'
    assert db.get(SportsCollectorJob,JOB_PREFIX+day).last_status=='partial'
    with SessionLocal() as reopened:
        saved=load_json(reopened.get(SportsCollectorJob,JOB_PREFIX+day).last_error)
        assert saved['deferred']['1000001']['attempts']==1
        old=reopened.get(SportsEvent,child.event_id)
        assert old.canonical_event_id=='not-present' and old.display_eligible is False


@pytest.mark.parametrize('change',['manual','reversed','wrong-time','wrong-competition','ambiguous','cycle'])
def test_collision_never_guesses_unsafe_keeper(setup,change):
    db,source=setup;raw,child,root=collision_case(db,source)
    if change=='manual':root.extra_json=dump_json({'collapsed_from':[child.event_id],'manual_hidden':True})
    if change=='reversed':
        p=load_json(root.participants_json);p['home'],p['away']=p['away'],p['home'];root.participants_json=dump_json(p)
    if change=='wrong-time':root.start_time+=timedelta(hours=1)
    if change=='wrong-competition':root.competition_id='other'
    if change=='ambiguous':
        db.add(SportsEvent(event_id='second-root',fingerprint='second-root',event_family=root.event_family,
            sport_id=root.sport_id,competition_id=root.competition_id,start_time=root.start_time,
            participants_json=root.participants_json,extra_json=root.extra_json,display_eligible=True))
    if change=='cycle':child.canonical_event_id=root.event_id;root.canonical_event_id=child.event_id
    db.commit();before=[(r.event_id,r.score_json,r.canonical_event_id,r.display_eligible) for r in db.query(SportsEvent).order_by(SportsEvent.event_id)]
    out=consume_board_match(db,fresh(raw),source,{})
    db.commit()
    assert out.get('reason')=='event_identity_conflict',out
    assert [(r.event_id,r.score_json,r.canonical_event_id,r.display_eligible) for r in db.query(SportsEvent).order_by(SportsEvent.event_id)]==before


def test_resolved_deferred_match_is_retried_and_cleared_without_changing_id(setup):
    db,source=setup;raw,child,_=collision_case(db,source,mode='dangling')
    raw['id']=1000001;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    getter=lambda _:FetchResult(ok=True,http_status=200,payload=board([raw]),fetched_at=isoformat(now))
    result=refresh_day(db,day,source,now=now,getter=getter);db.commit()
    assert result['deferred_count']==1
    root=SportsEvent(event_id='not-present',fingerprint='now-restored-root',event_family=child.event_family,
        sport_id=child.sport_id,competition_id=child.competition_id,start_time=child.start_time,
        participants_json=child.participants_json,status='scheduled',display_eligible=True,
        score_json=dump_json({'home':None,'away':None}),extra_json=dump_json({'display_eligible':True,'collapsed_from':[child.event_id]}))
    db.add(root);db.commit()
    result=refresh_day(db,day,source,now=now,getter=getter);db.commit()
    assert result['data_complete'] and not result['deferred_count']
    assert root.event_id=='not-present' and root.status=='finished'
    assert child.canonical_event_id==root.event_id and child.display_eligible is False
    assert db.query(SportsEvent).count()==2


def test_retry_queue_full_never_acknowledges_an_unrecorded_conflict(setup,monkeypatch):
    import collector.football_board_refresh as mod
    db,source=setup;now=datetime.utcnow();day=now.strftime('%Y%m%d')
    monkeypatch.setattr(mod,'MAX_DEFERRED_IDENTITIES',0)
    monkeypatch.setattr(mod,'consume_board_match',lambda *_:{'rejected':1,'reason':'event_identity_conflict'})
    result=refresh_day(db,day,source,now=now,getter=lambda _:FetchResult(ok=True,http_status=200,payload=board([RECORDED[0]])))
    db.commit();state=load_json(db.get(SportsCollectorJob,JOB_PREFIX+day).last_error)
    assert not result['complete'] and state['after_id']==''
    assert state['error']=='deferred_identity_capacity_reached'


def test_rich_and_slim_pointer_disagreement_fails_closed(setup):
    db,source=setup;raw,child,root=collision_case(db,source,mode='dangling')
    child.list_extra_json=dump_json({'canonical_event_id':'different-parent'})
    db.commit();before=child.extra_json
    out=consume_board_match(db,fresh(raw),source,{})
    db.commit();assert out['reason']=='event_identity_conflict'
    assert child.extra_json==before and child.canonical_event_id=='not-present'


def test_actual_brazilian_provider_spelling_routes_only_with_saved_lineage(setup):
    db,source=setup;raw,child,root=collision_case(db,source,mode='forward')
    raw['home']['name']='Sao Paulo';raw['away']['name']='Internacional'
    child.participants_json=dump_json({'home':{'name':'Sao Paulo'},'away':{'name':'Internacional'}})
    root.participants_json=dump_json({'home':{'name':'São Paulo - SP'},'away':{'name':'Internacional -'}})
    db.commit()
    from collector.football_write_identity import football_write_target
    incoming={'sport':'football','competition_key':root.competition_id,'start_time':isoformat(root.start_time),
              'home':raw['home'],'away':raw['away'],'source_family':'fotmob','source_event_id':str(raw['id'])}
    assert football_write_target(db,incoming,child) is root
    # Labels alone are insufficient: no lineage, no permission to select root.
    child.canonical_event_id=None;db.flush()
    root.extra_json='{}';db.flush()
    from collector.football_write_identity import FootballIdentityConflict
    with pytest.raises(FootballIdentityConflict):football_write_target(db,incoming,child)


def test_nonfootball_match_resolution_is_unchanged(setup):
    from collector.football_write_identity import football_write_target
    db,_=setup;sentinel=object()
    assert football_write_target(db,{'sport':'tennis'},sentinel) is sentinel
