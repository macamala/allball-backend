from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from bot import news_fact_guard as guard
from models import Article, ArticleTaxonomyResolution, NewsIncident
from public_index import _correct_confirmed_deadline_copy, repair_recent_gossip_news
from taxonomy_resolver import RESOLVER_VERSION

URL = 'https://www.mozzartsport.com/kosarka/vesti/ostoja-mijailovic-aba-liga-ce-poceti-poslali-smo-novi-predlog-sudijama/555050'
BODY = 'He noted that the deadline is tonight at midnight. The league will act after the deadline, which is set for 24 hours from now.'


@pytest.mark.parametrize('duration', ['24 hours from now', 'twenty-four hours later', 'in 24 hours'])
def test_midnight_translation_cannot_be_a_duration(monkeypatch, duration):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    source = 'Rok za izjašnjenje je večeras do 24 časa.'
    assert guard.fact_lock_reason({'title': 'League deadline', 'body': 'The deadline is '+duration},
                                 'Novi predlog', source) == 'clock_time_as_duration'
    assert guard.fact_lock_reason({'title': 'League deadline', 'body': 'The deadline is midnight that evening.'},
                                 'Novi predlog', source) is None


def test_real_duration_is_not_confused_with_midnight(monkeypatch):
    monkeypatch.setattr(guard, 'original_draft_reason', lambda *args: None)
    assert guard.fact_lock_reason({'body': 'The deadline is in 24 hours.'},
        'Novi predlog', 'Rok za odgovor ističe za 24 sata.') is None


@pytest.mark.parametrize('field,value', [('id', 22163), ('ai_generated', False),
    ('source_url', 'https://example.test/555050'), ('content', 'Unrelated story')])
def test_correction_requires_exact_audited_row_source_and_clause(field, value):
    row = SimpleNamespace(id=22162, ai_generated=True, source_url=URL, content=BODY, ai_content=None)
    setattr(row, field, value)
    before = vars(row).copy()
    assert _correct_confirmed_deadline_copy(row) == {}
    assert vars(row) == before


@pytest.mark.parametrize('public', [True, False])
def test_news_repair_is_idempotent_audited_and_never_resurrects_hold(public):
    engine = create_engine('sqlite:///:memory:')
    for model in (Article, ArticleTaxonomyResolution, NewsIncident):
        model.__table__.create(engine)
    with Session(engine) as db:
        article = Article(id=22162, title='ABA league seeks referee agreement', slug='deadline-test',
            sport='basketball', published_at=datetime.utcnow(), source_url=URL,
            content=BODY, ai_content=BODY, ai_generated=True)
        tax = ArticleTaxonomyResolution(article_id=22162, resolved_sport='basketball',
            resolver_version=RESOLVER_VERSION, public_ok=public)
        db.add_all([article, tax]); db.commit()
        assert repair_recent_gossip_news(db) == int(public)
        assert tax.public_ok is public
        if public:
            assert '24 hours from now' not in article.content
            assert 'tonight at midnight' in article.content
            assert article.content == article.ai_content
            assert db.query(NewsIncident).filter_by(reason_code='clock_time_as_duration',
                status='auto_corrected').count() == 1
        else:
            assert article.content == BODY
            assert db.query(NewsIncident).count() == 0
        assert repair_recent_gossip_news(db) == 0
    engine.dispose()
