import logging

from bot import news_openai as lane


def test_preflight_lists_models_without_paid_request_or_secret_log(monkeypatch, caplog):
    monkeypatch.setenv('OPENAI_API_KEY', 'private-fixture-token')
    monkeypatch.setattr(lane, '_catalog', (0, False))
    calls = []
    class Reply:
        status_code = 200
        def json(self): return {'data': [{'id': 'gpt-6-luna'}, {'id': 'gpt-6-sol'}]}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs): calls.append(url); return Reply()
    monkeypatch.setattr(lane.httpx, 'Client', Client)
    with caplog.at_level(logging.INFO):
        assert lane.model_preflight()
        assert lane.model_preflight()
    assert calls == ['https://api.openai.com/v1/models']
    assert 'private-fixture-token' not in caplog.text


def test_missing_key_disables_only_openai(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    assert not lane.model_preflight(force=True)
