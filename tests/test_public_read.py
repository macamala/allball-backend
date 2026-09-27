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


def test_bbc_programme_still_is_not_public_hero():
    article = _make(
        slug="bbc-graphic-hero",
        title="Liverpool hold Chelsea in the Premier League",
        image_url="https://ichef.bbci.co.uk/images/ic/240x135/p0p3n9ks.jpg",
        external_id="https://example.com/bbc-graphic-hero",
    )
    with TestClient(app) as client:
        detail_response = client.get(f"/articles/{article.slug}")
        assert detail_response.status_code == 404
        listed = client.get("/articles?sport=football&limit=50").json()
        row = next((item for item in listed if item["slug"] == article.slug), None)
        assert row is None


def test_missing_image_is_never_public():
    article = _make(
        slug="missing-image-hidden",
        title="Arsenal announce a Premier League squad update",
        image_url=None,
        external_id="https://example.com/missing-image-hidden",
    )
    db = SessionLocal()
    try:
        pairs = fetch_public(db, sport="football", limit=100)
        assert all(row.id != article.id for row, _ in pairs)
    finally:
        db.close()


def test_public_query_has_global_image_contract():
    db = SessionLocal()
    try:
        compiled = str(public_query(db, cards=True).statement.compile(compile_kwargs={"literal_binds": False}))
        lower = compiled.lower()
        assert "image_url is not null" in lower
        assert "hero_media_kind" in lower
    finally:
        db.close()


def test_recent_duplicate_repair_keeps_one_public_story():
    from public_index import repair_recent_duplicate_news
    first=_make(
        slug="dedupe-arsenal-one",
        title="Arsenal confirm Bukayo Saka will miss Liverpool clash after injury",
        external_id="https://source-one.example/dedupe-arsenal",
    )
    second=_make(
        slug="dedupe-arsenal-two",
        title="Arsenal confirms Saka will miss Liverpool game following injury",
        external_id="https://source-two.example/dedupe-arsenal",
    )
    db=SessionLocal()
    try:
        hidden=repair_recent_duplicate_news(db,limit=600,max_age_hours=168)
        assert hidden >= 1
        pairs=fetch_public(db,sport="football",limit=100)
        ids={row.id for row,_ in pairs}
        assert len({first.id,second.id} & ids)==1
    finally:
        db.close()


def test_recent_inventory_ignores_old_and_missing_image_rows():
    from datetime import timedelta
    from public_index import recent_public_sport_inventory
    fresh=_make(
        slug="inventory-fresh-photo",
        external_id="https://example.com/inventory-fresh-photo",
        published_at=datetime.utcnow(),
    )
    old=_make(
        slug="inventory-old-photo",
        external_id="https://example.com/inventory-old-photo",
        published_at=datetime.utcnow()-timedelta(days=10),
    )
    missing=_make(
        slug="inventory-missing-image",
        external_id="https://example.com/inventory-missing-image",
        image_url=None,
        published_at=datetime.utcnow(),
    )
    db=SessionLocal()
    try:
        inventory=recent_public_sport_inventory(db,max_age_hours=72)
        assert fresh.id != old.id != missing.id
        pairs=fetch_public(db,sport="football",limit=200)
        visible_ids={row.id for row,_ in pairs}
        assert fresh.id in visible_ids
        assert missing.id not in visible_ids
        assert inventory.get("football",0) >= 1
    finally:
        db.close()



def test_recent_cross_sport_mislabel_is_hidden():
    from models import ArticleTaxonomyResolution
    from public_index import repair_recent_sport_mislabels

    article = _make(
        slug="cycling-poisoned-as-nfl",
        title="Caroline Andersson conscious after heavy crash at Road World Championships",
        content=(
            "The Swedish rider crashed heavily during the road world championships. "
            "Medical staff treated the cyclist before she was taken for further checks. "
            "The road race was stopped briefly while the cycling medical team responded."
        ),
        sport="cycling",
        league=None,
        external_id="https://example.com/cycling-poisoned-as-nfl",
    )
    db = SessionLocal()
    try:
        tax = db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id == article.id
        ).first()
        assert tax is not None
        tax.resolved_sport = "american-football"
        tax.resolved_competition = None
        tax.sport_confidence = "0.920"
        tax.public_ok = True
        db.add(tax)
        db.commit()

        assert repair_recent_sport_mislabels(db, limit=100, max_age_hours=168) >= 1
        db.refresh(tax)
        assert tax.public_ok is False
    finally:
        db.close()



def test_cross_sport_repair_requires_distinctive_headline_evidence():
    from public_index import _distinctive_title_sport_support

    assert _distinctive_title_sport_support(
        "Caroline Andersson conscious after heavy crash at Road World Championships",
        "cycling",
    )
    assert not _distinctive_title_sport_support(
        "Pierre Royal becomes first Irish-trained Cambridgeshire winner this century",
        "ice-hockey",
    )
    assert not _distinctive_title_sport_support(
        "GBGB Calendar Vol 18 No.19 Now Available Online",
        "mma",
    )


def test_ambiguous_cross_sport_classifier_result_does_not_hide_valid_row(monkeypatch):
    import public_index as pi
    from models import ArticleTaxonomyResolution

    article = _make(
        slug="horse-repair-conservative",
        title="Pierre Royal becomes first Irish-trained Cambridgeshire winner this century",
        content=(
            "Pierre Royal won the Cambridgeshire after a strong run under his jockey. "
            "The horse was trained in Ireland and finished ahead of the field."
        ),
        sport="horse-racing",
        league=None,
        external_id="https://example.com/horse-repair-conservative",
    )
    db = SessionLocal()
    try:
        tax = db.query(ArticleTaxonomyResolution).filter(
            ArticleTaxonomyResolution.article_id == article.id
        ).first()
        assert tax is not None
        tax.resolved_sport = "horse-racing"
        tax.resolved_competition = None
        tax.sport_confidence = "0.920"
        tax.public_ok = True
        db.add(tax)
        db.commit()
        monkeypatch.setattr(
            "bot.classify.classify_article",
            lambda *a, **k: type("C", (), {"sport": "ice-hockey"})(),
        )
        assert pi.repair_recent_sport_mislabels(db, limit=100, max_age_hours=168) == 0
        db.refresh(tax)
        assert tax.public_ok is True
    finally:
        db.close()
