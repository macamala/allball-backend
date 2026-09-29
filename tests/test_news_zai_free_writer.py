"""The opt-in free Z.ai writer cannot spend on another model or approve itself."""
import httpx
import pytest

from bot import news_external_free as pool, free_ai_router as router
from bot.news_budget import AiRequestBudget, ai_budget_scope


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', '1')
    monkeypatch.setenv('NEWS_ZAI_FREE_WRITER_ENABLED', '1')
    monkeypatch.setenv('ZAI_API_KEY', 'fixture-secret')
    for key in ('GROQ_API_KEY', 'CLOUDFLARE_API_TOKEN', 'MISTRAL_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(pool, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(pool, '_UNAVAILABLE', {p: set() for p in pool._PURPOSES})
    monkeypatch.setattr(pool, '_CURSOR', {p: 0 for p in pool._PURPOSES})


@pytest.mark.parametrize('missing', ['NEWS_EXTERNAL_FREE_WRITERS_ENABLED', 'NEWS_ZAI_FREE_WRITER_ENABLED', 'ZAI_API_KEY'])
def test_no_implicit_activation(monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert pool.configured_identities('writer') == ()


def test_only_fixed_free_writer_is_exposed(monkeypatch):
    monkeypatch.setenv('NEWS_ZAI_MODEL', 'glm-4.7-flashx')
    assert pool.configured_identities('writer') == (('zai', 'glm-4.7-flash'),)
    assert pool.configured_identities('validator') == ()
    assert pool.configured_identities('translation') == ()
    monkeypatch.setattr(router, '_rate_limited', False)
    monkeypatch.setattr(router, '_xkiro_available', lambda: False)
    assert not router.free_ai_available()
    monkeypatch.setattr(router, '_xkiro_available', lambda: True)
    assert router.free_ai_available()


def test_fixed_endpoint_payload_and_shared_request_ledger(monkeypatch, tmp_path):
    calls = []
    class Client:
        def __init__(self, **kwargs): assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'unvalidated draft'}}]})
    monkeypatch.setattr(pool.httpx, 'Client', Client)
    budget = AiRequestBudget(1, tmp_path/'ledger.db')
    with ai_budget_scope(budget):
        assert pool.completion(system='source-only', user='facts', max_tokens=1800) == ('unvalidated draft', ('zai', 'glm-4.7-flash'))
        assert pool.completion(system='s', user='u', max_tokens=1800)[0] is None
    assert len(calls) == budget.attempts == 1
    url, request = calls[0]
    assert url == 'https://api.z.ai/api/paas/v4/chat/completions'
    assert request['json']['model'] == 'glm-4.7-flash'
    assert request['json']['thinking'] == {'type': 'disabled'}
    assert request['json']['max_tokens'] == 1800
    assert 'tools' not in request['json']


@pytest.mark.parametrize('status', [401, 403, 429])
def test_failure_holds_provider_across_cycles_and_never_logs_secret(monkeypatch, caplog, status):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append(url)
            return httpx.Response(status, headers={'retry-after': '120'}, json={'error': {'code': '1302', 'message': 'fixture-secret'}})
    monkeypatch.setattr(pool.httpx, 'Client', Client)
    monkeypatch.setattr(pool, 'reserve_ai_request', lambda: True)
    monkeypatch.setattr(pool.time, 'monotonic', lambda: 100.)
    assert pool.completion(system='s', user='u', max_tokens=1800)[0] is None
    pool.reset()
    assert pool.completion(system='s', user='u', max_tokens=1800)[0] is None
    assert len(calls) == 1 and pool._COOLDOWN_UNTIL['zai'] == 220.
    assert 'error_code=1302' in caplog.text and 'fixture-secret' not in caplog.text


def test_paid_model_rejected_before_spending(monkeypatch):
    monkeypatch.setattr(pool, 'reserve_ai_request', lambda: pytest.fail('paid model spent budget'))
    assert pool._zai({'model': 'glm-4.7-flashx'}, 's', 'u', 1800, False) is None
