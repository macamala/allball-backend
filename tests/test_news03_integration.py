from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from bot import fetch_sources as ingest, rewrite_ai as writer, feeds, pipeline
from bot.news_budget import AiRequestBudget, ai_budget_scope
from bot.news_verified_feeds import VERIFIED_RSS
import repair_content

BODY = ('A revised knockout structure has been confirmed for the football competition. '
        'Clubs will enter the tournament under the announced format, with the draw determining their opening opponents. '
        'The organising committee will publish the complete match programme after the participating teams are confirmed. '
        'The announcement concerns the competition schedule and does not change the existing qualification requirements.')
FACTS = ('The football federation announced a new cup format. The draw is scheduled after qualification. '
         'All teams will compete in the knockout stage and the federation will then release the fixtures. '
         'Qualification rules are unchanged. The organising committee confirmed that clubs will be notified of the revised schedule.')
DRAFT = {'title':'Football cup format confirmed for participating clubs','summary':'The football competition will use a revised knockout format.','body':BODY}


@pytest.fixture(autouse=True)
def no_real_writer(monkeypatch):
    monkeypatch.setattr(writer,'_rate_limited',False)
    monkeypatch.setattr(writer,'_hard_quota',False)
    monkeypatch.setattr(writer,'OPENAI_API_KEY','isolated-test-not-a-real-key')
    monkeypatch.setattr(writer.time,'sleep',lambda n:None)
    monkeypatch.delenv('NEWS_HISTORICAL_REPAIR_ENABLED',raising=False)


def mock_http(monkeypatch,responses):
    posts=[]
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):
            posts.append(kwargs)
            result=responses[len(posts)-1]
            if isinstance(result,Exception):raise result
            return result
    monkeypatch.setattr(writer.httpx,'Client',Client)
    return posts


def response(status=200,finish='stop',refusal=None):
    return httpx.Response(status,request=httpx.Request('POST','https://example.test'),json={
        'choices':[{'finish_reason':finish,'message':{'content':'Original test draft','refusal':refusal}}]})


def test_no_active_budget_means_no_request(monkeypatch):
    posts=mock_http(monkeypatch,[response()])
    assert writer._call_openai('fixture') is None
    assert not posts


def test_every_retry_charged_and_no_refund(monkeypatch,tmp_path):
    posts=mock_http(monkeypatch,[response(429),response()])
    budget=AiRequestBudget(2,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget):
        assert writer._call_openai('fixture')=='Original test draft'
        assert writer._call_openai('fixture') is None
    assert budget.attempts==len(posts)==2


def test_retry_cannot_exceed_remaining_allowance(monkeypatch,tmp_path):
    posts=mock_http(monkeypatch,[response(429)])
    budget=AiRequestBudget(1,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget):assert writer._call_openai('fixture') is None
    assert len(posts)==budget.attempts==1


@pytest.mark.parametrize('result',[response(finish='length'),response(refusal='Not produced'),httpx.ReadTimeout('synthetic timeout')])
def test_incomplete_or_failed_response_still_charged(monkeypatch,tmp_path,result):
    posts=mock_http(monkeypatch,[result])
    budget=AiRequestBudget(1,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget): assert writer._call_openai('fixture') is None
    assert len(posts)==budget.attempts==1


def prepare_ingest(monkeypatch,draft=DRAFT):
    monkeypatch.setattr(ingest,'existing_by_url',lambda *a:None)
    monkeypatch.setattr(ingest,'existing_near_duplicate',lambda *a:None)
    monkeypatch.setattr(ingest,'extract_from_url',lambda url:(FACTS,None))
    monkeypatch.setattr(ingest,'classify_article',lambda *a,**k:SimpleNamespace(sport='football',league=None,country=None))
    monkeypatch.setattr(ingest,'_ai_story',lambda **k:(draft,'ok' if draft else 'empty'))
    return {'title':'Football cup format announced','url':'https://example.test/cup',
            'summary':'Football cup draw and knockout format.', 'published_at':datetime.now(timezone.utc)-timedelta(hours=1)}


def test_no_ai_never_copies_or_extracts(monkeypatch):
    monkeypatch.setattr(ingest,'extract_from_url',lambda *a:pytest.fail('unexpected extraction'))
    assert ingest._ingest_item(None,{'url':'https://example.test'},False,6000,0)==(None,False)


@pytest.mark.parametrize('draft',[None,{**DRAFT,'body':FACTS},{**DRAFT,'body':BODY+' There are 37 clubs.'},{**DRAFT,'body':'Read the full story at https://example.test'},{**DRAFT,'body':BODY+'\nSource: Other outlet'}])
def test_invalid_original_draft_never_commits_raw_source(monkeypatch,draft):
    item=prepare_ingest(monkeypatch,draft)
    db=Mock()
    assert ingest._ingest_item(db,item,True,6000,1)==(None,False)
    db.add.assert_not_called();db.commit.assert_not_called()


