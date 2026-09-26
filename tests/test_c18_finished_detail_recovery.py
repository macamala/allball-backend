"""Post-match regressions: cached partial payloads, late data and fair retries.

The fixture uses the existing verified FotMob structure. No production records
or provider identities are created or changed by these tests.
"""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from collector.adapters import FetchResult
from collector.detail_enrich import enrich_event_row, PARSER_REV
from collector.fotmob_rich import REVISION
from collector.models import SportsCollectorJob, SportsEvent, SportsEventDetail
from collector.util import dump_json, load_json
from tests.test_fotmob_match_centre import stored, source
from tests.test_c15_live_tables import db


def _recent(stored, *, minutes=6, full_record=False):
    session, row, record = stored
    row.start_time = datetime.utcnow() - timedelta(hours=4)
    raw = source()
    raw['general']['matchTimeUTCDate'] = row.start_time.isoformat() + 'Z'
    meta = load_json(row.extra_json)
    meta.update(detail_status_at_fetch='finished', detail_empty=False,
                detail_negative=False, lineups_absent=not full_record,
                fotmob_detail_rev=REVISION,
                detail_fetched_at=(datetime.utcnow() - timedelta(minutes=minutes)).isoformat())
    row.extra_json = dump_json(meta)
    if not full_record:
        record.incidents_json = record.statistics_json = record.lineups_json = None
    session.commit()
    return session, row, record, raw


def _score_identity(row):
    return (row.event_id, row.fingerprint, row.competition_id, row.canonical_event_id,
            row.participants_json, row.start_time, row.score_json, row.status,
            row.live, row.display_eligible)


def test_finished_venue_only_response_does_not_freeze_later_core_details_for_a_week(stored):
    session, row, record, raw = _recent(stored)
    before = _score_identity(row)
    calls = []
    def getter(url):
        calls.append(url)
        return FetchResult(ok=True, payload=deepcopy(raw), http_status=200)
    enrich_event_row(session, row, getter=getter)
    session.commit()
    assert len(calls) == 1
    assert load_json(record.lineups_json)['away']['start'][0]['name'] == 'Scorer'
    assert load_json(record.statistics_json)
    assert load_json(record.incidents_json)
    assert _score_identity(row) == before
    enrich_event_row(session, row, getter=getter)
    assert len(calls) == 1, 'Immediate repeat views must not hammer the source'


def test_late_final_statistics_are_refreshed_even_when_some_lineups_already_exist(stored):
    session, row, record, raw = _recent(stored, full_record=True)
    before = _score_identity(row)
    calls = []
    enrich_event_row(session, row, getter=lambda url: calls.append(url) or FetchResult(ok=True, payload=raw))
    assert len(calls) == 1
    assert load_json(record.statistics_json) == [{'label': 'Total shots', 'home': 0, 'away': 3}]
    assert _score_identity(row) == before


def test_transient_final_failure_retains_all_previously_known_sections(stored):
    session, row, record, raw = _recent(stored, full_record=True)
    before = (record.incidents_json, record.statistics_json, record.lineups_json, _score_identity(row))
    calls = []
    def getter(url):
        calls.append(url)
        return FetchResult(ok=False, http_status=503, error='temporary upstream error')
    enrich_event_row(session, row, getter=getter)
    session.commit()
    assert len(calls) == 1
    assert (record.incidents_json, record.statistics_json, record.lineups_json, _score_identity(row)) == before
    enrich_event_row(session, row, getter=getter)
    assert len(calls) == 1


def test_parser_or_transport_exception_becomes_bounded_retry_not_an_aborted_queue(stored):
    session, row, record, raw = _recent(stored)
    meta = load_json(row.extra_json)
    meta['detail_fetched_at'] = (datetime.utcnow() - timedelta(days=8)).isoformat()
    row.extra_json = dump_json(meta)
    session.commit()
    before = _score_identity(row)
    calls = []
    def getter(url):
        calls.append(url)
        raise TimeoutError('private diagnostic text must not be persisted')
    enrich_event_row(session, row, getter=getter)
    session.commit()
    meta = load_json(row.extra_json)
    assert len(calls) == 1 and meta['detail_negative'] is True
    assert 'private diagnostic' not in row.extra_json
    assert _score_identity(row) == before
    enrich_event_row(session, row, getter=getter)
    assert len(calls) == 1


