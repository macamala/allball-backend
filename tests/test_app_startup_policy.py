"""Exercise the real FastAPI lifespan without executing background jobs."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize('opt_in,skip,expected_integrity', [
    (None, None, False), ('1', None, True), ('1', '1', False),
])
def test_repeated_app_startup_respects_explicit_maintenance_policy(monkeypatch, opt_in, skip, expected_integrity):
    import app as application
    from collector.models import SportsEvent
    from collector.list_extra import store_list_extra
    from collector.util import dump_json
    from database import SessionLocal

    monkeypatch.delenv('NINKO_RUN_STARTUP_INTEGRITY_BACKFILL', raising=False)
    monkeypatch.delenv('NINKO_SKIP_INTEGRITY_BACKFILL', raising=False)
    monkeypatch.setenv('NINKO_SKIP_STARTUP_INDEX', '1')
    if opt_in is not None:
        monkeypatch.setenv('NINKO_RUN_STARTUP_INTEGRITY_BACKFILL', opt_in)
    if skip is not None:
        monkeypatch.setenv('NINKO_SKIP_INTEGRITY_BACKFILL', skip)

    started = []
    class RecordingThread:
        def __init__(self, *, target, daemon):
            assert daemon is True
            self.target = target
        def start(self):
            started.append(self.target.__name__)

    # Replace only app's threading reference, not the interpreter's thread API
    # used by TestClient. No historical mutation or network call runs here.
    monkeypatch.setattr(application, 'threading', SimpleNamespace(Thread=RecordingThread))
    monkeypatch.setattr(application, 'ensure_schema', lambda *_: None)

    with SessionLocal() as db:
        keeper = SportsEvent(event_id='startup-keeper', fingerprint='startup-keeper',
            sport_id='football', competition_id='uefa-nations-league', status='finished',
            display_eligible=True, participants_json=dump_json({'home':{'name':'Andorra'},'away':{'name':'Malta'}}),
            score_json=dump_json({'home':1,'away':2}), extra_json=dump_json({'display_eligible':True}))
        child = SportsEvent(event_id='startup-alias', fingerprint='startup-alias',
            sport_id='football', competition_id='uefa-nations-league', status='scheduled',
            canonical_event_id=keeper.event_id, display_eligible=False,
            score_json='{}', extra_json=dump_json({'display_eligible':False,'canonical_event_id':keeper.event_id,'collapse_role':'observation_only'}))
        store_list_extra(keeper, {'display_eligible':True})
        store_list_extra(child, {'display_eligible':False})
        db.add_all([keeper,child]); db.commit()

    def snapshot():
        with SessionLocal() as db:
            return [(r.event_id,r.status,r.score_json,r.canonical_event_id,r.display_eligible,r.extra_json,r.list_extra_json)
                    for r in db.query(SportsEvent).order_by(SportsEvent.event_id)]
    before = snapshot()
    for _ in range(3):
        with TestClient(application.app) as client:
            assert client.get('/openapi.json').status_code == 200
        assert snapshot() == before
    assert started.count('_startup_list_indexes') == 3
    assert started.count('_startup_integrity') == (3 if expected_integrity else 0)
    assert '_startup_index' not in started


def test_index_thread_target_executes_as_a_normal_function(monkeypatch):
    import app as application
    import collector.schema_tune as schema
    calls = []
    monkeypatch.setattr(schema, 'ensure_event_list_indexes', lambda engine: calls.append(engine))
    assert application._startup_list_indexes() is None
    assert calls == [application.engine]
