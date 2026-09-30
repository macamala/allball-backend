"""No real credentials/provider requests; durable quota and publication gates."""
import copy
import sys
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot import news_deepl as deepl, news_translations as translations
from tests.test_news_translations import SOURCE


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('NEWS_DEEPL_FREE_ENABLED', '1')
    monkeypatch.setenv('DEEPL_API_KEY', 'fixture:fx')
    monkeypatch.setattr(deepl, '_cooldown_until', 0.)
    monkeypatch.setattr('bot.news_budget.ai_budget_exhausted', lambda: False)
    monkeypatch.setattr(translations, 'free_json_completion', lambda *args, **kw: '{"valid":true,"issues":[]}')


def test_only_explicit_free_key_is_enabled(enabled, monkeypatch):
    assert deepl.deepl_enabled()
    monkeypatch.setenv('DEEPL_API_KEY', 'pro-fixture')
    assert not deepl.deepl_enabled()
    monkeypatch.setenv('DEEPL_API_KEY', 'fixture:fx')
    monkeypatch.setenv('NEWS_DEEPL_FREE_ENABLED', '0')
    assert not deepl.deepl_enabled()


def test_xml_locks_names_numbers_acronyms_and_preserves_paragraphs():
    source = {**SOURCE, 'body': SOURCE['body'] + '\n\nUEFA confirmed 18:45 & no change.'}
    documents, locks = deepl._xml_fields(source)
    for field, document, locked in zip(deepl.FIELDS, documents, locks):
        assert deepl._restore_xml(document, locked, 'de') == source[field].replace('18th', '18')
    assert 'UEFA' in locks[2].values() and '18:45' in locks[2].values()
    assert 'Southport United' in locks[2].values()
    assert '&amp;' in documents[2]


@pytest.mark.parametrize('mutation', ['missing', 'changed', 'duplicate', 'foreign-tag', 'doctype'])
def test_xml_fails_closed_for_missing_changed_or_injected_locks(mutation):
    value = '<text>Result <lock id="0">2-1</lock> confirmed.</text>'
    if mutation == 'missing': value = '<text>Result confirmed.</text>'
    if mutation == 'changed': value = value.replace('2-1', '3-1')
    if mutation == 'duplicate': value = value.replace('</text>', '<lock id="0">2-1</lock></text>')
    if mutation == 'foreign-tag': value = value.replace('Result', '<script>Result</script>')
    if mutation == 'doctype': value = '<!DOCTYPE text>' + value
    assert deepl._restore_xml(value, {'0': '2-1'}, 'sr') is None


def test_serbian_script_conversion_keeps_protected_names_and_digraph_case():
    value = '<text>Љубав и ЊЕГОВ тим: <lock id="0">Luka Marin</lock> — Џек.</text>'
    assert deepl._restore_xml(value, {'0': 'Luka Marin'}, 'sr') == 'Ljubav i NJEGOV tim: Luka Marin — Džek.'
    assert deepl._latin('Ђорђе Ћирић, Шабац, Чачак, Жарко.') == 'Đorđe Ćirić, Šabac, Čačak, Žarko.'


def test_character_reservations_survive_sessions_and_never_exceed_daily_limit(monkeypatch, tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path/'deepl.sqlite'))
    factory = sessionmaker(bind=engine)
    monkeypatch.setitem(sys.modules, 'database', SimpleNamespace(SessionLocal=factory))
    monkeypatch.setenv('NEWS_DEEPL_MAX_CHARACTERS_PER_DAY', '100')
    assert deepl._character_ledger(60)
    assert deepl._character_ledger(60, reserve=True)
    assert not deepl._character_ledger(60)
    assert not deepl._character_ledger(60, reserve=True)
    assert deepl._character_ledger(40, reserve=True)
    assert not deepl._character_ledger(1, reserve=True)
    assert not deepl._character_ledger(0, reserve=True)
    engine.dispose()


def test_transport_uses_only_free_host_and_does_not_follow_redirects(enabled, monkeypatch, caplog):
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=456)
    monkeypatch.setattr(deepl.requests, 'request', request)
    assert deepl._request('GET', '/usage') is None
    assert deepl._request('GET', '/usage') is None
    assert len(calls) == 1
    assert calls[0][1] == 'https://api-free.deepl.com/v2/usage'
    assert calls[0][2]['allow_redirects'] is False
    assert calls[0][2]['headers']['Authorization'] == 'DeepL-Auth-Key fixture:fx'
    assert 'fixture:fx' not in caplog.text


@pytest.mark.parametrize('bad', [None, 'monthly', 'numeric', 'lock'])
def test_complete_batch_keeps_existing_validation_and_reserves_before_http(enabled, monkeypatch, bad):
    calls = []
    monkeypatch.setattr(deepl, '_character_ledger', lambda n, reserve=False: calls.append(('reserve' if reserve else 'check', n)) or True)
    def request(method, path, **kwargs):
        calls.append((method, path))
        if path == '/usage':
            return {'character_count': 0, 'character_limit': 1 if bad == 'monthly' else 1000000}
        assert kwargs['json']['tag_handling_version'] == 'v1'
        docs = kwargs['json']['text']
        if kwargs['json']['target_lang'] == 'DE':
            if bad == 'numeric': docs = [v.replace('</text>', ' 999</text>') for v in docs]
            if bad == 'lock': docs = [v.replace('id="0"', 'id="unknown"') for v in docs]
        return {'translations': [{'text': value} for value in docs]}
    monkeypatch.setattr(deepl, '_request', request)
    result = deepl.translate_source(SOURCE)
    if bad:
        assert result is None
    else:
        expected = {**SOURCE, 'body': SOURCE['body'].replace('18th', '18')}
        assert result == {language: expected for language in deepl.TARGETS}
    if bad == 'monthly':
        assert not any(c[0] in ('POST', 'reserve') for c in calls)
    else:
        assert next(i for i,c in enumerate(calls) if c[0] == 'reserve') < next(i for i,c in enumerate(calls) if c[0] == 'POST')


