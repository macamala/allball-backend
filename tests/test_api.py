from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from models import Article, Base


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


def _make_article(**kwargs):
    db = SessionLocal()
    try:
        article = Article(
            external_id=kwargs.get("external_id", "https://example.com/" + kwargs.get("slug", "a")),
            title=kwargs.get("title", "Test article title"),
            slug=kwargs.get("slug", "test-article"),
            sport=kwargs.get("sport", "football"),
            league=kwargs.get("league", "england-premier-league"),
            country=kwargs.get("country", "england"),
            summary=kwargs.get("summary", "Summary"),
            content=kwargs.get("content", "Body text for the article."),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            published_at=kwargs.get("published_at"),
            source_url=kwargs.get("source_url", "https://example.com/hidden"),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article
    finally:
        db.close()


def test_health_reports_database():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] in {"ok", "degraded"}
        assert "database" in body
        assert "DATABASE_URL" not in str(body)


def test_sitemap_handles_date_objects():
    with TestClient(app) as client:
        res = client.get("/sitemap.xml")
        assert res.status_code == 200
        assert "urlset" in res.text
        assert "ninkosports.com" in res.text


def test_published_at_preferred_and_created_at_fallback():
    older_created = datetime.utcnow() - timedelta(days=10)
    newer_source = datetime.utcnow() - timedelta(hours=1)
    _make_article(
        slug="with-published",
        title="Has source timestamp",
        created_at=older_created,
        published_at=newer_source,
        external_id="https://example.com/with-published",
    )
    _make_article(
        slug="legacy-created",
        title="Legacy uses created_at",
        created_at=datetime.utcnow(),
        published_at=None,
        external_id="https://example.com/legacy-created",
    )
    with TestClient(app) as client:
        res = client.get("/articles?sort=newest&limit=20")
        assert res.status_code == 200
        rows = res.json()
        by_slug = {row["slug"]: row for row in rows}
        assert by_slug["with-published"]["published_at"]
        assert by_slug["legacy-created"]["published_at"] == by_slug["legacy-created"]["created_at"]
        detail = client.get("/articles/with-published").json()
        assert detail["published_at"]
        assert "Has source timestamp" in detail["title"]
        related = client.get("/articles/with-published/related")
        assert related.status_code == 200


def test_articles_schema_compatible():
    with TestClient(app) as client:
        res = client.get("/articles")
        assert res.status_code == 200
        if res.json():
            row = res.json()[0]
            for key in ("id", "slug", "title", "sport", "league", "country", "created_at"):
                assert key in row
            assert "source_url" not in row
            assert "is_breaking" in row
            assert row["is_breaking"] is False
        leagues = client.get("/meta/leagues").json()
        assert isinstance(leagues, list)
        sports = client.get("/meta/sports").json()
        assert isinstance(sports, list)
        assert all(isinstance(s, str) for s in sports)
