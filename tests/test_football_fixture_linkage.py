"""Exact punctuation and source-backed fixture lineage, without ID rehashing."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from collector.football_board_refresh import consume_board_match, _identity_index
from collector.models import SportsEvent, SportsEventObservation
from collector.participant_alias import names_equivalent
from collector.participant_text import fold_for_identity
from collector.public_keeper import public_keeper_for_alias
from collector.util import dump_json, load_json, isoformat
from tests.test_football_global_refresh import setup, fresh, RECORDED
from tests.test_football_collision_routing import collision_case

@pytest.mark.parametrize('left,right',[("St. Patrick's Athletic","St Patrick's Athletic"),
                                     ('St. Mirren','St Mirren'),('St. Pauli','St Pauli')])
def test_punctuation_is_equivalent_without_changing_historical_fingerprints(left,right):
    assert names_equivalent(left,right)
    # This pass must not globally change old deterministic event fingerprints.
    assert fold_for_identity('St Mirren') == 'mirren'
    assert fold_for_identity('St. Mirren') == 'st mirren'

@pytest.mark.parametrize('left,right',[("St. Patrick's Athletic","Patrick's Athletic"),
                                     ('St. Mirren Women','St Mirren'),('St. Pauli II','St Pauli')])
def test_punctuation_does_not_drop_identity_qualifiers(left,right):
    assert not names_equivalent(left,right)


def duplicate_case(db,source):
    raw=fresh(next(r for r in RECORDED if str(r['_league'].get('primaryId') or r['_league'].get('id'))=='126'))
    raw['home']['name']='Sligo Rovers';raw['away']['name']="St. Patrick's Athletic"
    raw['status']['utcTime']=isoformat(datetime.utcnow()-timedelta(hours=2))
    raw['status'].update(started=True,finished=True,scoreStr='0-1')
    raw['home']['score']=0;raw['away']['score']=1
    consume_board_match(db,raw,source,{});db.commit()
    keeper=db.query(SportsEvent).one()
    parts=load_json(keeper.participants_json);parts['away']['name']="St Patrick's Athletic"
    legacy=SportsEvent(event_id='legacy-punctuation-link',fingerprint='legacy-punctuation-fingerprint',
        sport_id=keeper.sport_id,competition_id=keeper.competition_id,event_family='team_match',
        start_time=keeper.start_time,status='scheduled',participants_json=dump_json(parts),
        score_json=dump_json({'home':None,'away':None}),display_eligible=True,
        extra_json=dump_json({'display_eligible':True,'source_family':'old-fixtures',
                             'source_event_ids':{'old-fixtures':'legacy-123'}}))
    db.add(legacy);db.commit();db.info.clear()
    return raw,keeper,legacy


def test_source_refresh_persists_duplicate_link_not_just_list_filter(setup):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    for _ in range(2):
        out=consume_board_match(db,fresh(raw),source,_identity_index(db,datetime.utcnow().strftime('%Y%m%d')))
        db.commit();assert not out.get('rejected'),out
        assert db.query(SportsEvent).count()==2
        assert keeper.status=='finished' and load_json(keeper.score_json)['away']==1
        assert legacy.canonical_event_id==keeper.event_id and legacy.display_eligible is False
        assert public_keeper_for_alias(db,legacy).event_id==keeper.event_id
        assert legacy.event_id in load_json(keeper.extra_json)['collapsed_from']
        assert load_json(legacy.extra_json)['canonical_event_id']==keeper.event_id
        assert load_json(legacy.list_extra_json)['display_eligible'] is False


def test_indexed_reverse_link_does_not_block_source_before_write_resolver(setup):
    db,source=setup;raw,child,root=collision_case(db,source,mode='reverse')
    out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[child,root]});db.commit()
    assert not out.get('rejected'),out
    assert root.status=='finished' and load_json(root.score_json)['home']==2
    assert child.display_eligible is False and child.canonical_event_id is None


@pytest.mark.parametrize('unsafe',['other-id','other-time','other-comp','manual','slim-manual',
                                  'women','other-round','other-season','final-conflict','retired'])
def test_duplicate_linking_fails_closed_on_material_conflicts(setup,unsafe):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    meta=load_json(legacy.extra_json)
    if unsafe=='other-id':meta['source_event_ids']['fotmob']='other-real-id'
    if unsafe=='other-time':legacy.start_time+=timedelta(minutes=2)
    if unsafe=='other-comp':legacy.competition_id='other-league'
    if unsafe=='manual':meta['manual_hidden']=True
    if unsafe=='slim-manual':legacy.list_extra_json=dump_json({'manual_hidden':True})
    if unsafe=='women':
        p=load_json(legacy.participants_json);p['away']['name']+=' Women';legacy.participants_json=dump_json(p)
    if unsafe=='other-round':keeper.stage='Round A';legacy.stage='Round B'
    if unsafe=='other-season':keeper.season='2026';legacy.season='2025'
    if unsafe=='final-conflict':legacy.status='finished';legacy.score_json=dump_json({'home':3,'away':3})
    if unsafe=='retired':meta['collapse_role']='observation_only';legacy.display_eligible=False
    legacy.extra_json=dump_json(meta);db.commit()
    before=(legacy.event_id,legacy.score_json,legacy.canonical_event_id,legacy.display_eligible)
    out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    assert (legacy.event_id,legacy.score_json,legacy.canonical_event_id,legacy.display_eligible)==before
    assert not out.get('rejected'),out


def test_stale_source_cannot_consolidate_legacy_rows(setup):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    raw['_source_fetched_at']=isoformat(datetime.utcnow()-timedelta(hours=1))
    consume_board_match(db,raw,source,{str(raw['id']):[keeper]});db.commit()
    assert legacy.canonical_event_id is None and legacy.display_eligible


def test_multiple_independent_source_roots_use_stable_root_and_preserve_links(setup):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    meta=load_json(legacy.extra_json);meta['source_event_ids']['fotmob']=str(raw['id'])
    legacy.extra_json=dump_json(meta);db.commit()
    original=min(keeper.event_id,legacy.event_id)
    for order in ([legacy,keeper],[keeper,legacy]):
        out=consume_board_match(db,fresh(raw),source,{str(raw['id']):order});db.commit()
        assert not out.get('rejected'),out
        root=db.get(SportsEvent,original)
        assert root.canonical_event_id is None and root.status=='finished'
        assert db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).count()==1


def test_contradictory_index_pointer_does_not_choose_a_score_target(setup):
    db,source=setup;raw,child,root=collision_case(db,source,mode='forward')
    child.list_extra_json=dump_json({'canonical_event_id':'different-root'});db.commit()
    before=root.score_json
    out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[child,root]});db.commit()
    assert out.get('rejected') and root.score_json==before


def test_known_board_root_is_not_rematched_to_a_different_legacy_row(setup,monkeypatch):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    def wrong_rematch(*args,**kwargs):
        pytest.fail('Exact board keeper must be retained rather than rematched')
    monkeypatch.setattr('collector.collect.match_event',wrong_rematch)
    out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    assert not out.get('rejected') and legacy.canonical_event_id==keeper.event_id


def test_actual_public_old_link_uses_result_and_detail_of_verified_keeper(setup,monkeypatch):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda *_:None)
    monkeypatch.setattr('collector.provider._history_context',lambda *_:([],{}))
    from collector.provider import NinkoCollectedSportsDataProvider
    from database import SessionLocal
    payload=NinkoCollectedSportsDataProvider(session_factory=SessionLocal).get_event(legacy.event_id)
    assert payload['id']==keeper.event_id and payload['status']=='finished'
    assert payload['score']['home']==0 and payload['score']['away']==1


def retry_case(db, now):
    from collector.football_board_refresh import JOB_PREFIX,POLICY_REVISION
    from collector.models import SportsCollectorJob
    day=(now-timedelta(days=3)).strftime('%Y%m%d')
    job=SportsCollectorJob(job_key=JOB_PREFIX+day,last_status='partial',last_run_at=now,
        last_error=dump_json({'policy_revision':POLICY_REVISION,'after_id':'500',
            'next_due_at':isoformat(now+timedelta(hours=6)),
            'deferred':{'100':{'reason':'source_identity_conflict','attempts':2,
                               'last_seen_at':'2026-09-18T12:00:00Z'}}}))
    db.add(job);db.commit()
    return day,job


def test_retry_old_conflict_first_without_resetting_or_advancing_discovery_cursor(setup,monkeypatch):
    from collector.football_board_refresh import refresh_day,_select_day
    from collector.adapters import FetchResult
    from tests.test_football_global_refresh import board
    db,source=setup;now=datetime.utcnow();day,job=retry_case(db,now)
    assert _select_day(db,[day],now)[0]==day
    raws=[fresh(RECORDED[0]),fresh(RECORDED[1])];raws[0]['id']=100;raws[1]['id']=600
    seen=[]
    def consume(db,raw,*args):seen.append(str(raw['id']));return {'written':1}
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match',consume)
    getter=lambda _:FetchResult(ok=True,http_status=200,payload=board(raws),fetched_at=isoformat(now))
    first=refresh_day(db,day,source,now=now,getter=getter,max_events=1);db.commit()
    assert seen==['100'] and not first['complete']
    assert load_json(job.last_error)['after_id']=='500'
    second=refresh_day(db,day,source,now=now,getter=getter,max_events=1);db.commit()
    assert seen==['100','600'] and second['data_complete']


@pytest.mark.parametrize('mode',['absent','policy','source-failure'])
def test_one_time_upgrade_retry_preserves_unresolved_data_and_backoff(setup,monkeypatch,mode):
    from collector.football_board_refresh import refresh_day,_select_day
    from collector.football_fixture_linkage import LINKAGE_REVISION
    from collector.adapters import FetchResult
    from tests.test_football_global_refresh import board
    db,source=setup;now=datetime.utcnow();day,job=retry_case(db,now)
    raw=fresh(RECORDED[0]);raw['id']=600 if mode=='absent' else 100
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match',
                        lambda *_:{'rejected':1,'reason':'visibility_policy'} if mode=='policy' else {'written':1})
    getter=lambda _:FetchResult(ok=False,http_status=503,error='not reachable') if mode=='source-failure' else FetchResult(ok=True,http_status=200,payload=board([raw]),fetched_at=isoformat(now))
    result=refresh_day(db,day,source,now=now,getter=getter,max_events=5);db.commit()
    state=load_json(job.last_error);entry=state['deferred']['100']
    assert not result.get('data_complete')
    assert _select_day(db,[day],now) is None
    if mode=='source-failure':
        assert state['after_id']=='500' and entry.get('linkage_revision') is None
    else:
        assert entry['linkage_revision']==LINKAGE_REVISION
        if mode=='absent':
            assert entry['attempts']==2 and entry['last_seen_at']=='2026-09-18T12:00:00Z'
            assert entry['present_on_last_board'] is False
        else:assert entry['reason']=='visibility_policy' and entry['attempts']==3


@pytest.mark.parametrize('unsafe',['orientation','time','source-id','manual'])
def test_verified_write_target_cannot_override_material_identity_guards(setup,unsafe):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    from collector.collect import _consume_result
    from collector.models import SportsSourceCompetition,SportsCompetition
    from collector.adapters_fotmob import match_to_event
    from collector.adapters import FetchResult
    target=legacy
    meta=load_json(target.extra_json)
    if unsafe=='orientation':
        p=load_json(target.participants_json);p['home'],p['away']=p['away'],p['home'];target.participants_json=dump_json(p)
    if unsafe=='time':target.start_time+=timedelta(hours=1)
    if unsafe=='source-id':meta['source_event_ids']['fotmob']='another-fixture'
    if unsafe=='manual':meta['manual_hidden']=True
    target.extra_json=dump_json(meta);db.commit();before=target.score_json
    parsed=match_to_event(fresh(raw),keeper.competition_id)
    parsed.update(sport='football',competition_key=keeper.competition_id,source_family='fotmob')
    mapping=db.query(SportsSourceCompetition).filter_by(source_id=source.source_id,competition_id=keeper.competition_id).one()
    out=_consume_result(db,source=source,mapping=mapping,competition=db.get(SportsCompetition,keeper.competition_id),
        capability='results',result=FetchResult(ok=True,http_status=200,events=[parsed]),verified_target_id=target.event_id)
    db.commit();assert out['identity_conflicts']==1 and target.score_json==before


def test_duplicate_with_unrecorded_child_tree_is_not_reparented(setup):
    db,source=setup;raw,keeper,legacy=duplicate_case(db,source)
    child=SportsEvent(event_id='older-child',fingerprint='older-child',event_family='team_match',
        sport_id=legacy.sport_id,competition_id=legacy.competition_id,start_time=legacy.start_time,
        participants_json=legacy.participants_json,canonical_event_id=legacy.event_id,display_eligible=False)
    db.add(child);db.commit()
    consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    assert child.canonical_event_id==legacy.event_id and legacy.canonical_event_id is None
