import sys
import pytest
from types import SimpleNamespace

import bot.scheduler as scheduler


def _base_env(monkeypatch, tmp_path, *, max_articles="1", translations="0"):
    monkeypatch.setenv("NEWS_MAX_AI_ARTICLES", max_articles)
    monkeypatch.setenv("NEWS_HISTORICAL_REPAIR_ENABLED", "0")
    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED", translations)
    monkeypatch.setenv("NEWS_TRANSLATIONS_PER_CYCLE", "1" if translations == "1" else "0")
    monkeypatch.setenv("NEWS_ACCOUNTING_BACKEND", "file")
    monkeypatch.setenv("NEWS_AI_MAX_REQUESTS_PER_RUN", "3")
    monkeypatch.setenv("NEWS_AI_MAX_REQUESTS_PER_DAY", "3")
    monkeypatch.setenv("NEWS_AI_LEDGER_PATH", str(tmp_path / "ledger.sqlite"))
    # A legacy Railway variable may still exist, but there is no Result News lane.
    monkeypatch.setenv("NEWS_DATA_NEWS_ENABLED", "1")
    monkeypatch.setattr(scheduler, "_start_errors", lambda: [])


def test_removed_result_news_lane_never_imports_or_runs(monkeypatch, tmp_path):
    _base_env(monkeypatch, tmp_path, max_articles="0")
    trap = SimpleNamespace(
        ingest_result_briefs=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("removed Result News lane must never run")
        )
    )
    monkeypatch.setitem(sys.modules, "bot.data_news", trap)
    monkeypatch.setitem(
        sys.modules, "public_cache", SimpleNamespace(bump_public_cache=lambda: None)
    )
    assert scheduler._run_cycle() == 0


@pytest.mark.parametrize('debt,expected', [(0, ['english','translations']), (3,['english']), (None,['english'])])
def test_translation_lane_runs_after_english_ingest_only_without_coverage_debt(monkeypatch, tmp_path, debt, expected):
    _base_env(monkeypatch, tmp_path, max_articles="1", translations="1")
    order = []
    def ingest(**kwargs):
        from bot.news_budget import active_ai_budget
        active_ai_budget().english_coverage_debt = debt
        order.append('english')
        return 1
    monkeypatch.setitem(
        sys.modules,
        "bot.fetch_sources",
        SimpleNamespace(
            fetch_and_store_all_articles=ingest
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.rewrite_ai",
        SimpleNamespace(reset_openai_rate_limit=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.news_translations",
        SimpleNamespace(
            translate_latest_articles=lambda **kwargs: order.append("translations") or 6
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "public_cache",
        SimpleNamespace(bump_public_cache=lambda: None),
    )
    # Recent taxonomy repair is best-effort and must not affect lane ordering.
    monkeypatch.setitem(
        sys.modules,
        "database",
        SimpleNamespace(SessionLocal=lambda: SimpleNamespace(close=lambda: None)),
    )
    monkeypatch.setitem(
        sys.modules,
        "public_index",
        SimpleNamespace(repair_recent_unresolved=lambda db, limit=24: 0),
    )
    assert scheduler._run_cycle() == 1
    assert order == expected


def test_ai_lane_failure_fails_closed_without_result_news_fallback(monkeypatch, tmp_path):
    _base_env(monkeypatch, tmp_path, max_articles="1")
    monkeypatch.setitem(
        sys.modules,
        "bot.fetch_sources",
        SimpleNamespace(
            fetch_and_store_all_articles=lambda **kwargs: (_ for _ in ()).throw(
                RuntimeError("fixture")
            )
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.rewrite_ai",
        SimpleNamespace(reset_openai_rate_limit=lambda: None),
    )
    monkeypatch.setitem(
        sys.modules, "public_cache", SimpleNamespace(bump_public_cache=lambda: None)
    )
    assert scheduler._run_cycle() == 0
