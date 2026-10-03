import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_football_regional_desks import RSS_FEEDS, SOURCE_DESKS, regional_article_profile, excluded_feed_entry
from bot.news_policy import source_path_sport_hint

TEXT = ' '.join(['The football club confirmed its preparation schedule and the coach discussed the players available for the next match.'] * 8)
OUTSIDE = 'Unrelated recommendation describes another club and a transfer fee not mentioned in this story.'
CASES = [
    ('https://www.football-espana.net/2026/10/03/article', 'div', 'id="article-body"'),
    ('https://www.getfootballnewsgermany.com/2026/article/', 'div', 'class="entry-content"'),
    ('https://fotbolldirekt.se/allsvenskan/article/', 'div', 'class="entry-content"'),
    ('https://www.suomifutis.com/2026/10/article/', 'div', 'class="post-content"'),
    ('https://liga2.prosport.ro/seria-1/article-1234', 'div', 'class="single__content"'),
    ('https://www.blick.ch/sport/fussball/article-id123.html', 'article', 'class="Body__StyledContainer-sc-example-0"'),
    ('https://news.stv.tv/sport/article', 'div', 'class="article-content post-body"'),
    ('https://gong.bg/bg-football/article-123', 'div', 'class="article-content"'),
    ('https://equalizersoccer.com/2026/10/03/article/', 'div', 'id="mvp-content-main"'),
]

def page(url, inner, free=True, extra=''):
    access = {'@type':'NewsArticle','headline':'Confirmed football news'}
    if free is not None:
        access['isAccessibleForFree'] = free
    return (f'<link rel="canonical" href="{url}"><meta property="og:type" content="article">'
            f'<meta property="og:image" content="https://images.example.com/real-story.jpg">'
            '<meta name="twitter:image" content="https://images.example.com/real-story-twitter.jpg">'
            f'<script type="application/ld+json">{json.dumps(access)}</script>'
            f'<main><p>{OUTSIDE}</p>{inner}<aside><p>{OUTSIDE}</p></aside>{extra}</main>')

@pytest.mark.parametrize('url,tag,attrs', CASES)
def test_only_reviewed_visible_container_supplies_article_prose(url,tag,attrs):
    html=page(url,f'<{tag} {attrs}><p>{TEXT}</p></{tag}>')
    result=article_text_from_html(html)
    assert TEXT.rstrip('.') in result
    assert OUTSIDE not in result

@pytest.mark.parametrize('url,tag,attrs', CASES)
def test_missing_reviewed_container_cannot_fall_back_to_recommendations(url,tag,attrs):
    assert article_text_from_html(page(url,f'<article><p>{TEXT}</p></article>')) == ''

@pytest.mark.parametrize('url,tag,attrs', CASES)
def test_jsonld_other_images_and_neighbour_cards_are_not_fallback_heroes(url,tag,attrs):
    other=json.dumps({'@type':'NewsArticle','image':'https://images.example.com/other-story.jpg'})
    html=page(url,f'<{tag} {attrs}><p>{TEXT}</p><img src="https://images.example.com/card.jpg" width="1000"></{tag}>',extra=f'<script type="application/ld+json">{other}</script>')
    images=collect_page_image_candidates(html)
    assert {r['source'] for r in images} == {'og','twitter'}
    assert {r['url'] for r in images} == {'https://images.example.com/real-story.jpg','https://images.example.com/real-story-twitter.jpg'}

@pytest.mark.parametrize('idx', [2,5])
@pytest.mark.parametrize('free', [None,False,'true',1])
def test_publishers_with_paid_reports_need_explicit_boolean_free_article_metadata(idx,free):
    url,tag,attrs=CASES[idx]
    assert article_text_from_html(page(url,f'<{tag} {attrs}><p>{TEXT}</p></{tag}>',free=free)) == ''

@pytest.mark.parametrize('idx', range(len(CASES)))
def test_explicit_paid_article_flag_always_holds_copy(idx):
    url,tag,attrs=CASES[idx]
    assert article_text_from_html(page(url,f'<{tag} {attrs}><p>{TEXT}</p></{tag}>',free=False)) == ''

@pytest.mark.parametrize('paid_class', ['equalizer-paywall','paywall-block','subscriber-only','membership-required'])
def test_equalizer_visible_access_barrier_cannot_be_bypassed_by_html_or_jsonld_copy(paid_class):
    url,tag,attrs=CASES[-1]
    hidden=json.dumps({'@type':'NewsArticle','articleBody':TEXT})
    html=page(url,f'<{tag} {attrs}><p>{TEXT}</p><div class="{paid_class}">Members only</div><script type="application/ld+json">{hidden}</script></{tag}>')
    assert article_text_from_html(html)==''


