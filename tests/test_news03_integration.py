from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from bot import fetch_sources as ingest, rewrite_ai as writer, feeds, pipeline
from bot.news_budget import AiRequestBudget, ai_budget_scope
from bot.news_verified_feeds import VERIFIED_RSS
import repair_content
import public_index

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
    # These tests replace provider I/O and exercise admission/request accounting;
    # independent provider health has its own router tests.
    monkeypatch.setattr(writer, 'free_ai_rate_limited', lambda: False)
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
        'model':'gpt-6-luna', 'service_tier':'default',
        'usage':{'prompt_tokens':100,'completion_tokens':20},
        'choices':[{'finish_reason':finish,'message':{'content':'Original test draft','refusal':refusal}}]})


@pytest.fixture
def paid_operation(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from bot import news_openai, news_openai_ledger
    monkeypatch.setenv('OPENAI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_ROLLOUT_MODE', 'production')
    monkeypatch.setenv('OPENAI_PRODUCTION_APPROVED', 'true')
    monkeypatch.setattr(news_openai, 'model_preflight', lambda:True)
    monkeypatch.setattr(news_openai, '_cooldown_until', 0)
    book = news_openai_ledger.OpenAILedger(create_engine('sqlite:///' + str(tmp_path/'cost.db')))
    monkeypatch.setattr(news_openai_ledger, '_default', book)
    with news_openai.source_context({'url':'https://source.test/verified'}) as context:
        context.update(verified=True, evidence_hash='fixture')
        yield book


def test_no_active_budget_means_no_request(monkeypatch):
    posts=mock_http(monkeypatch,[response()])
    assert writer._call_openai('fixture') is None
    assert not posts


def test_429_has_no_automatic_paid_retry(monkeypatch,tmp_path,paid_operation):
    posts=mock_http(monkeypatch,[response(429),response()])
    budget=AiRequestBudget(2,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget):
        assert writer._call_openai('fixture') is None
        assert writer._call_openai('fixture') is None
    assert budget.attempts==len(posts)==1


def test_retry_cannot_exceed_remaining_allowance(monkeypatch,tmp_path,paid_operation):
    posts=mock_http(monkeypatch,[response(429)])
    budget=AiRequestBudget(1,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget):assert writer._call_openai('fixture') is None
    # Preserve a request for the independent validator; don't buy an unusable draft.
    assert len(posts)==budget.attempts==0


@pytest.mark.parametrize('result',[response(finish='length'),response(refusal='Not produced'),httpx.ReadTimeout('synthetic timeout')])
def test_incomplete_or_failed_response_still_charged(monkeypatch,tmp_path,result,paid_operation):
    posts=mock_http(monkeypatch,[result])
    budget=AiRequestBudget(2,str(tmp_path/'ledger.db'))
    with ai_budget_scope(budget): assert writer._call_openai('fixture') is None
    assert len(posts)==budget.attempts==1


def prepare_ingest(monkeypatch,draft=DRAFT):
    from bot import extract as extract_module
    monkeypatch.setattr(extract_module,'extract_image_candidates_from_url',lambda *a,**k:[])
    monkeypatch.setattr(ingest,'existing_by_url',lambda *a:None)
    monkeypatch.setattr(ingest,'existing_near_duplicate',lambda *a,**kw:None)
    monkeypatch.setattr(ingest,'_source_on_ai_cooldown',lambda *a:False)
    monkeypatch.setattr(ingest,'_hold_ai_source',lambda *a,**k:None)
    monkeypatch.setattr(ingest,'extract_from_url',lambda url:(FACTS,'https://example.test/hero.jpg'))
    monkeypatch.setattr(ingest,'classify_article',lambda *a,**k:SimpleNamespace(sport='football',league=None,country=None))
    monkeypatch.setattr(ingest,'_ai_story',lambda **k:(draft,'ok' if draft else 'empty'))
    monkeypatch.setattr(ingest,'news_image_is_reachable',lambda url:True)
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


def test_translated_duplicate_is_blocked_before_article_insert(monkeypatch):
    item=prepare_ingest(monkeypatch)
    item['title']='Fudbalski savez objavio format kupa'
    calls=[]
    def duplicate(db,title,stamp,**kwargs):
        calls.append(title)
        return SimpleNamespace(id=22231) if title == DRAFT['title'] else None
    monkeypatch.setattr(ingest,'existing_near_duplicate',duplicate)
    holds=[]
    monkeypatch.setattr(ingest,'_hold_ai_source',lambda url,reason: holds.append((url,reason)))
    db=Mock()
    assert ingest._ingest_item(db,item,True,6000,1) == (None,False)
    assert calls == [item['title'],DRAFT['title']]
    assert holds == [(item['url'],'duplicate_english_draft')]
    db.add.assert_not_called();db.commit.assert_not_called()


@pytest.mark.parametrize('days',[4,-1])
def test_stale_or_future_item_no_extraction(monkeypatch,days):
    item=prepare_ingest(monkeypatch)
    item['published_at']=datetime.now(timezone.utc)-timedelta(days=days)
    monkeypatch.setattr(ingest,'extract_from_url',lambda *a:pytest.fail('unexpected extraction'))
    assert ingest._ingest_item(None,item,True,6000,1)==(None,False)


def test_story_expiring_during_writing_is_rechecked_before_commit(monkeypatch):
    item = prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest, 'news_freshness_reason', Mock(side_effect=[None, 'stale_publication']))
    db = Mock()
    assert ingest._ingest_item(db,item,True,6000,1) == (None,False)
    db.add.assert_not_called()


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
    assert len(VERIFIED_RSS) >= 29
    assert len({r['url'] for r in VERIFIED_RSS}) == len(VERIFIED_RSS)
    assert len({r['sport'] for r in VERIFIED_RSS}) >= 27
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
    xml=('<rss version="2.0"><channel><title>Fixture</title>'+item('Old football cup',7)+item('Fresh football cup',0.5)+'</channel></rss>').encode()
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


