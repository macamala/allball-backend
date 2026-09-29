from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import SessionLocal, engine
from models import Article, Base, NewsCorrectionRule, NewsIncident
from bot import fetch_sources as ingest
from bot.news_learning import (
    add_confirmed_rule,
    article_has_open_incident,
    confirm_incident,
    learned_rule_violation_reason,
    record_incident,
    rule_prompt_instructions,
    writer_allowed,
)


FACTS = (
    "Arsenal confirmed a revised competition schedule after the organising committee "
    "completed its review. The club will play its next match under the published format. "
    "No transfer, injury or disciplinary announcement was included in the update."
)
DRAFT = {
    "title": "Arsenal schedule update follows competition review",
    "summary": "The club will play under the revised competition format.",
    "body": (
        "Following the organising committee's review, Arsenal have confirmed changes "
        "to the competition schedule.\n\n"
        "The announcement sets out the format for the club's forthcoming fixture. "
        "It contains no medical, transfer or disciplinary update."
    ),
}


@pytest.fixture(autouse=True)
def clean_news_memory():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(NewsIncident).delete()
        db.query(NewsCorrectionRule).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(NewsIncident).delete()
        db.query(NewsCorrectionRule).delete()
        db.commit()
    finally:
        db.close()


def test_confirmed_rule_is_prompt_memory_and_violation_gate():
    db = SessionLocal()
    try:
        rule = add_confirmed_rule(
            db,
            rule_type="exact_replace",
            bad_value="Northen Ireland",
            replacement="Northern Ireland",
            sport="football",
            source_url="https://example.test/news/a",
            source_scope=True,
            user_id=None,
        )
        prompt, ids = rule_prompt_instructions(
            db, source_url="https://example.test/news/b", sport="football"
        )
        assert rule.id in ids
        assert "Northen Ireland" in prompt and "Northern Ireland" in prompt
        bad = {
            "title": "Northen Ireland squad update",
            "summary": "Northen Ireland announced a squad update.",
            "body": "Northen Ireland announced a squad update for the next football match.",
        }
        assert learned_rule_violation_reason(
            db, bad, source_url="https://example.test/news/c", sport="football"
        ) == f"learned_rule_violation:{rule.id}"
        assert learned_rule_violation_reason(
            db,
            {**bad, "title": "Northern Ireland squad update",
             "summary": "Northern Ireland announced a squad update.",
             "body": "Northern Ireland announced a squad update for the next football match."},
            source_url="https://example.test/news/c",
            sport="football",
        ) is None
    finally:
        db.close()


def test_persistent_writer_circuit_uses_only_confirmed_incidents():
    db = SessionLocal()
    try:
        for idx in range(3):
            row = record_incident(
                db,
                reason_code=f"validator-unsupported-claim-{idx}",
                source_url=f"https://example.test/{idx}",
                sport="football",
                writer_provider="xkiro",
                writer_model="fixture:free",
            )
            assert writer_allowed(db, "xkiro", "fixture:free")
            confirm_incident(db, row, user_id=None, resolution_note="confirmed factual error")
        assert not writer_allowed(db, "xkiro", "fixture:free")
        assert writer_allowed(db, "xkiro", "other:free")
    finally:
        db.close()


def _prepare_ingest(monkeypatch):
    # These tests isolate incident/correction lifecycle. Public admission and
    # image failure behavior have dedicated News integration coverage.
    monkeypatch.setattr(ingest, 'news_image_is_reachable', lambda url: True)
    monkeypatch.setattr('public_read.public_query', lambda db: db.query(Article))
    monkeypatch.setattr(ingest, "existing_by_url", lambda *a: None)
    monkeypatch.setattr(ingest, "existing_near_duplicate", lambda *a: None)
    monkeypatch.setattr(ingest, "_source_on_ai_cooldown", lambda *a: False)
    monkeypatch.setattr(ingest, "_hold_ai_source", lambda *a, **k: None)
    monkeypatch.setattr(ingest, "extract_from_url", lambda *a: (FACTS, "https://example.test/hero.jpg"))
    monkeypatch.setattr(
        ingest,
        "classify_article",
        lambda *a, **k: SimpleNamespace(
            sport="football", league=None, country="international"
        ),
    )
    monkeypatch.setattr(ingest, "writer_identity", lambda: ("xkiro", "fixture:free"))
    monkeypatch.setattr(ingest, "writer_allowed", lambda *a, **k: True)
    monkeypatch.setattr(ingest, "openai_rate_limited", lambda: False)
    monkeypatch.setattr(ingest, "ai_budget_exhausted", lambda: False)
    monkeypatch.setattr(
        "taxonomy_resolver.resolve_article_competition",
        lambda article: SimpleNamespace(
            sport="football",
            public_competition=None,
            sport_confidence=0.95,
            competition_confidence=0.0,
            resolver_version="fixture",
        ),
    )
    monkeypatch.setattr("public_index.persist_public_article", lambda *a, **k: None)
    monkeypatch.setattr("public_cache.bump_public_cache", lambda: None)
    return {
        "title": "Arsenal competition schedule update",
        "url": "https://example.test/arsenal-schedule",
        "summary": "Arsenal competition schedule update.",
        "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        "feed": {"kind": "mixed", "sport": "football"},
        "image_candidates": [],
    }


