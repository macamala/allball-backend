from datetime import datetime, timezone

import pytest

from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_policy import non_article_news_reason


def test_volleynews_scopes_article_and_excludes_social_embed_and_related_stories():
    prose = 'Il nuovo giocatore di pallavolo torna ad allenarsi con la squadra di Trento. '
    html = '<link rel="canonical" href="https://www.volleynews.it/trento-allenamento/">'
    html += '<div class="elementor-widget elementor-widget-my-custom-post-content"><p>' + prose * 5 + '</p>'
    html += '<blockquote class="instagram-media"><p>Un post condiviso da someone says an unrelated player moves clubs.</p></blockquote></div>'
    html += '<div><p>Recommended: Another team signs an unrelated player and coach.</p></div>'
    body = article_text_from_html(html)
    assert prose.strip() in body
    assert 'Un post' not in body and 'unrelated' not in body and 'Recommended' not in body
    assert not article_text_from_html(html.replace('elementor-widget-my-custom-post-content', 'changed-unknown-widget'))


def test_volleynews_rss_and_page_keep_the_real_offset_and_sport_scope():
    from bot.extract import page_published_at_from_html
    from bot.fetch_sources import _rss_publication_time
    from bot.feeds import FEEDS
    cfg = next(row for row in FEEDS if row['url'] == 'https://www.volleynews.it/feed/')
    assert cfg['enabled'] and cfg['sport'] == 'volleyball' and not cfg.get('league') and not cfg.get('country')
    rss = _rss_publication_time({'published': 'Mon, 28 Sep 2026 14:43:37 +0000'}, cfg)
    page = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-09-28T16:43:37+02:00"}</script>'
    assert rss == page_published_at_from_html(page) == datetime(2026, 9, 28, 14, 43, 37, tzinfo=timezone.utc)


def test_golf_body_excludes_author_bio_despite_outer_widget():
    prose = 'The golfer confirmed his entry for the championship in Scotland with his team. '
    html = '<meta property="og:url" content="https://www.golfmonthly.com/news/new-entry">'
    html += '<div class="widget"><div class="article__body"><p>' + prose * 4 + '</p></div></div>'
    html += '<p>The author graduated from university and joined the magazine several years later.</p>'
    text = article_text_from_html(html)
    assert prose.strip() in text
    assert 'author graduated' not in text


def test_rugby_body_excludes_recommendations_marketing_and_comments():
    prose = 'The coach confirmed the winger would remain available for the national rugby team. '
    html = '<meta property="og:url" content="https://www.rugbypass.com/news/confirmed-extension/">'
    html += '<div class="copy-row new"><p>' + prose * 4 + '</p>'
    for cls in ('embedded-related-article', 'embedded-recommended-articles', 'promotion'):
        html += f'<div class="{cls}"><p>Unrelated recommendation says another club is signing a different player tomorrow.</p></div>'
    html += '</div><p>A reader speculates that the player is unhappy and will move to another club.</p>'
    text = article_text_from_html(html)
    assert prose.strip() in text and 'Unrelated' not in text and 'reader speculates' not in text


def test_harness_canonical_body_and_actual_story_photo():
    prose = 'The trotting filly set a new record during the stakes race at the track on Monday. '
    photo = 'https://ustrottingnews.com/wp-content/uploads/2026/09/filly.jpg'
    html = '<link rel="canonical" href="https://ustrottingnews.com/new-racing-record/">'
    html += '<article class="category-track-news"><div class="entry-content">'
    html += '<p>' + prose * 4 + '</p><img src="' + photo + '" width="1200" height="800"></div></article>'
    html += '<main><img src="https://example.test/unrelated.jpg" width="1600" height="900"></main>'
    assert prose.strip() in article_text_from_html(html)
    assert [x['url'] for x in collect_page_image_candidates(html)] == [photo]


def test_golf_rss_admission_keeps_reports_and_exact_time(monkeypatch):
    from bot import fetch_sources as fs
    from bot.feeds import FEEDS
    cfg = next(x for x in FEEDS if x['url'] == 'https://www.golfmonthly.com/feeds.xml')
    published = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    paths = ['/news/player-confirms-entry', '/betting/tournament-tips', '/features/gear-guide', '/news/live/leaderboard']
    xml = '<rss version="2.0"><channel><title>Golf</title>' + ''.join(
        f'<item><title>Golfer confirms championship entry today</title><link>https://www.golfmonthly.com{path}</link><pubDate>{published}</pubDate></item>' for path in paths
    ) + '</channel></rss>'
    monkeypatch.setattr(fs, 'read_news_feed', lambda url: xml.encode())
    rows = fs._fetch_feed_entries(cfg, 20)
    assert [x['url'] for x in rows] == ['https://www.golfmonthly.com/news/player-confirms-entry']
    assert rows[0]['published_at'].tzinfo is not None


