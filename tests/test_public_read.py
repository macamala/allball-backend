from datetime import datetime

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from editorial import is_photo_credit_text
from models import Article, Base
from public_index import persist_public_article
from public_read import fetch_public, public_query


GETTY_BODY = (
    "COMO, ITALY - SEPTEMBER 10: Players celebrate during the UEFA Champions League "
    "2026/27 match (Photo by Marco Bertorello/Getty Images) Como completed a stunning "
    "Champions League debut with a 4-1 win over RB Leipzig after a night that never "
    "looked like slipping away. The hosts scored early and kept pushing until the "
    "final whistle as the crowd stayed loud throughout a memorable European evening."
)

LONG = (
    "Aston Villa earned a late point against Arsenal in the Premier League. "
    "Unai Emery's side defended with discipline after the break and created "
    "enough chances to take something from the match. The result keeps both "
    "clubs in the mix as the season gathers pace in England. Supporters left "
    "encouraged by the performance even if the finishing was wasteful at times."
)


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


def _make(**kwargs):
    db = SessionLocal()
    try:
        article = Article(
            external_id=kwargs.get("external_id", "https://example.com/" + kwargs.get("slug", "a")),
            title=kwargs.get("title", "Aston Villa earn a point against Arsenal"),
            slug=kwargs.get("slug", "public-read-story"),
            sport=kwargs.get("sport", "football"),
            league=kwargs.get("league", "england-premier-league"),
            country=kwargs.get("country", "england"),
            summary=kwargs.get("summary", "Villa hold Arsenal after a disciplined display."),
            content=kwargs.get("content", LONG),
            image_url=kwargs.get("image_url", "https://example.com/hero.jpg"),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            published_at=kwargs.get("published_at", datetime.utcnow()),
            source_url="https://example.com/hidden-source",
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        persist_public_article(db, article, commit=True)
        db.refresh(article)
        return article
    finally:
        db.close()


def test_lists_are_card_payloads_only():
    _make(slug="card-only-home", external_id="https://example.com/card-only-home")
    with TestClient(app) as client:
        listed = client.get("/articles?sport=football&limit=24").json()
        assert listed
        row = listed[0]
        assert "content" not in row
        assert "blocks" not in row
        assert "media" not in row
        assert row["slug"]
        assert row["title"]
        home = client.get("/portal/home").json()
        assert "Cache-Control" in client.get("/portal/home").headers
        for bucket in (home.get("featured") or []) + (home.get("latest") or []):
            assert "content" not in bucket
            assert "blocks" not in bucket


def test_public_get_does_not_publish_photo_credits():
    _make(
        slug="getty-caption-story",
        title="Como complete a stunning Champions League debut",
        content=GETTY_BODY,
        league="uefa-champions-league",
        external_id="https://example.com/getty-caption-story",
    )
    with TestClient(app) as client:
        detail = client.get("/articles/getty-caption-story").json()
        blob = " ".join(
            [
                detail.get("content") or "",
                " ".join(block.get("text") or "" for block in detail.get("blocks") or []),
                " ".join(item.get("caption") or "" for item in detail.get("media") or []),
            ]
        )
        assert "Getty Images" not in blob
        assert "Photo by" not in blob
        assert not is_photo_credit_text(detail.get("content"))
        assert "Champions League debut" in (detail.get("content") or "")


def test_sport_filter_uses_indexed_taxonomy_join():
    _make(
        slug="explain-football",
        title="Arsenal beat Liverpool in the Premier League",
        external_id="https://example.com/explain-football",
    )
    db = SessionLocal()
    try:
        compiled = str(
            public_query(db, cards=True)
            .statement.compile(compile_kwargs={"literal_binds": False})
        )
        assert "article_taxonomy_resolutions" in compiled.lower()
        assert "public_ok" in compiled.lower()
        pairs = fetch_public(db, sport="football", limit=24)
        assert pairs
        assert all(tax.resolved_sport == "football" for _, tax in pairs)
    finally:
        db.close()