def test_css_or_javascript_word_paywall_does_not_misidentify_a_public_article():
    url,tag,attrs=CASES[2]
    html=page(url,f'<{tag} {attrs}><p>{TEXT}</p></{tag}>',extra='<style>.paywall-block{display:none}</style><script>const word="paywall-block";</script>')
    assert TEXT.rstrip('.') in article_text_from_html(html)


def test_whatsapp_callout_inside_stv_body_is_not_news_fact():
    url,tag,attrs=CASES[6]
    html=page(url,f'<{tag} {attrs}><p>{TEXT}</p><div class="whatsapp-callout"><p>{OUTSIDE}</p></div></{tag}>')
    result=article_text_from_html(html)
    assert TEXT.rstrip('.') in result and OUTSIDE not in result


def test_dynamic_blick_class_must_be_unique_and_on_article_tag():
    url,tag,attrs=CASES[5]
    assert regional_article_profile(page(url,'<div class="Body__StyledContainer-abc"><p>'+TEXT+'</p></div>'),url)['blocked']
    html=page(url,'<article class="Body__StyledContainer-abc"><p>'+TEXT+'</p></article><article class="Body__StyledContainer-xyz"><p>'+TEXT+'</p></article>')
    assert regional_article_profile(html,url)['blocked']
    assert regional_article_profile('', 'https://www.blick.ch/sport/tennis/article') is None


def test_malformed_type_array_and_nonarticle_access_flags_cannot_unlock_paywall():
    url,tag,attrs=CASES[2]
    for node in [{'@type':[{}],'isAccessibleForFree':True},{'@type':'Organization','isAccessibleForFree':True}]:
        html=page(url,f'<{tag} {attrs}><p>{TEXT}</p></{tag}>',free=None)+f'<script type="application/ld+json">{json.dumps(node)}</script>'
        assert article_text_from_html(html)==''


def test_entry_categories_only_filter_explicitly_configured_desks():
    cfg={'excluded_entry_categories':['Opinion','LIVE-TEXT','Extra']}
    assert excluded_feed_entry(cfg,{'tags':[{'term':'opinion'}]})
    assert excluded_feed_entry(cfg,{'tags':[{'term':'Live-Text'}]})
    assert not excluded_feed_entry(cfg,{'tags':[{'term':'News'}]})
    assert not excluded_feed_entry({}, {'tags':[{'term':'Opinion'}]})
    assert not excluded_feed_entry(cfg, {'tags':['bad',{}]})


def test_filters_are_wired_into_the_existing_rss_intake(monkeypatch):
    from bot import fetch_sources as fetch
    stamp=datetime.now(timezone.utc).isoformat()
    entry=lambda term:{'title':'Club confirms new football coach','link':'https://desk.example/news/one','published':stamp,'summary':TEXT,'tags':[{'term':term}]}
    monkeypatch.setattr(fetch,'read_news_feed',lambda url:b'feed')
    monkeypatch.setattr(fetch.feedparser,'parse',lambda raw:SimpleNamespace(version='rss20',entries=[entry('Opinion'),entry('News')],bozo=False))
    cfg={'url':'https://desk.example/feed','kind':'league','sport':'football','excluded_entry_categories':['Opinion']}
    assert len(fetch._fetch_feed_entries(cfg,10))==1
    assert len(fetch._fetch_feed_entries({**cfg,'excluded_entry_categories':[]},10))==2


def test_desks_join_existing_pipeline_without_creating_blanket_competition_facts():
    from bot.news_football_sources import RSS_FEEDS as all_feeds
    assert len(RSS_FEEDS)==9 and len({r['url'] for r in RSS_FEEDS})==9
    assert all(r in all_feeds for r in RSS_FEEDS)
    for row in RSS_FEEDS:
        assert row['article_body_required'] is True
        assert row.get('league') is None and row.get('country') is None
        assert 'verified_body_field' not in row
        assert 'exclude_article_paths' not in row
    assert next(r for r in RSS_FEEDS if r['publisher']=='STV Sport')['kind']=='mixed'
    assert next(r for r in RSS_FEEDS if r['publisher']=='Gong')['kind']=='mixed'


def test_gong_football_path_hint_is_exact_and_never_selects_a_league():
    assert source_path_sport_hint('https://gong.bg/football-sviat/drugi/article')=='football'
    assert source_path_sport_hint('https://gong.bg/bg-football/parva-liga/article')=='football'
    assert source_path_sport_hint('https://gong.bg/basketball/article') is None
    assert source_path_sport_hint('https://fakegong.bg/bg-football/article') is None
    assert source_path_sport_hint('https://gong.bg/not-football/article') is None
