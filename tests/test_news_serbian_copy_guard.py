from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot import news_fact_guard as guard
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_fss_copy, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://fss.rs/a-tim-promene-u-sastavu-pred-nastavak-lige-nacija/'
SOURCE = ('Селектор Вељко Пауновић скратио је групу играча. Огњен Мимовић је у А тиму. '
          'Позив голману Војводине Драгану Росићу. Следи гостовање Немачкој у Минхену.')
SUMMARY = 'Serbia’s coach Veľko Paukovic has changed the squad.'
BODY = ('Ognen Mimovic has joined the senior team.\n\n'
        'Goalkeeper Dragun Rosic of Voivodina has received a call-up.\n\n'
        'The next Nations League fixture will be a home game against Germany in Munich.')


@pytest.mark.parametrize('bad,good', [
    ('Veľko Paukovic', 'Veljko Paunović'), ('Ognen Mimovic', 'Ognjen Mimović'),
    ('Dragun Rosic', 'Dragan Rosić'), ('Voivodina', 'Vojvodina'),
])
def test_source_attested_names_block_near_spelling_without_inventing_identity(monkeypatch, bad, good):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    assert guard.fact_lock_reason({'body': bad + ' is mentioned.'}, '', SOURCE).startswith('source_name_spelling:')
    assert guard.fact_lock_reason({'body': good + ' is mentioned.'}, '', SOURCE) is None
    assert guard.fact_lock_reason({'body': bad + ' is mentioned.'}, '', 'Unrelated source') is None


def test_away_visit_cannot_become_a_home_fixture(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    assert guard.fact_lock_reason({'body': 'A home game against Germany in Munich.'}, '', SOURCE) == 'reversed_home_away'
    assert guard.fact_lock_reason({'body': 'An away game against Germany in Munich.'}, '', SOURCE) is None
    assert 'Veljko Paunović' in guard.source_name_spellings(SOURCE)
    assert guard.source_name_spellings('Unrelated football source') == ''


@pytest.mark.parametrize('field,value', [('id', 22192), ('ai_generated', False),
    ('source_url', 'https://example.test/a-tim-promene-u-sastavu-pred-nastavak-lige-nacija/')])
def test_public_correction_only_changes_exact_audited_news_row(field, value):
    row = SimpleNamespace(id=22191, ai_generated=True, source_url=URL,
                          summary=SUMMARY, content=BODY, ai_content=BODY)
    setattr(row, field, value)
    before = vars(row).copy()
    assert _correct_confirmed_fss_copy(row) == {}
    assert vars(row) == before


@pytest.mark.parametrize('public', [True, False])
def test_fss_repair_keeps_archive_identity_logs_incident_and_never_resurrects(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident): model.__table__.create(engine)
    with Session(engine) as db:
        published = datetime.utcnow()
        row = Article(id=22191, title='Serbia national football team reshuffles squad', slug='unchanged-url',
            sport='football', published_at=published, source_url=URL, summary=SUMMARY,
            content=BODY, ai_content=BODY, ai_generated=True)
        tax = ArticleTaxonomyResolution(article_id=22191, resolved_sport='football',
            resolver_version=RESOLVER_VERSION, public_ok=public)
        db.add_all([row, tax]); db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert tax.public_ok is public
        assert row.slug == 'unchanged-url' and row.published_at == published
        if public:
            assert 'Veljko Paunović' in row.summary
            assert 'Ognjen Mimović' in row.content and 'Dragan Rosić' in row.content
            assert 'home game' not in row.content and 'away game' in row.content
            assert 'Vojvodina' in row.content and row.content == row.ai_content
            assert db.query(NewsIncident).filter_by(reason_code='serbian_name_spelling_and_away_fixture',
                status='auto_corrected').count() == 1
        else:
            assert row.content == BODY
            assert db.query(NewsIncident).count() == 0
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()
