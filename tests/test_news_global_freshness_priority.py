from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bot.news_policy import NEWS_FRESHNESS_HOURS, fair_news_queue, news_freshness_reason, queue_priority_score
from bot.news_football_priority import football_editorial_priority


@pytest.mark.parametrize('now', [
    datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc),  # 00:05 Sydney
    datetime(2026, 10, 4, 13, 5, tzinfo=timezone.utc),  # 00:05 Sydney after DST
    datetime(2026, 9, 29, 0, 5, tzinfo=timezone.utc),   # UTC midnight
])
def test_recent_news_survives_calendar_midnight_without_retiming(now):
    stamp = now - timedelta(hours=1)
    before = stamp.isoformat()
    assert news_freshness_reason(stamp, now) is None
    for zone in ('Australia/Sydney', 'Europe/Belgrade', 'America/New_York'):
        assert news_freshness_reason(stamp.astimezone(ZoneInfo(zone)), now) is None
    assert stamp.isoformat() == before


def test_elapsed_age_does_not_allow_old_future_or_unverified_publication():
    now = datetime(2026, 9, 29, 7, tzinfo=timezone.utc)
    assert news_freshness_reason(now-timedelta(hours=24), now) is None
    assert news_freshness_reason(now-timedelta(hours=24, microseconds=1), now) == 'stale_publication'
    assert news_freshness_reason(now+timedelta(microseconds=1), now) == 'future_publication'
    assert news_freshness_reason(now.replace(tzinfo=None), now) == 'publication_time_unverified'
    assert news_freshness_reason(None, now) == 'publication_time_unverified'


def test_ranking_has_no_hidden_sydney_calendar_bonus(monkeypatch):
    stamp = datetime(2026, 9, 28, 13, 55, tzinfo=timezone.utc)
    now = stamp + timedelta(minutes=15)
    item = {'title':'Club confirms new coach', 'published_at':stamp}
    monkeypatch.setenv('NEWS_EDITORIAL_TIMEZONE', 'Australia/Sydney')
    a = queue_priority_score(item, now)
    monkeypatch.setenv('NEWS_EDITORIAL_TIMEZONE', 'America/New_York')
    assert queue_priority_score(item, now) == a


def test_primary_soccer_stays_ahead_even_when_other_publishers_have_richer_copy():
    now = datetime(2026, 9, 29, 7, tzinfo=timezone.utc)
    def row(host, title, league=None, age=1):
        return {'url':f'https://{host}/article', 'title':title, 'published_at':now-timedelta(hours=age),
                'sport':'football', 'league':league, 'feed':{'sport':'football'}}
    rows = [row('ge.globo.com','Botafogo sign new captain and win championship'),
            row('aleagues.com.au','Mariners appoint new coach and sign player'),
            row('crvenazvezdafk.com','Клуб потврдио промене у саставу',age=19),
            row('major.test','Club confirms injury',league='england-premier-league'),
            row('another.test','Bundesliga club names coach')]
    rows[0]['_extracted'] = 'Verified football facts. '*100
    before = repr(rows)
    classify = lambda item: SimpleNamespace(sport=item['sport'], league=item['league'])
    result, reasons = fair_news_queue(rows, classify, now=now, max_age_hours=NEWS_FRESHNESS_HOURS,
        allowed_sports={'football'}, prioritize_major_sports=True, spread_publishers=True)
    assert not reasons and len(result) == 5
    assert [x['url'] for x in result[:3]] == [rows[2]['url'],rows[3]['url'],rows[4]['url']]
    assert repr(rows) == before


@pytest.mark.parametrize('title', ['Црвена звезда потврдила појачање', 'Crvena zvezda potvrdila pojačanje',
    'U Crvenoj zvezdi potvrđene promene', 'Red Star Belgrade confirm new signing'])
def test_zvezda_aliases_enter_primary_soccer_but_never_basketball(title):
    item = {'title':title, 'url':'https://publisher.test/article'}
    assert football_editorial_priority(item, SimpleNamespace(sport='football',league=None)) == 2
    assert football_editorial_priority(item, SimpleNamespace(sport='basketball',league=None)) == 0


def test_priority_never_releases_stale_news_or_promotions():
    now = datetime(2026, 9, 29, 7, tzinfo=timezone.utc)
    rows = [{'title':'Red Star Belgrade confirm signing', 'url':'https://crvenazvezdafk.com/old',
             'published_at':now-timedelta(hours=25)},
            {'title':'Red Star Belgrade tickets on sale', 'url':'https://crvenazvezdafk.com/tickets',
             'published_at':now-timedelta(hours=1)}]
    result, reasons = fair_news_queue(rows, lambda x:SimpleNamespace(sport='football',league=None),
        now=now, max_age_hours=NEWS_FRESHNESS_HOURS, spread_publishers=True)
    assert not result
    assert reasons == {'stale_publication':1,'non_article_commercial_promotion':1}


def test_hln_football_named_feed_cannot_force_racing_into_soccer():
    from bot.fetch_sources import _classify_candidate
    from bot.feeds import FEEDS
    feed = next(x for x in FEEDS if x['url'] == 'https://www.hln.be/sport/voetbal/rss.xml')
    assert feed['kind'] == 'mixed' and not feed.get('sport')
    item = {'title':'Lando Norris apologises for comments',
            'url':'https://www.hln.be/formule-1/lando-norris~aa99b175/', 'feed':feed}
    assert _classify_candidate(item).sport == 'motorsport'
