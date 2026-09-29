import httpx
import pytest

from bot import news_external_free as pool, free_ai_router as router
from bot.news_budget import AiRequestBudget, ai_budget_scope

PRIMARY = 'openai/gpt-oss-120b'
BACKUP = 'openai/gpt-oss-20b'


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED', '1')
    monkeypatch.setenv('GROQ_API_KEY', 'fixture-secret')
    monkeypatch.setenv('NEWS_GROQ_MODEL', PRIMARY)
    monkeypatch.setenv('NEWS_GROQ_WRITER_FALLBACK_MODELS', BACKUP)
    monkeypatch.delenv('NEWS_GROQ_WRITER_MODEL', raising=False)
    monkeypatch.delenv('CLOUDFLARE_API_TOKEN', raising=False)
    monkeypatch.delenv('MISTRAL_API_KEY', raising=False)
    monkeypatch.setattr(pool, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(pool, '_UNAVAILABLE', {p: set() for p in pool._PURPOSES})
    monkeypatch.setattr(pool, '_CURSOR', {p: 0 for p in pool._PURPOSES})


def quota(message, status=429):
    return httpx.Response(status, headers={'retry-after': '120'}, json={'error': {'message': message}})


def test_only_approved_explicit_writer_fallback_is_added(monkeypatch):
    assert pool.configured_identities('writer') == (('groq', PRIMARY), ('groq', BACKUP))
    assert pool.configured_identities('validator') == (('groq', PRIMARY),)
    assert pool.configured_identities('translation') == (('groq', PRIMARY),)
    monkeypatch.setenv('NEWS_GROQ_WRITER_FALLBACK_MODELS', 'llama-3.3-70b-versatile,paid-model')
    assert pool.configured_identities('writer') == (('groq', PRIMARY),)


def test_primary_quota_can_be_reserved_for_validation_without_self_approval(monkeypatch):
    monkeypatch.setenv('NEWS_GROQ_WRITER_MODEL', BACKUP)
    assert pool.configured_identities('writer') == (('groq', BACKUP),)
    assert pool.configured_identities('validator') == (('groq', PRIMARY),)
    assert pool._ordered_configs('validator', avoid_provider='groq') == []
    monkeypatch.setattr(router, '_rate_limited', False)
    monkeypatch.setattr(router, '_xkiro_available', lambda: False)
    assert not router.free_ai_available()
    monkeypatch.setenv('NEWS_GROQ_WRITER_MODEL', 'unapproved-paid-model')
    assert pool.configured_identities('writer') == (('groq', PRIMARY), ('groq', BACKUP))


def test_explicit_model_quota_is_respected_across_purposes_and_cycles(monkeypatch, caplog):
    monkeypatch.setattr(pool.time, 'monotonic', lambda: 100.)
    pool._http_failure('groq', quota(f"Rate limit reached for model `{PRIMARY}` on tokens per day (TPD). fixture-secret"), model=PRIMARY)
    pool.reset()
    assert pool.configured_identities('writer') == (('groq', BACKUP),)
    assert pool.configured_identities('validator') == ()
    assert pool._COOLDOWN_UNTIL[pool._route_key('groq', PRIMARY)] == 220.
    assert 'fixture-secret' not in caplog.text
    monkeypatch.setattr(pool.time, 'monotonic', lambda: 221.)
    assert len(pool.configured_identities('writer')) == 2


def test_billing_help_url_does_not_turn_explicit_model_quota_into_account_limit():
    pool._http_failure('groq', quota(f'Rate limit reached for model `{PRIMARY}` on tokens per day (TPD). '
        'Please try again later. Upgrade at https://console.groq.com/settings/billing'), model=PRIMARY)
    pool.reset()
    assert pool.configured_identities('writer') == (('groq', BACKUP),)
    assert pool.configured_identities('validator') == ()


@pytest.mark.parametrize('status,message', [
    (401, 'Invalid credential'), (403, f'model {PRIMARY} access denied'),
    (429, 'Organization tokens per day (TPD) exhausted'),
    (429, f'Billing budget exceeded for model {PRIMARY}'),
    (429, f'Organization tokens per day (TPD) exhausted on request for model {PRIMARY}.'),
    (429, f'Rate limit reached for model {PRIMARY} on tokens per day (TPD). Billing credit exhausted.'),
    (429, 'Rate limit reached for model other-model on tokens per day (TPD).'),
])
def test_auth_billing_and_unscoped_limits_stop_all_models(status, message):
    pool._http_failure('groq', quota(message, status), model=PRIMARY)
    pool.reset()
    assert pool.configured_identities('writer') == ()
    assert 'groq' in pool._COOLDOWN_UNTIL


@pytest.mark.parametrize('specific,expected_calls', [(True, 2), (False, 1)])
def test_transport_respects_hold_scope_and_charges_each_request(monkeypatch, tmp_path, specific, expected_calls):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            model = kwargs['json']['model']; calls.append(model)
            assert url == 'https://api.groq.com/openai/v1/chat/completions'
            if len(calls) == 1:
                return quota(f'Rate limit reached for model {PRIMARY} on tokens per day (TPD).' if specific else 'Organization daily quota exceeded')
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': 'draft for independent validation'}}]})
    monkeypatch.setattr(pool.httpx, 'Client', Client)
    budget = AiRequestBudget(2, tmp_path/'ledger.db')
    with ai_budget_scope(budget):
        value, identity = pool.completion(system='source-only', user='facts', max_tokens=1800)
    assert budget.attempts == len(calls) == expected_calls
    if specific:
        assert identity == ('groq', BACKUP) and value
    else:
        assert value is None


def test_two_groq_models_are_not_two_independent_providers(monkeypatch):
    monkeypatch.setattr(router, '_rate_limited', False)
    monkeypatch.setattr(router, '_xkiro_available', lambda: False)
    assert not router.free_ai_available()
    assert pool._ordered_configs('validator', avoid_provider='groq') == []
    monkeypatch.setattr(router, '_xkiro_available', lambda: True)
    assert router.free_ai_available()
