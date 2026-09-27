import json

import bot.free_ai_router as free_ai
from bot.news_policy import original_draft_reason, protected_proper_names


def test_free_ai_route_requires_key_and_explicit_free_model_ids(monkeypatch):
    monkeypatch.setattr(free_ai, '_free_catalog_model', lambda model: True)
    monkeypatch.setattr(free_ai, '_free_tokens_available', lambda: True)
    monkeypatch.delenv('XKIRO_API_KEY', raising=False)
    assert not free_ai.free_ai_available()

    monkeypatch.setenv('XKIRO_API_KEY', 'fixture-key')
    monkeypatch.setenv('NEWS_XKIRO_WRITER_MODEL', 'qwen/qwen3.5-397b-a17b')
    monkeypatch.setenv('NEWS_XKIRO_VALIDATOR_MODEL', 'qwen/qwen3.5-397b-a17b:free')
    assert not free_ai.free_ai_available()

    monkeypatch.setenv('NEWS_XKIRO_WRITER_MODEL', 'qwen/qwen3.5-397b-a17b:free')
    assert free_ai.free_ai_available()



def test_free_model_requires_live_free_access_tier(monkeypatch):
    model='qwen/qwen3.5-397b-a17b:free'
    monkeypatch.setattr(free_ai, '_catalog_rows', lambda: [{
        'id': model,
        'access_tier': 'free',
        'pricing': {'input': 99, 'output': 99},
    }])
    assert free_ai._free_catalog_model(model)

    monkeypatch.setattr(free_ai, '_catalog_rows', lambda: [{
        'id': model,
        'access_tier': 'paid',
    }])
    assert not free_ai._free_catalog_model(model)

    monkeypatch.setattr(free_ai, '_catalog_rows', lambda: [{
        'id': model,
        'access_tier': 'free',
        'pay_as_you_go': True,
    }])
    assert not free_ai._free_catalog_model(model)

    monkeypatch.setattr(free_ai, '_catalog_rows', lambda: None)
    assert not free_ai._free_catalog_model(model)


def test_free_token_counter_fails_closed_at_zero(monkeypatch):
    class Response:
        status_code=200
        def json(self):
            return {'free_tokens': {'remaining': 0}}
    class Client:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,*args,**kwargs): return Response()

    free_ai._usage_cache.update(at=0.0, remaining=None, verified=False)
    monkeypatch.setenv('XKIRO_API_KEY','fixture-key')
    monkeypatch.setattr(free_ai.httpx,'Client',Client)
    assert not free_ai._free_tokens_available()


def test_free_validator_fails_closed_on_bad_or_unsupported_output(monkeypatch):
    monkeypatch.setenv('NEWS_XKIRO_VALIDATOR_MODEL', 'qwen/qwen3.5-397b-a17b:free')
    monkeypatch.setattr(free_ai, '_completion', lambda **kwargs: 'not json')
    assert free_ai.validate_free_story('A', 'facts', 'B', 'summary', 'body') == (False, 'validator-invalid-json')

    rejected=json.dumps({
        'approved': False,
        'unsupported_claims': ['invented early lead'],
        'changed_names': [],
    })
    monkeypatch.setattr(free_ai, '_completion', lambda **kwargs: rejected)
    assert free_ai.validate_free_story('A', 'facts', 'B', 'summary', 'body') == (False, 'validator-unsupported-claim')

    renamed=json.dumps({
        'approved': False,
        'unsupported_claims': [],
        'changed_names': ['Northbridge Athletic -> North Club'],
    })
    monkeypatch.setattr(free_ai, '_completion', lambda **kwargs: renamed)
    assert free_ai.validate_free_story('A', 'facts', 'B', 'summary', 'body') == (False, 'validator-changed-name')


def test_free_validator_accepts_only_exact_clean_shape(monkeypatch):
    monkeypatch.setenv('NEWS_XKIRO_VALIDATOR_MODEL', 'qwen/qwen3.5-397b-a17b:free')
    approved=json.dumps({'approved': True, 'unsupported_claims': [], 'changed_names': []})
    monkeypatch.setattr(free_ai, '_completion', lambda **kwargs: approved)
    assert free_ai.validate_free_story('A', 'facts', 'B', 'summary', 'body') == (True, 'ok')

    extra=json.dumps({'approved': True, 'unsupported_claims': [], 'changed_names': [], 'note': 'ok'})
    monkeypatch.setattr(free_ai, '_completion', lambda **kwargs: extra)
    assert free_ai.validate_free_story('A', 'facts', 'B', 'summary', 'body') == (False, 'validator-invalid-shape')


def test_protected_names_are_extracted_but_changed_name_rejection_is_semantic():
    source_title='Northbridge Athletic beat Southport United in Summer Shield'
    source_body=(
        'Northbridge Athletic beat Southport United in the Summer Shield practice match. '
        'Luka Marin scored before Daniel Okafor added another. Javier Costa replied late.'
    )
    names=protected_proper_names(source_title+'\n'+source_body)
    assert 'Northbridge Athletic' in names
    assert 'Southport United' in names
    assert 'Summer Shield' in names
    assert 'Luka Marin' in names

    body=(
        'Northbridge Athletic controlled enough of the supplied match facts to finish ahead of Southport United. '
        'Luka Marin was listed among the scorers, Daniel Okafor also scored, and Javier Costa replied. '
        'The Summer Shield practice match ended with Northbridge Athletic ahead, based only on the supplied report.'
    )
    good={'title':'Northbridge Athletic finish ahead of Southport United',
          'summary':'Northbridge Athletic finished ahead in the Summer Shield practice match.',
          'body':body}
    assert original_draft_reason(good, source_title, source_body) is None

    renamed=dict(good)
    renamed['body']=body.replace('Southport United', 'Southport Club')
    renamed['title']='Northbridge Athletic finish ahead'
    renamed['summary']='Northbridge Athletic finished ahead in the Summer Shield practice match.'
    # The brittle regex gate was intentionally removed from deterministic admission.
    # The xKiro semantic validator above is the authority for changed proper names.
    assert original_draft_reason(renamed, source_title, source_body) is None
