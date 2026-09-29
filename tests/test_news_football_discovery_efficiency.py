from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from bot import fetch_sources
from bot.feeds import FEEDS
from bot.news_policy import non_article_news_reason, source_path_sport_hint


def test_mozzart_football_rss_preserves_exact_dates_and_rejects_future_and_other_sports(monkeypatch):
    cfg = next(row for row in FEEDS if row['url'] == 'https://www.mozzartsport.com/rss/1.xml')
    now = datetime.now(timezone.utc).replace(microsecond=0)
    cases = [('/fudbal/vesti/confirmed-player-news/555078', now - timedelta(hours=1)),
             ('/fudbal/vesti/future/555079', now + timedelta(hours=1)),
             ('/fudbal/vesti/stale/555080', now - timedelta(hours=25)),
             ('/kosarka/vesti/basketball/555081', now - timedelta(hours=1))]
    items = ''.join(f'<item><title>Confirmed player news {i}</title><link>https://www.mozzartsport.com{path}</link><pubDate>{format_datetime(stamp)}</pubDate></item>'
                    for i, (path, stamp) in enumerate(cases))
    monkeypatch.setattr(fetch_sources, 'read_news_feed', lambda _: f'<rss version="2.0"><channel>{items}</channel></rss>'.encode())
    rows = fetch_sources._fetch_feed_entries(cfg, 50)
    assert len(rows) == 1
    assert rows[0]['published_at'] == cases[0][1]
    assert rows[0]['feed']['sport'] == 'football'
    assert not rows[0]['feed'].get('league')


def test_shared_zlin_club_does_not_make_czech_hockey_a_football_candidate():
    url = 'https://isport.blesk.cz/clanek/hokej-domaci-souteze-maxa-liga/480381/zlin-resi-krizi.html'
    item = {'url': url, 'title': 'Zlín řeší krizi. Hráči neplní své role, říká manažer Balaštík.', 'feed': {'kind': 'mixed'}}
    assert source_path_sport_hint(url) == 'ice-hockey'
    assert fetch_sources._classify_candidate(item).sport == 'ice-hockey'
    assert source_path_sport_hint(url.replace('isport.blesk.cz', 'other.test')) is None
    # The previously repaired explicit-UFC rule remains stronger than a path.
    assert fetch_sources._classify_candidate({**item, 'title': 'UFC announces title fight'}).sport == 'mma'


def test_fundraising_hospitality_is_rejected_but_sporting_and_charity_news_survive():
    for title in ('Forever Reds festive fundraising lunch returns to Anfield in December',
                  'Club announces a gala dinner', 'Forever Reds Christmas Lunch returns'):
        assert non_article_news_reason({'title': title}) == 'non_article_event_promotion'
    for title in ('Club confirms Christmas football fixture changes',
                  'Club donates funds to local hospital', 'Forward returns to training after injury'):
        assert non_article_news_reason({'title': title}) is None
    assert non_article_news_reason({'title': 'LUDI TIKET, utorak, 370.849 dinara: Majstorija sa Zlatibora'}) == 'non_article_betting_product'
    assert non_article_news_reason({'title': 'Rezzime jučeršanjeg dan (ponedeljak): Zamalo pa perfekcija',
        'url': 'https://www.mozzartsport.com/fudbal/vesti/rezzime-jucersanjeg-dan-ponedeljak-zamalo-pa-perfekcija/555066'}) == 'non_article_betting_product'
