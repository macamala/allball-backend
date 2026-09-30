"""Observed overnight failures: formatting, taxonomy and repeated quota calls."""
import httpx
import pytest

from bot import news_external_free as pool, news_fact_guard as guard
from bot.classify import classify_article
from bot.fetch_sources import _classify_item
from bot.news_policy import numeric_tokens, explicit_headline_sport
from public_index import _explicit_title_sport_override


def test_spanish_report_allows_only_same_explicit_money_values():
    source = ('La UEFA reparte 31,5 millones de euros para los clubes que ceden jugadores. '
              'El importe por aparición es de 3.845 euros y Leipzig recibe 353.000 euros.')
    allowed = numeric_tokens(source, include_spelled=True)
    assert {'31.5', '3,845', '3845', '353,000', '353000'} <= allowed
    assert not {'31.6', '31500000', '3.845000', '353,001', '35.3'} & allowed
    assert '31.5' not in numeric_tokens(source)


@pytest.mark.parametrize('source,forbidden', [
    ('The fee was 3.845 euros.', '3845'),
    ('Los clubes pagan una cantidad que es 0.123 euros.', '123'),
    ('Los clubes han medido una longitud que es 353.000 metros.', '353000'),
    ('La cifra para los clubes que participan es 31,5 puntos.', '31.5'),
    ('The score was 3:45 and the time 19:30.', '19-30'),
    ('Die Mannschaft trifft um 19:30 Uhr ein.', '19-30'),
    ('Die Mischung verwendet das Verhältnis 4:1.', '4-1'),
])
def test_ambiguous_numbers_are_not_reformatted(source, forbidden):
    assert forbidden not in numeric_tokens(source, include_spelled=True)


def test_explicit_german_score_retains_order_and_does_not_add_scores():
    source = ('Spanien feiert einen 4:1-Sieg. Bereits in der 2. Minute schliesst Lamine Yamal '
              'einen schnell vorgetragenen Angriff über die linke Seite aus rund 15 Metern flach zum 1:0 ab.')
    allowed = numeric_tokens(source, include_spelled=True)
    assert {'4-1', '1-0'} <= allowed
    assert not {'1-4', '0-1', '4-0', '2-0'} & allowed


def test_serbian_fixture_clock_format_is_not_a_timezone_conversion():
    source='Црвена звезда ће од 18 часова и 45 минута угостити Копенхаген.'
    allowed=numeric_tokens(source, include_spelled=True)
    assert '18:45' in allowed
    assert not {'6:45','20:45','18:54'} & allowed
    assert '18:45' not in numeric_tokens(source)
    for text in ('Трајање је 18 часова и 45 минута.', 'Од 25 часова и 45 минута.',
                 'Од 18 часова и 65 минута.', 'Од 18 часова до 45 минута.'):
        assert '18:45' not in numeric_tokens(text, include_spelled=True)


@pytest.mark.parametrize('source,allowed', [
    ('Der Präsident der Vereinigten Arabischen Emirate sprach.', True),
    ('The United Arab Emirates issued a statement.', True),
    ('The Emirates stadium hosted the match.', False),
    ('The chairman spoke at the stadium.', False),
    ('PseudoVereinigten Arabischen EmirateFake', False),
])
def test_country_acronym_requires_explicit_full_source_country(monkeypatch, source, allowed):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *a: None)
    reason = guard.fact_lock_reason({'body': 'The UAE issued a statement.'}, '', source)
    assert (reason != 'unsupported_acronym:UAE') is allowed


def test_record_rally_source_is_never_soccer_despite_shared_names():
    item = {'title':'João Ferreira vence primeira etapa em Marrocos após parar para socorrer piloto',
            'url':'https://www.record.pt/modalidades/motores/todo-o-terreno/detalhe/joao-ferreira-vence-primeira-etapa',
            'feed':{'kind':'mixed'}}
    tags = _classify_item(item, 'João Ferreira. World Cup Champions League Portugal.')
    assert tags.sport == 'motorsport' and tags.league is None
    title = 'João Ferreira Wins First Stage of Morocco Rally After Stopping to Assist a Rider'
    assert classify_article(title, 'World Championship', feed_kind='league', feed_sport='football').sport == 'motorsport'
    assert _explicit_title_sport_override(title) == explicit_headline_sport(title) == 'motorsport'


@pytest.mark.parametrize('title', ['Football supporters rally behind their club',
    'Tennis player wins a long rally', 'Darts World Grand Prix begins',
    'Brandon McNulty wins road cycling Grand Prix'])
def test_rally_word_and_shared_grand_prix_do_not_create_motorsport(title):
    assert _explicit_title_sport_override(title) != 'motorsport'
    assert explicit_headline_sport(title) != 'motorsport'


