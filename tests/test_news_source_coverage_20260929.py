from datetime import datetime, timezone

import pytest

from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_policy import non_article_news_reason


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
