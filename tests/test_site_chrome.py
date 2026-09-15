from fastapi.testclient import TestClient

from app import app
from bot.extract import paragraphs_from_html
from bot.fetch_sources import select_facts
from bot.quality import quality_check
from bot.site_chrome import is_site_chrome_text, strip_site_chrome
from editorial import evaluate_quality, public_summary, sanitize_body
from models import Article, ArticleTaxonomyResolution
from public_index import persist_public_article
from repair_content import repair_one
from database import SessionLocal, engine, ensure_schema
from models import Base
from datetime import datetime


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


CHROME_BLOB = (
    "Homepage Accessibility Help Your account Home News Sport Earth Reel "
    "Worklife Travel Culture Future Music TV Weather Sounds More menu More menu "
    "Search Sport Home News Sport Earth Reel Worklife Travel Culture Future Music "
    "TV Weather Sounds Close menu Sport Menu Home Football Cricket Formula 1 Rugby "
    "Tennis Golf Cycling Athletics More A-Z Sports Basketball Boxing "
    "Skubala will not underestimate former team Lincoln "
    "To play this video you need to enable JavaScript in your browser "
    "Bristol City head coach Michael Skubala says he will not underestimate "
    "his former club Lincoln City when they visit Ashton Gate on Tuesday night. "
    "The Championship encounter is the first time Skubala has come up against "
    "the Imps since guiding them to the League One title and promotion."
)

CLEAN_PROSE = (
    "Aston Villa earned a late point against Arsenal in the Premier League. "
    "Unai Emery's side defended with discipline after the break and created "
    "enough chances to take something from the match. The result keeps both "
    "clubs in the mix as the season gathers pace in England."
)


def test_chrome_blob_is_detected_without_publisher_brand():
    assert is_site_chrome_text(CHROME_BLOB)
    assert "BBC" not in CHROME_BLOB


def test_legitimate_bbc_and_football_prose_survives():
    prose = (
        "The BBC reported that football news broke after the match in London. "
        "Arsenal found a late winner and the home crowd stayed loud until full-time."
    )
    assert is_site_chrome_text(prose) is False
    cleaned = sanitize_body(prose, title="Arsenal find a late winner")
    assert "BBC" in cleaned
    assert "football news" in cleaned
    assert "Arsenal" in cleaned


def test_strip_chrome_keeps_article_prose():
    cleaned = strip_site_chrome(CHROME_BLOB)
    assert "Accessibility Help" not in cleaned
    assert "More menu" not in cleaned
    assert "Your account" not in cleaned
    assert "Skubala" in cleaned or "Bristol City" in cleaned
    assert "Lincoln City" in cleaned
    body = sanitize_body(CHROME_BLOB, title="Skubala will not underestimate former team Lincoln")
    assert "More menu" not in body
    assert "Accessibility Help" not in body
    assert "Bristol City" in body
    assert public_summary(CHROME_BLOB[:400], title="Skubala will not underestimate former team Lincoln") == ""


def test_html_extractor_drops_nav_and_keeps_article():
    html = """
    <html><body>
    <nav><p>Home News Sport Earth Reel Worklife Travel Culture</p></nav>
    <header role="banner"><p>Accessibility Help Your account More menu</p></header>
    <article>
      <p>Aston Villa earned a late point against Arsenal in the Premier League.</p>
      <p>Unai Emery's side defended with discipline after the break and created chances.</p>
    </article>
    <footer><p>All rights reserved subscribe to our newsletter</p></footer>
    </body></html>
    """
    text = paragraphs_from_html(html)
    assert "Accessibility Help" not in text
    assert "Your account" not in text
    assert "Aston Villa" in text
    assert "Unai Emery" in text


def test_select_facts_ignores_chrome_rss():
    extracted = CLEAN_PROSE
    rss = CHROME_BLOB
    facts = select_facts(extracted, rss)
    assert "More menu" not in facts
    assert "Aston Villa" in facts
    assert select_facts("", rss).startswith("Bristol City") or "Skubala" in select_facts("", rss)
    assert select_facts("", "Home News Sport Earth Reel Worklife Travel") == ""


