from datetime import datetime

from fastapi.testclient import TestClient

from app import app
from auth import hash_password, verify_password
from comments_api import sanitize_comment
from database import SessionLocal, engine, ensure_schema
from models import Article, Base, User


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


LONG = (
    "The match produced a late twist as the visitors pushed for a winner while the home side held their shape. "
    "Players kept working through stoppage time and the crowd stayed loud until the final whistle. "
    "Coaches later pointed to concentration and the value of taking the few chances that appeared."
)


def _article(**kwargs):
    db = SessionLocal()
    try:
        article = Article(
            external_id=kwargs.get("external_id", "https://example.com/" + kwargs.get("slug", "auth-a")),
            title=kwargs.get("title", "Chelsea hold Manchester City in the Premier League"),
            slug=kwargs.get("slug", "auth-story"),
            sport="football",
            league="england-premier-league",
            country="england",
            summary="A tight Premier League night in London.",
            content=LONG,
            image_url="https://example.com/img.jpg",
            created_at=datetime.utcnow(),
            published_at=datetime.utcnow(),
            source_url="https://example.com/hidden",
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article
    finally:
        db.close()


def _csrf(client: TestClient) -> str:
    res = client.get("/auth/csrf")
    assert res.status_code == 200
    return res.json()["csrf"]


def _headers(token: str) -> dict:
    return {"X-CSRF-Token": token}


def test_password_hashing_is_not_plaintext():
    stored = hash_password("correct-horse")
    assert stored.startswith("pbkdf2_sha256$")
    assert "correct-horse" not in stored
    assert verify_password("correct-horse", stored) is True
    assert verify_password("wrong-pass", stored) is False


def test_register_login_profile_language_and_logout():
    with TestClient(app) as client:
        token = _csrf(client)
        bad = client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "password12", "display_name": "Alex"},
            headers=_headers(token),
        )
        assert bad.status_code == 400
        short = client.post(
            "/auth/register",
            json={"email": "alex@example.com", "password": "123", "display_name": "Alex"},
            headers=_headers(token),
        )
        assert short.status_code == 400
        created = client.post(
            "/auth/register",
            json={"email": "alex@example.com", "password": "password12", "display_name": "Alex Reader"},
            headers=_headers(token),
        )
        assert created.status_code == 200
        user = created.json()["user"]
        assert user["email"] == "alex@example.com"
        assert user["display_name"] == "Alex Reader"
        assert user["preferred_language"] == "en"
        session = client.get("/auth/session").json()
        assert session["user"]["email"] == "alex@example.com"
        token = created.json().get("csrf") or _csrf(client)
        updated = client.patch(
            "/auth/profile",
            json={"preferred_language": "sr", "display_name": "Alex R"},
            headers=_headers(token),
        )
        assert updated.status_code == 200
        assert updated.json()["user"]["preferred_language"] == "sr"
        client.post("/auth/logout")
        assert client.get("/auth/session").json()["user"] is None
        token = _csrf(client)
        login = client.post(
            "/auth/login",
            json={"email": "alex@example.com", "password": "password12"},
            headers=_headers(token),
        )
        assert login.status_code == 200
        assert login.json()["user"]["preferred_language"] == "sr"


def test_favorites_merge_and_saved_articles():
    article = _article(slug="saved-story", external_id="https://example.com/saved-story")
    with TestClient(app) as client:
        token = _csrf(client)
        client.post(
            "/auth/register",
            json={"email": "favs@example.com", "password": "password12", "display_name": "Fav User"},
            headers=_headers(token),
        )
        token = _csrf(client)
        merged = client.put(
            "/auth/favorites",
            json={"sports": ["football", "tennis"], "leagues": ["nba"], "teams": []},
            headers=_headers(token),
        )
        assert merged.status_code == 200
        again = client.put(
            "/auth/favorites",
            json={"sports": ["football", "basketball"], "leagues": [], "teams": []},
            headers=_headers(token),
        )
        body = again.json()
        assert body["sports"] == ["basketball", "football", "tennis"]
        saved = client.put(f"/auth/saved/{article.id}", headers=_headers(token))
        assert saved.status_code == 200
        listed = client.get("/auth/saved").json()
        assert any(row["slug"] == "saved-story" for row in listed)
        assert all("source_url" not in row for row in listed)
        removed = client.delete(f"/auth/saved/{article.id}", headers=_headers(token))
        assert removed.json()["saved"] is False
        assert client.get("/auth/saved").json() == []


