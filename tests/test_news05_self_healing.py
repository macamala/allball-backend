from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from database import SessionLocal, engine
from models import Base, NewsCorrectionRule, NewsIncident
from bot.news_fact_guard import fact_lock_reason
from bot.news_learning import (
    add_confirmed_rule,
    apply_confirmed_rules,
    record_incident,
    writer_allowed,
)
from bot import fetch_sources as ingest


SOURCE = (
    "Arsenal confirmed a revised competition schedule after the organising committee "
    "completed its review. The club will play its next match under the published format. "
    "No transfer, injury or disciplinary announcement was included in the update."
)
GOOD = {
    "title": "Arsenal schedule update follows competition review",
    "summary": "The club will play under the revised competition format.",
    "body": (
        "Arsenal will play its next match under the revised competition schedule after "
        "the organising committee completed its review.\n\n"
        "The update concerns the published competition format and the club's next match."
    ),
}


@pytest.fixture(autouse=True)
def clean_tables():
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


def test_fact_lock_accepts_supported_original_copy():
    assert fact_lock_reason(GOOD, "Arsenal competition schedule update", SOURCE) is None


def test_fact_lock_blocks_new_known_entity():
    bad = {**GOOD, "body": GOOD["body"] + " Chelsea will also join the event."}
    reason = fact_lock_reason(bad, "Arsenal competition schedule update", SOURCE)
    assert reason and reason.startswith("unsupported_known_entity:chelsea")


def test_fact_lock_blocks_new_high_risk_claim_family():
    source = "Arsenal published the timetable for its next competition match."
    bad = {
        "title": "Arsenal schedule update",
        "summary": "A new deal changes the club's plans.",
        "body": "Arsenal signed a transfer deal before the next competition match. The club published the timetable.",
    }
    assert fact_lock_reason(bad, "Arsenal schedule", source) == "unsupported_claim_family:transfer"


def test_confirmed_exact_rule_is_applied_only_inside_scope():
    db = SessionLocal()
    try:
        add_confirmed_rule(
            db,
            rule_type="exact_replace",
            bad_value="Northen Ireland",
            replacement="Northern Ireland",
            sport="football",
            source_url="https://example.test/story",
            source_scope=True,
            user_id=None,
        )
        draft = {"title": "Northen Ireland update", "summary": "Northen Ireland news", "body": "Northen Ireland announced the squad."}
        fixed, blocked, ids = apply_confirmed_rules(
            db, draft, source_url="https://example.test/other", sport="football"
        )
        assert not blocked and ids
        assert "Northen Ireland" not in fixed["body"]
        assert "Northern Ireland" in fixed["body"]

        untouched, blocked, ids = apply_confirmed_rules(
            db, draft, source_url="https://different.test/story", sport="football"
        )
        assert not blocked and not ids
        assert untouched["body"] == draft["body"]
    finally:
        db.close()


def test_confirmed_block_rule_holds_matching_draft():
    db = SessionLocal()
    try:
        rule = add_confirmed_rule(
            db,
            rule_type="block_phrase",
            bad_value="unnamed insiders",
            sport="football",
            user_id=None,
        )
        draft = {"title": "Arsenal update", "summary": "Club news", "body": "Unnamed insiders claimed a major change at Arsenal."}
        _, blocked, ids = apply_confirmed_rules(
            db, draft, source_url="https://example.test/a", sport="football"
        )
        assert blocked == f"learned_block_phrase:{rule.id}"
        assert ids == [rule.id]
    finally:
        db.close()


def test_writer_circuit_breaks_only_on_confirmed_errors():
    db = SessionLocal()
    try:
        for idx in range(3):
            row = record_incident(
                db,
                reason_code=f"unsupported_number:{idx}",
                source_url=f"https://example.test/{idx}",
                sport="football",
                writer_provider="fixture",
                writer_model="writer-a",
            )
            row.confirmed = True
            row.status = "resolved"
            db.add(row)
            db.commit()
        assert not writer_allowed(db, "fixture", "writer-a", max_confirmed_errors=3)
        assert writer_allowed(db, "fixture", "writer-b", max_confirmed_errors=3)
    finally:
        db.close()


def test_ingest_auto_corrects_first_bad_draft_and_publishes_second(monkeypatch):
    from models import Article

    now = datetime.now(timezone.utc)
    first = {
        "title": "Arsenal and Chelsea schedule update",
        "summary": "The two clubs received a revised schedule.",
        "body": "Arsenal and Chelsea will use the revised competition schedule. The organising committee completed its review.",
    }
    second = GOOD
    calls = []

    monkeypatch.setattr(ingest, "existing_by_url", lambda *a: None)
    monkeypatch.setattr(ingest, "existing_near_duplicate", lambda *a: None)
    monkeypatch.setattr(ingest, "extract_from_url", lambda *a: (SOURCE, None))
    monkeypatch.setattr(
        ingest,
        "classify_article",
        lambda *a, **k: SimpleNamespace(sport="football", league=None, country="international"),
    )
    monkeypatch.setattr(ingest, "writer_identity", lambda: ("fixture", "writer-a"))
    monkeypatch.setattr(ingest, "writer_allowed", lambda *a, **k: True)
    monkeypatch.setattr(ingest, "openai_rate_limited", lambda: False)

    def fake_story(**kwargs):
        calls.append(kwargs.get("correction_reason") or "")
        return (first, "ok") if len(calls) == 1 else (second, "ok")

    monkeypatch.setattr(ingest, "_ai_story", fake_story)
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

    item = {
        "title": "Arsenal competition schedule update",
        "url": "https://example.test/arsenal-schedule",
        "summary": "Arsenal competition schedule update.",
        "published_at": now - timedelta(hours=1),
        "feed": {"kind": "mixed", "sport": "football"},
        "image_candidates": [],
    }

    db = SessionLocal()
    try:
        article, used = ingest._ingest_item(db, item, True, 6000, 2)
        assert article is not None and used
        assert len(calls) == 2 and calls[1].startswith("unsupported_known_entity:")
        incident = (
            db.query(NewsIncident)
            .filter(NewsIncident.source_url == item["url"])
            .order_by(NewsIncident.id.desc())
            .first()
        )
        assert incident is not None and incident.status == "auto_corrected"
        db.query(Article).filter(Article.id == article.id).delete()
        db.commit()
    finally:
        db.close()
