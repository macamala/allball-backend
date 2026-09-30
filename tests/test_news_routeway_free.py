import httpx
import pytest
from bot import news_external_free as external
from bot.news_budget import AiRequestBudget, ai_budget_scope

@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setenv('NEWS_EXTERNAL_FREE_WRITERS_ENABLED','1')
    monkeypatch.setenv('NEWS_ROUTEWAY_FREE_ENABLED','1')
    monkeypatch.setenv('ROUTEWAY_API_KEY','fixture-secret')
    for name in ('GROQ_API_KEY','CLOUDFLARE_API_TOKEN','GEMINI_API_KEY','MISTRAL_API_KEY','ZAI_API_KEY'):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setattr(external,'_COOLDOWN_UNTIL',{})
    monkeypatch.setattr(external,'_ROUTEWAY_VERIFIED_UNTIL',0.)
    monkeypatch.setattr(external,'_UNAVAILABLE',{p:set() for p in external._PURPOSES})
    monkeypatch.setattr(external,'_CURSOR',{p:0 for p in external._PURPOSES})

@pytest.mark.parametrize('missing',['NEWS_EXTERNAL_FREE_WRITERS_ENABLED','NEWS_ROUTEWAY_FREE_ENABLED','ROUTEWAY_API_KEY'])
def test_explicit_optin(pool,monkeypatch,missing):
    monkeypatch.delenv(missing)
    assert external._config('routeway') is None

@pytest.mark.parametrize('price,available,finish,returned_model,expected',[
    (0,True,'stop',external._ROUTEWAY_FREE_MODEL,'{"ok":true}'),
    (0,True,'length',external._ROUTEWAY_FREE_MODEL,None),
    (0,True,'stop','paid-alias',None),
    (0.1,True,'stop',external._ROUTEWAY_FREE_MODEL,None),
    (None,True,'stop',external._ROUTEWAY_FREE_MODEL,None),
    (False,True,'stop',external._ROUTEWAY_FREE_MODEL,None),
    (0,False,'stop',external._ROUTEWAY_FREE_MODEL,None),
])
def test_only_verified_zero_cost_route_is_called(pool,monkeypatch,tmp_path,price,available,finish,returned_model,expected):
    posts=[]
    class Client:
        def __init__(self,**kwargs): assert kwargs['follow_redirects'] is False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            assert url == 'https://api.routeway.ai/v1/models'
            assert 'Authorization' not in kwargs['headers']
            return httpx.Response(200,json={'data':[{'id':external._ROUTEWAY_FREE_MODEL,'available':available,
                'pricing':{k:{'price_per_million_t':price} for k in ('input','output')}}]})
        def post(self,url,**kwargs):
            posts.append(kwargs)
            assert url == 'https://api.routeway.ai/v1/chat/completions'
            assert kwargs['json']['model'].endswith(':free')
            assert kwargs['json']['response_format']=={'type':'json_object'}
            assert not {'tools','service_tier','fallbacks'} & kwargs['json'].keys()
            return httpx.Response(200,json={'model':returned_model,'choices':[{'finish_reason':finish,'message':{'content':'{"ok":true}'}}]})
    monkeypatch.setattr(external.httpx,'Client',Client)
    budget=AiRequestBudget(1,str(tmp_path/'ledger.sqlite'))
    with ai_budget_scope(budget):
        result,_=external.completion(system='Return JSON',user='source',max_tokens=1000,json_mode=True)
        assert result==expected
        external.completion(system='s',user='u',max_tokens=1000)
    assert budget.attempts==len(posts)
    assert len(posts)==int(type(price) in (int,float) and price==0 and available)


def test_no_self_validation_and_no_paid_configuration(pool,monkeypatch):
    monkeypatch.setenv('NEWS_ROUTEWAY_MODEL','paid-model')
    assert external._config('routeway')['model']==external._ROUTEWAY_FREE_MODEL
    assert not external._ordered_configs('validator',avoid_provider='routeway')


def test_daily_hold_survives_cycle_and_never_logs_secret(pool,monkeypatch,caplog):
    monkeypatch.setattr(external.time,'monotonic',lambda:100.)
    external._http_failure('routeway',httpx.Response(429,headers={'Retry-After':'10','X-RateLimit-Remaining-Day':'0'},json={'error':{'message':'fixture-secret daily limit'}}))
    external.reset()
    assert external._COOLDOWN_UNTIL['routeway']>1000
    assert not external.configured_identities()
    assert 'fixture-secret' not in caplog.text