def _worker_setup(db, monkeypatch):
    from collector.lock import acquire_scheduler_lock
    monkeypatch.setattr('collector.football_enrichment_cycle.writes_enabled', lambda: True)
    monkeypatch.setattr('collector.provider._blocked_public_sources', lambda _: (set(), set()))
    monkeypatch.setattr('collector.provider._row_public_source_allowed', lambda *_: True)
    monkeypatch.setattr('collector.standings_enrich.load_standings', lambda *a, **k: [])
    acquire_scheduler_lock(db, owner='c18-test-owner')
    db.commit()


def _row(db, eid, *, hours=4, status='finished', family='fotmob', fresh=False):
    meta = {'source_event_ids': {family: '100'}}
    if fresh:
        meta.update(parser_rev=PARSER_REV, detail_fetched_at=datetime.utcnow().isoformat(),
                    detail_status_at_fetch=status, detail_empty=False, lineups_absent=False)
    row = SportsEvent(event_id=eid, fingerprint=eid, sport_id='football',
                      competition_id='league', event_family='team_match',
                      start_time=datetime.utcnow()-timedelta(hours=hours), status=status,
                      live=status=='live', display_eligible=True,
                      participants_json=dump_json({'home': {'name': 'Home FC'}, 'away': {'name': 'Away FC'}}),
                      score_json=dump_json({'home': 0, 'away': 1}), extra_json=dump_json(meta))
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize('hours', [13, 25, 48, 71])
def test_finished_match_does_not_leave_automatic_recovery_after_twelve_hours(db, monkeypatch, hours):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    row = _row(db, 'late-finished', hours=hours)
    before = _score_identity(row)
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert calls == ['late-finished']
    assert _score_identity(row) == before


@pytest.mark.parametrize('family', ['sofascore-web', 'openligadb'])
def test_already_linked_supported_football_source_can_fill_detail_queue(db, monkeypatch, family):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    _row(db, 'alternate', family=family)
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert calls == ['alternate']


