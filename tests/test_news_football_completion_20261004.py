"""Regression coverage for observed October 4 News publication gaps."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from bot.news_count_lexemes import portuguese_count_equivalents
from bot.news_policy import numeric_tokens, non_article_news_reason, original_draft_reason
from bot.news_verified_desks import ARTICLE_PROFILES, RSS_FEEDS
from bot.extract import article_text_from_html, collect_page_image_candidates
from bot.news_publisher_media import is_publisher_branding


@pytest.mark.parametrize('text,expected', [
    ('capacidade para até 21 mil torcedores', {'21000', '21,000'}),
    ('capacidade para 14 mil torcedores.', {'14000', '14,000'}),
    ('Foram 12 mil pessoas.', {'12000', '12,000'}),
    ('São 30 mil assentos.', {'30000', '30,000'}),
    ('capacidade para 50 mil lugares', {'50000', '50,000'}),
])
def test_explicit_portuguese_counts_have_exact_source_only_equivalents(text, expected):
    assert portuguese_count_equivalents(text) == expected
    assert expected <= numeric_tokens(text, include_spelled=True)
    assert not expected.intersection(numeric_tokens(text))


@pytest.mark.parametrize('text', [
    '14 milhões de torcedores', '14 mil euros', '14 mil quilômetros',
    '14,5 mil torcedores', '1.014 mil torcedores', '14-21 mil torcedores',
    '14 – 21 mil torcedores', '14:21 mil torcedores', '14/21 mil torcedores',
    'R$ 14 mil torcedores', '€14 mil pessoas', '€ 14 mil pessoas',
    '50% 14 mil torcedores', 'FC14 mil torcedores', '014 mil torcedores',
    '14mil torcedores', '14 milímetros', 'quatorze mil torcedores',
])
def test_decimals_money_ranges_scores_and_unobserved_spellings_cannot_be_expanded(text):
    assert not portuguese_count_equivalents(text)


def test_new_quantities_still_fail_original_draft_validation():
    draft = {'title': 'Sion outlines its stadium proposal',
             'summary': 'The project concerns a new venue.',
             'body': 'The proposed stadium would have room for 22,000 supporters. The club has presented its plans for the venue and explained how it expects the development to accommodate people attending its football matches.'}
    assert original_draft_reason(draft, 'Projeto do estádio', 'Capacidade para 21 mil torcedores.') == 'unsupported_number'
    assert not {'14,000', '210,000', '1991', '92'}.intersection(
        numeric_tokens('21 mil torcedores e campeão em 1991/92.', include_spelled=True))


@pytest.mark.parametrize('title', [
    'BET INFO: Ovo je pet najigranijih parova dana!',
    'Bet Info: Najigraniji parovi i kvote danas',
    'BET-INFO — Najigraniji tiketi danas',
])
def test_betting_products_are_rejected_before_writer_requests(title):
    assert non_article_news_reason({'title': title}) == 'non_article_betting_product'


@pytest.mark.parametrize('title', [
    'League announces investigation into betting misconduct',
    'Mozzart Bet Prva liga Srbije confirms fixture changes',
    'BET INFO: Regulator announces investigation into the company',
    'Five players return to training before the weekend match',
])
def test_betting_related_reporting_and_normal_football_are_not_products(title):
    assert non_article_news_reason({'title': title}) != 'non_article_betting_product'


TEXT = 'The football club explained its preparations and confirmed its plans for the upcoming match. ' * 16
OTHER = 'UNRELATED CARD WITH INVENTED PLAYERS'


def page(host, *, different=False, free=True, body=TEXT):
    profile = ARTICLE_PROFILES[host]
    cls = 'changed-body' if different else profile.get('body_class', '')
    ident = 'changed-id' if different else profile.get('body_id', '')
    tag = profile.get('body_tag', 'div')
    return (f'<link rel="canonical" href="https://{host}/confirmed-report/">'
            '<meta property="og:image" content="https://photos.example/own.jpg">'
            f'<script type="application/ld+json">{json.dumps({"@type":"NewsArticle","isAccessibleForFree":free,"articleBody":TEXT})}</script>'
            f'<main><p>{OTHER}</p><{tag} class="{cls}" id="{ident}"><p>{body}</p></{tag}>'
            f'<aside><p>{OTHER}</p><img src="https://photos.example/unrelated.jpg" width="1400"></aside></main>')


@pytest.mark.parametrize('host', ARTICLE_PROFILES)
def test_verified_desks_use_only_own_body_and_own_social_photo(host):
    text = article_text_from_html(page(host))
    assert TEXT.strip() in text and OTHER not in text
    photos = collect_page_image_candidates(page(host))
    assert len(photos) == 1 and photos[0]['url'] == 'https://photos.example/own.jpg'


@pytest.mark.parametrize('host', ARTICLE_PROFILES)
def test_changed_paid_or_missing_body_never_falls_back_to_hidden_schema(host):
    assert article_text_from_html(page(host, different=True)) == ''
    assert article_text_from_html(page(host, free=False)) == ''
    assert article_text_from_html(page(host, body='')) == ''


def test_known_publisher_square_is_not_an_article_photograph():
    assert is_publisher_branding('https://getfootballnewsbene.com/wp-content/uploads/2023/02/GBeNeFNWhiteSquare512.png')
    assert not is_publisher_branding('https://getfootballnewsbene.com/wp-content/uploads/2026/10/real-match.jpg')
    assert not is_publisher_branding('https://other.example/wp-content/uploads/2023/02/GBeNeFNWhiteSquare512.png')
    assert is_publisher_branding('https://www.soccernews.com/og/og-image.png')


def test_sources_join_existing_pipeline_without_invented_membership_or_full_rss_fallback():
    from bot.news_football_sources import RSS_FEEDS as all_feeds
    from bot.feeds import enabled_feeds
    urls = [row['url'] for row in enabled_feeds()]
    for config in RSS_FEEDS:
        assert config in all_feeds and urls.count(config['url']) == 1
        assert config['article_body_required'] is True
        assert config['article_https_host'] in ARTICLE_PROFILES
        assert not config.get('league') and not config.get('country')
        assert 'verified_body_field' not in config


@pytest.mark.parametrize('config', RSS_FEEDS)
def test_old_or_future_stories_and_other_hosts_are_not_new_candidates(monkeypatch, config):
    from bot import fetch_sources as fetch
    now = datetime.now(timezone.utc)
    host = config['article_https_host']
    def row(hours, hostname=host):
        return {'title': 'Football club announces preparations',
                'link': 'https://' + hostname + '/confirmed-report/', 'summary': TEXT,
                'published': (now - timedelta(hours=hours)).isoformat()}
    monkeypatch.setattr(fetch, 'read_news_feed', lambda url: b'feed')
    monkeypatch.setattr(fetch.feedparser, 'parse', lambda raw: SimpleNamespace(
        entries=[row(1), row(48), row(-24), row(0, 'unreviewed.example')], version='rss20', bozo=False))
    items = fetch._fetch_feed_entries(config, 60)
    assert len(items) == 1
    assert items[0]['published_at'] == now - timedelta(hours=1)


SION = 'https://ge.globo.com/futebol/futebol-internacional/noticia/2026/10/04/clube-suico-apresenta-projeto-de-estadio-com-montanha-russa-veja.ghtml'


def test_only_exact_pre_fix_sion_number_hold_can_expire(monkeypatch):
    from bot import news_source_holds as holds
    class Cursor:
        rowcount = 0
        def __init__(self): self.calls = []
        def execute(self, sql, args=None): self.calls.append((sql, args))
        def fetchall(self): return []
        def close(self): pass
    class Conn:
        def __init__(self, cursor): self.c = cursor
        def cursor(self): return self.c
        def commit(self): pass
        def close(self): pass
        def rollback(self): pass
    cursor = Cursor()
    monkeypatch.setattr(holds, '_postgres_dsn', lambda: 'unused')
    monkeypatch.setattr(holds, '_connect', lambda _: Conn(cursor))
    monkeypatch.setattr(holds, '_SCHEMA_READY', True)
    holds.held_source_urls([SION, SION + '?different=true'])
    updates = [(sql, args) for sql, args in cursor.calls if 'audited-portuguese-count' in sql]
    assert len(updates) == 1
    sql, args = updates[0]
    assert 'source_hash=%s' in sql and "reason='unsupported_number'" in sql
    assert 'updated_at < %s::timestamptz' in sql
    assert args == (holds._fingerprint(SION), '2026-10-04T05:22:00Z')
    assert 'public_ok' not in sql and 'UPDATE articles' not in sql
    cursor.calls.clear()
    holds.held_source_urls([SION + '?different=true', 'https://other.example/story'])
    assert not any('audited-portuguese-count' in sql for sql, _ in cursor.calls)
