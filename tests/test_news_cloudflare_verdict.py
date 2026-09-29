import json

import httpx
import pytest

from bot import news_external_free as pool
from bot.news_budget import AiRequestBudget, ai_budget_scope


@pytest.mark.parametrize('shape', ['choice', 'object'])
def test_cloudflare_verdict_requests_json_and_preserves_rejection(monkeypatch, tmp_path, shape):
    verdict = {'source_type': 'news', 'approved': False,
               'unsupported_claims': ['Changed the player name'], 'changed_names': ['Kubo']}
    result = ({'response': verdict} if shape == 'object' else
              {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(verdict)}}]})
    requests = []

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            requests.append(kwargs['json'])
            return httpx.Response(200, json={'success': True, 'result': result})

    monkeypatch.setattr(pool.httpx, 'Client', Client)
    budget = AiRequestBudget(1, tmp_path/'ledger.db')
    with ai_budget_scope(budget):
        raw = pool._cloudflare({'account': 'a'*32, 'key': 'fixture-secret',
            'model': '@cf/qwen/qwen3-30b-a3b-fp8'}, 'Compare source and draft', 'source', 700, True)
    assert json.loads(raw) == verdict
    assert budget.attempts == len(requests) == 1
    assert requests[0]['response_format'] == {'type': 'json_object'}
    assert requests[0]['max_tokens'] == 1400


def test_cloudflare_incomplete_verdict_is_not_salvaged(monkeypatch, caplog):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            return httpx.Response(200, json={'success': True, 'result': {'choices': [
                {'finish_reason': 'length', 'message': {'content': '{"approved": true}',
                    'reasoning_content': 'private fixture reasoning'}}]}})

    monkeypatch.setattr(pool.httpx, 'Client', Client)
    monkeypatch.setattr(pool, 'reserve_ai_request', lambda: True)
    assert pool._cloudflare({'account': 'a'*32, 'key': 'fixture-secret',
        'model': '@cf/qwen/qwen3-30b-a3b-fp8'}, 'system', 'source', 700, True) is None
    assert 'unusable_completion finish=length json_mode=True' in caplog.text
    assert 'fixture-secret' not in caplog.text
    assert 'private fixture reasoning' not in caplog.text


def test_cloudflare_writer_format_and_budget_are_unchanged(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert 'response_format' not in kwargs['json']
            assert kwargs['json']['max_tokens'] == 1800
            return httpx.Response(200, json={'success': True, 'result': {'response': 'Draft for validation'}})

    monkeypatch.setattr(pool.httpx, 'Client', Client)
    monkeypatch.setattr(pool, 'reserve_ai_request', lambda: True)
    assert pool._cloudflare({'account': 'a'*32, 'key': 'fixture-secret',
        'model': '@cf/qwen/qwen3-30b-a3b-fp8'}, 'system', 'source', 1800, False) == 'Draft for validation'