def test_recent_final_and_future_each_get_budget_even_during_continuous_live_play(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football, JOB_KEY
    _worker_setup(db, monkeypatch)
    for eid, hours, status in [('live', 1, 'live'), ('final', 5, 'finished'), ('future', -2, 'scheduled')]:
        _row(db, eid, hours=hours, status=status)
    tick = [0.0]
    calls = []
    monkeypatch.setattr('collector.football_enrichment_cycle.time.monotonic', lambda: tick[0])
    def consume_budget(db, row, **kw):
        calls.append(row.event_id)
        tick[0] += 6.1
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', consume_budget)
    for cycle in range(3):
        job = db.get(SportsCollectorJob, JOB_KEY)
        if job:
            job.last_run_at = datetime.utcnow()-timedelta(seconds=31)
            db.commit()
        warm_current_football(db, owner='c18-test-owner')
        db.commit()
    assert len(calls) == 3 and set(calls) == {'live', 'final', 'future'}


def test_recovery_excludes_hidden_retired_and_old_records(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    _row(db, 'valid')
    hidden = _row(db, 'hidden'); hidden.display_eligible = False
    alias = _row(db, 'alias'); alias.canonical_event_id = 'valid'
    restricted = _row(db, 'restricted'); meta = load_json(restricted.extra_json); meta['manual_hidden'] = True; restricted.extra_json=dump_json(meta)
    _row(db, 'too-old', hours=80)
    _row(db, 'unsupported', family='not-a-detail-provider')
    db.commit()
    before = {r.event_id: _score_identity(r) for r in db.query(SportsEvent).all()}
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert calls == ['valid']
    assert {r.event_id: _score_identity(r) for r in db.query(SportsEvent).all()} == before

@pytest.mark.parametrize('hours,age,negative,expected', [
    (4, 299, False, True), (4, 301, False, False),
    (24.1, 899, False, True), (24.1, 901, False, False),
    (70, 901, False, False), (4, 119, True, True), (4, 121, True, False),
])
def test_recent_final_retry_cadence_is_bounded(hours, age, negative, expected):
    from collector.detail_enrich import _fresh
    now = datetime(2026, 9, 26, 5, 0)
    meta = {'parser_rev': PARSER_REV, 'detail_status_at_fetch': 'finished',
            'detail_fetched_at': (now-timedelta(seconds=age)).isoformat(),
            'detail_negative': negative, 'detail_empty': negative}
    assert _fresh(meta, 'finished', sport='football', start_time=now-timedelta(hours=hours), now=now) is expected


def test_other_sports_keep_existing_final_detail_policy():
    from collector.detail_enrich import _fresh
    now = datetime(2026, 9, 26, 5, 0)
    meta = {'parser_rev': PARSER_REV, 'detail_status_at_fetch': 'finished',
            'detail_fetched_at': (now-timedelta(hours=1)).isoformat(), 'detail_empty': False}
    assert _fresh(meta, 'finished', sport='basketball', start_time=now-timedelta(hours=5), now=now)


def test_old_partial_detail_is_retried_on_demand_without_polling_every_old_game():
    from collector.detail_enrich import _fresh
    now = datetime(2026, 9, 26, 5, 0)
    meta = {'parser_rev': PARSER_REV, 'detail_status_at_fetch': 'finished',
            'detail_fetched_at': (now-timedelta(hours=2)).isoformat(), 'detail_empty': False,
            '_football_detail_sync': {'sections': {'incidents': 4, 'statistics': 0, 'home_starters': 11, 'away_starters': 11}}}
    assert not _fresh(meta, 'finished', sport='football', start_time=now-timedelta(days=10), now=now)
    meta['_football_detail_sync']['sections']['statistics'] = 30
    assert _fresh(meta, 'finished', sport='football', start_time=now-timedelta(days=10), now=now)


def test_attempt_state_does_not_leak_into_public_payloads():
    from collector.provider import _public_value
    internal = {'id': 'same', 'score': {'home': 1, 'away': 0},
                '_football_detail_sync': {'error_types': ['TimeoutError'], 'sections': {}}}
    assert _public_value(internal) == {'id': 'same', 'score': {'home': 1, 'away': 0}}


def test_failed_attempt_does_not_rewrite_the_last_success_time(stored):
    from collector.football_detail_retry import note_attempt, STATE_KEY
    session, row, record, raw = _recent(stored, full_record=True)
    at = datetime(2026, 9, 26, 4, 0)
    meta = {}
    note_attempt(meta, record, received=True, now=at)
    successful = deepcopy(meta[STATE_KEY])
    note_attempt(meta, record, errors=['TimeoutError'], now=at+timedelta(minutes=5))
    failed = meta[STATE_KEY]
    assert failed['last_success_at'] == successful['last_success_at']
    assert failed['last_attempt_at'] != successful['last_attempt_at']
    assert failed['sections'] == successful['sections']
    assert failed['outcome'] == 'retry_pending'


def test_persisted_candidate_cursor_reaches_matches_beyond_the_query_cap(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football, JOB_KEY
    _worker_setup(db, monkeypatch)
    monkeypatch.setattr('collector.football_enrichment_cycle.MAX_CANDIDATES', 3)
    for name in ('a', 'b', 'c'):
        _row(db, name, fresh=True)
    _row(db, 'z', fresh=False)
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    first = warm_current_football(db, owner='c18-test-owner'); db.commit()
    assert first['detail_attempts'] == 0 and calls == []
    job = db.get(SportsCollectorJob, JOB_KEY)
    assert load_json(job.last_error)['after_detail_event'] == 'c'
    job.last_run_at = datetime.utcnow()-timedelta(seconds=31); db.commit()
    # Expunge/reload proves progress is stored, not a process-local Python cursor.
    db.expire_all()
    second = warm_current_football(db, owner='c18-test-owner'); db.commit()
    assert second['detail_attempts'] == 1 and calls == ['z']
    assert len({r.event_id for r in db.query(SportsEvent).all()}) == 4


def test_live_match_beyond_scan_page_can_still_be_enriched(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    monkeypatch.setattr('collector.football_enrichment_cycle.MAX_CANDIDATES', 2)
    _row(db, 'a', fresh=True); _row(db, 'b', fresh=True); _row(db, 'z-live', status='live')
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert calls == ['z-live']


def test_source_restrictions_are_not_relaxed_by_the_recovery_window(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    _row(db, 'denied', hours=25)
    monkeypatch.setattr('collector.provider._row_public_source_allowed', lambda *_: False)
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda db, r, **kw: calls.append(r.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert calls == []


def test_zero_budget_never_starts_a_detail_or_table_request(db, monkeypatch):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    _row(db, 'waiting')
    calls = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda *a, **kw: calls.append('detail'))
    monkeypatch.setattr('collector.standings_enrich.load_standings', lambda *a, **kw: calls.append('table'))
    result = warm_current_football(db, owner='c18-test-owner', budget_seconds=0)
    assert result['detail_attempts'] == 0 and calls == []
