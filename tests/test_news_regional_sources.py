from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from bot import extract as ex
from bot import fetch_sources as fs
from bot.news_football_sources import RSS_FEEDS
from bot.feeds import enabled_feeds

STORY = 'The football club announced the appointment after discussions with the coaching staff and the board. '
OTHER = 'Unrelated football headline about a different club and a separate competition that is not part of this article.'

def page(host, body, extra=''):
    return (f'<html><head><meta property="og:url" content="https://{host}/story/">'
            '<meta property="og:type" content="article"></head><body><main>' + body + extra + '</main></body></html>')

@pytest.mark.parametrize('host,container', [
    ('www.index.hr','<section class="text sport-link-underline">{}</section>'),
    ('nb1.hu','<div id="content-post" class="entry-content">{}</div>'),
    ('www.goal.pl','<div class="entry-content">{}</div>'),
])
def test_news_body_does_not_include_neighboring_articles(host,container):
    html=page(host, container.format('<p>'+STORY*8+'</p>'), '<article><p>'+OTHER+'</p></article>')
    body=ex.article_text_from_html(html)
    assert STORY.strip() in body
    assert OTHER not in body

@pytest.mark.parametrize('host',['www.index.hr','nb1.hu','www.goal.pl'])
def test_changed_or_absent_cms_body_fails_closed(host):
    assert ex.article_text_from_html(page(host,'<article><p>'+STORY*8+'</p></article>')) == ''

@pytest.mark.parametrize('host,container,widget',[
    ('nb1.hu','<div id="content-post">{}</div>','wp-embedded-content'),
    ('www.goal.pl','<div class="entry-content">{}</div>','related-post-container'),
    ('www.index.hr','<section class="text">{}</section>','js-slot-container'),
])
def test_in_article_recommendations_and_adverts_are_not_source_facts(host,container,widget):
    inner='<p>'+STORY*4+'</p><div class="'+widget+'"><p>'+OTHER+'</p></div><p>'+STORY*5+'</p>'
    body=ex.article_text_from_html(page(host,container.format(inner)))
    assert STORY.strip() in body and OTHER not in body

@pytest.mark.parametrize('host',['www.index.hr','nb1.hu','www.goal.pl'])
def test_only_same_article_social_hero_is_an_image_candidate(host):
    html=page(host,'<article><img src="https://photos.example/unrelated-football-1400.jpg" width="1400"></article>')
    assert ex.collect_page_image_candidates(html)==[]
    html=html.replace('</head>','<meta property="og:image" content="https://photos.example/article-1400.jpg"></head>')
    rows=ex.collect_page_image_candidates(html)
    assert [r['url'] for r in rows]==['https://photos.example/article-1400.jpg']


def test_existing_generic_extractors_keep_their_normal_default_behavior():
    body=ex.article_text_from_html(page('other.example','<article><p>'+STORY*3+'</p></article>'))
    assert STORY.strip() in body


def test_required_full_body_does_not_send_a_teaser_to_any_writer(monkeypatch):
    for name in ['news_source_is_excluded','openai_rate_limited','existing_by_url','_source_on_ai_cooldown','existing_near_duplicate']:
        monkeypatch.setattr(fs,name,lambda *args,**kwargs:False)
    monkeypatch.setattr(fs,'extract_from_url',lambda *args:('',None))
    monkeypatch.setattr(fs,'_ai_story',lambda **kwargs:pytest.fail('Writer called without verified article body'))
    item={'title':'Club announces a new coach','summary':STORY*10,'published_at':datetime.now(timezone.utc),
          'url':'https://www.goal.pl/ekstraklasa/club-news/','feed':{'article_body_required':True}}
    assert fs._ingest_item(None,item,True,8000,2)==(None,False)


def test_regional_feeds_are_unique_and_never_stamp_a_domestic_league(monkeypatch):
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY','1')
    feeds=enabled_feeds()
    for publisher in ['Index.hr','NB1.hu','Goal.pl','The72']:
        rows=[f for f in feeds if f.get('publisher')==publisher]
        assert len(rows)==(2 if publisher=='NB1.hu' else 1)
        if publisher=='NB1.hu':
            assert {row['url'] for row in rows}=={'https://nb1.hu/feed/','https://nb1.hu/category/nb2/feed/'}
        for row in rows:
            assert row['kind']=='league' and row['sport']=='football'
            assert not row.get('league') and row['verified_official'] is False
    assert len({f['url'] for f in feeds})==len(feeds)


def test_the72_full_feed_admission_keeps_date_and_rejects_teasers(monkeypatch):
    cfg=next(f for f in RSS_FEEDS if f.get('publisher')=='The72')
    stamp=datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    def feed(content):return f'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>EFL</title><item><title>Club appoints a new head coach</title><link>https://the72.co.uk/2026/10/02/club-new-coach/</link><pubDate>{stamp}</pubDate><description>Only a short teaser.</description><content:encoded><![CDATA[<p>{content}</p>]]></content:encoded></item></channel></rss>'''.encode()
    monkeypatch.setattr(fs,'read_news_feed',lambda _:feed(STORY*12))
    rows=fs._fetch_feed_entries(cfg,2)
    assert len(rows)==1 and rows[0]['_source_body_origin']=='verified-full-rss'
    assert 'teaser' not in rows[0]['_extracted']
    assert rows[0]['_publication_evidence']=='rss-published'
    monkeypatch.setattr(fs,'read_news_feed',lambda _:feed('A teaser without the article.'))
    assert fs._fetch_feed_entries(cfg,2)==[]
