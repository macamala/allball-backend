from bot.classify import classify_article
from bot.feeds import enabled_feeds


def test_expanded_catalog_contains_new_free_sources(monkeypatch):
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED','1')
    rows=enabled_feeds()
    urls=[row['url'] for row in rows]
    assert len(urls)==len(set(urls))
    expected={
        'https://www.afl.com.au/rss',
        'https://feeds.bbci.co.uk/sport/badminton/rss.xml',
        'https://feeds.bbci.co.uk/sport/hockey/rss.xml',
        'https://feeds.bbci.co.uk/sport/table-tennis/rss.xml',
        'https://feeds.bbci.co.uk/sport/water-polo/rss.xml',
        'https://news.ea.com/rss/pressrelease.aspx',
    }
    assert expected <= set(urls)


def test_new_source_sports_classify_from_article_evidence():
    samples={
        'australian-rules': ('AFL Grand Final clubs prepare for premiership decider', 'Australian rules teams meet in the AFL Grand Final.'),
        'badminton': ('Badminton world champions return for final', 'The badminton tournament reaches its deciding matches.'),
        'field-hockey': ('Field hockey World Cup finalists confirmed', 'The field hockey tournament has reached the final.'),
        'table-tennis': ('Table tennis title decided after final', 'The table tennis championship concluded on Sunday.'),
        'water-polo': ('Water polo World Cup hosts announced', 'The water polo competition returns next season.'),
        'ea-sports-fc': ('EA SPORTS FC 27 competition update', 'EA SPORTS FC esports competition details were announced.'),
    }
    for sport,(title,body) in samples.items():
        tags=classify_article(title,body,feed_kind='mixed')
        assert tags.sport==sport, (sport,tags)
