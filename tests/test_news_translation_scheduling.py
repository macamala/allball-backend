from datetime import datetime
from types import SimpleNamespace

from bot import news_translations as translations, scheduler
from bot.news_budget import AiRequestBudget, ai_budget_scope, reserve_ai_request
from models import Article, ArticleTranslation


def test_translation_slice_leaves_writer_allowance_and_preserves_daily_stop(monkeypatch, tmp_path):
    monkeypatch.setenv('NEWS_TRANSLATIONS_ENABLED', '1')
    monkeypatch.setenv('NEWS_TRANSLATIONS_PER_CYCLE', '1')
    monkeypatch.setenv('NEWS_FOOTBALL_ONLY', '1')
    def consume(**kwargs):
        while reserve_ai_request():
            pass
        return 1
    monkeypatch.setattr(translations, 'translate_latest_articles', consume)
    budget = AiRequestBudget(16, str(tmp_path / 'requests.db'))
    with ai_budget_scope(budget):
        assert scheduler._run_translation_slice(budget) == 1
        assert budget.attempts == 8 and budget.max_requests == 16
        assert reserve_ai_request()
    limited = AiRequestBudget(16, str(tmp_path / 'daily.db'), daily_limit=2)
    with ai_budget_scope(limited):
        scheduler._run_translation_slice(limited)
        assert limited.attempts == 2 and limited.blocked_reason == 'daily_request_limit'
        assert not reserve_ai_request()


class Query:
    def __init__(self, rows): self.rows = rows
    def join(self, *a): return self
    def filter(self, *a): return self
    def order_by(self, *a): return self
    def limit(self, *a): return self
    def all(self): return self.rows
    def first(self): return self.rows[0] if self.rows else None


def test_serbian_backlog_precedes_other_languages_without_repeating_ready(monkeypatch):
    monkeypatch.setenv('NEWS_TRANSLATION_LANGUAGES_PER_ARTICLE', '1')
    newest, older = SimpleNamespace(id=2), SimpleNamespace(id=1)
    rows = iter([
        [SimpleNamespace(language_code='sr', status='ready'),
         SimpleNamespace(language_code='es', status='failed', provider=translations._provider(), updated_at=datetime.utcnow())],
        [],
    ])
    db = SimpleNamespace(query=lambda model: Query([newest, older] if model is Article else next(rows)))
    result = translations._latest_missing(db, 2)
    assert result == [older, newest]
    assert older._news_missing_translation_languages == ('sr',)
    assert newest._news_missing_translation_languages == ('de',)


def test_translation_failure_cools_only_attempted_language():
    added = []
    db = SimpleNamespace(query=lambda model: Query([]), add=added.append)
    article = SimpleNamespace(id=4, _news_missing_translation_languages=('sr',))
    translations._mark_failed(db, article)
    assert len(added) == 1 and added[0].language_code == 'sr'


def test_role_is_translated_but_attested_surname_remains_locked():
    source = {'title': 'Vivian returns to training',
              'summary': 'Defender Vivian is available again.',
              'body': 'Vivian is training with the group. ' * 8}
    translated = {'sr': {'title': 'Vivian ponovo trenira',
                        'summary': 'Defanzivac Vivian je ponovo na raspolaganju.',
                        'body': 'Vivian trenira sa ekipom i radi sa ostalim igračima. ' * 6}}
    assert translations.translation_names(source['summary']) == ['Vivian']
    assert translations._validate(source, translated, languages=('sr',))
    changed = {'sr': {k: v.replace('Vivian', 'Drugoime') for k, v in translated['sr'].items()}}
    assert translations._validate(source, changed, languages=('sr',)) is None
    from bot.news_deepl import _xml_fields
    documents, locks = _xml_fields(source)
    assert 'Defender ' in documents[1]
    assert 'Vivian' in locks[1].values()


def test_exhausted_slice_does_not_cool_down_unattempted_articles(monkeypatch, tmp_path):
    import database
    monkeypatch.setenv('NEWS_TRANSLATIONS_ENABLED', '1')
    db = SimpleNamespace(commit=lambda: None, close=lambda: None, rollback=lambda: None)
    monkeypatch.setattr(database, 'SessionLocal', lambda: db)
    articles = [SimpleNamespace(id=i) for i in (1, 2, 3)]
    monkeypatch.setattr(translations, '_latest_missing', lambda *a: articles)
    def failed(article):
        while reserve_ai_request():
            pass
        return None
    attempted = []
    monkeypatch.setattr(translations, 'translate_article_payload', failed)
    monkeypatch.setattr(translations, '_mark_failed', lambda db, article: attempted.append(article.id))
    with ai_budget_scope(AiRequestBudget(4, str(tmp_path / 'bounded.db'))):
        assert translations.translate_latest_articles(limit=3) == 0
    assert attempted == [1]


def test_archive_behind_more_than_120_completed_articles_remains_reachable(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from models import Base, ArticleTaxonomyResolution
    from taxonomy_resolver import RESOLVER_VERSION
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    monkeypatch.setenv('NEWS_TRANSLATION_LANGUAGES_PER_ARTICLE', '6')
    with Session(engine) as db:
        for article_id in range(1, 132):
            db.add(Article(id=article_id, title='Source', ai_generated=True))
            db.add(ArticleTaxonomyResolution(article_id=article_id,
                resolver_version=RESOLVER_VERSION, public_ok=True))
            if article_id > 1:
                db.add_all([ArticleTranslation(article_id=article_id, language_code=lang,
                    status='ready') for lang in translations.LANGUAGES])
        db.commit()
        rows = translations._latest_missing(db, 3)
        assert [row.id for row in rows] == [1]
        assert rows[0]._news_missing_translation_languages == translations.LANGUAGES
        # A reported article can precede the backlog, but a complete validated
        # copy never re-enters it. The initial unvalidated rollout is reviewed.
        monkeypatch.setenv('NEWS_TRANSLATION_PRIORITY_ARTICLE_IDS', '2,3,invalid')
        row = db.query(ArticleTranslation).filter_by(article_id=2, language_code='sr').one()
        row.provider = 'multi-free-v15'
        db.commit()
        rows = translations._latest_missing(db, 3)
        assert [row.id for row in rows] == [2, 1]
        assert rows[0]._news_missing_translation_languages == ('sr',)