def test_failed_first_draft_auto_corrects_before_publication(monkeypatch):
    item = _prepare_ingest(monkeypatch)
    calls = []

    def fake_story(**kwargs):
        calls.append(kwargs.get("correction_reason") or "")
        if len(calls) == 1:
            return None, "validator-unsupported-claim"
        return DRAFT, "ok"

    monkeypatch.setattr(ingest, "_ai_story", fake_story)
    db = SessionLocal()
    try:
        article, used = ingest._ingest_item(db, item, True, 6000, 4)
        assert article is not None and used
        assert calls == ["", "validator-unsupported-claim"]
        incident = (
            db.query(NewsIncident)
            .filter(NewsIncident.source_url == item["url"])
            .order_by(NewsIncident.id.desc())
            .first()
        )
        assert incident is not None
        assert incident.status == "auto_corrected"
        assert not incident.confirmed
        db.query(Article).filter(Article.id == article.id).delete()
        db.commit()
    finally:
        db.close()


def test_failed_retry_stays_open_and_cooldown_gets_retry_reason(monkeypatch):
    item = _prepare_ingest(monkeypatch)
    holds = []
    monkeypatch.setattr(
        ingest,
        "_hold_ai_source",
        lambda url, reason: holds.append((url, reason)),
    )
    answers = iter([
        (None, "validator-changed-name"),
        (None, "validator-unsupported-claim"),
    ])
    monkeypatch.setattr(ingest, "_ai_story", lambda **kwargs: next(answers))

    db = SessionLocal()
    try:
        article, used = ingest._ingest_item(db, item, True, 6000, 4)
        assert article is None and not used
        incident = db.query(NewsIncident).filter(
            NewsIncident.source_url == item["url"]
        ).first()
        assert incident is not None
        assert incident.status == "open"
        assert incident.retry_reason_code == "validator-unsupported-claim"
        assert holds[-1] == (item["url"], "validator-unsupported-claim")
    finally:
        db.close()


