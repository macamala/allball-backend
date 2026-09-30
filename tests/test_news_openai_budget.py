from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine

from bot import news_openai as lane, news_openai_ledger as accounting
from bot.news_budget import AiRequestBudget, ai_budget_scope


def reserve(book, key='one', **overrides):
    args = dict(request_key=key, source_key='source-' + key, article_id=None,
        model=lane.MODEL, purpose='write', language='', phase='production',
        reserve_usd=Decimal('.1'), daily=Decimal('.5'), monthly=Decimal('15'), total=Decimal('15'))
    args.update(overrides)
    return book.reserve(**args)


@pytest.fixture
def book(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path/'accounting.db'), connect_args={'timeout':20})
    return accounting.OpenAILedger(engine)


def test_concurrent_reservations_and_restart_cannot_overrun(book):
    book._ensure()
    def attempt(i):
        return reserve(accounting.OpenAILedger(book.engine), str(i))[0]
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(attempt, range(30)))
    assert outcomes.count('reserved') == 5
    assert outcomes.count('budget_exhausted:daily') == 25
    restarted = accounting.OpenAILedger(book.engine)
    assert reserve(restarted, 'after-restart')[0] == 'budget_exhausted:daily'
    assert sum(Decimal(r['charged_usd']) for r in restarted.report()) == Decimal('.5')


def test_daily_and_monthly_rollovers_keep_total_credit_reserve(book):
    now = datetime(2026,9,30,23,59,tzinfo=timezone.utc)
    book.clock = lambda:now
    assert reserve(book, daily=Decimal('.1'), monthly=Decimal('.1'), total=Decimal('.2'))[0] == 'reserved'
    now += timedelta(days=1)
    assert reserve(book,'two',daily=Decimal('.1'),monthly=Decimal('.1'),total=Decimal('.2'))[0] == 'reserved'
    now += timedelta(days=32)
    assert reserve(book,'three',daily=Decimal('.1'),monthly=Decimal('.1'),total=Decimal('.2'))[0] == 'budget_exhausted:total'


def test_month_limit_blocks_on_new_day(book):
    now = datetime(2026,9,25,tzinfo=timezone.utc)
    book.clock = lambda:now
    assert reserve(book, monthly=Decimal('.1'))[0] == 'reserved'
    now += timedelta(days=1)
    assert reserve(book,'two',monthly=Decimal('.1'))[0] == 'budget_exhausted:monthly'


def test_pending_and_timeout_remain_charged_and_never_replayed(book):
    assert reserve(book)[0] == 'reserved'
    assert reserve(book)[0] == 'already_attempted'
    book.finish('one', status='ambiguous')
    assert reserve(accounting.OpenAILedger(book.engine))[0] == 'already_attempted'
    assert book.report()[0]['charged_usd'] == '0.100000000'


def test_cache_reuses_without_new_charge_and_article_id_is_backfilled(book):
    reserve(book)
    book.finish('one',status='success',response_text='accepted draft',
        token_usage={'input_tokens':100,'output_tokens':100,'cached_input_tokens':0,'cache_write_tokens':0}, cost=Decimal('.00006'))
    assert reserve(book)[0] == 'cached'
    assert reserve(book)[1]['response_text'] == 'accepted draft'
    book.bind_article('source-one', 123)
    assert book.report()[0]['article_id'] == 123
    assert len(book.report()) == 1
    assert 'response_text' not in book.report()[0]


def test_incomplete_response_is_metered_and_unknown_usage_keeps_full_reserve(book):
    reserve(book)
    book.finish('one',status='incomplete',cost=Decimal('.012'),
                token_usage={'input_tokens':200,'output_tokens':1800})
    assert reserve(book)[0] == 'already_attempted'
    assert book.report()[0]['charged_usd'] == '0.012000000'
    reserve(book,'two')
    book.finish('two',status='ambiguous')
    assert book.report()[1]['charged_usd'] == '0.100000000'


def test_dry_run_stops_at_12_even_across_instances(book):
    for i in range(12):
        assert reserve(book,str(i),phase='dry_run',reserve_usd=Decimal('.001'))[0]=='reserved'
    assert reserve(accounting.OpenAILedger(book.engine),'13',phase='dry_run',reserve_usd=Decimal('.001'))[0]=='dry_run_review_required'


def test_unexpected_cost_locks_paid_lane(book):
    reserve(book)
    book.finish('one',status='success',cost=Decimal('.11'))
    assert reserve(book,'two')[0]=='safety_stop:cost_bound_exceeded'


