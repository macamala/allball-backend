import pytest

from bot.classify import classify_article
from bot import news_fact_guard as guard
from bot.news_policy import non_article_news_reason


@pytest.mark.parametrize("sport,title,body", [
    ("darts", "Littler stunned by Waterhouse at World Grand Prix", "Waterhouse advanced after defeating Littler."),
    ("water-polo", "Novi Beograd keeps perfect record beating Budva", "The Champions League qualifiers returned to domestic competition."),
    ("rugby", "Newcastle agree delay to Fineanganofo arrival", "Fineanganofo will join Newcastle later than planned."),
])
def test_verified_source_context_disambiguates_shared_names_without_rewriting_facts(monkeypatch, sport, title, body):
    # Isolate taxonomy: other original-writing gates have their own tests.
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    draft = {"title": title, "summary": "", "body": body}
    assert guard.fact_lock_reason(draft, title, body, expected_sport=sport) is None


@pytest.mark.parametrize("expected,title,body,actual", [
    ("water-polo", "Liverpool football squad confirmed", "The soccer team returned to training.", "football"),
    ("darts", "Formula 1 driver wins Grand Prix", "The Formula 1 race ended.", "motorsport"),
    ("football", "UFC champion prepares for MMA title fight", "The MMA champion trained.", "mma"),
    ("rugby", "Newcastle United confirm Premier League transfer", "Newcastle United signed a football player.", "football"),
])
def test_verified_context_never_overrides_real_contradictory_sport(monkeypatch, expected, title, body, actual):
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    assert guard.fact_lock_reason({"title": title, "body": body}, title, body, expected_sport=expected) == "draft_sport_mismatch:" + actual


def test_home_debut_qualifier_is_mandatory(monkeypatch):
    monkeypatch.setattr(guard, "original_draft_reason", lambda *args: None)
    source = "The coach lost on his debut in the home dugout after an away draw."
    assert guard.fact_lock_reason({"title": "Coach loses on debut"}, "Visitors win", source) == "lost_debut_qualifier"
    assert guard.fact_lock_reason({"title": "Coach loses on home debut"}, "Visitors win", source) is None
    assert guard.fact_lock_reason({"title": "Visitors beat hosts"}, "Visitors win", source) is None


def test_confirmed_public_errors_remain_held_during_repairs():
    assert non_article_news_reason({"title": "Greece defeat Germany in Klopp debut as Gakpo suffers ankle injury"}) == "lost_debut_qualifier"
    assert non_article_news_reason({"title": "Germany's unexpected defeat to Greece in Nations League matches sparks surprise"}) == "confirmed_duplicate_with_unsupported_reaction"
