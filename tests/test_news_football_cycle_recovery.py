"""Keep scarce News requests for reports, not dated reference pages."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bot.news_policy import fair_news_queue, non_article_news_reason


@pytest.mark.parametrize('title', [
    "UEFA Women's Champions League records | UEFA Women's Champions League | UEFA.com",
    "Women's Champions League 2026/27 top scorer: Marie-Antoinette Katoto",
    "UEFA Women’s Champions League records",
    'UEFA Champions League records',
    'Champions League 2026/27 top scorers: current leaders',
])
def test_uefa_reference_pages_are_filtered_before_writer_queue(title):
    now = datetime(2026, 9, 30, 10, tzinfo=timezone.utc)
    item = {'title': title, 'url': 'https://www.uefa.com/womenschampionsleague/news/reference/',
            'published_at': now}
    assert non_article_news_reason(item) == 'non_article_rolling_tracker'
    selected, reasons = fair_news_queue([item],
        lambda _: SimpleNamespace(sport='football', league='uefa-womens-champions-league'), now=now)
    assert selected == [] and reasons == {'non_article_rolling_tracker': 1}


@pytest.mark.parametrize('title', [
    "Katoto breaks Women's Champions League record with hat-trick",
    "Women's Champions League top scorer confirms injury",
    "UEFA Women's Champions League records new attendance high",
    'Champions League top scorer receives award',
    'Champions League clubs confirm new contracts',
])
def test_actual_news_about_records_and_scorers_stays_eligible(title):
    assert non_article_news_reason({'title': title,
        'url': 'https://www.uefa.com/womenschampionsleague/news/new-report/'}) is None


def test_reference_filter_is_bounded_to_uefa_article_hosts():
    for url in ('https://uefa.com.other.test/news/report', 'https://reporter.test/news/report',
                'https://www.uefa.com/competition/report'):
        assert non_article_news_reason({'title': "UEFA Women's Champions League records", 'url': url}) is None