def test_cost_uses_actual_cached_and_write_tokens():
    tokens,cost=lane.usage_cost({'prompt_tokens':2000,'completion_tokens':1000,
        'prompt_tokens_details':{'cached_tokens':1000,'cache_write_tokens':500}})
    assert tokens['cached_input_tokens']==1000
    assert cost==Decimal('.0006225')
    with pytest.raises(ValueError):
        lane.usage_cost({'prompt_tokens':100,'completion_tokens':1,
            'prompt_tokens_details':{'cached_tokens':101}})


@pytest.mark.parametrize('name,value',[('OPENAI_MODEL','gpt-6-sol'),
    ('OPENAI_MODEL','gpt-6-astra'),('OPENAI_EXPENSIVE_MODELS_ENABLED','true'),
    ('OPENAI_WEB_SEARCH_ENABLED','true'),('OPENAI_DAILY_BUDGET_USD','0.51'),
    ('OPENAI_MONTHLY_BUDGET_USD','16'),('OPENAI_TOTAL_BUDGET_USD','20'),
    ('OPENAI_DAILY_BUDGET_USD','NaN'),('OPENAI_MONTHLY_BUDGET_USD','Infinity')])
def test_unsafe_config_disables_only_paid_lane(monkeypatch,name,value):
    monkeypatch.setenv('OPENAI_ENABLED','true')
    monkeypatch.setenv(name,value)
    assert lane.settings() is None


@pytest.fixture
def configured(monkeypatch,book,tmp_path):
    monkeypatch.setenv('OPENAI_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','private-test-key')
    monkeypatch.setenv('OPENAI_ROLLOUT_MODE','production')
    monkeypatch.setenv('OPENAI_PRODUCTION_APPROVED','true')
    monkeypatch.setattr(lane,'_cooldown_until',0)
    monkeypatch.setattr(lane,'model_preflight',lambda:True)
    monkeypatch.setattr(accounting,'_default',book)
    with ai_budget_scope(AiRequestBudget(20,str(tmp_path/'request-ledger.db'))):
        with lane.source_context({'url':'https://news.test/story'}) as context:
            context.update(verified=True,evidence_hash='one',priority=1)
            yield context


def http_fake(monkeypatch,reply):
    calls=[]
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            calls.append(kwargs)
            if isinstance(reply,Exception): raise reply
            return httpx.Response(200,json=reply,headers={'x-request-id':'fixture-request'})
    monkeypatch.setattr(lane.httpx,'Client',Client)
    return calls


REPLY={'model':'gpt-6-luna','service_tier':'default',
       'choices':[{'finish_reason':'stop','message':{'content':'original draft'}}],
       'usage':{'prompt_tokens':500,'completion_tokens':400,'prompt_tokens_details':{'cached_tokens':0,'cache_write_tokens':0}}}


def test_actual_transport_only_luna_without_tools_and_one_paid_call(configured,book,monkeypatch):
    calls=http_fake(monkeypatch,REPLY)
    assert lane.complete('system','source')=='original draft'
    assert lane.complete('system','source')=='original draft'
    assert len(calls)==1
    payload=calls[0]['json']
    assert payload['model']=='gpt-6-luna' and payload['reasoning_effort']=='low'
    assert payload['service_tier']=='default' and payload['max_completion_tokens']==1800
    assert 'tools' not in payload and payload['store'] is False
    row=book.report()[0]
    assert row['charged_usd']=='0.000250000' and row['output_tokens']==400
    assert row['purpose']=='write' and row['api_request_id']=='fixture-request'


def test_timeout_restart_keeps_reservation_without_replaying(configured,book,monkeypatch):
    calls=http_fake(monkeypatch,httpx.ReadTimeout('provider echo private-test-key'))
    assert lane.complete('system','source') is None
    monkeypatch.setattr(lane,'_cooldown_until',0)
    monkeypatch.setattr(accounting,'_default',accounting.OpenAILedger(book.engine))
    assert lane.complete('system','source') is None
    assert len(calls)==1 and Decimal(book.report()[0]['charged_usd'])>0


def test_substantial_paid_source_requests_full_body_without_changing_system(configured, monkeypatch):
    configured['source_words'] = 250
    calls = http_fake(monkeypatch, REPLY)
    assert lane.complete('stable system', 'verified source')
    messages = calls[0]['json']['messages']
    assert messages[0]['content'][0]['text'] == 'stable system'
    assert '180-240 words' in messages[1]['content']
    assert 'Never repeat facts, invent context' in messages[1]['content']
    # Prompt refinement does not replay a previously charged source.
    assert lane.complete('stable system', 'refined instructions')
    assert len(calls) == 1


