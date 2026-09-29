from datetime import datetime, timedelta, timezone

import pytest

from bot import feeds, news_official_indexes as indexes
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.fetch_sources import _classify_candidate, source_article_facts
from bot.news_image_http import pick_news_article_image
from bot.news_policy import fair_news_queue, non_article_news_reason
from bot.textutil import word_count


def test_focus_selects_soccer_without_relabelling_other_football_or_old_news():
    now = datetime(2026, 9, 29, 6, tzinfo=timezone.utc)
    rows = [dict(title=title, url=f'https://example.test/{i}', published_at=stamp,
                 feed={'kind': 'league', 'sport': sport}) for i, (title, sport, stamp) in enumerate([
        ('Football club confirms new coach', 'football', now),
        ('NFL club confirms new coach', 'american-football', now),
        ('AFL team confirms new coach', 'australian-rules', now),
        ('Football club confirms new coach yesterday', 'football', now-timedelta(days=1)),
    ])]
    selected, reasons = fair_news_queue(rows, _classify_candidate, now=now,
        same_day_timezone='Australia/Sydney', allowed_sports={'football'}, prioritize_major_sports=True)
    assert [x['url'] for x in selected] == ['https://example.test/0']
    assert reasons == {'outside_editorial_focus': 2, 'not_editorial_today': 1}
    all_sports, _ = fair_news_queue(rows, _classify_candidate, now=now, same_day_timezone='Australia/Sydney')
    assert len(all_sports) == 3


def test_focus_discovery_preserves_mixed_sources_and_does_not_mutate_catalog(monkeypatch):
    monkeypatch.setenv('NEWS_EXPANDED_FEEDS_ENABLED', '1')
    before = repr(feeds.FEEDS)
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY', '1')
    selected = feeds.enabled_feeds()
    assert selected and all(not x.get('sport') or x['sport'] == 'football' for x in selected)
    assert any(x['url'] == 'https://www.b92.net/rss/sport' for x in selected)
    assert all('bbci.co.uk' not in x['url'] for x in selected)
    seen = []
    monkeypatch.setattr(indexes, '_hydrate_source', lambda cfg, limit, **kwargs: seen.append(cfg) or [])
    assert indexes.fetch_official_index_entries() == []
    assert seen and all(not x.get('sport') or x['sport'] == 'football' for x in seen)
    assert any(x['id'] == 'uefa-football-competitions' for x in seen)
    monkeypatch.delenv('NEWS_FOOTBALL_ONLY')
    assert any(x.get('sport') == 'basketball' for x in feeds.enabled_feeds())
    assert repr(feeds.FEEDS) == before


def test_cyrillic_source_word_count_is_real_but_numeric_tables_are_not_prose():
    prose = 'Репрезентација Србије наставља припреме за предстојеће утакмице. '
    assert word_count(prose * 5) == 35
    assert word_count('0 1 2 3 4 5 _ __') == 0
    assert source_article_facts('', prose * 5, 'https://fss.rs/example/')[1] == 'rss-fallback'


def test_federation_body_and_css_hero_exclude_neighbouring_stories():
    photo = 'https://fss.rs/wp-content/uploads/2026/09/MET_5386-1-scaled.jpg'
    gallery = 'https://fss.rs/wp-content/uploads/2026/09/other-match-angle.jpg'
    html = '<link rel="canonical" href="https://fss.rs/team-news/">'
    html += '<meta property="og:image" content="https://fss.rs/wp-content/uploads/2026/09/MET_5386-1-780x460.jpg">'
    html += '<div class="fss-single__featimg"><div class="fss-single__featimg-cont" style="background-image: url(' + photo + ')"></div></div>'
    html += '<div class="fss-single__content"><p>Селектор Србије потврдио је промене у саставу репрезентације.</p>'
    html += '<a class="fss-gallery__link" style="background-image:url(' + gallery + ')"></a></div>'
    html += '<div class="fss-single__underpost"><p>Other club signs an unrelated player.</p>'
    html += '<img src="https://fss.rs/unrelated.jpg"><a class="fss-gallery__link" style="background-image:url(https://fss.rs/wp-content/uploads/unrelated.jpg)"></a></div>'
    body = article_text_from_html(html)
    assert 'Селектор Србије' in body and 'unrelated' not in body
    images = collect_page_image_candidates(html)
    assert photo in {i['url'] for i in images} and gallery in {i['url'] for i in images}
    assert all('unrelated' not in i['url'] for i in images)
    assert pick_news_article_image(images) == photo


def test_marca_body_and_images_stay_inside_the_report():
    prose = 'El club confirmó la contratación del nuevo entrenador para el equipo de fútbol. '
    html = '<link rel="canonical" href="https://www.marca.com/futbol/club/news.html">'
    html += '<meta property="og:image" content="https://example.test/coach-photo.jpg">'
    html += '<div class="ue-c-article__body"><p>' + prose * 5 + '</p></div>'
    html += '<article><p>Unrelated story about another team.</p><img src="https://example.test/unrelated.jpg"></article>'
    assert 'Unrelated' not in article_text_from_html(html)
    assert [x['url'] for x in collect_page_image_candidates(html)] == ['https://example.test/coach-photo.jpg']
    assert not article_text_from_html(html.replace('ue-c-article__body', 'missing-body'))


@pytest.mark.parametrize('url,reason', [
    ('https://www.marca.com/futbol/seleccion/opinion/2026/09/29/example.html', 'non_article_analysis'),
    ('https://www.marca.com/futbol/en-directo/2026/09/29/example.html', 'non_article_live_program'),
    ('https://www.sportschau.de/fussball/nationsleague/match,video-nations-league-100.html', 'non_article_video_highlights'),
    ('https://www.ardsounds.de/episode/urn:ard:episode:123/', 'non_article_podcast'),
    ('https://www.marca.com/futbol/andorra/2026/09/29/confirmed-sanction.html', None),
])
def test_new_football_sources_keep_only_news_products(url, reason):
    assert non_article_news_reason({'url': url, 'title': 'Federation confirms decision'}) == reason


@pytest.mark.parametrize('audited', [False, True])
def test_photo_fix_expires_only_audited_prefixed_cooldowns(monkeypatch, audited):
    from bot import news_source_holds as holds
    url = ('https://fss.rs/a-tim-promene-u-sastavu-pred-nastavak-lige-nacija/'
           if audited else 'https://other.test/held-article')
    statements = []
    class Cursor:
        rowcount = 1
        def execute(self, query, params=None): statements.append((query, params))
        def fetchall(self): return [(holds._fingerprint(url), 'validator-unsupported-claim')]
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(holds, '_postgres_dsn', lambda: 'fixture')
    monkeypatch.setattr(holds, '_connect', lambda dsn: Connection())
    monkeypatch.setattr(holds, '_ensure_schema', lambda cursor: None)
    # Even an audited URL must remain held for an unrelated editorial failure.
    assert holds.held_source_urls([url]) == {url}
    writes = [(q, p) for q, p in statements if q.startswith('UPDATE')]
    assert len(writes) == int(audited)
    if audited:
        query, params = writes[0]
        assert params == ([holds._fingerprint(url)], '2026-09-29T05:55:00Z')
        assert "reason='missing-or-unreachable-publishable-image'" in query
        assert 'updated_at < %s::timestamptz' in query
