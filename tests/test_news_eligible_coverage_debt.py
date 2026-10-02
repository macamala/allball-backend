from pathlib import Path
import pytest
from bot.news_policy import eligible_news_coverage_debt
from bot.news_budget import AiRequestBudget, ai_budget_scope
from bot.fetch_sources import _correction_retry_allowed

@pytest.mark.parametrize("candidates,inventory,expected", [
    ({"football": 18}, {}, 1),
    ({"football": 18}, {"football": 30}, 0),
    ({"football": 18, "basketball": 2}, {}, 2),
    ({"football": 18, "basketball": 2}, {"basketball": 8}, 1),
    ({"tennis": 2, "football": 1}, {"football": 12, "tennis": 6}, 0),
    ({}, {}, 0),
    (["football", "football", None], {}, 1),
])
def test_only_eligible_source_supply_reserves_requests(candidates, inventory, expected):
    assert eligible_news_coverage_debt(candidates, inventory) == expected


def test_football_correction_still_needs_a_full_attempt_and_respects_caps(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED", "0")
    budget = AiRequestBudget(6, str(tmp_path / "isolated.sqlite"))
    breadth = eligible_news_coverage_debt({"football": 10}, {}) > 1
    with ai_budget_scope(budget):
        assert _correction_retry_allowed(prefer_breadth=breadth)
        budget.attempts = 5
        assert not _correction_retry_allowed(prefer_breadth=breadth)
        budget.attempts = 0
        budget.blocked_reason = "daily_limit"
        assert not _correction_retry_allowed(prefer_breadth=breadth)


def test_multisport_cycle_still_protects_other_sports(tmp_path):
    with ai_budget_scope(AiRequestBudget(8, str(tmp_path / "isolated.sqlite"))):
        breadth = eligible_news_coverage_debt({"football": 1, "basketball": 2}, {}) > 1
        assert not _correction_retry_allowed(prefer_breadth=breadth)


def test_ingest_uses_the_same_eligible_debt_for_corrections_and_budget():
    source = (Path(__file__).parents[1] / "bot/fetch_sources.py").read_text()
    assert "prefer_breadth = update_coverage_debt() > 1" in source
    assert "active_news_sports =" not in source