def test_quality_rejects_chrome_and_allows_clean_english():
    ok, reason = quality_check("Skubala faces Lincoln", CHROME_BLOB, "football")
    assert ok is False
    assert reason == "boilerplate"
    ok, reason = quality_check("Villa earn a point against Arsenal", CLEAN_PROSE, "football")
    assert ok is True


def test_evaluate_quality_hides_unsalvageable_chrome():
    quality = evaluate_quality(
        title="Menu dump",
        summary="Accessibility Help Your account More menu Home News Sport",
        body="Accessibility Help Your account More menu Home News Sport Earth Reel Worklife Travel Culture Future Music TV Weather Sounds Close menu",
        image_url="https://example.com/photo.jpg",
    )
    assert quality["ok"] is False
    assert "navigation" in quality["flags"]


def test_repair_salvages_contaminated_row_without_fetch():
    db = SessionLocal()
    try:
        article = Article(
            external_id="https://example.com/skubala-chrome",
            title="Who has made Troy's Premier League team of the week?",
            slug="skubala-chrome-repair",
            sport="football",
            league="england-premier-league",
            summary=CHROME_BLOB[:400],
            content=CHROME_BLOB,
            image_url="https://example.com/skubala.jpg",
            source_url="https://example.com/skubala-chrome",
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        persist_public_article(db, article, commit=True)
        result = repair_one(db, article, allow_fetch=False)
        db.commit()
        db.refresh(article)
        assert result == "repaired"
        assert "More menu" not in (article.content or "")
        assert "Accessibility Help" not in (article.content or "")
        assert "Bristol City" in article.content
        assert article.image_url == "https://example.com/skubala.jpg"
        tax = (
            db.query(ArticleTaxonomyResolution)
            .filter(ArticleTaxonomyResolution.article_id == article.id)
            .first()
        )
        assert tax is not None
        assert tax.quality_ok is True
    finally:
        db.close()


def test_repair_hides_unsalvageable_chrome():
    db = SessionLocal()
    try:
        article = Article(
            external_id="https://example.com/nav-only",
            title="A late winner decided the derby",
            slug="nav-only-repair",
            sport="football",
            league="england-premier-league",
            summary="Accessibility Help Your account More menu Home News Sport",
            content=(
                "Accessibility Help Your account More menu Close menu Home News Sport "
                "Earth Reel Worklife Travel Culture Future Music TV Weather Sounds "
                "Home News Sport Earth Reel Worklife Travel Culture"
            ),
            image_url="https://example.com/nav.jpg",
            source_url="https://example.com/nav-only",
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        persist_public_article(db, article, commit=True)
        result = repair_one(db, article, allow_fetch=False)
        db.commit()
        assert result in {"hidden", "clean"}
        tax = (
            db.query(ArticleTaxonomyResolution)
            .filter(ArticleTaxonomyResolution.article_id == article.id)
            .first()
        )
        if result == "hidden":
            assert tax.public_ok is False
        else:
            # already rejected at persist
            assert tax.public_ok is False
    finally:
        db.close()


def test_public_get_does_not_publish_site_chrome():
    db = SessionLocal()
    try:
        article = Article(
            external_id="https://example.com/chrome-public-get",
            title="Who has made Troy's Premier League team of the week?",
            slug="chrome-public-get",
            sport="football",
            league="england-premier-league",
            summary=CHROME_BLOB[:400],
            content=CHROME_BLOB,
            image_url="https://example.com/troy.jpg",
            source_url="https://example.com/chrome-public-get",
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
        )
        db.add(article)
        db.commit()
        persist_public_article(db, article, commit=True)
    finally:
        db.close()
    with TestClient(app) as client:
        detail = client.get("/articles/chrome-public-get").json()
        blob = " ".join(
            [
                detail.get("summary") or "",
                detail.get("content") or "",
                " ".join(block.get("text") or "" for block in detail.get("blocks") or []),
            ]
        )
        assert "Accessibility Help" not in blob
        assert "More menu" not in blob
        assert "Your account" not in blob
        assert "Bristol City" in blob or "Skubala" in blob
        assert "Getty Images" not in blob