def test_rugby_discovery_uses_explicit_article_date_and_excludes_subscription_paths(monkeypatch):
    from bot import news_official_indexes as idx
    cfg = next(x for x in idx.HTML_INDEXES if x['id'] == 'rugbypass-rugby-news')
    assert cfg['paths'] == ('/news/',) and not cfg['verified_official']
    now = datetime.now(timezone.utc).isoformat()
    page = '<meta property="og:title" content="Rugby team confirms player extension">'
    page += '<meta property="og:url" content="https://www.rugbypass.com/news/new-deal/">'
    page += '<meta property="article:published_time" content="' + now + '">'
    page += '<meta property="og:image" content="https://example.test/real-photo.jpg">'
    page += '<div class="copy-row"><p>' + ('The rugby player signed an extension with his club and remains available for the national team. ' * 5) + '</p></div>'
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: page.encode())
    row = idx._hydrate(cfg, 'https://www.rugbypass.com/news/new-deal/', '')
    assert row and row['published_at'] == datetime.fromisoformat(now)
    page = page.replace(now, '2026-09-29 00:57:28')
    assert idx._hydrate(cfg, 'https://www.rugbypass.com/news/new-deal/', '') is None


@pytest.mark.parametrize('title,reason', [
    ('Watch WSL derby highlights: Liverpool 2-0 Everton', 'non_article_video_highlights'),
    ('Jazz participate in Reddit AMA', 'non_article_event_promotion'),
    ('Analysis: How Chelsea turned the tide against Arsenal', 'non_article_analysis'),
])
def test_non_news_candidates_are_held_before_ai(title, reason):
    assert non_article_news_reason({'title':title}) == reason


def test_highlights_as_a_verb_does_not_block_real_reporting():
    assert non_article_news_reason({'title':'Rugby coach highlights injury concerns before squad selection'}) is None


def test_cycling_article_scoped_past_outer_sidebar_without_reader_comments():
    prose = 'De renner bevestigt dat hij dit seizoen geen wegwedstrijden meer zal rijden. '
    html = '<meta property="og:url" content="https://www.wielerflits.nl/nieuws/renner/">'
    html += '<div class="container with-sidebar"><article class="post-wrapper"><div id="single-content">'
    html += '<p>' + prose * 5 + '</p></div><p>A reader guesses that the rider has signed for a different team.</p></article></div>'
    body = article_text_from_html(html)
    assert prose.strip() in body and 'reader guesses' not in body


def test_sky_body_and_mixed_feed_keep_sport_evidence_without_adverts():
    from bot.feeds import FEEDS
    from bot.classify import classify_article
    cfg = next(x for x in FEEDS if x['url'] == 'https://www.skysports.com/rss/12040')
    assert cfg['kind'] == 'mixed' and cfg['enabled'] and not cfg.get('sport') and not cfg.get('league')
    prose = 'Luke Woodhouse beat Luke Littler at the World Grand Prix darts tournament in Leicester. '
    html = '<meta property="og:url" content="https://www.skysports.com/darts/news/fixture">'
    html += '<div class="sdc-article-body"><p>' + prose * 4 + '</p>'
    html += '<p>Watch the darts tournament live on Sky Sports with streaming access and no contract on NOW.</p></div>'
    html += '<p>Premier League football news: Arsenal and Liverpool announce new transfers.</p>'
    body = article_text_from_html(html)
    assert 'streaming access' not in body and 'Arsenal' not in body
    assert classify_article('Littler exits World Grand Prix', body).sport == 'darts'


def test_verified_bst_offset_does_not_promote_yesterdays_sky_news_into_today():
    from bot.fetch_sources import _rss_publication_time
    from bot.feeds import FEEDS
    from bot.news_policy import editorial_day_reason
    cfg = next(x for x in FEEDS if x['url'] == 'https://www.skysports.com/rss/12040')
    raw = {'published': 'Mon, 28 Sep 2026 14:30:00 BST'}
    parsed = _rss_publication_time(raw, cfg)
    assert parsed == datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc)
    assert editorial_day_reason(parsed, datetime(2026, 9, 29, 1, tzinfo=timezone.utc), 'Australia/Sydney') == 'not_editorial_today'
    assert _rss_publication_time({'published': 'Mon, 28 Sep 2026 14:30:00 GMT'}, cfg).hour == 14
    # A publisher without a confirmed mapping is never assigned a guessed zone.
    assert _rss_publication_time(raw, {}).tzinfo is None


def test_rugby_latest_discovery_never_spends_hydration_budget_on_navigation(monkeypatch):
    from bot import news_official_indexes as idx
    cfg = next(x for x in idx.HTML_INDEXES if x['id'] == 'rugbypass-rugby-news')
    html = '<nav><a class="link-box" href="/news/rugby-transfers/">Transfers</a></nav>'
    html += '<a class="link-box" href="/news/old-pinned-story/">Old pinned story</a>'
    html += '<div class="latest right-column"><article><a class="link-box" href="/news/player-extension/">Player extension</a></article></div>'
    html += '<a class="link-box" href="/news/most-commented/">Most commented</a>'
    monkeypatch.setattr(idx, 'read_news_feed', lambda url: html.encode())
    assert idx._anchor_candidates(cfg) == [('https://www.rugbypass.com/news/player-extension/', 'Player extension')]
