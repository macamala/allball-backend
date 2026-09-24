"""Only exact current source evidence restores an existing hidden canonical root."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from collector.adapters_fotmob import _extract_matches, match_to_event
from collector.collect import _consume_result
from collector.normalize import normalize_event
from collector.competition_identity import event_accepted_for_mapping
from collector.adapters import FetchResult
from collector.identity import remember_mapping
from collector.keeper_revalidation import revalidate_current_keeper
from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition, SportsEvent
from collector.util import dump_json, load_json, parse_datetime
from database import SessionLocal

@pytest.fixture
def case():
    db=SessionLocal()
    payload=json.loads((Path(__file__).parent/'fixtures/fotmob_nations_groups_20260924.json').read_text())
    raw=next(x for x in _extract_matches(payload) if x['id']==5181874)
    raw['status']['utcTime']=(datetime.utcnow()-timedelta(hours=6)).isoformat()+'Z'
    incoming=match_to_event(raw,'uefa-nations-league',source_league_id='9809')
    incoming['source_fetch_time']=datetime.utcnow().isoformat()+'Z'
    incoming=normalize_event(incoming,sport_id='football',competition_id='uefa-nations-league')
    incoming.update(event_accepted_for_mapping(incoming,'uefa-nations-league')[1])
    assert incoming['accepted']
    comp=SportsCompetition(competition_id='uefa-nations-league',sport_id='football',name='Nations League',slug='nations',event_model='team_match')
    source=SportsSource(source_id='verified-fotmob',upstream_family='fotmob',adapter_key='fotmob',display_name='test',kind='test',enabled=True)
    mapping=SportsSourceCompetition(competition_id=comp.competition_id,source_id=source.source_id,enabled=True,upstream_family='fotmob',priority=1)
    parts={key:deepcopy(incoming[key]) for key in ('home','away')}
    extra={key:value for key,value in incoming.items() if key not in ('home','away','score')}
    extra.update({'collapsed_from':['original-link'], 'display_eligible':False,'quality_flags':['duplicate_or_contaminated']})
    common=dict(sport_id='football',competition_id=comp.competition_id,start_time=parse_datetime(incoming['start_time']),event_family='team_match',status='finished',participants_json=dump_json(parts),score_json=dump_json({'home':1,'away':2}),display_eligible=False)
    root=SportsEvent(event_id='stable-root',extra_json=dump_json(extra),**common)
    child=SportsEvent(event_id='original-link',canonical_event_id=root.event_id,extra_json='{}',**common)
    db.add_all([comp,source,mapping,root,child]);db.flush()
    remember_mapping(db,entity_kind='event',ninko_id=child.event_id,source_id=source.source_id,source_entity_id=incoming['source_event_id'])
    db.commit()
    yield SimpleNamespace(db=db,root=root,child=child,incoming=incoming,source=source,mapping=mapping,comp=comp)
    db.close()


def test_current_scored_observation_restores_root_only_and_is_idempotent(case):
    c=case; original_score=c.root.score_json;original_parts=c.root.participants_json
    assert revalidate_current_keeper(c.db,c.root,c.incoming,source_id=c.source.source_id)
    c.db.commit()
    assert c.root.display_eligible is True
    assert load_json(c.root.extra_json)['quality_flags']==[]
    assert c.child.display_eligible is False and c.child.canonical_event_id==c.root.event_id
    assert c.root.score_json==original_score and c.root.participants_json==original_parts
    assert not revalidate_current_keeper(c.db,c.root,c.incoming,source_id=c.source.source_id)


def test_real_consume_pipeline_restores_canonical_score_and_preserves_old_link(case):
    c=case
    result=FetchResult(ok=True,http_status=200,events=[{k:v for k,v in c.incoming.items() if k!='accepted'}])
    for _ in range(2):
        _consume_result(c.db,source=c.source,mapping=c.mapping,competition=c.comp,capability='results',result=result)
        c.db.commit();c.db.refresh(c.root);c.db.refresh(c.child)
        assert c.root.display_eligible is True
        assert load_json(c.root.score_json)['home']==1
        assert load_json(c.root.score_json)['away']==2
        assert c.child.display_eligible is False and c.child.canonical_event_id==c.root.event_id
        assert c.db.query(SportsEvent).count()==2


@pytest.mark.parametrize('change', ['unaccepted','untrusted','wrong-competition','wrong-sport','wrong-home','reversed-pair','wrong-start','invalid-score','future-fetch','stale-fetch','scheduled','unmapped','manual-hidden','no-lineage','foreign-quality','child-root'])
def test_restore_fails_closed_without_exact_current_proof(case,change):
    c=case; inc=deepcopy(c.incoming);ext=load_json(c.root.extra_json)
    if change=='unaccepted':inc['accepted']=False
    if change=='untrusted':inc['source_family']='untrusted'
    if change=='wrong-competition':inc['competition_key']='other'
    if change=='wrong-sport':inc['sport']='basketball'
    if change=='wrong-home':inc['home']['name']='England'
    if change=='reversed-pair':inc['home'],inc['away']=inc['away'],inc['home']
    if change=='wrong-start':inc['start_time']=(c.root.start_time+timedelta(hours=1)).isoformat()+'Z'
    if change=='invalid-score':inc['score']['home']=None
    if change=='future-fetch':inc['source_fetch_time']=(datetime.utcnow()+timedelta(hours=1)).isoformat()+'Z'
    if change=='stale-fetch':inc['source_fetch_time']=(datetime.utcnow()-timedelta(minutes=10)).isoformat()+'Z'
    if change=='scheduled':inc['status']='scheduled'
    if change=='unmapped':inc['source_event_id']='unmapped'
    if change=='manual-hidden':ext['manual_hidden']=True
    if change=='no-lineage':ext['collapsed_from']=[]
    if change=='foreign-quality':ext['quality_flags']=['invalid_name']
    if change=='child-root':c.root.canonical_event_id=c.child.event_id
    c.root.extra_json=dump_json(ext);c.db.flush()
    assert not revalidate_current_keeper(c.db,c.root,inc,source_id=c.source.source_id)
    assert c.root.display_eligible is False
    assert c.child.display_eligible is False


def test_existing_visible_same_fixture_prevents_restoration(case):
    c=case
    other=SportsEvent(event_id='visible-root',sport_id='football',competition_id=c.comp.competition_id,start_time=c.root.start_time,event_family='team_match',status='finished',participants_json=c.root.participants_json,score_json=c.root.score_json,display_eligible=True)
    c.db.add(other);c.db.flush()
    assert not revalidate_current_keeper(c.db,c.root,c.incoming,source_id=c.source.source_id)
    assert c.root.display_eligible is False and other.display_eligible is True


def test_unchanged_observation_revalidates_before_skip(case, monkeypatch):
    c=case
    monkeypatch.setattr('collector.collect.event_unchanged',lambda *_:True)
    result=FetchResult(ok=True,http_status=200,events=[c.incoming])
    outcome=_consume_result(c.db,source=c.source,mapping=c.mapping,competition=c.comp,capability='results',result=result)
    c.db.commit();c.db.refresh(c.root)
    assert outcome['written']==0
    assert c.root.display_eligible is True
    assert load_json(c.root.extra_json)['quarantine_disposition']=='RESTORED_VERIFIED_CANONICAL'
    assert c.child.display_eligible is False