def test_rally_repair_preserves_article_archive_and_records_correction():
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Article, ArticleTaxonomyResolution, NewsIncident
    from public_index import repair_recent_sport_mislabels
    from taxonomy_resolver import RESOLVER_VERSION
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):
        model.__table__.create(engine)
    with Session(engine) as db:
        body = ('João Ferreira won the opening stage of the Morocco Rally after stopping to help a rider. '
                'Ferreira and his co-driver resumed the stage after the stoppage and completed the timed route. '
                'He explained that helping the rider took priority over the classification.\n\n'
                'The driver said the car had performed well and described the remaining stages as demanding. '
                'The next stage will take place in Zagora, where the competitors will continue the rally.')
        a = Article(id=22224, title='João Ferreira Wins First Stage of Morocco Rally After Stopping to Assist a Rider',
            slug='stable-rally-url', sport='football', league='fifa-world-cup', content=body, ai_content=body,
            summary='Ferreira completed the stage after helping a rider.', ai_generated=True,
            source_url='https://www.record.pt/modalidades/motores/todo-o-terreno/detalhe/joao-ferreira-vence-primeira-etapa',
            image_url='https://cdn.record.pt/images/2026-09/img_1280x720uu2026-09-23-08-48-47-2464183.jpg',
            published_at=datetime.utcnow())
        tax = ArticleTaxonomyResolution(article_id=a.id, resolved_sport='football',
            sport_confidence=.98, resolver_version=RESOLVER_VERSION, public_ok=True, quality_ok=True)
        db.add_all([a,tax]); db.commit()
        before=(a.title,a.content,a.ai_content,a.published_at,a.image_url,a.slug)
        assert repair_recent_sport_mislabels(db) == 1
        assert a.sport == tax.resolved_sport == 'motorsport' and tax.public_ok
        assert a.league is None
        assert before == (a.title,a.content,a.ai_content,a.published_at,a.image_url,a.slug)
        assert db.query(NewsIncident).filter_by(article_id=a.id, reason_code='taxonomy_sport_mismatch',status='auto_corrected').count() == 1
        assert repair_recent_sport_mislabels(db) == 0
    engine.dispose()


def test_repeated_unknown_quota_backs_off_across_cycles_but_recovers(monkeypatch):
    monkeypatch.setattr(pool, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(pool, '_UNKNOWN_QUOTA_STREAK', {})
    monkeypatch.setattr(pool, '_UNAVAILABLE', {p:set() for p in pool._PURPOSES})
    now = [100.]
    monkeypatch.setattr(pool.time, 'monotonic', lambda: now[0])
    response = httpx.Response(429, json={'message':'Rate limit exceeded', 'code':1300})
    for seconds in (600, 1200, 2400, 3600, 3600):
        pool._http_failure('mistral', response)
        pool.reset()
        assert pool._COOLDOWN_UNTIL['mistral'] == now[0] + seconds
        assert not pool._provider_ready('mistral') and pool._provider_ready('groq')
        now[0] += seconds + 1
    monkeypatch.setattr(pool, '_ordered_configs', lambda *a,**k:[{'provider':'mistral','model':'mistral-small-latest'}])
    monkeypatch.setattr(pool, '_mistral', lambda *a:'recovered')
    assert pool.completion(system='s',user='u',max_tokens=800)[0] == 'recovered'
    pool._http_failure('mistral', response)
    assert pool._COOLDOWN_UNTIL['mistral'] == now[0] + 600


def test_explicit_retry_after_is_not_replaced_by_guessed_backoff(monkeypatch):
    monkeypatch.setattr(pool, '_COOLDOWN_UNTIL', {})
    monkeypatch.setattr(pool, '_UNKNOWN_QUOTA_STREAK', {'mistral':4})
    monkeypatch.setattr(pool, '_UNAVAILABLE', {p:set() for p in pool._PURPOSES})
    monkeypatch.setattr(pool.time, 'monotonic', lambda:100.)
    pool._http_failure('mistral', httpx.Response(429, headers={'retry-after':'90'}))
    assert pool._COOLDOWN_UNTIL['mistral'] == 190.


def test_reordered_confirmed_verdict_is_one_announcement():
    from bot.dedupe import titles_are_near_duplicate
    a='Independent commission finds Manchester City guilty of Premier League financial rule breaches'
    assert titles_are_near_duplicate(a, 'Premier League finds Manchester City guilty in financial case')
    assert titles_are_near_duplicate(a, 'Manchester City found guilty of 115 Premier League financial charges')


@pytest.mark.parametrize('different', [
    'Premier League finds Chelsea guilty in financial case',
    'Manchester City found not guilty of Premier League financial charges',
    'Manchester City appeals Premier League financial verdict',
    'Manchester City could be found guilty of Premier League financial charges',
    'UEFA finds Manchester City guilty of financial rule breaches',
    'Premier League confirms sanctions for Manchester City financial breaches',
    'Manchester City chief executive reacts to Premier League financial verdict',
])
def test_verdict_key_preserves_different_clubs_decisions_and_developments(different):
    from bot.dedupe import _confirmed_financial_verdict, titles_are_near_duplicate
    a='Independent commission finds Manchester City guilty of Premier League financial rule breaches'
    assert _confirmed_financial_verdict(a) != _confirmed_financial_verdict(different)
    assert not titles_are_near_duplicate(a, different)