def test_missing_image_stops_before_ai_writer(monkeypatch):
    item=prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest,'extract_from_url',lambda url:(FACTS,None))
    monkeypatch.setattr(ingest,'_ai_story',lambda **kw:pytest.fail('writer must not run without image'))
    holds=[]
    monkeypatch.setattr(ingest,'_hold_ai_source',lambda url,reason:holds.append((url,reason)))
    assert ingest._ingest_item(Mock(),item,True,6000,1)==(None,False)
    assert holds[-1]==(item['url'],'missing-or-unreachable-publishable-image')


def test_logo_image_stops_before_ai_writer(monkeypatch):
    item=prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest,'extract_from_url',lambda url:(FACTS,'https://example.test/team-logo.svg'))
    monkeypatch.setattr(ingest,'_ai_story',lambda **kw:pytest.fail('writer must not run for logo-only hero'))
    assert ingest._ingest_item(Mock(),item,True,6000,1)==(None,False)



def test_expanded_bbc_feeds_are_discovery_only_for_sport_taxonomy():
    bbc = [row for row in VERIFIED_RSS if row.get("publisher") == "BBC Sport"]
    assert bbc
    assert all(row.get("kind") == "mixed" for row in bbc)
    assert any(row.get("sport") == "ice-hockey" for row in bbc)
    assert any(row.get("sport") == "american-football" for row in bbc)



def test_repair_order_keeps_dedupe_as_final_guard():
    import inspect
    source = inspect.getsource(ingest._fetch_and_store_all_articles)
    mislabel = source.index("repair_recent_sport_mislabels")
    unresolved = source.index("repair_recent_unresolved", mislabel)
    dedupe = source.index("repair_recent_duplicate_news", unresolved)
    inventory = source.index("recent_public_sport_inventory", dedupe)
    assert mislabel < unresolved < dedupe < inventory


def test_prequeue_cooldown_filter_runs_before_fair_queue():
    import inspect
    source=inspect.getsource(ingest._fetch_and_store_all_articles)
    batch=source.index("_held_ai_source_urls")
    queue=source.index("fair_news_queue", batch)
    assert batch < queue


