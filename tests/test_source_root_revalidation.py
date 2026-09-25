"""Fresh exact provider identity can resolve a former automatic ambiguity."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from tests.test_football_global_refresh import setup, fresh
from tests.test_football_source_roots import split_case, index, snap
from collector.models import SportsEvent
from collector.football_board_refresh import consume_board_match
from collector.util import dump_json, load_json, isoformat
from collector.list_extra import store_list_extra


def ambiguous(row):
    meta=load_json(row.extra_json) or {}
    meta['quarantine_disposition']='AMBIGUOUS'
    row.extra_json=dump_json(meta);store_list_extra(row,meta)


@pytest.mark.parametrize('domestic,fixture',[(False,False),(False,True),(True,False),(True,True)])
def test_exact_native_team_ids_leaf_and_time_revalidate_automatic_ambiguity(setup,domestic,fixture):
    db,source=setup;raw,root,old=split_case(db,source,domestic=domestic,fixture=fixture)
    ambiguous(root);ambiguous(old);db.commit();ids={root.event_id,old.event_id}
    out=consume_board_match(db,fresh(raw),source,index(raw,root,old));db.commit()
    assert not out.get('rejected'),out
    assert root.display_eligible and old.canonical_event_id==root.event_id and not old.display_eligible
    assert set(r.event_id for r in db.query(SportsEvent).all())==ids
    assert load_json(root.extra_json)['source_root_proofs'][-1]['source_event_id']==str(raw['id'])
    out=consume_board_match(db,fresh(raw),source,index(raw,root,old));db.commit()
    assert not out.get('rejected') and root.display_eligible and not old.display_eligible


def test_single_hidden_native_root_can_recover_without_manufacturing_an_alias(setup):
    db,source=setup;raw,root,old=split_case(db,source)
    db.delete(old);ambiguous(root);db.commit();eid,fp=root.event_id,root.fingerprint
    out=consume_board_match(db,fresh(raw),source,index(raw,root));db.commit()
    assert not out.get('rejected'),out
    assert root.display_eligible and root.status=='finished'
    assert root.event_id==eid and root.fingerprint==fp and db.query(SportsEvent).count()==1
    proof=load_json(root.extra_json)['source_root_proofs'][-1]
    assert proof['linked_ids']==[]


@pytest.mark.parametrize('bad',[
    'missing-home-id','wrong-away-id','swapped-ids','other-family','missing-typed-id',
    'wrong-leaf','parent-only','other-team','wrong-time','manual-hidden','slim-manual',
    'unknown-quality','slim-unknown-quality','unknown-disposition','slim-unknown-disposition',
    'provider-conflicts','stale-source','contradictory-final','independent-children',
])
def test_old_ambiguous_label_is_not_blanket_permission(setup,bad):
    db,source=setup;raw,root,old=split_case(db,source)
    ambiguous(root);ambiguous(old);m=load_json(old.extra_json);p=load_json(old.participants_json)
    if bad=='missing-home-id':p['home'].pop('id',None)
    if bad=='wrong-away-id':p['away']['id']='WRONG'
    if bad=='swapped-ids':p['home']['id'],p['away']['id']=p['away']['id'],p['home']['id']
    if bad=='other-family':m['source_family']='thesportsdb'
    if bad=='missing-typed-id':m['source_event_ids']={'thesportsdb':'123'};m.pop('source_event_id',None)
    if bad=='wrong-leaf':m['source_competition_id']='943313';m['source_group_id']='943313'
    if bad=='parent-only':m['source_competition_id']='13287';m.pop('source_group_id',None)
    if bad=='other-team':p['home']['name']='Another club'
    if bad=='wrong-time':old.start_time+=timedelta(minutes=5)
    if bad=='manual-hidden':m['manual_hidden']=True
    if bad=='unknown-quality':m['quality_flags']=['unverified-participants']
    if bad=='unknown-disposition':m['quarantine_disposition']='TRUE_GARBAGE'
    if bad=='provider-conflicts':m['provider_conflicts']=['bad-id']
    if bad=='stale-source':raw['_source_fetched_at']=isoformat(datetime.utcnow()-timedelta(hours=1))
    if bad=='contradictory-final':old.status='finished';old.score_json=dump_json({'home':8,'away':8})
    if bad=='independent-children':m['collapsed_from']=['existing-child']
    old.extra_json=dump_json(m);old.participants_json=dump_json(p);store_list_extra(old,m)
    if bad=='slim-manual':old.list_extra_json=dump_json({'manual_hidden':True})
    if bad=='slim-unknown-quality':old.list_extra_json=dump_json({'quality_flags':['unverified-participants']})
    if bad=='slim-unknown-disposition':old.list_extra_json=dump_json({'quarantine_disposition':'TRUE_GARBAGE'})
    db.commit();before=snap(db)
    out=consume_board_match(db,raw,source,index(raw,root,old));db.commit()
    assert out.get('rejected'),out
    assert snap(db)==before


def test_missing_public_counterpart_proof_still_blocks_third_representation(setup):
    db,source=setup;raw,root,old=split_case(db,source);ambiguous(root);ambiguous(old)
    db.add(SportsEvent(event_id='unproven-parent',fingerprint='unproven-parent',sport_id='football',
        competition_id='football-fifa-asean-cup',event_family='team_match',status='scheduled',
        start_time=root.start_time,participants_json=root.participants_json,display_eligible=True,extra_json='{}'))
    db.commit();before=snap(db)
    out=consume_board_match(db,fresh(raw),source,index(raw,root,old));db.commit()
    assert out.get('rejected') and snap(db)==before
