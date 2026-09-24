"""Repeated maintenance must not resurrect retired fixture observations."""
from datetime import datetime, timedelta
import ast
from pathlib import Path
import pytest
from collector.models import SportsEvent
from collector.util import dump_json, load_json
from collector.list_extra import store_list_extra, extra_for_list
from collector.integrity import plan_backfill, apply_backfill, _mutate_row, restore_orphaned_duplicate_football, apply_competition_attribution
from collector.source_native_reconcile import revalidate_current_source_native
from collector.canonical_collapse import collapse_canonical_events, _collapse_pair, _sync_public_flags, classify_quarantine
from database import SessionLocal


def event(eid, *, canonical=None, extra=None, visible=True, score=None, status='scheduled', updated=None):
    metadata={'source_family':'fotmob', 'source_competition_name':'UEFA Nations League',
              'source_competition_id':'9809','source_event_id':eid,
              'resolution_method':'mapping_request_trusted','display_eligible':visible,
              'quality_flags':[], **(extra or {})}
    row=SportsEvent(event_id=eid, fingerprint=eid, sport_id='football', competition_id='uefa-nations-league',
        event_family='team_match', start_time=datetime.utcnow().replace(microsecond=0)-timedelta(hours=2),
        updated_at=updated or datetime.utcnow(), canonical_event_id=canonical, display_eligible=visible,
        participants_json=dump_json({'home':{'name':'Andorra'},'away':{'name':'Malta'}}),
        score_json=dump_json(score or {'home':None,'away':None}), status=status, extra_json=dump_json(metadata))
    store_list_extra(row,metadata)
    return row


@pytest.fixture
def db():
    session=SessionLocal()
    try: yield session
    finally: session.close()


def test_retired_newer_observation_cannot_quarantine_its_finished_keeper(db):
    root=event('keeper',score={'home':1,'away':2},status='finished',updated=datetime.utcnow()-timedelta(hours=1),extra={'collapsed_from':['child']})
    child=event('child',canonical='keeper',visible=False,extra={'canonical_event_id':'keeper','collapse_role':'observation_only'})
    db.add_all([root,child]);db.commit()
    plan=plan_backfill(db)
    assert 'keeper' not in plan['quarantine']
    assert not any(pair[0]=='child' for pair in plan['auto_merge'])


@pytest.mark.parametrize('metadata,canonical',[({},'missing-keeper'),({'canonical_event_id':'missing-keeper'},None),({'collapse_role':'observation_only'},None),({'manual_hidden':True},None),({'do_not_restore':True},None)])
def test_orphan_guard_never_promotes_retired_or_explicitly_blocked_rows(db, metadata, canonical):
    row=event('blocked',canonical=canonical,visible=False,extra={'quality_flags':['duplicate_or_contaminated'],**metadata})
    db.add(row);db.commit()
    assert restore_orphaned_duplicate_football(db)['restored']==0
    assert row.display_eligible is False
    assert row.canonical_event_id==canonical


@pytest.mark.parametrize('metadata,canonical',[({},'keeper'),({'canonical_event_id':'keeper'},None),({'collapse_role':'observation_only'},None),({'manual_hidden':True},None),({'do_not_restore':True},None)])
def test_source_revalidation_cannot_override_lifecycle_or_manual_policy(db,metadata,canonical):
    row=event('blocked',canonical=canonical,visible=False,extra=metadata)
    db.add(row);db.commit()
    result=revalidate_current_source_native(db)
    assert result['promoted']==0
    assert row.display_eligible is False


def test_name_repair_keeps_a_retired_observation_hidden_in_both_views(db):
    row=event('child',canonical='keeper',visible=False,extra={'canonical_event_id':'keeper','collapse_role':'observation_only'})
    db.add(row);db.commit()
    _mutate_row(row,set(),{'child'})
    assert row.display_eligible is False
    assert load_json(row.extra_json)['display_eligible'] is False
    assert extra_for_list(row)['display_eligible'] is False
    assert row.canonical_event_id=='keeper'


def test_repeated_backfill_and_collapse_preserve_one_final_result_and_alias(db):
    root=event('keeper',score={'home':1,'away':2},status='finished',extra={'collapsed_from':['child']})
    child=event('child',canonical='keeper',visible=False,extra={'canonical_event_id':'keeper','collapse_role':'observation_only'})
    db.add_all([root,child]);db.commit()
    for _ in range(3):
        apply_backfill(db);collapse_canonical_events(db);revalidate_current_source_native(db);db.commit()
        public=db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None),SportsEvent.display_eligible.is_(True)).all()
        assert [r.event_id for r in public]==['keeper']
        assert load_json(public[0].score_json)=={'home':1,'away':2}
        assert db.get(SportsEvent,'child').canonical_event_id=='keeper'
        assert extra_for_list(db.get(SportsEvent,'child'))['display_eligible'] is False


