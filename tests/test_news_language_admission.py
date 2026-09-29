from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from editorial import evaluate_quality, looks_non_english
from bot import fetch_sources as ingest, news_fact_guard as guard
from bot.news_policy import non_article_news_reason, numeric_tokens
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import repair_recent_gossip_news, _correct_confirmed_chema_currency
from taxonomy_resolver import RESOLVER_VERSION

TITLE = 'Stanković discusses Serbia call-up with Tadić and Paunović'
BODY = ('Aleksandar Stanković said playing for Serbia at the stadium had been one of his dreams. '
        'Stanković thanked the football supporters for their welcome and described his experience with the national team. '
        'The midfielder said he would continue to work with the squad under Veljko Paunović. '
        'He also spoke about the support he had received from Dušan Tadić before the match.')


def test_english_proper_names_keep_diacritics_without_false_language_failure():
    before = (TITLE, BODY)
    result = evaluate_quality(title=TITLE, summary='The midfielder spoke about his football experience.',
        body=BODY, image_url='https://photo.test/serbia.jpg')
    assert result['ok'] and 'non_english' not in result['flags']
    assert before == (TITLE, BODY)


@pytest.mark.parametrize('foreign', [
    'Александар Станковић је играо за Србију и говорио о својим сновима.',
    'Stanković je govorio o svojim snovima. Fudbaler se zahvalio navijačima i rekao da je mnogo srećan. '
    'Igrač je dodao da će se truditi da u narednim utakmicama bude još bolji i pomogne svojoj reprezentaciji.',
    'Le milieu de terrain a rejoint son nouveau club et a participé au début de saison. '
    'Il a parlé de son ancien club et de ses ambitions pour la suite de sa carrière.',
    'Třetí komerční pauza v extralize. Moc mi to nesedí do úprav pravidel, říká eso Liberce',
])
def test_real_foreign_prose_remains_held(foreign):
    assert looks_non_english(foreign)


def test_language_rejection_happens_before_paid_or_free_semantic_request(monkeypatch):
    monkeypatch.setattr(ingest, 'write_ninkosports_story', lambda **kw: 'ignored')
    monkeypatch.setattr(ingest, 'parse_ai_output', lambda value: {
        'title': 'Станковић о репрезентацији Србије', 'summary': 'Изјава играча.', 'body': 'Станковић је говорио о утакмици.'})
    monkeypatch.setattr(ingest, 'is_dramatic_shortening', lambda *args: False)
    monkeypatch.setattr(ingest, 'validate_story_facts', lambda *args, **kw: pytest.fail('language must be checked first'))
    assert ingest._ai_story('Source', BODY, 'football', '', 6000) == (None, 'non_english')


@pytest.mark.parametrize('bad', [None, 'broken_image', 'incident', 'live_scores', 'foreign', 'not_ai', 'unobserved_id'])
def test_only_observed_false_holds_recover_with_gates_and_archive_intact(monkeypatch, bad):
    monkeypatch.setattr('bot.news_image_http.news_image_is_reachable', lambda url: bad != 'broken_image')
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        stamp = datetime.utcnow()
        aid = 22204 if bad != 'unobserved_id' else 22300
        source = 'https://fss.rs/aleksandar-stankovic-prva-utakmica/' if bad != 'live_scores' else 'https://fss.rs/live-scores/serbia'
        body = BODY if bad != 'foreign' else 'Станковић је говорио о свом наступу за репрезентацију Србије.'
        a = Article(id=aid,title=TITLE,summary='The midfielder spoke about his football experience.',content=body,ai_content=body,
            slug='stable-serbia-url',sport='football',ai_generated=bad != 'not_ai',source_url=source,
            published_at=stamp,image_url='https://photo.test/serbia.jpg')
        tax = ArticleTaxonomyResolution(article_id=aid, resolved_sport='football',sport_confidence=.98,
            resolver_version=RESOLVER_VERSION, public_ok=False,quality_ok=False,hero_media_kind='EDITORIAL_PHOTO')
        db.add_all([a,tax])
        if bad == 'incident':
            db.add(NewsIncident(article_id=aid, reason_code='unsupported_claim',source_url=source,
                phase='postpublish', status='open',severity='block'))
        db.commit()
        before = (a.title, a.content, a.image_url, a.published_at, a.slug)
        repair_recent_gossip_news(db)
        assert tax.public_ok is (bad is None)
        assert before == (a.title, a.content, a.image_url, a.published_at, a.slug)
        if bad is None:
            assert db.query(NewsIncident).filter_by(reason_code='english_proper_name_false_language_hold',status='auto_corrected').count() == 1
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()


def test_currency_format_equivalence_is_scoped_and_repair_is_exact():
    assert '14.5' in numeric_tokens('14,5 millions d’euros', include_spelled=True)
    assert '14.5' not in numeric_tokens('14,5 points', include_spelled=True)
    assert '14.5' not in numeric_tokens('14,5 millions de dollars', include_spelled=True)
    a = SimpleNamespace(id=22206,ai_generated=True,
        source_url='https://www.footmercato.net/a2290739679306661964-un-ancien-prodige-du-real-madrid-evoque-un-eventuel-retour',
        content="23 millions d'euros and 14,5 millions d'euros", ai_content=None)
    assert _correct_confirmed_chema_currency(a) and a.content == '€23 million and €14.5 million'
    assert _correct_confirmed_chema_currency(a) == {}


@pytest.mark.parametrize('title', [
    '30 años del "Rafa, no me jodas", la frase que nunca existió',
    'Football referee Mejuto González awarded a penalty but expelled the wrong player in 1996',
])
def test_anniversary_cannot_be_rewritten_into_current_news(title):
    assert non_article_news_reason({'title':title}) == 'non_news_retrospective_commentary'


def test_current_development_with_historical_background_is_not_removed():
    assert non_article_news_reason({'title':'Club appoints new manager who won the title in 1996'}) is None


def test_club_broadcast_promotion_is_rejected_before_writer():
    assert non_article_news_reason({'title':'Live on Wednesday: Watch Birmingham v Liverpool in Subway Players Cup'}) == 'non_article_live_program'
    assert non_article_news_reason({'title':'Liverpool confirm squad for Wednesday football match'}) is None


def test_french_prose_does_not_activate_english_only_calendar_guard():
    text = ('La France a battu la Belgique vendredi. On a vu une belle rencontre et on a aussi '
            'constaté que la France a obtenu ce résultat pour la première fois depuis vingt ans.')
    assert not guard._source_probably_english(text)
    assert guard._source_probably_english(BODY)


@pytest.mark.parametrize('competition,source,expected', [
    ('uefa-champions-league', 'Судиће утакмицу Лиге шампиона у среду.', True),
    ('uefa-champions-league', 'Suspendu en Ligue des champions.', True),
    ('uefa-champions-league', 'UEFA anunciou na Liga dos Campeões.', True),
    ('fifa-world-cup', 'La prochaine Coupe du monde.', True),
    ('fifa-world-cup', 'Coupe du monde des clubs', False),
    ('fifa-world-cup', 'Coupe du monde féminine', False),
    ('fifa-world-cup', 'Coupe du monde U-20', False),
    ('uefa-champions-league', 'Женске Лиге шампиона', False),
    ('uefa-champions-league', 'PseudoЛиге шампионаFake', False),
])
def test_language_equivalences_preserve_competition_scope(competition, source, expected):
    assert guard.competition_in_source(competition, source) is expected