def test_valid_original_keeps_source_identity_but_stores_own_body(monkeypatch):
    from database import SessionLocal
    from models import Article
    item=prepare_ingest(monkeypatch)
    db=SessionLocal()
    try:
        article,used=ingest._ingest_item(db,item,True,6000,1)
        assert article is not None and used
        assert article.ai_generated and article.ai_content==article.content
        assert 'revised knockout structure' in article.content
        assert article.content!=FACTS
        assert article.source_url==item['url']
        assert article.published_at.replace(tzinfo=timezone.utc)==item['published_at']
    finally:
        db.query(Article).filter(Article.source_url==item['url']).delete();db.commit();db.close()


@pytest.mark.parametrize('days',[4,-1])
def test_stale_or_future_item_no_extraction(monkeypatch,days):
    item=prepare_ingest(monkeypatch)
    item['published_at']=datetime.now(timezone.utc)-timedelta(days=days)
    monkeypatch.setattr(ingest,'extract_from_url',lambda *a:pytest.fail('unexpected extraction'))
    assert ingest._ingest_item(None,item,True,6000,1)==(None,False)


def test_historical_jobs_default_to_no_session_no_mutation(monkeypatch):
    import database
    monkeypatch.setattr(database,'SessionLocal',lambda:pytest.fail('session opened'))
    for f in [repair_content.repair_summary_only,repair_content.repair_contaminated]:
        result=f();assert result['disabled'] and result['scanned']==0


def test_summary_repair_without_budget_skips_before_fetch(monkeypatch):
    monkeypatch.setattr(repair_content,'extract_from_url',lambda *a:pytest.fail('unexpected extraction'))
    assert repair_content.repair_summary_one(None,SimpleNamespace())=='skipped'


def test_failed_summary_repair_never_stores_source(monkeypatch,tmp_path):
    from models import Article
    article=Article(title='Football championship update',content='A short existing brief.',summary='Existing brief',slug='repair-test',source_url='https://example.test/a')
    before=article.content
    monkeypatch.setattr(repair_content,'extract_from_url',lambda url:('Football clubs competed for the national championship under the announced format. '*30,None))
    monkeypatch.setattr(ingest,'_ai_story',lambda **kw:(None,'empty'))
    db=Mock()
    with ai_budget_scope(AiRequestBudget(1,str(tmp_path/'ledger.db'))):
        assert repair_content.repair_summary_one(db,article)=='skipped'
    assert article.content==before
    db.add.assert_not_called();db.commit.assert_not_called()


def test_expanded_feeds_opt_in_and_deduplicated(monkeypatch):
    monkeypatch.delenv('NEWS_EXPANDED_FEEDS_ENABLED',raising=False)
    before=feeds.enabled_feeds()
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED','1')
    after=feeds.enabled_feeds()
    assert len(after)>len(before)
    assert len({r['url'] for r in after})==len(after)
    assert len(VERIFIED_RSS)==29 and len({r['sport'] for r in VERIFIED_RSS})==27
    assert all(r['reuse_rights']=='NOT_VERIFIED' for r in VERIFIED_RSS)
    assert any(r['metadata_state']=='RSS_METADATA_STALE_OR_UNDATED' for r in VERIFIED_RSS)


def test_html_cannot_be_misrepresented_as_rss(monkeypatch):
    monkeypatch.setattr(ingest,'read_news_feed',lambda url:b'<html><title>Landing page</title><p>News</p></html>')
    assert ingest._fetch_feed_entries({'url':'https://example.test/feed'},3)==[]


def test_feed_sort_filters_stale_before_item_limit(monkeypatch):
    from email.utils import format_datetime
    now=datetime.now(timezone.utc)
    def item(title,delta):
        return f'<item><title>{title}</title><link>https://example.test/{title.replace(" ","-")}</link><pubDate>{format_datetime(now-timedelta(days=delta))}</pubDate></item>'
    xml=('<rss version="2.0"><channel><title>Fixture</title>'+item('Old football cup',7)+item('Fresh football cup',1)+'</channel></rss>').encode()
    monkeypatch.setattr(ingest,'read_news_feed',lambda url:xml)
    rows=ingest._fetch_feed_entries({'url':'https://example.test/feed'},1)
    assert len(rows)==1 and rows[0]['title']=='Fresh football cup'


def test_legacy_pipeline_uses_guarded_ingestor(monkeypatch):
    call=Mock(return_value=2);monkeypatch.setattr(pipeline,'fetch_and_store_all_articles',call)
    monkeypatch.setenv('NEWS_MAX_AI_ARTICLES','2')
    assert pipeline.run_pipeline()==2
    call.assert_called_once_with(max_per_league=3,hard_limit=2,use_ai=True,max_ai_articles=2)


def test_missing_ledger_does_not_start_feed_or_db_work(monkeypatch):
    monkeypatch.delenv('NEWS_AI_LEDGER_PATH',raising=False)
    monkeypatch.setattr(ingest,'_fetch_and_store_all_articles',lambda *a:pytest.fail('ingestion began'))
    assert ingest.fetch_and_store_all_articles(max_ai_articles=2)==0