def test_rejected_cached_paid_draft_does_not_block_free_fallback(configured, book, monkeypatch):
    from bot import rewrite_ai as writer
    calls = http_fake(monkeypatch, REPLY)
    assert lane.complete('system', 'facts')
    book.record_quality(configured['request_key'], 'too-short')
    monkeypatch.setattr(writer, 'AI_PROVIDER_MODE', 'xkiro_free')
    monkeypatch.setattr(writer, 'write_free_story', lambda *a: 'accepted free draft')
    assert writer._call_selected_ai('facts') == 'accepted free draft'
    assert len(calls) == 1


def test_translation_group_rejection_is_revalidated_from_cache_without_new_payment(configured, book, monkeypatch):
    calls = http_fake(monkeypatch, REPLY)
    assert lane.complete('system', 'facts', purpose='translate', language='sr') == 'original draft'
    book.record_quality(configured['request_key'], 'translation_semantic_rejected')
    assert lane.complete('more explicit target language', 'facts', purpose='translate', language='sr') == 'original draft'
    assert len(calls) == 1


def test_disabled_paid_translation_never_calls_provider_or_reserves_money(configured, book, monkeypatch):
    monkeypatch.setenv('OPENAI_TRANSLATIONS_ENABLED', 'false')
    calls = http_fake(monkeypatch, REPLY)
    assert lane.complete('system', 'facts', purpose='translate', language='sr') is None
    assert not calls and not book.report()
    assert lane.status() == 'translations_disabled'
    assert lane.complete('system', 'facts', purpose='write') == 'original draft'
    assert len(calls) == 1


def test_free_correction_cannot_overwrite_paid_quality(configured, book, monkeypatch):
    from bot import free_ai_router
    http_fake(monkeypatch, REPLY)
    assert lane.complete('system', 'facts')
    monkeypatch.setattr(free_ai_router, 'last_writer_identity', lambda: ('openai', lane.MODEL))
    lane.record_quality('unsupported_number')
    monkeypatch.setattr(free_ai_router, 'last_writer_identity', lambda: ('groq', 'free-model'))
    lane.record_quality('ok')
    assert book.report()[0]['quality_result'] == 'unsupported_number'


def test_reviewed_shadow_source_skips_repeated_writers(configured, book, monkeypatch):
    from bot import rewrite_ai as writer
    calls = http_fake(monkeypatch, REPLY)
    monkeypatch.setenv('OPENAI_ROLLOUT_MODE', 'dry_run')
    assert lane.complete('system', 'facts')
    book.record_quality(configured['request_key'], 'ok')
    monkeypatch.setattr(writer, 'AI_PROVIDER_MODE', 'xkiro_free')
    monkeypatch.setattr(writer, 'write_free_story', lambda *a: pytest.fail('shadow already reviewed'))
    assert writer._call_selected_ai('facts') is None
    assert lane.status() == 'dry_run_reviewed' and len(calls) == 1


def test_budget_cutoff_makes_no_http_request(configured,monkeypatch):
    monkeypatch.setenv('OPENAI_DAILY_BUDGET_USD','.0000001')
    calls=http_fake(monkeypatch,REPLY)
    assert lane.complete('system','source') is None
    assert not calls and lane.status()=='budget_exhausted:daily'


def test_ledger_outage_has_no_paid_network_call(configured,monkeypatch):
    def unavailable(): raise RuntimeError('fixture outage')
    monkeypatch.setattr(accounting,'ledger',unavailable)
    calls=http_fake(monkeypatch,REPLY)
    assert lane.complete('system','source') is None
    assert not calls


def test_routing_primary_secondary_failure_and_budget_fallback(configured,monkeypatch):
    from bot import rewrite_ai as writer
    monkeypatch.setattr(writer,'AI_PROVIDER_MODE','xkiro_free')
    order=[]
    monkeypatch.setattr(lane,'complete',lambda *a,**kw:order.append('paid') or 'paid draft')
    monkeypatch.setattr(writer,'write_free_story',lambda *a:order.append('free') or 'free draft')
    assert writer._call_selected_ai('facts')=='paid draft'
    assert order==['paid']
    order.clear();configured['priority']=0
    assert writer._call_selected_ai('facts')=='free draft'
    assert order==['free']
    order.clear();monkeypatch.setattr(writer,'write_free_story',lambda *a:order.append('free') or None)
    assert writer._call_selected_ai('facts')=='paid draft'
    assert order==['free','paid']
    order.clear();configured['priority']=1
    monkeypatch.setattr(lane,'complete',lambda *a,**kw:order.append('paid-blocked') or None)
    monkeypatch.setattr(writer,'write_free_story',lambda *a:order.append('free') or 'free draft')
    assert writer._call_selected_ai('facts')=='free draft'
    assert order==['paid-blocked','free']