def test_non_article_podcast_and_scorecard_are_rejected_before_queue_classification():
    from bot.news_policy import fair_news_queue
    now=datetime.now(timezone.utc)
    calls=[]
    def classify(item):
        calls.append(item["title"])
        return SimpleNamespace(sport="cricket")
    items=[
        {"title":"The Chequered Flag Podcast","url":"https://www.bbc.co.uk/iplayer/episode/m002zvgw","published_at":now},
        {"title":"India v West Indies - first ODI scorecard","url":"https://www.bbc.co.uk/sport/cricket/scorecard/e-237254","published_at":now},
        {"title":"Cricket captain returns for decisive series","url":"https://example.test/cricket-return","published_at":now},
    ]
    queued,rejected=fair_news_queue(items,classify,sport_order=["cricket"])
    assert [row["title"] for row in queued]==["Cricket captain returns for decisive series"]
    assert rejected["non_article_podcast"]==1
    assert rejected["non_article_scorecard"]==1
    assert calls==["Cricket captain returns for decisive series"]


def test_unknown_enrichment_skips_non_articles_and_prefers_sport_hinted_story(monkeypatch):
    now=datetime.now(timezone.utc)
    candidates=[
        {
            "title":"The Chequered Flag Podcast",
            "url":"https://www.bbc.co.uk/iplayer/episode/m002zvgw",
            "published_at":now,
            "feed":{"kind":"mixed","sport":"motorsport"},
        },
        {
            "title":"India v West Indies - first ODI scorecard",
            "url":"https://www.bbc.co.uk/sport/cricket/scorecard/e-237254",
            "published_at":now,
            "feed":{"kind":"mixed","sport":"cricket"},
        },
        {
            "title":"Internationals hold three-point lead over US",
            "url":"https://www.bbc.co.uk/sport/golf/articles/c64gvvjze807o",
            "published_at":now,
            "feed":{"kind":"mixed","sport":"golf"},
        },
        {
            "title":"Generic unknown sport story",
            "url":"https://example.test/unknown",
            "published_at":now-timedelta(minutes=1),
            "feed":{"kind":"mixed"},
        },
    ]
    monkeypatch.setattr(
        ingest,
        "_classify_candidate",
        lambda item: SimpleNamespace(sport=None),
    )
    calls=[]
    def extract(url):
        calls.append(url)
        return ("Golf players contested the tournament on the final day. "*8, "https://example.test/photo.jpg")
    monkeypatch.setattr(ingest,"extract_from_url",extract)
    assert ingest._enrich_unknown_candidates(candidates,limit=1)==1
    assert calls==["https://www.bbc.co.uk/sport/golf/articles/c64gvvjze807o"]
    assert "_extracted" in candidates[2]
    assert "_extracted" not in candidates[0]
    assert "_extracted" not in candidates[1]


def test_public_image_repair_never_revives_live_score_derived_legacy_rows(monkeypatch):
    from bot import extract as extract_module
    monkeypatch.setattr(
        extract_module,
        "extract_image_candidates_from_url",
        lambda *a, **k: pytest.fail("legacy live-score source must not be fetched"),
    )
    assert public_index._reachable_source_image(
        "https://ninkosports.com/live-scores?date=2026-09-27&sport=football"
    ) is None


def test_public_image_repair_falls_back_to_second_source_candidate(monkeypatch):
    from bot import extract as extract_module
    from bot import news_image_http

    monkeypatch.setattr(
        extract_module,
        "extract_image_candidates_from_url",
        lambda *a, **k: [
            {"url":"https://example.test/dead.jpg","source":"og","width":1600,"in_article":True},
            {"url":"https://example.test/good.jpg","source":"jsonld","width":1200,"in_article":True},
        ],
    )
    seen=[]
    monkeypatch.setattr(
        news_image_http,
        "news_image_is_reachable",
        lambda url: seen.append(url) or url.endswith("good.jpg"),
    )
    assert public_index._reachable_source_image("https://example.test/story") == "https://example.test/good.jpg"
    assert seen == ["https://example.test/dead.jpg","https://example.test/good.jpg"]


