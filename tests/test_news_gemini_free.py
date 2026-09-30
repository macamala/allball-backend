import httpx
import pytest

from bot import news_external_free as external, free_ai_router as router
from bot.news_budget import AiRequestBudget, ai_budget_scope


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', '1')
    monkeypatch.setenv('NEWS_GEMINI_FREE_ENABLED', '1')
    monkeypatch.setenv('GEMINI_API_KEY', 'fixture-secret')
    for key in ('GROQ_API_KEY', 'CLOUDFLARE_API_TOKEN', 'MISTRAL_API_KEY', 'ZAI_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(external, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(external, '_UNAVAILABLE', {p: set() for p in external._PURPOSES})
    monkeypatch.setattr(external, '_CURSOR', {p: 0 for p in external._PURPOSES})


@pytest.mark.parametrize('missing', ['NEWS_EXTERNAL_FREE_WRITERS_ENABLED', 'NEWS_GEMINI_FREE_ENABLED', 'GEMINI_API_KEY'])
def test_gemini_requires_explicit_free_project_opt_in(pool, monkeypatch, missing):
    monkeypatch.delenv(missing)
    assert not external.configured_identities()


@pytest.mark.parametrize('finish,expected', [('STOP', 'complete'), ('MAX_TOKENS', None), ('SAFETY', None)])
def test_native_transport_accounts_requests_and_rejects_incomplete_output(pool, monkeypatch, tmp_path, finish, expected):
    calls = []
    class Client:
        def __init__(self, **kwargs): assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, json={'candidates': [{'finishReason': finish, 'content': {'parts': [
                {'text': 'internal thought', 'thought': True}, {'text': 'complete'}]}}]})
    monkeypatch.setattr(external.httpx, 'Client', Client)
    budget = AiRequestBudget(1, str(tmp_path/'budget.sqlite'))
    with ai_budget_scope(budget):
        result, identity = external.completion(system='facts only', user='source', max_tokens=1800,
            purpose='validator', json_mode=True)
        assert result == expected
        assert external.completion(system='s', user='u', max_tokens=800)[0] is None
    assert budget.attempts == len(calls) == 1
    url, request = calls[0]
    assert url == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent'
    assert request['headers']['x-goog-api-key'] == 'fixture-secret'
    assert request['json']['generationConfig']['responseMimeType'] == 'application/json'
    assert not {'tools', 'cachedContent', 'serviceTier'} & request['json'].keys()


def test_gemini_never_approves_its_own_draft(pool, monkeypatch):
    monkeypatch.setattr(router, '_rate_limited', False)
    monkeypatch.setattr(router, '_xkiro_available', lambda: False)
    assert not router.free_ai_available()
    assert external._ordered_configs('validator', avoid_provider='gemini') == []
    monkeypatch.setattr(router, '_xkiro_available', lambda: True)
    assert router.free_ai_available()


def test_google_daily_quota_holds_provider_across_cycles_without_key_logs(pool, monkeypatch, caplog):
    monkeypatch.setattr(external.time, 'monotonic', lambda: 100.)
    external._http_failure('gemini', httpx.Response(429, json={'error': {
        'message': 'fixture-secret',
        'details': [{'retryDelay': '30s'}, {'violations': [
            {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}]}]}}))
    external.reset()
    assert not external.configured_identities()
    assert external._COOLDOWN_UNTIL['gemini'] > 160.
    assert 'daily_free_requests' in caplog.text
    assert 'fixture-secret' not in caplog.text


def test_google_minute_quota_preserves_explicit_retry_delay(pool, monkeypatch):
    monkeypatch.setattr(external.time, 'monotonic', lambda: 100.)
    external._http_failure('gemini', httpx.Response(429, json={'error': {'details': [
        {'violations': [{'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'}]},
        {'retryDelay': '40s'}]}}))
    assert external._COOLDOWN_UNTIL['gemini'] == 140.