def test_priority_reuses_existing_catalog_and_zvezda(configured):
    item={'url':'https://www.crvenazvezdafk.com/vesti/story','title':'Club announcement'}
    lane.verified_source(item,SimpleNamespace(sport='football',league=None),'The club confirmed a new manager.')
    assert configured['priority']==2


def test_production_requires_explicit_dry_run_review(monkeypatch):
    monkeypatch.setenv('OPENAI_ENABLED','true')
    monkeypatch.setenv('OPENAI_ROLLOUT_MODE','production')
    monkeypatch.delenv('OPENAI_PRODUCTION_APPROVED',raising=False)
    assert lane.settings() is None


def test_cutoff_probe_never_inserts_usage_or_sends_http(configured,book,monkeypatch):
    calls=http_fake(monkeypatch,REPLY)
    assert lane.cutoff_probe()=={'daily':True,'monthly':True,'total':True}
    assert book.report()==[] and not calls


def test_failed_free_draft_gets_one_paid_quality_attempt(configured,monkeypatch):
    from bot import fetch_sources as ingest
    calls=[]
    def attempt(**kwargs):
        calls.append(lane.forced())
        if not lane.forced():
            return None,'unsupported_number'
        configured['paid_returned']=True
        return {'title':'Verified title','summary':'Summary','body':'Source-based body'},'ok'
    monkeypatch.setattr(ingest,'_ai_story_attempt',attempt)
    monkeypatch.setattr(ingest,'quality_check',lambda *a,**k:(True,'ok'))
    parsed,reason=ingest._ai_story(title='source',facts='verified facts',sport='football',league='',max_ai_chars=6000)
    assert parsed and reason=='ok' and calls==[False,True]


@pytest.mark.parametrize('reason',['validator-unavailable','validator-independent-unavailable',
                                 'validator-source-type:fan_poll'])
def test_no_paid_rewrite_can_bypass_bad_source_or_missing_validator(configured,monkeypatch,reason):
    from bot import fetch_sources as ingest
    calls=[]
    monkeypatch.setattr(ingest,'_ai_story_attempt',lambda **kw:(calls.append('attempt') or None,reason))
    assert ingest._ai_story(title='source',facts='facts',sport='football',league='',max_ai_chars=6000)==(None,reason)
    assert calls==['attempt']


def test_old_paid_mode_still_requires_independent_validation(monkeypatch):
    from bot import rewrite_ai as writer
    monkeypatch.setattr(writer,'AI_PROVIDER_MODE','openai_legacy')
    monkeypatch.setattr(writer,'validate_free_story',lambda *a:(False,'validator-unsupported-claim'))
    assert writer.validate_story_facts('Source','facts',{'title':'Title','summary':'Summary','body':'Body'})==(False,'validator-unsupported-claim')


def test_translation_free_first_then_paid_only_missing_languages(configured,monkeypatch):
    import json
    from bot import news_translations as translations, news_deepl
    from tests.test_news_translations import SOURCE
    article=SimpleNamespace(id=9,source_url='https://source.test/article',title=SOURCE['title'],
        summary=SOURCE['summary'],content=SOURCE['body'],ai_content=None,
        _news_missing_translation_languages=('sr',))
    order=[]
    monkeypatch.setattr(news_deepl,'deepl_enabled',lambda:True)
    monkeypatch.setattr(news_deepl,'translate_source',lambda *a,**k:order.append('deepl') or None)
    monkeypatch.setattr(translations,'free_json_completion',lambda *a,**k:order.append('free') or None)
    def paid(system,prompt,**kwargs):
        order.append('paid:'+kwargs['language'])
        assert 'sr_title,sr_summary,sr_body' in system and 'de_body' not in system
        return json.dumps({'sr': SOURCE})
    monkeypatch.setattr(lane,'complete',paid)
    monkeypatch.setattr(news_deepl,'_semantic_validation',lambda *a, **k:order.append('validator') or True)
    assert translations.translate_article_payload(article)=={'sr': SOURCE}
    assert order==['deepl','free','paid:sr','validator']
    assert translations._TRANSLATION_META.get()=={'sr':('openai','gpt-6-luna')}


