"""Collector completion timestamp remains usable as current observation proof."""
from collector.adapters import FetchResult
from collector.collect import _consume_result
from collector.normalize import normalize_event
from collector.util import load_json
from tests.test_keeper_revalidation import case


def test_normalization_preserves_real_fetch_completion_without_inventing_contact(case):
    c=case; raw=dict(c.incoming)
    stamp=raw.pop('source_fetch_time');raw.pop('retrieved_at',None)
    raw['fetch_completed_at']=stamp
    out=normalize_event(raw,sport_id='football',competition_id=c.comp.competition_id)
    assert out['source_fetch_time']==stamp
    raw.pop('fetch_completed_at')
    assert normalize_event(raw,sport_id='football',competition_id=c.comp.competition_id)['source_fetch_time'] is None


def test_actual_fetch_stamp_revalidates_an_unchanged_hidden_keeper(case,monkeypatch):
    c=case;raw=dict(c.incoming)
    raw['fetch_completed_at']=raw.pop('source_fetch_time');raw.pop('retrieved_at',None)
    monkeypatch.setattr('collector.collect.event_unchanged',lambda *_:True)
    out=_consume_result(c.db,source=c.source,mapping=c.mapping,competition=c.comp,capability='results',result=FetchResult(ok=True,http_status=200,events=[raw]))
    c.db.commit();c.db.refresh(c.root)
    assert out['written']==0
    assert c.root.display_eligible is True
    assert load_json(c.root.score_json)['home']==1
    assert load_json(c.root.score_json)['away']==2
    assert c.child.display_eligible is False