def test_collapse_cannot_make_an_existing_child_the_new_root(db):
    parent=event('parent')
    child=event('child',canonical='parent',visible=False,extra={'canonical_event_id':'parent'})
    other=event('other')
    db.add_all([parent,child,other]);db.commit()
    assert _collapse_pair(db,'child','other') is False
    assert db.get(SportsEvent,'child').canonical_event_id=='parent'
    assert db.get(SportsEvent,'other').canonical_event_id is None


def test_flag_sync_updates_slim_list_metadata(db):
    row=event('keeper');db.add(row);db.commit()
    meta=load_json(row.extra_json)
    _sync_public_flags(row,meta,False)
    assert extra_for_list(row)['display_eligible'] is False


def test_valid_orphan_root_still_recovers(db):
    root=event('keeper',visible=False,extra={'quality_flags':['duplicate_or_contaminated']})
    child=event('child',visible=False,canonical='keeper',extra={'quality_flags':['duplicate_or_contaminated'],'canonical_event_id':'keeper','collapse_role':'observation_only'})
    db.add_all([root,child]);db.commit()
    result=restore_orphaned_duplicate_football(db)
    assert result['restored_ids']==['keeper']
    assert root.display_eligible is True
    assert child.display_eligible is False
    assert child.canonical_event_id=='keeper'
    assert extra_for_list(root)['display_eligible'] is True


def test_startup_maintenance_requires_explicit_opt_in():
    from collector.maintenance_policy import startup_integrity_enabled
    assert not startup_integrity_enabled({})
    assert not startup_integrity_enabled({'NINKO_SKIP_INTEGRITY_BACKFILL':'0'})
    assert startup_integrity_enabled({'NINKO_RUN_STARTUP_INTEGRITY_BACKFILL':'1'})
    assert not startup_integrity_enabled({'NINKO_RUN_STARTUP_INTEGRITY_BACKFILL':'1','NINKO_SKIP_INTEGRITY_BACKFILL':'1'})
    tree=ast.parse(Path('app.py').read_text())
    lifespan=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='lifespan')
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='startup_integrity_enabled' for n in ast.walk(lifespan))
    assert any(isinstance(n,ast.Name) and n.id=='asynccontextmanager' for n in lifespan.decorator_list)
    indexes=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_startup_list_indexes')
    assert not indexes.decorator_list


@pytest.mark.parametrize('policy',[{'manual_hidden':True},{'do_not_restore':True},{'collapse_role':'observation_only'},{'canonical_event_id':'parent'}])
@pytest.mark.parametrize('operation',['classify','attribution','sync'])
def test_every_visibility_repair_preserves_explicit_restrictions(db,policy,operation):
    row=event('blocked',visible=False,extra=policy)
    db.add(row);db.commit()
    if operation=='classify': classify_quarantine(db)
    elif operation=='attribution': apply_competition_attribution(db,fetch_live=False)
    else: _sync_public_flags(row,{'display_eligible':True},True)
    assert row.display_eligible is False
    assert extra_for_list(row)['display_eligible'] is False
    for key,value in policy.items(): assert load_json(row.extra_json)[key]==value


def test_stale_slim_blob_cannot_override_rich_policy(db):
    row=event('blocked',visible=False,extra={'manual_hidden':True})
    row.list_extra_json=dump_json({'display_eligible':True,'manual_hidden':False,'source_family':'fotmob','source_competition_name':'UEFA Nations League'})
    db.add(row);db.commit()
    assert revalidate_current_source_native(db)['promoted']==0
    assert row.display_eligible is False
    assert load_json(row.extra_json)['manual_hidden'] is True
    assert extra_for_list(row)['display_eligible'] is False


def test_collapse_synchronizes_keeper_and_child_list_views(db):
    root=event('keeper',score={'home':1,'away':2},status='finished')
    child=event('child')
    db.add_all([root,child]);db.commit()
    assert _collapse_pair(db,'keeper','child')
    assert extra_for_list(root)['display_eligible'] is True
    assert extra_for_list(child)['display_eligible'] is False
    assert child.canonical_event_id=='keeper'
    assert load_json(root.score_json)=={'home':1,'away':2}
