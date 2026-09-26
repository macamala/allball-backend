"""Do not make recovery frequent at the expense of identity or stored lineups."""
from copy import deepcopy
import pytest
from collector.adapters import FetchResult
from collector.detail_enrich import enrich_event_row, fetch_family_detail
from collector.util import load_json, dump_json
from tests.test_c18_finished_detail_recovery import _recent, _score_identity, _worker_setup, _row
from tests.test_fotmob_match_centre import stored, source
from tests.test_c15_live_tables import db


@pytest.mark.parametrize('mismatch', ['home', 'away', 'kickoff', 'missing_identity'])
def test_empty_cache_never_accepts_wrong_or_unverified_football_match(stored, mismatch):
    session, row, record, raw = _recent(stored)
    if mismatch in ('home', 'away'):
        raw['general'][mismatch + 'Team']['name'] = 'Different team'
    elif mismatch == 'kickoff':
        raw['general']['matchTimeUTCDate'] = '2020-01-01T00:00:00Z'
    else:
        del raw['general']['matchTimeUTCDate']
    before = _score_identity(row)
    enrich_event_row(session, row, getter=lambda _: FetchResult(ok=True, payload=deepcopy(raw)))
    assert not load_json(record.statistics_json)
    assert not load_json(record.incidents_json)
    assert not load_json(record.lineups_json)
    assert _score_identity(row) == before


def test_partial_final_lineup_does_not_erase_the_previously_observed_other_side(stored):
    session, row, record, raw = _recent(stored, full_record=True)
    record.lineups_json = dump_json({'confirmed': True,
        'home': {'start': [{'id': '10', 'name': 'First Player'}], 'formation': '4-3-3'},
        'away': {'start': [{'id': '20', 'name': 'Scorer'}], 'formation': '4-4-2'}})
    before = _score_identity(row)
    del raw['content']['lineup']['awayTeam']
    enrich_event_row(session, row, getter=lambda _: FetchResult(ok=True, payload=deepcopy(raw)))
    lineup = load_json(record.lineups_json)
    assert lineup['away']['start'] == [{'id': '20', 'name': 'Scorer'}]
    assert str(lineup['home']['start'][0]['id']) == '10'
    assert lineup['home']['formation'] == '4-3-3'
    assert lineup['confirmed'] is True
    assert _score_identity(row) == before


@pytest.mark.parametrize('status', ['cancelled', 'canceled', 'abandoned', 'postponed', 'awarded'])
def test_nonplayed_terminal_rows_do_not_consume_finished_repair_slots(db, monkeypatch, status):
    from collector.football_enrichment_cycle import warm_current_football
    _worker_setup(db, monkeypatch)
    _row(db, 'a-nonplayed', status=status)
    _row(db, 'b-final', status='finished')
    seen = []
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row', lambda _db, row, **kw: seen.append(row.event_id))
    warm_current_football(db, owner='c18-test-owner')
    assert seen == ['b-final']


def test_failed_sofa_component_does_not_discard_other_successful_components():
    def getter(url):
        if url.endswith('/incidents'):
            raise TimeoutError('private secret should not be copied')
        if url.endswith('/statistics'):
            return FetchResult(ok=True, payload={'statistics': [{'period': 'ALL', 'groups': [
                {'statisticsItems': [{'name': 'Ball possession', 'home': '51%', 'away': '49%'}]}]}]})
        return FetchResult(ok=True, payload={'event': {'venue': {'stadium': {'name': 'Known stadium'}}}})
    result = fetch_family_detail('sofascore-web', '100', getter=getter, sport='football')
    assert result['statistics'][0]['home'] == '51%'
    assert result['venue'] == 'Known stadium'
    assert 'private secret' not in repr(result)


def test_final_roster_corrections_replace_players_without_mutating_either_input():
    from collector.football_detail_retry import retain_final_lineup_sections
    current = {'confirmed': True, 'home': {'start': [{'id': 'old', 'name': 'Withdrawn'}]},
               'away': {'start': [{'id': 'away', 'name': 'Away'}]}}
    incoming = {'confirmed': False, 'home': {'start': [{'id': 'new', 'name': 'Replacement'}]}, 'away': {}}
    expected_current, expected_incoming = deepcopy(current), deepcopy(incoming)
    result = retain_final_lineup_sections(current, incoming)
    assert result['home']['start'] == [{'id': 'new', 'name': 'Replacement'}]
    assert result['away'] == current['away'] and result['confirmed'] is False
    result['home']['start'][0]['name'] = 'Only result edited'
    assert current == expected_current and incoming == expected_incoming


def test_other_sport_component_exceptions_keep_the_existing_policy():
    with pytest.raises(TimeoutError):
        fetch_family_detail('sofascore-web', '100', sport='basketball',
            getter=lambda _: (_ for _ in ()).throw(TimeoutError('temporary')))


def test_wrong_football_detail_retains_good_cache_then_accepts_verified_retry(stored):
    from datetime import datetime, timedelta
    session, row, record, raw = _recent(stored, full_record=True)
    before = (record.incidents_json, record.statistics_json, record.lineups_json, _score_identity(row))
    wrong = deepcopy(raw);wrong['general']['homeTeam']['name'] = 'Wrong team'
    calls = []
    enrich_event_row(session, row, getter=lambda url: calls.append(url) or FetchResult(ok=True, payload=wrong))
    assert (record.incidents_json, record.statistics_json, record.lineups_json, _score_identity(row)) == before
    enrich_event_row(session, row, getter=lambda url: calls.append(url) or FetchResult(ok=True, payload=wrong))
    assert len(calls) == 1
    meta = load_json(row.extra_json);meta['detail_fetched_at'] = (datetime.utcnow()-timedelta(seconds=121)).isoformat()
    row.extra_json = dump_json(meta)
    enrich_event_row(session, row, getter=lambda url: calls.append(url) or FetchResult(ok=True, payload=deepcopy(raw)))
    assert len(calls) == 2 and load_json(record.statistics_json)[0]['label'] == 'Total shots'
    assert _score_identity(row) == before[-1]
