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
        assert budget.attempts == 4 and budget.max_requests == 16
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
