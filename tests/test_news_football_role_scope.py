from datetime import datetime
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from bot import news_fact_guard as guard
from public_index import _correct_confirmed_yakin_copy, _correct_confirmed_taranto_format, repair_recent_gossip_news
from bot.news_policy import non_article_news_reason, original_draft_reason
from bot.news_image_http import probe_news_image
from models import Article, ArticleTaxonomyResolution, NewsIncident
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://www.blick.ch/sport/fussball/nations-league/nati-pk-vor-schottland-yakin-und-elvedi-live/mqh1lxn'
SOURCE = 'Assistenztrainer Davide Callà und Nico Elvedi übernahmen die Fragen der Medien. Wegen Unstimmigkeiten bei der Gewichtsberechnung musste das Flugzeug in Zürich fürs Nachtanken zwischenlanden.'
BAD_ROLE = 'Assistant coaches Davide Callà and Nico Elvedi addressed media questions.'
BAD_TRAVEL = 'The team’s arrival also faced delays after a fuel calculation error forced an emergency refueling stop in Zurich, causing a three-hour delay.'
BODY = BAD_TRAVEL + '\n\n' + BAD_ROLE


@pytest.mark.parametrize('body,reason', [(BAD_ROLE, 'expanded_role_scope'),
    (BAD_TRAVEL, 'unsupported_travel_cause'),
    ('Davide Callà and Nico Elvedi answered media questions. The aircraft stopped to refuel following a weight calculation problem.', None)])
def test_audited_translation_cannot_expand_role_or_change_flight_cause(monkeypatch, body, reason):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *a: None)
    assert guard.fact_lock_reason({'body': body}, 'Team news', SOURCE) == reason


@pytest.mark.parametrize('field,value', [('id', 22194), ('ai_generated', False),
    ('source_url', 'https://example.test/mqh1lxn')])
def test_translation_repair_only_touches_exact_audited_source(field, value):
    row = SimpleNamespace(id=22193, ai_generated=True, source_url=URL, content=BODY, ai_content=BODY)
    setattr(row, field, value);before = vars(row).copy()
    assert _correct_confirmed_yakin_copy(row) == {}
    assert vars(row) == before


@pytest.mark.parametrize('public', [True, False])
def test_role_repair_is_audited_idempotent_and_keeps_archive_status(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        article = Article(id=22193, title='Yakin misses Switzerland press conference', slug='unchanged-yakin-url',
            sport='football', source_url=URL, content=BODY, ai_content=BODY, ai_generated=True, published_at=stamp)
        tax = ArticleTaxonomyResolution(article_id=22193, resolved_sport='football', resolver_version=RESOLVER_VERSION, public_ok=public)
        db.add_all([article, tax]);db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert tax.public_ok is public and article.published_at == stamp and article.slug == 'unchanged-yakin-url'
        if public:
            assert 'Assistant coaches' not in article.content and 'fuel calculation' not in article.content
            assert 'emergency' not in article.content and 'weight calculations' in article.content
            assert 'Davide Callà and Nico Elvedi answered' in article.content
            assert article.content == article.ai_content
            assert db.query(NewsIncident).filter_by(reason_code='expanded_role_scope_and_travel_cause',status='auto_corrected').count() == 1
        else:
            assert article.content == BODY and db.query(NewsIncident).count() == 0
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


def test_seo_headline_cannot_hide_source_calculator_product():
    item = {'title': 'Atlético-MG faces tough October', 'url': 'https://ge.globo.com/futebol/times/atletico-mg/noticia/2026/09/29/libertadores-via-brasileiro-veja-contas.ghtml'}
    assert non_article_news_reason(item) == 'non_article_analysis'
    item['url'] = item['url'].replace('libertadores-via-brasileiro-veja-contas', 'treinador-confirma-retorno')
    assert non_article_news_reason(item) is None


@pytest.mark.parametrize('title', ['A qué hora es el España - Croacia: horario y dónde ver hoy en TV y online el partido',
    'Vasco x Flamengo: horário e onde assistir ao vivo'])
def test_translated_service_guides_stop_before_writer(title):
    assert non_article_news_reason({'title':title}) == 'non_article_service_guide'


def test_editorial_placeholder_is_rejected_and_exact_public_copy_can_be_repaired():
    assert original_draft_reason({'title':'New club captain appointed','summary':'The club named a captain.',
        'body':'First paragraph.\n[Blank Line]\nSecond paragraph.'}, 'Captain chosen', 'Source report') == 'draft_placeholder'
    row = SimpleNamespace(id=22195, ai_generated=True, source_url='https://aleagues.com.au/news/news-adriana-taranto-named-new-adelaide-united-captain/',
        content='First.\n[Blank Line]\nSecond.', ai_content='First.\n[Blank Line]\nSecond.')
    assert _correct_confirmed_taranto_format(row)
    assert row.content == row.ai_content == 'First.\n\nSecond.'
    assert _correct_confirmed_taranto_format(row) == {}


def test_publisher_building_is_not_a_sports_hero_and_needs_no_network():
    assert probe_news_image('https://images.ctfassets.net/id/DPG_Media_Building_Antwerp.PNG?w=1600') == (False, 'publisher_default_image')