def test_successful_deepl_never_calls_paid_lane(configured,monkeypatch):
    from bot import news_translations as translations, news_deepl
    from tests.test_news_translations import SOURCE
    article=SimpleNamespace(id=10,title=SOURCE['title'],summary=SOURCE['summary'],content=SOURCE['body'],ai_content=None)
    monkeypatch.setattr(news_deepl,'deepl_enabled',lambda:True)
    monkeypatch.setattr(news_deepl,'translate_source',lambda *a,**k:{'sr':SOURCE})
    monkeypatch.setattr(lane,'complete',lambda *a,**kw:pytest.fail('unnecessary paid translation'))
    assert translations.translate_article_payload(article)=={'sr':SOURCE}


def test_partial_free_translation_only_pays_for_failed_language(configured, monkeypatch):
    import json
    from bot import news_translations as translations, news_deepl
    from tests.test_news_translations import SOURCE
    article = SimpleNamespace(id=11, title=SOURCE['title'], summary=SOURCE['summary'],
        content=SOURCE['body'], ai_content=None, _news_missing_translation_languages=('sr', 'de'))
    monkeypatch.setattr(news_deepl, 'deepl_enabled', lambda: False)
    monkeypatch.setattr(translations, 'free_json_completion', lambda *a, **k: json.dumps({'sr': SOURCE}))
    calls = []
    def paid(*args, **kwargs):
        calls.append(kwargs['language'])
        return json.dumps({'de': SOURCE})
    monkeypatch.setattr(lane, 'complete', paid)
    monkeypatch.setattr(news_deepl, '_semantic_validation', lambda *a, **k: True)
    assert translations.translate_article_payload(article) == {'sr': SOURCE, 'de': SOURCE}
    assert calls == ['de']
    assert translations._TRANSLATION_META.get()['sr'][0] == translations.TRANSLATION_PROVIDER


def test_production_ledger_reuses_news_configured_driver(monkeypatch):
    import database
    engine=SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
    monkeypatch.setattr(database,'engine',engine)
    monkeypatch.setattr(accounting,'_default',None)
    monkeypatch.setenv('NEWS_ACCOUNTING_BACKEND','postgres')
    monkeypatch.setenv('DATABASE_URL','postgresql://fixture:fixture@fixture/fixture')
    assert accounting.ledger().engine is engine


def test_free_translation_with_wrong_meaning_uses_paid_quality_fallback(configured, monkeypatch):
    import json
    from bot import news_translations as translations, news_deepl
    from tests.test_news_translations import SOURCE
    article = SimpleNamespace(id=12, title=SOURCE['title'], summary=SOURCE['summary'],
        content=SOURCE['body'], ai_content=None, _news_missing_translation_languages=('sr',))
    monkeypatch.setattr(news_deepl, 'deepl_enabled', lambda: False)
    bad = {**SOURCE, 'body': SOURCE['body'] + ' The player did not score.'}
    monkeypatch.setattr(translations, 'free_json_completion', lambda *a, **k: json.dumps({'sr': bad}))
    checked = []
    def validate(source, output, **kwargs):
        checked.append(output)
        return output == {'sr': SOURCE}
    monkeypatch.setattr(news_deepl, '_semantic_validation', validate)
    calls = []
    monkeypatch.setattr(lane, 'complete', lambda *a, **k: calls.append(k['language']) or json.dumps({'sr': SOURCE}))
    assert translations.translate_article_payload(article) == {'sr': SOURCE}
    assert calls == ['sr'] and len(checked) == 2


def test_good_free_language_survives_bad_language_and_paid_rejection(configured, monkeypatch):
    import json
    from bot import news_translations as translations, news_deepl
    from tests.test_news_translations import SOURCE
    article = SimpleNamespace(id=13, title=SOURCE['title'], summary=SOURCE['summary'],
        content=SOURCE['body'], ai_content=None, _news_missing_translation_languages=('sr', 'es'))
    monkeypatch.setattr(news_deepl, 'deepl_enabled', lambda: False)
    monkeypatch.setattr(translations, 'free_json_completion', lambda *a, **k: json.dumps({'sr': SOURCE, 'es': SOURCE}))
    monkeypatch.setattr(news_deepl, '_semantic_validation', lambda *a, **k: {'sr'})
    calls = []
    def paid(system, prompt, **kwargs):
        calls.append(kwargs['language'])
        assert 'es = Spanish' in system and 'sr = Serbian' not in system
        return json.dumps({'es': SOURCE})
    monkeypatch.setattr(lane, 'complete', paid)
    assert translations.translate_article_payload(article) == {'sr': SOURCE}
    assert calls == ['es']