def test_deepl_failure_tries_free_translation_without_modifying_english(enabled, monkeypatch):
    article = SimpleNamespace(id=1, **SOURCE, ai_content=None)
    article.content = article.body
    before = copy.deepcopy(article.__dict__)
    monkeypatch.setattr(deepl, 'translate_source', lambda source: None)
    calls = []
    monkeypatch.setattr(translations, 'free_json_completion', lambda *a, **k: calls.append('free') or None)
    monkeypatch.setenv('OPENAI_ENABLED', 'false')
    assert translations.translate_article_payload(article) is None
    assert article.__dict__ == before
    assert calls == ['free']


def test_single_language_validation_stays_strict():
    assert translations._validate(SOURCE, {'de': SOURCE}, languages=('de',))
    assert translations._validate(SOURCE, {'sr': {**SOURCE, 'summary': 'Ћирилица'}}, languages=('sr',)) is None
    assert translations._validate(SOURCE, {'de': SOURCE}) is None
    assert translations._validate(SOURCE, {}, languages=()) is None


def test_v1_locked_name_preserves_world_cup_and_word_boundary():
    # V1 keeps real protected text intact; a translated name is still rejected.
    response = '<text>Селекција женске фудбалске репрезентације Енглеске за <lock id="0">World Cup</lock>плеј-оф против Грчке</text>'
    restored = deepl._restore_xml(response, {'0': 'World Cup'}, 'sr')
    assert restored == 'Selekcija ženske fudbalske reprezentacije Engleske za World Cup plej-of protiv Grčke'
    changed = response.replace('World Cup', 'Светског првенства')
    assert deepl._restore_xml(changed, {'0': 'World Cup'}, 'sr') is None


def test_adjacent_locks_keep_numeric_word_boundaries():
    raw = '<text><lock id="0">World Cup</lock><lock id="1">2026</lock></text>'
    assert deepl._restore_xml(raw, {'0': 'World Cup', '1': '2026'}, 'de') == 'World Cup 2026'


def test_names_never_span_sentence_boundaries_and_short_forms_are_locked():
    source = {'title': 'Roma keep Dybala and Molina from Messi farewell',
              'summary': 'AS Roma explained Paulo Dybala, Nahuel Molina and Lionel Messi.',
              'body': "The date is 6 October. Roma play on 11 October. Gian Piero Gasperini's team won."}
    documents, locks = deepl._xml_fields(source)
    assert {'Roma', 'Dybala', 'Molina', 'Messi'} <= set(locks[0].values())
    assert 'October. Roma' not in locks[2].values()
    assert 'Gian Piero Gasperini' in locks[2].values()


def test_only_punctuation_may_move_inside_a_protected_token():
    raw = '<text>Игра <lock id="0">11.</lock> октобра.</text>'
    assert deepl._restore_xml(raw, {'0': '11'}, 'sr') == 'Igra 11. oktobra.'
    assert deepl._restore_xml(raw.replace('11.', '1110'), {'0': '11'}, 'sr') is None
    assert deepl._restore_xml(raw.replace('11.', '11injured'), {'0': '11'}, 'sr') is None


@pytest.mark.parametrize('response', [None, '{}', '{"valid":false,"issues":["sr: changed team"]}',
    '{"valid":true}', '{"valid":true,"issues":["sr: uncertainty"]}'])
def test_translation_semantics_fail_closed(enabled, monkeypatch, response):
    monkeypatch.setattr(translations, 'free_json_completion', lambda *a, **kw: response)
    assert not deepl._semantic_validation(SOURCE, {'sr': SOURCE})


def test_no_translation_characters_spent_without_semantic_allowance(enabled, monkeypatch):
    monkeypatch.setattr('bot.news_budget.ai_budget_exhausted', lambda: True)
    monkeypatch.setattr(deepl, '_character_ledger', lambda *a, **kw: pytest.fail('spent characters'))
    assert deepl.translate_source(SOURCE) is None


def test_english_ordinal_suffix_is_localized_without_changing_value():
    raw = '<text>U <lock id="0">37th</lock>-oj minuti i <lock id="1">72nd</lock>. minuti.</text>'
    value = deepl._restore_xml(raw, {'0': '37th', '1': '72nd'}, 'sr')
    assert value == 'U 37-oj minuti i 72. minuti.'
    assert translations._numbers(value) == {'37', '72'}

def test_real_v2_sentence_fragment_inside_lock_is_still_rejected():
    raw = '<text>Tim <lock id="0">rangiran na 49th mestu</lock>.</text>'
    assert deepl._restore_xml(raw, {'0': '49th'}, 'sr') is None