def test_postpublish_open_incident_is_a_public_quarantine_signal():
    db = SessionLocal()
    try:
        article = Article(
            external_id="self-heal-article",
            title="Football article",
            slug="self-heal-article",
            sport="football",
            summary="A football article summary with enough factual text.",
            content="A football article body with enough factual text to remain valid for this fixture.",
            ai_content="A football article body with enough factual text to remain valid for this fixture.",
            ai_generated=True,
            is_live=True,
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        assert not article_has_open_incident(db, article.id)
        record_incident(
            db,
            reason_code="staff-factual-review",
            source_url="https://example.test/article",
            sport="football",
            phase="postpublish-staff",
            article_id=article.id,
        )
        assert article_has_open_incident(db, article.id)
        db.query(NewsIncident).filter(NewsIncident.article_id == article.id).delete()
        db.delete(article)
        db.commit()
    finally:
        db.close()


def test_unknown_sport_enrichment_is_bounded_and_reuses_source(monkeypatch):
    rows = [
        {
            "title": f"National team update {idx}",
            "url": f"https://example.test/{idx}",
            "summary": "",
            "feed": {"kind": "mixed"},
        }
        for idx in range(6)
    ]
    calls = []

    def classify(item):
        return SimpleNamespace(
            sport="football" if item.get("_classification_text") else None
        )

    def extract(url):
        calls.append(url)
        return (
            "The football national team named its squad for the next international match. "
            "The coach confirmed the selection after training.",
            None,
        )

    monkeypatch.setattr(ingest, "_classify_candidate", classify)
    monkeypatch.setattr(ingest, "extract_from_url", extract)
    assert ingest._enrich_unknown_candidates(rows, limit=3) == 3
    assert len(calls) == 3
    assert all(rows[i].get("_extracted") for i in range(3))
    assert all(not rows[i].get("_extracted") for i in range(3, 6))


def test_correction_retry_preserves_translation_reserve(monkeypatch, tmp_path):
    from bot.news_budget import AiRequestBudget, ai_budget_scope

    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED", "1")
    monkeypatch.setenv("NEWS_TRANSLATIONS_PER_CYCLE", "6")
    budget = AiRequestBudget(4, str(tmp_path / "budget.sqlite"), daily_limit=20)
    with ai_budget_scope(budget):
        budget.attempts = 1
        assert ingest._correction_retry_allowed()
        budget.attempts = 2
        assert not ingest._correction_retry_allowed()

    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED", "0")
    with ai_budget_scope(budget):
        budget.blocked_reason = None
        budget.attempts = 2
        assert ingest._correction_retry_allowed()


def test_correction_retry_yields_to_breadth_when_coverage_is_sparse(monkeypatch, tmp_path):
    from bot.news_budget import AiRequestBudget, ai_budget_scope

    monkeypatch.setenv("NEWS_TRANSLATIONS_ENABLED", "1")
    monkeypatch.setenv("NEWS_TRANSLATIONS_PER_CYCLE", "1")
    budget = AiRequestBudget(6, str(tmp_path / "breadth-ledger.sqlite"), daily_limit=50)
    with ai_budget_scope(budget):
        # First writer + validator have already consumed two attempts.
        budget.attempts = 2
        assert ingest._correction_retry_allowed(prefer_breadth=False)
        assert not ingest._correction_retry_allowed(prefer_breadth=True)


def test_fact_lock_does_not_false_positive_normal_proper_names():
    from bot.news_fact_guard import fact_lock_reason
    source_title="England win series as Banton delivers on potential"
    source_body=(
        "Jacob Bethell played for England while Luke Humphries was discussed in a separate sports update. "
        "Brandon McNulty also appeared in the supplied source material without any invented injury or transfer."
    )
    draft={
        "title":"England finish series with Banton delivering",
        "summary":"Jacob Bethell featured for England.",
        "body":(
            "Jacob Bethell featured for England as the series was completed. "
            "The supplied account also names Luke Humphries and Brandon McNulty without adding a new claim."
        ),
    }
    assert fact_lock_reason(draft,source_title,source_body) is None


def test_cross_language_claim_words_defer_to_semantic_validator(monkeypatch):
    monkeypatch.setattr('bot.news_fact_guard.original_draft_reason', lambda *args: None)
    from bot.news_fact_guard import fact_lock_reason
    source_title="Lierse laat zich verrassen in de beker"
    source_body=(
        "De ploeg verloor de wedstrijd na een spannend duel en de tegenstander ging door. "
        "Het verslag beschrijft de uitslag, spelers en wedstrijd zonder Engelse formulering."
    )
    draft={
        "title":"Lierse beaten in cup tie",
        "summary":"Lierse suffered defeat in the cup.",
        "body":"Lierse were defeated in the cup match and their opponents advanced.",
    }
    assert fact_lock_reason(draft,source_title,source_body) is None


def test_event_claim_words_defer_to_semantic_validator(monkeypatch):
    monkeypatch.setattr('bot.news_fact_guard.original_draft_reason', lambda *args: None)
    from bot.news_fact_guard import fact_lock_reason
    source_title="Arsenal publish squad schedule"
    source_body=(
        "The club published the schedule for the next match and confirmed the squad list. "
        "The update contained no medical announcement and no change to player availability."
    )
    draft={
        "title":"Arsenal squad schedule update",
        "summary":"Arsenal published the schedule.",
        "body":"Arsenal published the schedule but one player suffered a knee injury.",
    }
    # Lexical synonyms are not publication authority. The mandatory semantic
    # source-vs-draft validator is responsible for this unsupported event claim.
    assert fact_lock_reason(draft,source_title,source_body) is None


def test_retryable_old_hold_reasons():
    from bot.news_source_holds import _retryable_reason
    # A failed bounded correction now waits before spending another cycle.
    assert not _retryable_reason("direct_quote_requires_review")
    assert _retryable_reason("unsupported_proper_name:fixture")
    assert _retryable_reason("unsupported_claim_family:appointment")
    assert _retryable_reason("validator-unavailable")
    assert not _retryable_reason("missing-or-unreachable-publishable-image")