def test_comments_auth_xss_and_own_edit():
    article = _article(slug="comment-story", external_id="https://example.com/comment-story")
    assert "<script>" not in sanitize_comment("<script>alert(1)</script>hello")
    with TestClient(app) as client:
        listed = client.get("/articles/comment-story/comments")
        assert listed.status_code == 200
        assert listed.json()["comments"] == []
        blocked = client.post(
            "/articles/comment-story/comments",
            json={"body": "Nice finish from Chelsea."},
        )
        assert blocked.status_code == 401
        token = _csrf(client)
        client.post(
            "/auth/register",
            json={"email": "c1@example.com", "password": "password12", "display_name": "Comment One"},
            headers=_headers(token),
        )
        token = _csrf(client)
        created = client.post(
            "/articles/comment-story/comments",
            json={"body": "<script>alert(1)</script>Great finish by Chelsea."},
            headers=_headers(token),
        )
        assert created.status_code == 200
        assert "<script>" not in created.json()["body"]
        comment_id = created.json()["id"]
        reply = client.post(
            "/articles/comment-story/comments",
            json={"body": "Agreed, that late goal changed it.", "parent_id": comment_id},
            headers=_headers(token),
        )
        assert reply.status_code == 200
        client.post("/auth/logout")
        token = _csrf(client)
        client.post(
            "/auth/register",
            json={"email": "c2@example.com", "password": "password12", "display_name": "Comment Two"},
            headers=_headers(token),
        )
        token = _csrf(client)
        forbidden = client.patch(
            f"/comments/{comment_id}",
            json={"body": "I should not be able to edit this."},
            headers=_headers(token),
        )
        assert forbidden.status_code == 403
        deleted = client.delete(f"/comments/{comment_id}", headers=_headers(token))
        assert deleted.status_code == 403
        public = client.get("/articles/comment-story/comments").json()
        assert public["count"] >= 1
        assert any("Great finish" in row["body"] for row in public["comments"])
        assert all("<script>" not in (row["body"] or "") for row in public["comments"])
        like = client.post(f"/comments/{comment_id}/like", headers=_headers(token))
        assert like.status_code == 200
        report = client.post(
            f"/comments/{comment_id}/report",
            json={"reason": "spam", "detail": "Repeated praise"},
            headers=_headers(token),
        )
        assert report.status_code == 200
    assert article.slug == "comment-story"


def test_login_rate_limit():
    from auth import _rate_hits

    _rate_hits.clear()
    with TestClient(app) as client:
        token = _csrf(client)
        client.post(
            "/auth/register",
            json={"email": "limit@example.com", "password": "password12", "display_name": "Limit User"},
            headers=_headers(token),
        )
        client.post("/auth/logout")
        statuses = []
        for _ in range(13):
            token = _csrf(client)
            res = client.post(
                "/auth/login",
                json={"email": "limit@example.com", "password": "wrong-password"},
                headers=_headers(token),
            )
            statuses.append(res.status_code)
        assert 429 in statuses


def test_scheduler_architecture_unchanged():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1].joinpath("bot", "scheduler.py").read_text(encoding="utf-8")
    assert "BlockingScheduler" in source
    assert "max_instances=1" in source
    assert "fetch_and_store_all_articles" in source
    assert "never mass-rewrite historical articles" in source
