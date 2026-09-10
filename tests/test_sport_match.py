from datetime import datetime

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from models import Article, ArticleTranslation, Base
from sport_match import belongs_to_sport


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


LONG = (
    "The contest stayed open until the closing minutes as both sides looked for a decisive moment. "
    "Coaches later talked about concentration, the value of taking chances, and how the crowd lifted the players. "
    "It was a reminder that the season is still wide open and that every fixture can change the table."
)


class _Row:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.summary = kwargs.get("summary", "")
        self.league = kwargs.get("league")
        self.sport = kwargs.get("sport")


def test_football_story_rejected_from_motorsport():
    row = _Row(
        title="Arsenal and Liverpool prepare for a huge Premier League meeting",
        summary="The Premier League leaders meet at the Emirates.",
        league="england-premier-league",
        sport="motorsport",
    )
    assert belongs_to_sport(row, "motorsport") is False
    assert belongs_to_sport(row, "football") is True


def test_tennis_story_rejected_from_football():
    row = _Row(
        title="ATP and WTA stars arrive for the US Open",
        summary="The Grand Slam begins in New York.",
        league="us-open",
        sport="football",
    )
    assert belongs_to_sport(row, "football") is False
    assert belongs_to_sport(row, "tennis") is True


def test_formula_one_rejected_from_tennis():
    row = _Row(
        title="Formula 1 drivers prepare for the next Grand Prix",
        summary="Qualifying sets the grid for Sunday.",
        league="formula-1",
        sport="tennis",
    )
    assert belongs_to_sport(row, "tennis") is False
    assert belongs_to_sport(row, "motorsport") is True


def test_football_tagged_formula_one_rejected_from_motorsport():
    row = _Row(
        title="Who has your Premiership club brought in this summer",
        summary="Edu leaves Nottingham Forest after a turbulent spell.",
        league="formula-1",
        sport="motorsport",
    )
    assert belongs_to_sport(row, "motorsport", strict=True) is False


def test_haaland_city_story_rejected_from_tennis():
    row = _Row(
        title="Haaland iguala o melhor marcador da história do Manchester City na Liga dos Campeões",
        summary="",
        league="us-open",
        sport="tennis",
    )
    assert belongs_to_sport(row, "tennis", strict=True) is False
    row = _Row(
        title="Lakers and 76ers meet in a heavy NBA night",
        summary="The Eastern Conference remains tight.",
        league="nba",
        sport="football",
    )
    assert belongs_to_sport(row, "football") is False
    assert belongs_to_sport(row, "basketball") is True


def _make(**kwargs):
    db = SessionLocal()
    try:
        article = Article(
            external_id=kwargs.get("external_id", "https://example.com/" + kwargs.get("slug", "a")),
            title=kwargs.get("title", "Test article title"),
            slug=kwargs.get("slug", "test-article"),
            sport=kwargs.get("sport", "football"),
            league=kwargs.get("league", "england-premier-league"),
            country=kwargs.get("country", "england"),
            summary=kwargs.get("summary", "Summary about the match."),
            content=kwargs.get("content", LONG),
            image_url=kwargs.get("image_url", "https://example.com/img.jpg"),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            published_at=kwargs.get("published_at", datetime.utcnow()),
            source_url="https://example.com/hidden-source",
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article
    finally:
        db.close()


def test_sport_pages_isolate_mismatches():
    _make(
        slug="pl-on-motorsport",
        title="Arsenal beat Liverpool in the Premier League",
        sport="motorsport",
        league="england-premier-league",
        external_id="https://example.com/pl-on-motorsport",
    )
    _make(
        slug="open-on-football",
        title="ATP and WTA stars arrive for the US Open",
        sport="football",
        league="us-open",
        country="usa",
        external_id="https://example.com/open-on-football",
    )
    _make(
        slug="f1-on-tennis",
        title="Formula 1 drivers prepare for the next Grand Prix",
        sport="tennis",
        league="formula-1",
        country="international",
        external_id="https://example.com/f1-on-tennis",
    )
    _make(
        slug="nba-on-football",
        title="Lakers and 76ers meet in a heavy NBA night",
        sport="football",
        league="nba",
        country="usa",
        external_id="https://example.com/nba-on-football",
    )
    _make(
        slug="clean-football",
        title="Chelsea hold Manchester City in the Premier League",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/clean-football",
    )
    with TestClient(app) as client:
        motorsport = client.get("/articles/by-sport/motorsport").json()
        football = client.get("/articles/by-sport/football").json()
        tennis = client.get("/articles/by-sport/tennis").json()
        basketball = client.get("/articles/by-sport/basketball").json()
        assert all(row["slug"] != "pl-on-motorsport" for row in motorsport)
        assert all(row["slug"] != "open-on-football" for row in football)
        assert all(row["slug"] != "nba-on-football" for row in football)
        assert any(row["slug"] == "clean-football" for row in football)
        assert all(row["slug"] != "f1-on-tennis" for row in tennis)
        assert all(row["slug"] != "nba-on-football" for row in basketball)
        search = client.get("/search?q=Arsenal").json()
        assert any(row["slug"] == "pl-on-motorsport" for row in search)
        for row in football + motorsport:
            assert "source_url" not in row


def test_translation_cache_is_missing_until_ready():
    article = _make(
        slug="translate-me",
        title="Chelsea hold Manchester City in the Premier League",
        external_id="https://example.com/translate-me",
    )
    db = SessionLocal()
    try:
        db.add(
            ArticleTranslation(
                article_id=article.id,
                language_code="sr",
                status="missing",
                provider=None,
                model_name=None,
            )
        )
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        missing = client.get("/articles/translate-me/translation/sr").json()
        assert missing["available"] is False
        assert missing["status"] == "missing"
        english = client.get("/articles/translate-me").json()
        assert english["title"]
        assert "source_url" not in english
        assert english["presentation_type"] in {"brief", "standard", "major"}
