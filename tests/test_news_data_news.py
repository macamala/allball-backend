"""Regression: Live Scores-derived Result News was intentionally retired."""

import importlib.util
from pathlib import Path


def test_result_news_module_is_removed():
    root = Path(__file__).parents[1]
    assert not (root / "bot" / "data_news.py").exists()
    assert importlib.util.find_spec("bot.data_news") is None


def test_scheduler_has_no_result_news_lane():
    text = (Path(__file__).parents[1] / "bot" / "scheduler.py").read_text()
    assert "data_news" not in text
    assert "ingest_result_briefs" not in text
    assert "_run_data_lane" not in text


def test_legacy_result_news_flag_cannot_restore_removed_code():
    text = (Path(__file__).parents[1] / "news_runtime.py").read_text()
    assert "NEWS_DATA_NEWS_ENABLED" not in text
