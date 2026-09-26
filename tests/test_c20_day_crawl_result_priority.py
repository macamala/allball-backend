"""Whole-page coverage must not make a newly observed score wait behind fixtures."""
from datetime import datetime, timedelta
import pytest
from collector.adapters import FetchResult
from collector.models import SportsCollectorJob, SportsEvent
from collector.source_ids import id_for_family
from collector.util import dump_json, load_json, isoformat
from collector.football_board_refresh import refresh_day, JOB_PREFIX
from tests.test_football_board_priority import candidate
from tests.test_football_global_refresh import setup, board


def source_page(now):
    raws = []
    for sid in ('100', '200', '300', '400', '999'):
        raw, _ = candidate(sid, now=now)
        if sid != '999':
            raw['status'].update(started=False, finished=False, reason={},
                                 utcTime=isoformat(now+timedelta(hours=2, minutes=int(sid))))
        raws.append(raw)
    return raws


def test_new_finished_result_reaches_real_ingestion_before_future_date_cursor(setup):
    db, source = setup; now = datetime.utcnow(); day = now.strftime('%Y%m%d')
    payload = board(source_page(now)); requests = []
    def get(url):
        requests.append(url)
        return FetchResult(ok=True, http_status=200, payload=payload, fetched_at=isoformat(now))
    out = refresh_day(db, day, source, now=now, getter=get, max_events=2)
    db.commit()
    rows = db.query(SportsEvent).all()
    by_source = {id_for_family(load_json(r.extra_json), 'fotmob'): r for r in rows}
    assert set(by_source) == {'100', '999'}
    final = by_source['999']
    assert final.status == 'finished' and not final.live
    assert load_json(final.score_json)['home'] == 2 and load_json(final.score_json)['away'] == 1
    state = load_json(db.get(SportsCollectorJob, JOB_PREFIX+day).last_error)
    assert state['after_id'] == '100' and not out['complete']
    assert out['priority_processed'] == 1 and len(requests) == 1


def test_failed_priority_does_not_acknowledge_unvisited_coverage(setup, monkeypatch):
    db, source = setup; now = datetime.utcnow(); day = now.strftime('%Y%m%d'); seen = []
    def consume(db, raw, *_):
        seen.append(str(raw['id']))
        if str(raw['id']) == '999':
            raise RuntimeError('isolated test transient failure')
        return {'written': 1}
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match', consume)
    out = refresh_day(db, day, source, now=now,
        getter=lambda _: FetchResult(ok=True, http_status=200, payload=board(source_page(now)), fetched_at=isoformat(now)), max_events=2)
    db.commit(); state = load_json(db.get(SportsCollectorJob, JOB_PREFIX+day).last_error)
    assert seen == ['100', '999']
    assert not out['complete'] and state['after_id'] == '100'
    assert '999' not in state.get('priority_receipts', {})


def test_cursor_continues_after_priority_without_skipping_future_rows(setup, monkeypatch):
    db, source = setup; now = datetime.utcnow(); day = now.strftime('%Y%m%d'); seen = []
    monkeypatch.setattr('collector.football_board_refresh.consume_board_match',
        lambda db, raw, *_: (seen.append(str(raw['id'])) or {'written': 1}))
    get = lambda _: FetchResult(ok=True, http_status=200, payload=board(source_page(now)), fetched_at=isoformat(now))
    a = refresh_day(db, day, source, now=now, getter=get, max_events=2); db.commit()
    assert seen == ['100', '999']
    seen.clear(); db.info.clear()
    b = refresh_day(db, day, source, now=now+timedelta(seconds=20), getter=get, max_events=10); db.commit()
    assert seen == ['200','300','400','999']
    assert b['complete'] and load_json(db.get(SportsCollectorJob, JOB_PREFIX+day).last_error)['after_id'] == ''
