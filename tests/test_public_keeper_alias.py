"""Old detail links resolve to the same public keeper shown by the scoreboard."""
from datetime import timedelta
import pytest
from collector.public_keeper import public_keeper_for_alias
from collector.provider import NinkoCollectedSportsDataProvider
from collector.models import SportsEvent
from collector.util import dump_json, load_json
from database import SessionLocal
from tests.test_keeper_revalidation import case


def ready(c):
    c.root.display_eligible=True
    extra=load_json(c.root.extra_json);extra.update(display_eligible=True,quality_flags=[])
    c.root.extra_json=dump_json(extra)
    c.child.canonical_event_id=None
    c.child.display_eligible=True
    c.child.status='scheduled';c.child.score_json=dump_json({'home':None,'away':None})
    c.db.commit()


def test_retired_link_resolves_without_mutating_either_row(case):
    c=case;ready(c)
    assert public_keeper_for_alias(c.db,c.child) is c.root
    assert public_keeper_for_alias(c.db,c.root) is c.root
    assert c.child.canonical_event_id is None
    assert c.child.status=='scheduled'


@pytest.mark.parametrize('change',['wrong-competition','wrong-time','wrong-name','hidden-root','no-lineage','ambiguous'])
def test_reverse_alias_requires_unique_exact_public_lineage(case,change):
    c=case;ready(c)
    if change=='wrong-competition':c.root.competition_id='other'
    if change=='wrong-time':c.root.start_time+=timedelta(hours=1)
    if change=='wrong-name':c.root.participants_json=dump_json({'home':{'name':'France'},'away':{'name':'Malta'}})
    if change=='hidden-root':c.root.display_eligible=False
    if change=='no-lineage':c.root.extra_json='{}'
    if change=='ambiguous':
        c.db.add(SportsEvent(event_id='other-root',event_family='team_match',sport_id=c.root.sport_id,competition_id=c.root.competition_id,start_time=c.root.start_time,participants_json=c.root.participants_json,score_json=c.root.score_json,extra_json=c.root.extra_json,status='finished',display_eligible=True))
    c.db.flush()
    assert public_keeper_for_alias(c.db,c.child) is c.child


def test_public_match_detail_uses_the_scoreboard_keeper_for_old_link(case,monkeypatch):
    c=case;ready(c)
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda *_:None)
    monkeypatch.setattr('collector.provider._history_context',lambda *_:([],{}))
    provider=NinkoCollectedSportsDataProvider(session_factory=SessionLocal)
    detail=provider.get_event(c.child.event_id)
    assert detail['id']==c.root.event_id
    assert detail['status']=='finished'
    assert detail['score']['home']==1 and detail['score']['away']==2
