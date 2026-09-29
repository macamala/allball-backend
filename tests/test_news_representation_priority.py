from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from bot.news_policy import fair_news_queue

NOW = datetime(2026, 9, 29, 3, tzinfo=timezone.utc)


def candidates():
    rss = {'url': 'https://www.espn.com/nba/story/_/id/123/team-update',
           'title': 'Basketball team confirms training squad', 'summary': 'Squad announced.',
           'published_at': NOW - timedelta(hours=1), 'sport': 'basketball'}
    rich = {**rss, '_extracted': 'A factual source description with the selection details.',
            'image_candidates': [{'url': 'https://a.espncdn.com/photo/player.jpg'}],
            'feed': {'kind': 'league', 'sport': 'basketball'}}
    return rss, rich


@pytest.mark.parametrize('reverse', [True, False])
def test_duplicate_discovery_keeps_richer_metadata_independent_of_collection_order(reverse):
    rss, rich = candidates()
    rows = [rss, rich] if reverse else [rich, rss]
    before = repr(rows)
    selected, rejected = fair_news_queue(rows, lambda row: SimpleNamespace(sport=row['sport']), now=NOW)
    assert selected == [rich]
    assert rejected == {'duplicate_source_url': 1}
    assert repr(rows) == before


@pytest.mark.parametrize('change,reason', [
    ({'published_at': NOW + timedelta(hours=1)}, 'future_publication'),
    ({'published_at': None}, 'publication_time_unverified'),
    ({'sport': None}, 'unknown_sport'),
    ({'title': 'Basketball podcast: coach discusses training'}, 'non_article_podcast'),
])
def test_rich_metadata_never_bypasses_admission_or_suppresses_valid_alternative(change, reason):
    rss, rich = candidates()
    rich.update(change)
    selected, rejected = fair_news_queue([rss, rich], lambda row: SimpleNamespace(sport=row['sport']), now=NOW)
    assert selected == [rss]
    assert rejected == {reason: 1}
