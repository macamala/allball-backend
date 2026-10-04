"""Discovery cannot lose unseen stories behind a full prefix of known URLs."""
from collections import Counter
import json
import pytest
from bot import news_official_indexes as idx
from bot import news_index_selection as selection
from bot.news_policy import news_source_identity


@pytest.fixture(autouse=True)
def clear_selection_cache():
    with selection._LOCK:
        selection._STALE.clear()
    yield
    with selection._LOCK:
        selection._STALE.clear()


def config(**extra):
    return {'id':'selection-test','sport':'football','publisher':'Example league',
            'url':'https://example.test/news/','host':'example.test',
            'paths':('/news/',),'article_path_re':r'^/news/story-\d+/?$',**extra}


def links(count=25):
    return ['https://example.test/news/story-'+str(i) for i in range(count)]


def html(count=25):
    return ''.join('<a href="'+url+'">Club announces development '+str(i)+'</a>'
                   for i,url in enumerate(links(count))).encode()


def test_eight_known_headlines_do_not_exhaust_the_eight_unseen_link_quota(monkeypatch):
    monkeypatch.setattr(idx,'read_news_feed',lambda url:html())
    cfg=config();unchanged=dict(cfg)
    selected=selection.discovery_config(cfg,links()[:8])
    assert [u for u,_ in idx._anchor_candidates(selected)]==links()[8:16]
    assert len(idx._anchor_candidates(cfg))==8
    assert cfg==unchanged and '_news_exclude_ids' not in cfg


def test_tracking_spellings_are_excluded_without_changing_emitted_url(monkeypatch):
    monkeypatch.setattr(idx,'read_news_feed',lambda url:html())
    known=[url+'?utm_source=newsletter' for url in links()[:8]]
    assert [u for u,_ in idx._anchor_candidates(selection.discovery_config(config(),known))]==links()[8:16]


def test_sitemap_quota_preserves_the_selected_url_publication_evidence(monkeypatch):
    xml='<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'+''.join(
        '<url><loc>'+url+'</loc><news:news><news:title>Football club news</news:title>'
        '<news:publication_date>2026-10-04T04:30:00Z</news:publication_date></news:news></url>'
        for url in links())+'</urlset>'
    monkeypatch.setattr(idx,'read_news_feed',lambda url:xml.encode())
    cfg=selection.discovery_config(config(url_markers=('/news/',)),links()[:8]);dates={}
    chosen=idx._sitemap_candidates(cfg,publication_times=dates)
    assert [u for u,_ in chosen]==links()[8:16]
    assert set(dates)==set(links()[8:16])
    assert all(d.hour==4 and d.minute==30 and d.tzinfo is not None for d in dates.values())


def test_scoped_chelsea_component_obeys_same_pre_quota_exclusions(monkeypatch):
    cfg=config(index_component='NewsListModule')
    items=[{'type':'Article','requiresLogin':False,'isPremiumContent':False,'url':url,'title':'Article '+str(i)} for i,url in enumerate(links())]
    monkeypatch.setattr(idx,'read_news_feed',lambda url:b'html')
    monkeypatch.setattr(idx,'public_components',lambda *args:{'NewsListModule':{'initialContent':{'items':items}}})
    assert [u for u,_ in idx._anchor_candidates(selection.discovery_config(cfg,links()[:8]))]==links()[8:16]
    items[8]['isPremiumContent']=True
    assert links()[8] not in {u for u,_ in idx._anchor_candidates(selection.discovery_config(cfg,links()[:8]))}


def test_full_source_hydration_reaches_unseen_articles_without_extra_page_requests(monkeypatch):
    monkeypatch.setattr(idx,'read_news_feed',lambda url:html())
    calls=[]
    def hydrate(cfg,url,title,**kwargs):
        calls.append(url)
        return {'url':url,'title':title,'original_date':'unchanged'}
    monkeypatch.setattr(idx,'_hydrate',hydrate)
    found=idx._hydrate_source(config(),3,known_urls=links()[:8])
    assert [r['url'] for r in found]==links()[8:11]
    assert calls==links()[8:11]
    assert all(r['original_date']=='unchanged' for r in found)


def test_confirmed_stale_prefix_yields_to_other_stories_next_cycle(monkeypatch):
    monkeypatch.setattr(idx,'read_news_feed',lambda url:html())
    calls=[]
    def hydrate(cfg,url,title,*,diagnostics,**kwargs):
        calls.append(url)
        if url in links()[:8]:
            diagnostics['stale_publication']+=1
            return None
        return {'url':url}
    monkeypatch.setattr(idx,'_hydrate',hydrate)
    assert idx._hydrate_source(config(),3)==[]
    assert calls==links()[:8]
    calls.clear()
    assert [r['url'] for r in idx._hydrate_source(config(),3)]==links()[8:11]
    assert calls==links()[8:11] and len(calls)<=idx.MAX_LINKS_PER_SOURCE


@pytest.mark.parametrize('reason',['future_publication','publication_time_unverified','missing_article_body',
    'missing_image_candidates','feed_http_429','feed_robots_disallowed','request_failed','restricted_article'])
def test_transport_access_and_unverified_dates_never_enter_stale_cache(reason):
    cfg=config();url=links()[0]
    selection.record_stale_index_page(cfg,url,Counter({reason:1}))
    assert not selection.excluded_index_link(selection.discovery_config(cfg),url)


def test_successful_story_waiting_for_ai_is_not_excluded_by_discovery():
    cfg=config();url=links()[0]
    selection.record_stale_index_page(cfg,url,{})
    assert not selection.excluded_index_link(selection.discovery_config(cfg),url)


def test_stale_cache_is_desk_specific_expires_and_is_bounded(monkeypatch):
    clock=[100.0];monkeypatch.setattr(selection.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(selection,'_MAX_STALE',3)
    cfg=config()
    for url in links(4):selection.record_stale_index_page(cfg,url,{'stale_publication':1})
    assert len(selection._STALE)==3
    chosen=selection.discovery_config(cfg)
    assert not selection.excluded_index_link(chosen,links()[0])
    assert selection.excluded_index_link(chosen,links()[1])
    assert not selection.excluded_index_link(selection.discovery_config(config(id='other-desk')),links()[1])
    clock[0]+=selection._STALE_SECONDS+1
    assert not selection.discovery_config(cfg)['_news_exclude_ids'] and not selection._STALE


def test_other_sports_keep_their_existing_index_selection():
    cfg=config(sport='basketball')
    selection.record_stale_index_page(cfg,links()[0],{'stale_publication':1})
    assert selection.discovery_config(cfg,links()) is cfg
    assert not selection._STALE


def test_exclusion_never_reintroduces_cross_host_or_non_article_links(monkeypatch):
    bad='<a href="https://evil.test/news/story-1">Foreign article</a><a href="/news/">News</a>'
    monkeypatch.setattr(idx,'read_news_feed',lambda url:bad.encode()+html())
    cfg=selection.discovery_config(config(),links()[:8])
    assert [u for u,_ in idx._anchor_candidates(cfg)]==links()[8:16]
