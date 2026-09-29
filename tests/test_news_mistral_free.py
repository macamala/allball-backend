"""Optional Free-account route: spending guard, transport and validator independence."""
import httpx
import pytest

from bot import news_external_free as external, free_ai_router as router
from bot.news_budget import AiRequestBudget, ai_budget_scope


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', '1')
    monkeypatch.setenv('NEWS_MISTRAL_FREE_ENABLED', '1')
    monkeypatch.setenv('MISTRAL_API_KEY', 'fixture-secret')
    for key in ('GROQ_API_KEY', 'CLOUDFLARE_API_TOKEN', 'NEWS_MISTRAL_MODEL'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(external, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(external, '_UNAVAILABLE', {p: set() for p in external._PURPOSES})
    monkeypatch.setattr(external, '_CURSOR', {p: 0 for p in external._PURPOSES})


@pytest.mark.parametrize('missing', ['NEWS_EXTERNAL_FREE_WRITERS_ENABLED',
    'NEWS_MISTRAL_FREE_ENABLED', 'MISTRAL_API_KEY'])
def test_route_requires_both_opt_ins_and_key(pool, monkeypatch, missing):
    monkeypatch.delenv(missing)
    monkeypatch.setattr(external, 'reserve_ai_request', lambda: pytest.fail('disabled route spent budget'))
    assert external.completion(system='s', user='u', max_tokens=800) == (None, ('unknown', 'unknown'))


@pytest.mark.parametrize('purpose,json_mode', [('writer', False), ('validator', True), ('translation', True)])
def test_transport_uses_fixed_endpoint_and_common_ledger(pool, monkeypatch, tmp_path, purpose, json_mode):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                'message': {'content': 'completed'}}]})
    monkeypatch.setattr(external.httpx, 'Client', Client)
    budget = AiRequestBudget(1, str(tmp_path/'quota.db'))
    with ai_budget_scope(budget):
        assert external.completion(system='source only', user='facts', max_tokens=1300,
            purpose=purpose, json_mode=json_mode) == ('completed', ('mistral', 'mistral-small-latest'))
        assert external.completion(system='s', user='u', max_tokens=1300, purpose=purpose)[0] is None
    assert len(calls) == budget.attempts == 1
    url, request = calls[0]
    assert url == 'https://api.mistral.ai/v1/chat/completions'
    assert request['headers']['Authorization'] == 'Bearer fixture-secret'
    payload = request['json']
    assert payload['max_tokens'] == 1300 and payload['stream'] is False
    assert 'max_completion_tokens' not in payload and 'reasoning_effort' not in payload
    if json_mode:
        assert payload['response_format'] == {'type': 'json_object'}
        assert 'JSON' in payload['messages'][0]['content']
    else:
        assert 'response_format' not in payload


def test_mistral_cannot_validate_itself_but_can_pair_with_xkiro(pool, monkeypatch):
    monkeypatch.setattr(router, '_rate_limited', False)
    monkeypatch.setattr(router, '_xkiro_available', lambda: False)
    assert not router.free_ai_available()
    assert external._ordered_configs('validator', avoid_provider='mistral') == []
    monkeypatch.setattr(router, '_xkiro_available', lambda: True)
    assert router.free_ai_available()
    assert [r['provider'] for r in external._ordered_configs('validator', avoid_provider='xkiro')] == ['mistral']


def test_quota_cooldown_survives_cycle_reset_without_logging_key(pool, monkeypatch, caplog):
    monkeypatch.setattr(external.time, 'monotonic', lambda: 100.)
    external._http_failure('mistral', httpx.Response(429, headers={'retry-after': '90'},
        json={'message': 'fixture-secret must not be logged'}))
    external.reset()
    assert not external.configured_identities('writer')
    assert not external.configured_identities('validator')
    assert not external.configured_identities('translation')
    assert external._COOLDOWN_UNTIL['mistral'] == 190.
    assert external._provider_ready('groq')
    assert 'fixture-secret' not in caplog.text


@pytest.mark.parametrize('choice', [
    {'finish_reason': 'length', 'message': {'content': 'truncated'}},
    {'finish_reason': 'stop', 'message': {'content': 'refused', 'refusal': 'cannot answer'}},
    {'finish_reason': 'stop', 'message': {'content': [{'text': 'unexpected shape'}]}},
])
def test_incomplete_or_unexpected_responses_fail_closed(choice):
    assert external._choice_text({'choices': [choice]}) is None


@pytest.mark.parametrize('message,dimension', [
    ('Service tier capacity exceeded for this model.', 'service_tier_capacity'),
    ('Tokens per month exceeded.', 'tokens_per_month'),
    ('Rate limit exceeded.', 'unknown'),
])
def test_top_level_mistral_quota_reason_is_visible_without_response_text(pool, monkeypatch, caplog, message, dimension):
    monkeypatch.setattr(external.time, 'monotonic', lambda: 100.)
    external._http_failure('mistral', httpx.Response(429, json={
        'message': message + ' fixture-secret', 'code': '1300', 'type': 'rate_limited'}))
    assert 'limit_dimension=' + dimension in caplog.text
    assert 'error_codes=[1300]' in caplog.text
    assert 'fixture-secret' not in caplog.text
    assert external._COOLDOWN_UNTIL['mistral'] == 700.
    external.reset()
    assert not external.configured_identities('writer')
    assert not external.configured_identities('validator')
