from datetime import datetime

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from models import Article, Base
from public_index import persist_public_article
from taxonomy_resolver import resolve_article_competition


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


LONG = (
    "The contest stayed open until the closing minutes as both sides looked for a decisive moment. "
    "Coaches later talked about concentration, the value of taking chances, and how the crowd lifted the players. "
)


def _csrf(client: TestClient) -> str:
    return client.get("/auth/csrf").json()["csrf"]


def test_golf_resolves_to_directory_sport_not_tennis():
    class Row:
        title = "Scottie Scheffler cards a birdie binge on the PGA Tour"
        summary = "A late birdie on the fairway sealed the PGA Tour win."
        content = "Scheffler made birdie after birdie on the back nine of the PGA Tour event."
        ai_content = None
        sport = "tennis"
        league = "us-open"

    resolved = resolve_article_competition(Row())
    assert resolved.sport == "golf"
    assert resolved.sport != "tennis"


def test_taxonomy_meta_exposes_directory_sports():
    with TestClient(app) as client:
        payload = client.get("/meta/taxonomy").json()
        slugs = {row["sport"] for row in payload["sports"]}
        assert "football" in slugs
        assert "golf" in slugs
        assert "american-football" in slugs
        assert any(row["group"] == "other" for row in payload["sports"])


def test_favorites_replace_allows_unfollow():
    with TestClient(app) as client:
        token = _csrf(client)
        client.post(
            "/auth/register",
            json={"email": "unfollow@example.com", "password": "password12", "display_name": "Unfollow"},
            headers={"X-CSRF-Token": token},
        )
        token = _csrf(client)
        added = client.put(
            "/auth/favorites",
            json={"sports": ["football", "tennis", "basketball"], "leagues": ["nba"], "teams": []},
            headers={"X-CSRF-Token": token},
        )
        assert added.status_code == 200
        assert set(added.json()["sports"]) == {"basketball", "football", "tennis"}
        removed = client.put(
            "/auth/favorites",
            json={"sports": ["football", "basketball"], "leagues": [], "teams": []},
            headers={"X-CSRF-Token": token},
        )
        body = removed.json()
        assert body["sports"] == ["basketball", "football"]
        assert "tennis" not in body["sports"]
        assert body["leagues"] == []
        persisted = client.get("/auth/favorites").json()
        assert persisted["sports"] == ["basketball", "football"]
        emptied = client.put(
            "/auth/favorites",
            json={"sports": [], "leagues": [], "teams": []},
            headers={"X-CSRF-Token": token},
        )
        assert emptied.json()["sports"] == []
