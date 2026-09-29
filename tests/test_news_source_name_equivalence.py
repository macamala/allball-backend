import json

import pytest

from bot import news_fact_guard as guard, free_ai_router as router, news_external_free as pool


SOURCE = ('Стефан Гудељ је на листи, поред Кубарсија из Барселоне, '
          'Жеремија Жакеа из Ливерпула и Дина Хујсена из Реал Мадрида.')


def test_audited_name_evidence_does_not_add_missing_people_or_biography():
    pairs = guard.source_name_equivalences(SOURCE)
    assert pairs == ('Стефан Гудељ = Stefan Gudelj; Кубарсија = Cubarsí; '
                     'Жеремија Жакеа = Jeremy Jacquet; Дина Хујсена = Dean Huijsen')
    assert 'Pau' not in pairs  # source attests surname only
    assert 'Liverpool' not in pairs and 'Real Madrid' not in pairs
    assert guard.source_name_equivalences('ПСЕВДОКубарсија НЕЖеремија Жакеа ПСЕВДОДина Хујсена') == ''
    assert guard.source_name_equivalences('Unrelated football source') == ''


@pytest.mark.parametrize('bad,reason', [('Kubarski','Cubarsí'), ('Dean Huysen','Dean Huijsen')])
def test_similar_wrong_spellings_remain_rejected_before_semantic_validation(bad, reason):
    assert guard._serbian_transcription_reason(SOURCE, bad) == 'source_name_spelling:'+reason
    assert guard._serbian_transcription_reason(SOURCE, 'Stefan Gudelj, Cubarsi, Jeremy Jacquet and Dean Huijsen') is None


@pytest.mark.parametrize('approved', [True, False])
def test_validator_receives_matched_equivalences_but_controls_the_verdict(monkeypatch, approved):
    writer = router._LAST_WRITER.set(('cloudflare','fixture'))
    calls = []
    def complete(**kwargs):
        calls.append(kwargs)
        assert kwargs['avoid_provider'] == 'cloudflare'
        return json.dumps({'source_type':'news','approved':approved,
            'unsupported_claims':[],'changed_names':[] if approved else ['Kubo']}), ('groq','fixture')
    monkeypatch.setattr(pool,'completion',complete)
    try:
        result = router.validate_free_story('Гудељ на листи',SOURCE,'Gudelj included','Summary','Draft')
    finally:
        router._LAST_WRITER.reset(writer)
    assert result == ((True,'ok') if approved else (False,'validator-changed-name'))
    assert 'Кубарсија = Cubarsí' in calls[0]['user']
    assert 'Do not infer a club or biography from a name.' in calls[0]['user']
