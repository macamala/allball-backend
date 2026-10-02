from bot.classify import classify_article
from bot.feeds import enabled_feeds


def test_expanded_catalog_contains_new_free_sources(monkeypatch):
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED','1')
    rows=enabled_feeds()
    urls=[row['url'] for row in rows]
    assert len(urls)==len(set(urls))
    expected={
        'https://www.afl.com.au/rss',
        'https://pbsi.id/feed/',
        'https://www.tabletennisengland.co.uk/feed',
        'https://total-waterpolo.com/feed/',
        'https://www.kleagueunited.com/feeds/posts/default?alt=rss',
    }
    assert expected <= set(urls)
    from bot.feeds import news_source_is_excluded
    assert not any(news_source_is_excluded(url) for url in urls)


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


def test_dedicated_feed_can_hint_sport_when_article_text_is_silent(monkeypatch):
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED','1')
    rows=enabled_feeds()
    afl=next(row for row in rows if row['url']=='https://www.afl.com.au/rss')
    assert afl['kind']=='league'
    tags=classify_article(
        'Swans name squad for Sunday clash',
        'The club confirmed its squad and coaching changes before Sunday.',
        feed_kind=afl['kind'],
        feed_sport=afl['sport'],
        feed_league=afl.get('league'),
        feed_country=afl.get('country'),
    )
    assert tags.sport=='australian-rules'


def test_dead_cross_product_ea_press_feed_stays_removed(monkeypatch):
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED','1')
    urls={row['url'] for row in enabled_feeds()}
    assert 'https://news.ea.com/rss/pressrelease.aspx' not in urls


def test_table_tennis_and_futsal_fallback_feeds_are_present():
    from bot.news_verified_feeds import VERIFIED_RSS
    by_url={row['url']:row for row in VERIFIED_RSS}
    assert by_url['https://www.tabletennisengland.co.uk/feed']['sport']=='table-tennis'
    assert by_url['https://www.futsalfocus.net/feed']['sport']=='futsal'


def test_espn_dedicated_sport_feeds_are_enabled_without_league_stamp():
    from bot.feeds import FEEDS
    by_url={row["url"]:row for row in FEEDS}
    expected={
        "https://www.espn.com/espn/rss/mlb/news":"baseball",
        "https://www.espn.com/espn/rss/nfl/news":"american-football",
        "https://www.espn.com/espn/rss/nhl/news":"ice-hockey",
        "https://www.espn.com/espn/rss/golf/news":"golf",
    }
    for url,sport in expected.items():
        row=by_url[url]
        assert row["enabled"] is True
        assert row["sport"]==sport
        assert row.get("league") is None


def test_espn_feeds_are_rss_fallback_only():
    from bot.feeds import FEEDS
    rows=[row for row in FEEDS if row["url"].startswith("https://www.espn.com/espn/rss/")]
    assert rows
    assert all(row.get("rss_fallback_only") is True for row in rows)
