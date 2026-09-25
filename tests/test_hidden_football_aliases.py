"""A quarantined duplicate may become an alias, never a public replacement."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from collector.football_board_refresh import consume_board_match
from collector.football_fixture_linkage import link_accepted_duplicates
from collector.adapters_fotmob import match_to_event
from collector.models import SportsEvent
from collector.list_extra import store_list_extra
from collector.util import load_json, dump_json, isoformat
from tests.test_football_global_refresh import setup, fresh
from tests.test_football_fixture_linkage import duplicate_case


def hidden_case(db, source):
    raw, keeper, peer = duplicate_case(db, source)
    meta=load_json(peer.extra_json)
    meta.update(display_eligible=False, quality_flags=['duplicate_or_contaminated'], quarantine_disposition='AMBIGUOUS')
    meta['source_event_ids']['fotmob']=str(raw['id'])
    peer.display_eligible=False;peer.extra_json=dump_json(meta);store_list_extra(peer,meta)
    db.commit();db.info.clear()
    return raw, keeper, peer


def test_hidden_same_fixture_links_to_visible_keeper_not_the_reverse(setup):
    db,source=setup;raw,keeper,peer=hidden_case(db,source)
    identities=[keeper.event_id,peer.event_id];fps=[keeper.fingerprint,peer.fingerprint]
    for _ in range(2):
        result=consume_board_match(db,fresh(raw),source,{str(raw['id']):[peer,keeper]});db.commit()
        assert not result.get('rejected'),result
        assert keeper.canonical_event_id is None and keeper.display_eligible is True
        assert peer.canonical_event_id==keeper.event_id and peer.display_eligible is False
        assert keeper.status=='finished' and load_json(keeper.score_json)['away']==1
        assert [keeper.event_id,peer.event_id]==identities
        assert [keeper.fingerprint,peer.fingerprint]==fps
        assert load_json(peer.list_extra_json)['display_eligible'] is False
        assert db.query(SportsEvent).count()==2


def test_hidden_alias_discovered_outside_source_index(setup):
    db,source=setup;raw,keeper,peer=hidden_case(db,source)
    result=consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    assert not result.get('rejected') and peer.canonical_event_id==keeper.event_id


@pytest.mark.parametrize('unsafe',['manual','slim-manual','do-not-restore','retired','unknown-quality','slim-quality','unknown-disposition','no-typed-id','different-id','provider-conflict','different-group','other-team','other-time','conflicting-final','independent-child'])
def test_hidden_alias_repair_preserves_all_restrictions(setup,unsafe):
    db,source=setup;raw,keeper,peer=hidden_case(db,source)
    m=load_json(peer.extra_json)
    if unsafe=='manual':m['manual_hidden']=True
    if unsafe=='do-not-restore':m['do_not_restore']=True
    if unsafe=='retired':m['collapse_role']='observation_only'
    if unsafe=='unknown-quality':m['quality_flags'].append('unverified-participants')
    if unsafe=='unknown-disposition':m['quarantine_disposition']='TRUE_GARBAGE'
    if unsafe=='no-typed-id':m['source_event_ids'].pop('fotmob')
    if unsafe=='different-id':m['source_event_ids']['fotmob']='other'
    if unsafe=='provider-conflict':m['provider_conflicts']=[{'event_id':'other'}]
    if unsafe=='different-group':peer.competition_id='football-different-group'
    if unsafe=='other-team':
        p=load_json(peer.participants_json);p['away']['name']+=' Women';peer.participants_json=dump_json(p)
    if unsafe=='other-time':peer.start_time+=timedelta(minutes=3)
    if unsafe=='conflicting-final':peer.status='finished';peer.score_json=dump_json({'home':8,'away':8})
    if unsafe=='independent-child':
        db.add(SportsEvent(event_id='unrelated-child',fingerprint='unrelated-child',sport_id='football',competition_id=peer.competition_id,event_family='team_match',canonical_event_id=peer.event_id,display_eligible=False))
    peer.extra_json=dump_json(m);store_list_extra(peer,m)
    if unsafe=='slim-manual':peer.list_extra_json=dump_json({'manual_hidden':True})
    if unsafe=='slim-quality':peer.list_extra_json=dump_json({'quality_flags':['unverified-participants']})
    db.commit();old=(peer.canonical_event_id,peer.display_eligible,peer.score_json,peer.extra_json,peer.list_extra_json)
    consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper]});db.commit()
    assert (peer.canonical_event_id,peer.display_eligible,peer.score_json,peer.extra_json,peer.list_extra_json)==old


def test_hidden_alias_transaction_cannot_change_confirmed_score(setup,monkeypatch):
    db,source=setup;raw,keeper,peer=hidden_case(db,source)
    event={**match_to_event(fresh(raw),keeper.competition_id), 'competition_key':keeper.competition_id}
    from collector.canonical_collapse import _collapse_pair
    def corrupt(db,k,p):
        result=_collapse_pair(db,k,p);db.get(SportsEvent,k).score_json=dump_json({'home':9,'away':9});return result
    monkeypatch.setattr('collector.canonical_collapse._collapse_pair',corrupt)
    old=(keeper.score_json,keeper.status,peer.canonical_event_id,peer.extra_json)
    with pytest.raises(RuntimeError,match='accepted result'):
        link_accepted_duplicates(db,keeper,event)
    db.commit()
    assert (keeper.score_json,keeper.status,peer.canonical_event_id,peer.extra_json)==old


def test_hidden_alias_needs_fresh_evidence_and_writes(setup,monkeypatch):
    db,source=setup;raw,keeper,peer=hidden_case(db,source)
    event={**match_to_event(fresh(raw),keeper.competition_id), 'competition_key':keeper.competition_id}
    event['source_fetch_time']=isoformat(datetime.utcnow()-timedelta(hours=1))
    assert link_accepted_duplicates(db,keeper,event)==0
    event['source_fetch_time']=isoformat(datetime.utcnow())
    monkeypatch.setenv('RESULTS_WRITE_ENABLED','false')
    assert link_accepted_duplicates(db,keeper,event)==0
    db.commit();assert peer.canonical_event_id is None and peer.display_eligible is False
