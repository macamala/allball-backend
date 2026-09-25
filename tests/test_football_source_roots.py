"""Current source proof reconciles duplicate roots, not arbitrary hidden rows."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from tests.test_football_global_refresh import setup, fresh, RECORDED
from collector.football_board_refresh import consume_board_match, _identity_index
from collector.football_source_roots import plan_source_roots
from collector.adapters_fotmob import match_to_event
from collector.models import SportsEvent, SportsCompetition, SportsEventDetail
from collector.list_extra import store_list_extra, extra_for_list
from collector.util import dump_json, load_json, isoformat


def split_case(db, source, *, domestic=False, fixture=False):
    raw=fresh(next(r for r in RECORDED if r['_league'].get('id')==943311))
    raw['status']['utcTime']=isoformat(datetime.utcnow()+timedelta(days=2) if fixture else datetime.utcnow()-timedelta(hours=2))
    if domestic:
        raw['_league']={'id':9227,'primaryId':9227,'parentLeagueId':None,'name':'WSL','ccode':'ENG','isGroup':False}
        raw['home']['name']='Brighton Women';raw['away']['name']='Everton Women'
    if fixture:
        raw['status'].update(started=False,finished=False,scoreStr='0 - 0',reason={})
        raw['home']['score']=raw['away']['score']=0
    assert not consume_board_match(db,raw,source,{}).get('rejected');db.commit()
    keeper=db.query(SportsEvent).one()
    old='football-eng-wsl' if domestic else keeper.competition_id.replace('football-fifa-','football-',1)
    db.add(SportsCompetition(competition_id=old,sport_id='football',name='Old source label',slug=old,event_model='team_match'))
    kmeta=load_json(keeper.extra_json)
    legacy=SportsEvent(event_id='legacy-source-root',fingerprint='legacy-source-root-fp',sport_id='football',
        competition_id=old,event_family='team_match',start_time=keeper.start_time,status='scheduled',
        participants_json=keeper.participants_json,score_json=dump_json({'home':None,'away':None}),
        display_eligible=True,extra_json=dump_json({**kmeta,'display_eligible':True}))
    kmeta.update(display_eligible=False,quality_flags=['duplicate_or_contaminated'])
    keeper.extra_json=dump_json(kmeta);keeper.display_eligible=False
    store_list_extra(keeper,kmeta);store_list_extra(legacy,load_json(legacy.extra_json))
    db.add(legacy);db.commit();db.info.clear()
    return raw,keeper,legacy


def index(raw, *rows): return {str(raw['id']):list(rows)}
def snap(db):
    return [(r.event_id,r.competition_id,r.status,r.score_json,r.display_eligible,r.canonical_event_id,r.extra_json,r.list_extra_json)
            for r in db.query(SportsEvent).order_by(SportsEvent.event_id)]


@pytest.mark.parametrize('domestic,fixture',[(False,False),(True,False),(True,True)])
def test_verified_same_leaf_roots_keep_current_identity_result_and_old_alias(setup,domestic,fixture):
    db,source=setup;raw,keeper,legacy=split_case(db,source,domestic=domestic,fixture=fixture)
    ids={keeper.event_id,legacy.event_id};fingerprints=(keeper.fingerprint,legacy.fingerprint)
    for _ in range(2):
        out=consume_board_match(db,fresh(raw),source,index(raw,legacy,keeper));db.commit()
        assert not out.get('rejected'),out
        assert keeper.display_eligible is True
        assert legacy.canonical_event_id==keeper.event_id and legacy.display_eligible is False
        assert extra_for_list(keeper)['display_eligible'] is True
        assert extra_for_list(legacy)['display_eligible'] is False
        assert (keeper.fingerprint,legacy.fingerprint)==fingerprints
        assert {r.event_id for r in db.query(SportsEvent)}==ids
        assert keeper.status==('scheduled' if fixture else 'finished')
        assert load_json(keeper.score_json)['home']==(None if fixture else 3)
        assert load_json(keeper.score_json)['away']==(None if fixture else 1)
    assert load_json(keeper.extra_json)['source_root_proofs'][-1]['source_leaf_id']==str(raw['_league']['id'])


def test_hidden_roots_with_same_event_proof_recover_without_fabricating_result(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    legacy.display_eligible=False
    e=load_json(legacy.extra_json);e['display_eligible']=False;legacy.extra_json=dump_json(e);store_list_extra(legacy,e);db.commit()
    out=consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    assert not out.get('rejected') and keeper.display_eligible and legacy.canonical_event_id==keeper.event_id


def test_cross_label_alias_returns_actual_result_through_real_provider(setup,monkeypatch):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda *_:None)
    monkeypatch.setattr('collector.provider._history_context',lambda *_:([],{}))
    from collector.provider import NinkoCollectedSportsDataProvider
    from database import SessionLocal
    event=NinkoCollectedSportsDataProvider(session_factory=SessionLocal).get_event(legacy.event_id)
    assert event['id']==keeper.event_id and event['status']=='finished'
    assert (event['score']['home'],event['score']['away'])==(3,1)


@pytest.mark.parametrize('unsafe',['manual','slim-manual','do-not-restore','observation','wrong-source-id','wrong-group',
    'parent-not-leaf','other-team','reverse','other-kickoff','other-season','other-stage','finished-conflict',
    'other-provider-id','unknown-flag','slim-unknown-flag','unknown-quarantine','independent-tree','stale','future-finished',
    'known-domestic-conflict','no-current-key'])
def test_unsafe_root_sets_remain_unchanged(setup,unsafe):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    e=load_json(legacy.extra_json)
    if unsafe=='manual':e['manual_hidden']=True
    if unsafe=='do-not-restore':e['do_not_restore']=True
    if unsafe=='observation':e['collapse_role']='observation_only'
    if unsafe=='wrong-source-id':e['source_event_ids']={'fotmob':'other-match'}
    if unsafe=='wrong-group':e['source_group_id']='943313'
    if unsafe=='parent-not-leaf':e.pop('source_group_id',None);e['source_competition_id']='13287'
    if unsafe=='unknown-flag':e['quality_flags']=['unverified-participants']
    if unsafe=='unknown-quarantine':e['quarantine_disposition']='TRUE_GARBAGE'
    if unsafe=='independent-tree':e['collapsed_from']=['old-child']
    if unsafe=='other-season':keeper.season='2026';legacy.season='2025'
    if unsafe=='other-stage':keeper.stage='Group A';legacy.stage='Group B'
    if unsafe=='other-kickoff':legacy.start_time+=timedelta(minutes=10)
    if unsafe=='finished-conflict':legacy.status='finished';legacy.score_json=dump_json({'home':9,'away':9})
    if unsafe in ('other-team','reverse'):
        p=load_json(legacy.participants_json)
        if unsafe=='reverse':p['home'],p['away']=p['away'],p['home']
        else:p['away']['name']+=' Women'
        legacy.participants_json=dump_json(p)
    if unsafe=='other-provider-id':
        m=load_json(keeper.extra_json);m['source_event_ids']['fifa-digital']='left';keeper.extra_json=dump_json(m)
        e['source_event_ids']['fifa-digital']='right'
    if unsafe=='stale':raw['_source_fetched_at']=isoformat(datetime.utcnow()-timedelta(hours=1))
    if unsafe=='future-finished':raw['status']['utcTime']=isoformat(datetime.utcnow()+timedelta(days=1))
    if unsafe=='known-domestic-conflict':legacy.competition_id='england-premier-league'
    if unsafe=='no-current-key':keeper.competition_id='football-another-key'
    legacy.extra_json=dump_json(e);store_list_extra(legacy,e)
    if unsafe=='slim-manual':legacy.list_extra_json=dump_json({'manual_hidden':True})
    if unsafe=='slim-unknown-flag':legacy.list_extra_json=dump_json({'quality_flags':['unverified-participants']})
    db.commit();before=snap(db)
    out=consume_board_match(db,raw,source,index(raw,keeper,legacy));db.commit()
    assert out.get('rejected'),out
    assert snap(db)==before


def test_read_only_plan_does_not_mutate_score_visibility_or_fingerprint(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source);before=snap(db)
    event={**match_to_event(fresh(raw),keeper.competition_id),'competition_key':keeper.competition_id}
    plan=plan_source_roots(db,[keeper,legacy],event)
    assert plan and plan.keeper_id==keeper.event_id and snap(db)==before


def test_link_failure_rolls_back_accepted_score_and_visibility(setup,monkeypatch):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    keeper.status='scheduled';keeper.score_json=dump_json({'home':None,'away':None});db.commit();before=snap(db)
    monkeypatch.setattr('collector.canonical_collapse._collapse_pair',lambda *_:False)
    with pytest.raises(RuntimeError):
        consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy))
    db.commit();assert snap(db)==before


def test_policy_keeps_sequential_cursor_and_already_retired_source_aliases(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    old=legacy.canonical_event_id
    consume_board_match(db,fresh(raw),source,index(raw,legacy));db.commit()
    assert legacy.canonical_event_id==old and legacy.display_eligible is False


def test_physical_child_tree_is_not_reparented(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    child=SportsEvent(event_id='unrecorded-child',fingerprint='unrecorded-child',sport_id='football',
        competition_id=legacy.competition_id,event_family='team_match',canonical_event_id=legacy.event_id,display_eligible=False)
    db.add(child);db.commit();before=snap(db)
    out=consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    assert out.get('rejected') and snap(db)==before


def test_blocked_writes_do_not_promote_or_link_source_roots(setup,monkeypatch):
    db,source=setup;raw,keeper,legacy=split_case(db,source);before=snap(db)
    monkeypatch.setenv('RESULTS_WRITE_ENABLED','false')
    with pytest.raises(RuntimeError,match='writes disabled'):
        consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy))
    db.commit();assert snap(db)==before


def test_future_source_schedule_cannot_erase_played_result(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source,fixture=True)
    legacy.status='finished';legacy.score_json=dump_json({'home':3,'away':1});db.commit();before=snap(db)
    out=consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    assert out.get('rejected') and snap(db)==before


def public_peer_case(db,source):
    raw,source_root,public=split_case(db,source)
    public.competition_id=source_root.competition_id
    public.extra_json=dump_json({'display_eligible':True,'source_family':'old-fixtures','source_event_ids':{'old-fixtures':'one'}})
    store_list_extra(public,load_json(public.extra_json));db.commit();db.info.clear()
    return raw,source_root,public


def test_hidden_exact_source_updates_existing_public_id_and_keeps_source_alias(setup):
    db,source=setup;raw,source_root,public=public_peer_case(db,source)
    ids=[source_root.event_id,public.event_id];fps=[source_root.fingerprint,public.fingerprint]
    out=consume_board_match(db,fresh(raw),source,index(raw,source_root));db.commit()
    assert not out.get('rejected'),out
    assert public.status=='finished' and load_json(public.score_json)['home']==3
    assert public.display_eligible and source_root.canonical_event_id==public.event_id
    assert not source_root.display_eligible
    assert [source_root.fingerprint,public.fingerprint]==fps
    consume_board_match(db,fresh(raw),source,index(raw,source_root,public));db.commit()
    assert public.event_id==ids[1] and public.status=='finished' and db.query(SportsEvent).count()==2


@pytest.mark.parametrize('unsafe',['other-competition','different-final','typed-other-match','other-team','manual','unknown-hidden-quality'])
def test_hidden_to_public_candidate_requires_full_proof(setup,unsafe):
    db,source=setup;raw,source_root,public=public_peer_case(db,source)
    if unsafe=='other-competition':public.competition_id='football-different-group'
    if unsafe=='different-final':public.status='finished';public.score_json=dump_json({'home':9,'away':9})
    if unsafe=='typed-other-match':public.extra_json=dump_json({'display_eligible':True,'source_event_ids':{'fotmob':'other'}})
    if unsafe=='other-team':
        p=load_json(public.participants_json);p['away']['name']='Other club';public.participants_json=dump_json(p)
    if unsafe=='manual':public.extra_json=dump_json({'display_eligible':True,'manual_hidden':True})
    if unsafe=='unknown-hidden-quality':
        e=load_json(source_root.extra_json);e['quality_flags']=['unverified-participants'];source_root.extra_json=dump_json(e)
    db.commit();old=(public.score_json,public.canonical_event_id,public.display_eligible)
    consume_board_match(db,fresh(raw),source,index(raw,source_root));db.commit()
    assert (public.score_json,public.canonical_event_id,public.display_eligible)==old
    assert source_root.canonical_event_id is None


def test_unproven_public_parent_prevents_publishing_a_third_duplicate(setup):
    db,source=setup;raw,keeper,legacy=split_case(db,source)
    third=SportsEvent(event_id='parent-only',fingerprint='parent-only',sport_id='football',competition_id='football-parent',
        event_family='team_match',start_time=keeper.start_time,participants_json=keeper.participants_json,
        status='scheduled',display_eligible=True,score_json='{}',extra_json='{}')
    db.add(third);db.commit();before=snap(db)
    out=consume_board_match(db,fresh(raw),source,index(raw,keeper,legacy));db.commit()
    assert out.get('rejected') and snap(db)==before


def test_hidden_final_result_is_prioritized_even_if_score_already_matches(setup):
    from collector.football_board_priority import changed_result_signature, priority_plan
    db,source=setup;raw,keeper,public=public_peer_case(db,source);now=datetime.utcnow()
    signature=changed_result_signature(raw,[keeper],now)
    assert signature
    p=priority_plan({str(raw['id']):raw},index(raw,keeper),{},now,20)
    assert str(raw['id']) in p
    consume_board_match(db,fresh(raw),source,index(raw,keeper));db.commit()
    assert changed_result_signature(raw,[keeper,public],now) is None


def test_manual_hidden_same_score_never_enters_recovery_priority(setup):
    from collector.football_board_priority import changed_result_signature
    db,source=setup;raw,keeper,public=public_peer_case(db,source)
    e=load_json(keeper.extra_json);e['manual_hidden']=True;keeper.extra_json=dump_json(e);db.commit()
    assert changed_result_signature(raw,[keeper],datetime.utcnow()) is None
