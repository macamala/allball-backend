from datetime import datetime, timezone
import pytest
from bot import fetch_sources as fs
from bot.feeds import enabled_feeds, news_source_is_excluded
from bot.news_football_sources import HTML_INDEXES, RSS_FEEDS

def xml(content, *, link='https://example.org/story/1/', summary='A teaser with no article facts.'):
    return f'''<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Football</title><item><title>United appoint a new coach for the next season</title><link>{link}</link><pubDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate><description><![CDATA[<p>{summary}</p>]]></description><content:encoded><![CDATA[{content}]]></content:encoded></item></channel></rss>'''.encode()

@pytest.fixture
def cfg():
    return {'url':'https://example.org/feed/','kind':'league','sport':'football','verified_body_field':'content','verified_body_min_words':120}

def test_only_verified_full_feed_field_becomes_source_body(monkeypatch,cfg):
    text='The football club confirmed the appointment of its new coach after the board meeting. '*12
    monkeypatch.setattr(fs,'read_news_feed',lambda _:xml('<p>'+text+'</p>'))
    rows=fs._fetch_feed_entries(cfg,3)
    assert len(rows)==1
    assert rows[0]['_source_body_origin']=='verified-full-rss'
    assert 'teaser' not in rows[0]['_extracted']
    assert rows[0]['_publication_evidence']=='rss-published'
    assert rows[0]['_classification_text']==rows[0]['_extracted']

@pytest.mark.parametrize('variant',['thin','external','wrong_field'])
def test_full_feed_mode_fails_closed(monkeypatch,cfg,variant):
    content='<p>'+'The football club confirmed the appointment of its new coach. '*20+'</p>'
    if variant=='thin':content='<p>Not enough article facts.</p>'
    if variant=='wrong_field':cfg['verified_body_field']='invented'
    link='https://other.example/story/1/' if variant=='external' else 'https://example.org/story/1/'
    monkeypatch.setattr(fs,'read_news_feed',lambda _:xml(content,link=link))
    assert fs._fetch_feed_entries(cfg,3)==[]

def test_football_extension_retains_publisher_and_sport_guards(monkeypatch):
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY','1')
    sources=enabled_feeds()
    assert all(not news_source_is_excluded(source['url']) for source in sources)
    assert len({s['url'] for s in sources})==len(sources)
    conmebol=next(s for s in sources if s.get('publisher')=='CONMEBOL')
    assert conmebol['kind']=='mixed' and not conmebol.get('sport')
    argentina=next(s for s in sources if s.get('publisher')=='Liga Profesional')
    assert argentina['allowed_article_paths']==('/notas/primera/',)
    for source in HTML_INDEXES:
        assert source['sport']=='football' and not source.get('league')
        assert source['url'].startswith('https://'+source['host'])
    assert len(HTML_INDEXES)==13
    assert len({source["id"] for source in HTML_INDEXES})==13
