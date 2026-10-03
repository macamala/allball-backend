import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bot.news_official_club_desks import CLUB_PROFILES, RSS_FEEDS, explicit_women_club_headline
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_football_source_context import WOMEN_CONTEXT, preserve_women_qualifier_reason

TEXT = 'The football club confirmed the appointment and explained its preparations. ' * 18
OTHER = 'UNRELATED CLUB CARD WITH UNSUPPORTED FIGURES'


def page(host, cls=None, *, title='Football club confirms preparations', body=TEXT, free=True, extra=''):
    cls = cls or CLUB_PROFILES[host]['body_class']
    url = 'https://' + host + '/confirmed-report/'
    return (f'<link rel="canonical" href="{url}"><meta property="og:title" content="{title}">'
            '<meta property="og:image" content="https://photos.example/own-article.jpg">'
            f'<script type="application/ld+json">{json.dumps({"@type":"NewsArticle","isAccessibleForFree":free})}</script>'
            f'<main><p>{OTHER}</p><div class="{cls}"><p>{body}</p></div><aside><p>{OTHER}</p></aside>{extra}</main>')


@pytest.mark.parametrize('host', CLUB_PROFILES)
def test_only_reviewed_visible_club_body_and_own_photo_are_used(host):
    markup = page(host, extra='<img src="https://photos.example/other-card.jpg" width="1000">')
    text = article_text_from_html(markup)
    assert TEXT.strip() in text and OTHER not in text
    photos = collect_page_image_candidates(markup)
    assert len(photos) == 1 and photos[0]['source'] == 'og'
    assert photos[0]['url'] == 'https://photos.example/own-article.jpg'


@pytest.mark.parametrize('host', CLUB_PROFILES)
def test_missing_changed_or_paid_body_never_falls_back_to_hidden_text(host):
    hidden = f'<script type="application/ld+json">{json.dumps({"@type":"NewsArticle","articleBody":TEXT})}</script>'
    assert article_text_from_html(page(host, cls='different-body', extra=hidden)) == ''
    assert article_text_from_html(page(host, free=False, extra=hidden)) == ''
    assert article_text_from_html(page(host, body='', extra=hidden)) == ''


@pytest.mark.parametrize('title', ['Интервју са председницом ЖФК Војводина', 'Predsednica ŽFK Vojvodina govori',
    'ZFK Vojvodina confirms programme', 'Женски фудбал у Војводини', 'Ženska ekipa Vojvodine'])
def test_explicit_womens_headline_survives_source_extraction_and_fact_guard(title):
    host = 'www.fkvojvodina.rs'
    assert explicit_women_club_headline('https://' + host + '/report/', title)
    text = article_text_from_html(page(host, title=title))
    assert text.startswith(WOMEN_CONTEXT + '\n\n')
    assert preserve_women_qualifier_reason(text, {'title':'Vojvodina discusses plans','summary':''})
    assert preserve_women_qualifier_reason(text, {'title':"Vojvodina women's team discusses plans"}) is None


@pytest.mark.parametrize('title', ['Vojvodina first team confirms schedule', 'FK Vojvodina signs midfielder',
    'Dudic talks about the match'])
def test_incidental_navigation_womens_words_cannot_relabel_the_mens_article(title):
    markup = page('www.fkvojvodina.rs', title=title,
                  extra='<a href="/women">ЖФК Војводина</a><p>Женски фудбал</p>')
    assert WOMEN_CONTEXT not in article_text_from_html(markup)


@pytest.mark.parametrize('url', ['https://www.fkvojvodina.rs.evil.example/report/',
    'https://fknovipazar.rs/report/', 'http://www.fkvojvodina.rs/report/',
    'https://user:pass@www.fkvojvodina.rs/report/', 'https://www.fkvojvodina.rs:444/report/',
    'https://www.fkvojvodina.rs/category/women/', None, {}, []])
def test_unreviewed_domain_or_nonarticle_cannot_supply_category(url):
    assert not explicit_women_club_headline(url, 'ЖФК Војводина')


def test_three_feed_configs_join_one_intake_and_do_not_force_league_or_gender():
    from bot.feeds import enabled_feeds, news_source_is_excluded
    from bot.news_football_sources import RSS_FEEDS as ALL
    assert len(RSS_FEEDS) == 3
    for cfg in RSS_FEEDS:
        assert cfg in ALL and cfg['article_body_required'] and cfg['verified_official']
        assert not cfg.get('league') and not cfg.get('country') and 'verified_body_field' not in cfg
        assert cfg['article_https_host'] in CLUB_PROFILES
        assert cfg['url'] in {f['url'] for f in enabled_feeds()}
    assert not any('fknovipazar.rs' in cfg['url'] for cfg in ALL)
    assert news_source_is_excluded('https://feeds.bbci.co.uk/sport/football/teams/everton/rss.xml')


def test_stale_original_feed_dates_and_wrong_hosts_stay_out(monkeypatch):
    from bot import fetch_sources as fetch
    now = datetime.now(timezone.utc)
    cfg = RSS_FEEDS[0]
    def row(age, host='www.fkvojvodina.rs'):
        return {'title':'Vojvodina confirms programme','link':'https://' + host + '/report/',
                'summary':TEXT,'published':(now-timedelta(days=age)).isoformat()}
    monkeypatch.setattr(fetch,'read_news_feed',lambda url:b'feed')
    monkeypatch.setattr(fetch.feedparser,'parse',lambda raw:SimpleNamespace(
        entries=[row(0),row(4),row(0,'fknovipazar.rs')], version='rss20',bozo=False))
    items = fetch._fetch_feed_entries(cfg,60)
    assert len(items) == 1
    assert items[0]['published_at'] == now
    assert items[0]['url'] == 'https://www.fkvojvodina.rs/report/'


@pytest.mark.parametrize('title', ['ŽFK Vojvodina appoints manager','ЖФК Војводина представила појачање',
                                 'Женска екипа Војводине почиње припреме'])
def test_source_qualifier_never_creates_mens_league_queue_debt(title):
    from bot.news_football_sections import football_news_section
    article = SimpleNamespace(title=title,summary='',content=TEXT,published_at='2026-10-03')
    assert football_news_section(article,today=date(2026,10,3)) == 'football-women'


def test_the_existing_pipeline_scans_deeper_only_in_football_mode():
    import inspect
    from bot.fetch_sources import _fetch_and_store_all_articles
    code = inspect.getsource(_fetch_and_store_all_articles)
    assert "60 if os.getenv('NEWS_FOOTBALL_ONLY') == '1' else 20" in code
    assert 'football_club_coverage=club_coverage' in code
    assert 'active_budget.max_requests - active_budget.attempts' in code