def test_reachable_image_selector_falls_back_to_second_candidate(monkeypatch):
    seen=[]
    monkeypatch.setattr(
        ingest,
        "news_image_is_reachable",
        lambda url: seen.append(url) or url.endswith("good.jpg"),
    )
    candidates=[
        {"url":"https://example.test/best.jpg","source":"og","width":1600,"in_article":True},
        {"url":"https://example.test/good.jpg","source":"body","width":1200,"in_article":False},
    ]
    assert ingest._pick_reachable_article_image(candidates)=="https://example.test/good.jpg"
    assert seen==["https://example.test/best.jpg","https://example.test/good.jpg"]


def test_unreachable_image_stops_before_ai_writer(monkeypatch):
    item=prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest,"news_image_is_reachable",lambda url:False)
    monkeypatch.setattr(ingest,"_ai_story",lambda **kw:pytest.fail("writer must not run for dead hero"))
    holds=[]
    monkeypatch.setattr(ingest,"_hold_ai_source",lambda url,reason:holds.append((url,reason)))
    assert ingest._ingest_item(Mock(),item,True,6000,1)==(None,False)
    assert holds[-1][1]=="missing-or-unreachable-publishable-image"


def test_source_path_sport_hint_resolves_unclassified_text():
    item={
        "title":"Four men down - but Australia still beat South Africa",
        "url":"https://www.bbc.co.uk/sport/rugby-union/articles/cx05r4gg209ro",
        "summary":"Australia overcame South Africa after playing short-handed.",
        "feed":{"kind":"mixed","sport":"rugby","publisher":"BBC Sport"},
    }
    tags=ingest._classify_item(item,item["summary"])
    assert tags.sport=="rugby"
    assert tags.reason=="trusted-source-path"


def test_trusted_rugby_section_beats_shared_football_city_alias():
    item = {
        'title': 'Cornish Pirates concede club-record 73 points in Championship defeat at Coventry',
        'url': 'https://www.bbc.co.uk/sport/rugby-union/articles/cmzxzj8n9wwwo',
        'feed': {'kind': 'mixed', 'publisher': 'BBC Sport'},
    }
    tags = ingest._classify_item(item, 'The Pirates lost at Coventry in the Championship.')
    assert tags.sport == 'rugby'
    assert tags.reason == 'trusted-source-path'


def test_explicit_ufc_headline_survives_misplaced_football_source_path():
    item = {'title': 'UFC fighter announces next MMA bout',
        'url': 'https://www.bbc.co.uk/sport/football/articles/misplaced',
        'feed': {'kind': 'mixed'}}
    assert ingest._classify_item(item, 'The fighter visited Brighton before the fight.').sport == 'mma'


def test_textual_sport_evidence_beats_conflicting_source_path():
    item={
        "title":"NBA: Lakers beat Celtics after LeBron triple-double",
        "url":"https://www.bbc.co.uk/sport/rugby-union/articles/conflict-fixture",
        "summary":"The basketball game ended after LeBron recorded a triple-double in the NBA.",
        "feed":{"kind":"mixed","sport":"rugby","publisher":"BBC Sport"},
    }
    tags=ingest._classify_item(item,item["summary"])
    assert tags.sport=="basketball"
    assert tags.reason!="trusted-source-path"


def test_explicit_mma_title_override_beats_incidental_football_words():
    assert public_index._explicit_title_sport_override(
        "Christian Eckerlin brings MMA edge to Brighton before Frankfurt farewell"
    ) == "mma"


def test_explicit_mma_title_override_does_not_guess_plain_football_title():
    assert public_index._explicit_title_sport_override(
        "McInnes reaches 100 days at Rangers with Old Firm double"
    ) is None


