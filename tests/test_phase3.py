from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import app, _recent_views
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
            summary=kwargs.get("summary", "Summary about the match and how both sides approached the closing minutes."),
            content=kwargs.get(
                "content",
                "The match produced a late twist as the visitors pushed for a winner while the home side held their shape. "
                "Players kept working through stoppage time and the crowd stayed loud until the final whistle. "
                "Coaches later pointed to concentration and the value of taking the few chances that appeared.",
            ),
            image_url=kwargs.get("image_url"),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            published_at=kwargs.get("published_at"),
            source_url=kwargs.get("source_url", "https://example.com/hidden"),
            is_breaking=kwargs.get("is_breaking", False),
            view_count=kwargs.get("view_count", 0),
        )
        db.add(article)
        db.commit()
        db.flush()
        db.refresh(article)
        return article
    finally:
        db.close()


def test_health_still_ok():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["database"] in {"ok", "error"}


def test_article_detail_hides_source_and_has_neighbors():
    older = datetime.utcnow() - timedelta(hours=2)
    newer = datetime.utcnow() - timedelta(hours=1)
    _make_article(
        slug="older-story",
        title="Older story",
        created_at=older,
        published_at=older,
        external_id="https://example.com/older-story",
    )
    _make_article(
        slug="current-story",
        title="Current story",
        created_at=newer,
        published_at=newer,
        external_id="https://example.com/current-story",
        content=" ".join(["word"] * 440),
    )
    with TestClient(app) as client:
        res = client.get("/articles/current-story")
        assert res.status_code == 200
        body = res.json()
        assert "source_url" not in body
        assert body["title"] == "Current story"
        assert body["reading_time_minutes"] >= 1
        assert body["previous"] is None or "slug" in body["previous"]
        assert "next" in body


def test_sport_and_league_endpoints():
    _make_article(
        slug="pl-news",
        title="Premier League news",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/pl-news",
    )
    _make_article(
        slug="nba-news",
        title="NBA news",
        sport="basketball",
        league="nba",
        country="usa",
        external_id="https://example.com/nba-news",
    )
    with TestClient(app) as client:
        football = client.get("/articles/by-sport/football")
        assert res_ok(football)
        assert any(row["slug"] == "pl-news" for row in football.json())
        by_alias = client.get("/articles/by-league/premier-league")
        assert res_ok(by_alias)
        assert any(row["slug"] == "pl-news" for row in by_alias.json())
        nba = client.get("/articles?sport=basketball&league=nba")
        assert res_ok(nba)
        assert any(row["slug"] == "nba-news" for row in nba.json())


def res_ok(res):
    return res.status_code == 200


def test_search_title_and_no_full_scan_on_short_query():
    _make_article(
        slug="searchable-villa",
        title="Aston Villa win late",
        summary="A late goal in Birmingham",
        external_id="https://example.com/searchable-villa",
    )
    with TestClient(app) as client:
        empty = client.get("/search?q=a")
        assert empty.status_code == 200
        assert empty.json() == []
        hits = client.get("/search?q=villa")
        assert hits.status_code == 200
        assert any(row["slug"] == "searchable-villa" for row in hits.json())
        sport_miss = client.get("/search?q=villa&sport=tennis")
        assert sport_miss.status_code == 200
        assert sport_miss.json() == []
        for row in hits.json():
            assert "source_url" not in row


def test_breaking_defaults_false_and_only_flagged_rows_returned():
    _make_article(
        slug="normal-news",
        title="Normal news",
        external_id="https://example.com/normal-news",
    )
    _make_article(
        slug="breaking-news",
        title="Breaking news",
        is_breaking=True,
        external_id="https://example.com/breaking-news",
    )
    with TestClient(app) as client:
        listed = client.get("/articles?limit=50").json()
        by_slug = {row["slug"]: row for row in listed}
        assert by_slug["normal-news"]["is_breaking"] is False
        breaking = client.get("/articles/breaking").json()
        slugs = [row["slug"] for row in breaking]
        assert "breaking-news" in slugs
        assert "normal-news" not in slugs


def test_most_read_does_not_fabricate_and_view_dedupes():
    _make_article(
        slug="viewed-story",
        title="Viewed story",
        view_count=0,
        external_id="https://example.com/viewed-story",
    )
    _recent_views.clear()
    with TestClient(app) as client:
        empty = client.get("/articles/most-read").json()
        assert all(row["slug"] != "viewed-story" for row in empty)
        first = client.post("/articles/viewed-story/view")
        assert first.status_code == 200
        assert first.json()["counted"] is True
        second = client.post("/articles/viewed-story/view")
        assert second.json()["counted"] is False
        ranked = client.get("/articles/most-read").json()
        assert any(row["slug"] == "viewed-story" for row in ranked)


def test_portal_home_and_featured_use_real_articles():
    _make_article(
        slug="hero-story",
        title="Hero story",
        image_url="https://example.com/img.jpg",
        external_id="https://example.com/hero-story",
    )
    with TestClient(app) as client:
        home = client.get("/portal/home")
        assert home.status_code == 200
        body = home.json()
        assert "featured" in body
        assert "latest" in body
        assert "most_read" in body
        assert "by_sport" in body
        assert "football" in body["by_sport"]
        assert body["sports_data"]["connected"] is False
        featured = client.get("/articles/featured")
        assert featured.status_code == 200


def test_sports_data_is_empty_not_fake():
    with TestClient(app) as client:
        scores = client.get("/sports-data/scores").json()
        assert scores["connected"] is False
        assert scores["matches"] == []
        standings = client.get("/sports-data/standings?league=premier-league").json()
        assert standings["rows"] == []
        match = client.get("/sports-data/matches/abc").json()
        assert match["header"] is None
        team = client.get("/sports-data/teams/arsenal").json()
        assert team["available"] is False


def test_backward_compatible_schema_columns():
    article = _make_article(
        slug="compat-row",
        title="Compat row",
        external_id="https://example.com/compat-row",
    )
    assert article.is_breaking is False or article.is_breaking == 0
    assert int(article.view_count or 0) == 0
    with TestClient(app) as client:
        sitemap = client.get("/sitemap.xml")
        assert sitemap.status_code == 200
        assert "/football" in sitemap.text
        nav = client.get("/meta/navigation")
        assert nav.status_code == 200
        assert "sports" in nav.json()
