import sys
from types import SimpleNamespace

import bot.scheduler as scheduler


def _minimal_cycle_env(monkeypatch, *, data_news='1'):
    monkeypatch.setenv('NEWS_MAX_AI_ARTICLES', '0')
    monkeypatch.setenv('NEWS_HISTORICAL_REPAIR_ENABLED', '0')
    monkeypatch.setenv('NEWS_DATA_NEWS_ENABLED', data_news)
    monkeypatch.setenv('NEWS_TRANSLATIONS_ENABLED', '0')
    monkeypatch.setenv('NEWS_TRANSLATIONS_PER_CYCLE', '0')
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_RUN', '1')
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_DAY', '1')
    monkeypatch.delenv('NEWS_AI_LEDGER_PATH', raising=False)


def test_zero_ai_result_lane_runs_when_ai_allowance_is_unavailable(monkeypatch):
    _minimal_cycle_env(monkeypatch, data_news='1')
    monkeypatch.setattr(scheduler, '_start_errors', lambda: [])
    calls=[]
    monkeypatch.setitem(sys.modules, 'bot.data_news', SimpleNamespace(
        ingest_result_briefs=lambda **kwargs: calls.append(kwargs) or 7
    ))
    monkeypatch.setitem(sys.modules, 'public_cache', SimpleNamespace(
        bump_public_cache=lambda: None
    ))
    assert scheduler._run_cycle() == 7
    assert calls == [{'days': 2, 'max_groups': 120}]


def test_zero_ai_result_lane_stays_off_without_explicit_flag(monkeypatch):
    _minimal_cycle_env(monkeypatch, data_news='0')
    monkeypatch.setattr(scheduler, '_start_errors', lambda: [])
    monkeypatch.setitem(sys.modules, 'bot.data_news', SimpleNamespace(
        ingest_result_briefs=lambda **kwargs: (_ for _ in ()).throw(AssertionError('must stay off'))
    ))
    monkeypatch.setitem(sys.modules, 'public_cache', SimpleNamespace(
        bump_public_cache=lambda: None
    ))
    assert scheduler._run_cycle() == 0


def test_translation_lane_runs_after_english_ingest(monkeypatch, tmp_path):
    monkeypatch.setenv('NEWS_MAX_AI_ARTICLES', '1')
    monkeypatch.setenv('NEWS_HISTORICAL_REPAIR_ENABLED', '0')
    monkeypatch.setenv('NEWS_DATA_NEWS_ENABLED', '0')
    monkeypatch.setenv('NEWS_TRANSLATIONS_ENABLED', '1')
    monkeypatch.setenv('NEWS_TRANSLATIONS_PER_CYCLE', '1')
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_RUN', '3')
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_DAY', '3')
    monkeypatch.setenv('NEWS_AI_LEDGER_PATH', str(tmp_path/'ledger.sqlite'))
    monkeypatch.setattr(scheduler, '_start_errors', lambda: [])
    order=[]
    monkeypatch.setitem(sys.modules, 'bot.fetch_sources', SimpleNamespace(
        fetch_and_store_all_articles=lambda **kwargs: order.append('english') or 1
    ))
    monkeypatch.setitem(sys.modules, 'bot.rewrite_ai', SimpleNamespace(
        reset_openai_rate_limit=lambda: None
    ))
    monkeypatch.setitem(sys.modules, 'bot.news_translations', SimpleNamespace(
        translate_latest_articles=lambda **kwargs: order.append('translations') or 6
    ))
    monkeypatch.setitem(sys.modules, 'public_cache', SimpleNamespace(
        bump_public_cache=lambda: None
    ))
    assert scheduler._run_cycle() == 1
    assert order == ['english', 'translations']