def test_coverage_debt_does_not_reserve_writer_budget_for_translations(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED","1")
    monkeypatch.setenv("NEWS_TRANSLATIONS_PER_CYCLE","3")
    budget=AiRequestBudget(6,str(tmp_path/"ledger.db"))
    with ai_budget_scope(budget):
        assert ingest._correction_retry_allowed(prefer_breadth=True) is False


def test_writer_prompt_includes_numeric_and_quote_safety_contract(monkeypatch):
    captured=[]
    monkeypatch.setattr(writer, "_call_selected_ai", lambda prompt, **kw: captured.append(prompt) or "draft")
    writer.write_ninkosports_story(
        "Club wins 3:1 in 2026 final",
        "The club won 3:1 in the 2026 final.",
        sport="football",
    )
    assert captured
    assert "ALLOWED NUMERIC TOKENS:" in captured[0]
    assert "3:1" in captured[0] and "2026" in captured[0]
    assert "Do not output straight or curly double quotation marks anywhere" in captured[0]
    assert "TAXONOMY LOCK: the exact article sport is football" in captured[0]


def test_ai_story_runs_deterministic_fact_lock_before_semantic_validator(monkeypatch):
    draft={
        "title":"Northbridge Athletic injury update on Friday",
        "summary":"A player suffered a knee injury.",
        "body":"Northbridge Athletic confirmed a knee injury. "*15 + "\n\n" + "Northbridge Athletic confirmed a knee injury. "*15,
    }
    monkeypatch.setattr(ingest,"write_ninkosports_story",lambda **kw:"fixture")
    monkeypatch.setattr(ingest,"parse_ai_output",lambda raw:draft)
    monkeypatch.setattr(
        ingest,"validate_story_facts",
        lambda *a,**k:pytest.fail("semantic validator must not run"),
    )
    parsed,reason=ingest._ai_story(
        title="Northbridge Athletic schedule update",
        facts="The Northbridge Athletic club has published its schedule for the season. "*40,
        sport="football",
        league="",
        max_ai_chars=6000,
    )
    assert parsed is None
    assert reason == "unsupported_time_reference:friday"


def test_rejected_story_preserves_draft_and_specific_validator_feedback(monkeypatch):
    from bot import free_ai_router
    monkeypatch.setattr(ingest, 'write_ninkosports_story', lambda **kw: 'fixture')
    monkeypatch.setattr(ingest, 'parse_ai_output', lambda raw: dict(DRAFT))
    feedback = {'unsupported_claims': ['The draw has already taken place'], 'changed_names': []}
    def reject(*args, **kwargs):
        free_ai_router._LAST_VALIDATION.set(feedback)
        return False, 'validator-unsupported-claim'
    monkeypatch.setattr(ingest, 'validate_story_facts', reject)
    parsed, reason = ingest._ai_story('Football cup format announced', FACTS, 'football', '', 6000)
    assert parsed is None and reason == 'validator-unsupported-claim'
    evidence = ingest._LAST_STORY_FAILURE.get()
    assert evidence['draft'] == DRAFT
    assert evidence['source_facts'] == FACTS
    assert evidence['validator_feedback'] == feedback


@pytest.mark.parametrize('corrected', [False, True])
@pytest.mark.parametrize('reason_code', ['validator-unsupported-claim', 'unsupported_number', 'publisher_branding'])
def test_major_sport_correction_retains_incident_and_requires_pass(monkeypatch, tmp_path, corrected, reason_code):
    import json
    from database import SessionLocal
    from models import Article, NewsIncident
    item = prepare_ingest(monkeypatch)
    item['url'] = f'https://example.test/priority-correction-{reason_code}-{corrected}'
    feedback = {'unsupported_claims': ['The draw has already taken place'], 'changed_names': []}
    calls = []
    def story(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            ingest._LAST_STORY_FAILURE.set({'draft': DRAFT, 'source_facts': FACTS,
                                            'validator_feedback': feedback})
            return None, reason_code
        assert kwargs['correction_feedback'] == feedback
        return (DRAFT, 'ok') if corrected else (None, 'validator-unsupported-claim')
    monkeypatch.setattr(ingest, '_ai_story', story)
    db = SessionLocal()
    try:
        budget = AiRequestBudget(8, str(tmp_path/'correction.db'))
        with ai_budget_scope(budget):
            article, used = ingest._ingest_item(db, item, True, 6000, 1, prefer_breadth=True)
        assert len(calls) == 2
        assert bool(article) is corrected and used is corrected
        incident = db.query(NewsIncident).filter_by(source_url=item['url']).one()
        assert DRAFT['title'] in incident.draft_excerpt
        assert json.loads(incident.details_json)['validator_feedback'] == feedback
        assert incident.status == ('auto_corrected' if corrected else 'open')
    finally:
        db.query(NewsIncident).filter_by(source_url=item['url']).delete()
        db.query(Article).filter_by(source_url=item['url']).delete()
        db.commit()
        db.close()


def test_live_ingest_rejects_candidate_older_than_24_hours(monkeypatch):
    item=prepare_ingest(monkeypatch)
    item["published_at"]=datetime.now(timezone.utc)-timedelta(hours=25)
    monkeypatch.setattr(
        ingest,
        "extract_from_url",
        lambda *a: pytest.fail("stale article reached extraction"),
    )
    assert ingest._ingest_item(Mock(),item,True,6000,1)==(None,False)


@pytest.mark.parametrize('first_coverage,reason,attempts',[(False,'validator-unsupported-claim',1),(True,'validator-unsupported-claim',2),(True,'validator-source-type:fan_poll',1)])
def test_first_coverage_can_correct_facts_but_never_rewrite_a_non_news_source(monkeypatch,tmp_path,first_coverage,reason,attempts):
    item=prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest,'_classify_item',lambda *a,**kw:SimpleNamespace(sport='snooker',league='snooker-international',country='international'))
    calls=[]
    def story(**kwargs):
        calls.append(kwargs)
        ingest._LAST_STORY_FAILURE.set({'draft':DRAFT,'source_facts':FACTS,'validator_feedback':{'unsupported_claims':['Unsupported draw timing'],'changed_names':[]}})
        return None,reason
    monkeypatch.setattr(ingest,'_ai_story',story)
    db=Mock()
    with ai_budget_scope(AiRequestBudget(8,str(tmp_path/'coverage.db'))):
        assert ingest._ingest_item(db,item,True,6000,1,prefer_breadth=True,first_coverage=first_coverage)==(None,False)
    assert len(calls)==attempts
    db.add.assert_not_called()


def test_sport_mismatch_retry_gets_taxonomy_correction_prompt(monkeypatch):
    captured=[]
    monkeypatch.setattr(writer, "_call_selected_ai", lambda prompt, **kw: captured.append(prompt) or "draft")
    writer.write_ninkosports_story(
        "NRLW signing update",
        "The source reports a rugby league signing update.",
        sport="rugby-league",
        correction_reason="draft_sport_mismatch:rugby",
    )
    assert captured
    assert "previous draft changed the article's sport taxonomy" in captured[0]
    assert "TAXONOMY LOCK: the exact article sport is rugby-league" in captured[0]


@pytest.mark.parametrize("index_failure", [False, True])
def test_nonpublic_original_is_never_counted_as_published(monkeypatch, index_failure):
    from database import SessionLocal
    from models import Article, ArticleTaxonomyResolution
    item = prepare_ingest(monkeypatch)
    item['url'] = f'https://example.test/held-public-admission-{index_failure}'
    persist = public_index.persist_public_article

    def hold(db, article, *args, **kwargs):
        if index_failure:
            raise RuntimeError('synthetic index failure')
        persist(db, article, *args, **kwargs)
        row = db.query(ArticleTaxonomyResolution).filter_by(article_id=article.id).one()
        row.public_ok = False
        db.commit()

    monkeypatch.setattr(public_index, 'persist_public_article', hold)
    db = SessionLocal()
    try:
        assert ingest._ingest_item(db, item, True, 6000, 1) == (None, False)
        assert db.query(Article).filter_by(source_url=item['url']).count() == 1
        from public_read import public_query
        assert public_query(db).filter(Article.source_url == item['url']).first() is None
    finally:
        db.close()


def test_rss_ingest_tries_same_article_alternative_photo_before_spending_ai(monkeypatch):
    from bot import extract as extract_module
    item=prepare_ingest(monkeypatch)
    monkeypatch.setattr(ingest,'news_image_is_reachable',lambda url:url.endswith('good.jpg'))
    fetched=[]
    monkeypatch.setattr(extract_module,'extract_image_candidates_from_url',lambda url:fetched.append(url) or [
        {'url':'https://example.test/dead.jpg','source':'body','in_article':True},
        {'url':'https://example.test/good.jpg','source':'og'},
    ])
    writer_call=Mock(return_value=(None,'empty'))
    monkeypatch.setattr(ingest,'_ai_story',writer_call)
    assert ingest._ingest_item(Mock(),item,True,6000,1) == (None,False)
    assert fetched == [item['url']]
    writer_call.assert_called_once()
