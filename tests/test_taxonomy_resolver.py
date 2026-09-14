from datetime import datetime

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from models import Article, Base
from taxonomy_resolver import resolve_article_competition


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


LONG = (
    "The contest stayed open until the closing minutes as both sides looked for a decisive moment. "
    "Coaches later talked about concentration, the value of taking chances, and how the crowd lifted the players. "
    "It was a reminder that the season is still wide open and that every fixture can change the table. "
    "Supporters filled the stands and the night finished with a clear result that will shape the coming weeks."
)


class _Row:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.summary = kwargs.get("summary", "")
        self.content = kwargs.get("content", "")
        self.ai_content = kwargs.get("ai_content")
        self.league = kwargs.get("league")
        self.sport = kwargs.get("sport")


def test_ucl_outranks_stored_premier_league():
    row = _Row(
        title="Champions League Liveblog: Napoli vs Arsenal",
        summary="",
        league="england-premier-league",
        sport="football",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "football"
    assert resolved.public_competition == "uefa-champions-league"


def test_ucl_outranks_bundesliga_and_world_cup_tags():
    for stored in ("germany-bundesliga", "fifa-world-cup", "england-premier-league"):
        row = _Row(
            title="Arsenal prepare for a huge UEFA Champions League night",
            league=stored,
            sport="football",
        )
        assert resolve_article_competition(row).public_competition == "uefa-champions-league"


def test_serie_a_explicit_outranks_stored_premier_league():
    row = _Row(
        title="Napoli vs Bologna — Serie A probable line-ups",
        league="england-premier-league",
        sport="football",
    )
    assert resolve_article_competition(row).public_competition == "italy-serie-a"
    row = _Row(
        title="Sassuolo vs Juventus in Serie A",
        league="england-premier-league",
        sport="football",
    )
    assert resolve_article_competition(row).public_competition == "italy-serie-a"


def test_team_only_does_not_imply_competition():
    arsenal = _Row(title="Arsenal train ahead of a busy week", sport="football", league="england-premier-league")
    juve = _Row(title="Juventus return to Turin after a long trip", sport="football", league="italy-serie-a")
    assert resolve_article_competition(arsenal).public_competition is None
    assert resolve_article_competition(juve).public_competition is None


def test_nba_and_euroleague_not_mixed():
    nba = _Row(title="Lakers and 76ers meet in a heavy NBA night", sport="basketball", league="euroleague")
    euro = _Row(
        title="EuroLeague has expansion plans regardless of NBA",
        sport="basketball",
        league="nba",
    )
    assert resolve_article_competition(nba).public_competition == "nba"
    assert resolve_article_competition(euro).public_competition == "euroleague"


def test_serie_a_title_ignores_champions_league_body_chrome():
    row = _Row(
        title="Serie A official line-ups: Napoli vs. Bologna",
        summary="Napoli host Bologna in Serie A.",
        content="Related: Champions League Liveblog Fenerbahce vs Roma and Como vs Leipzig. " + LONG,
        league="england-premier-league",
        sport="football",
    )
    assert resolve_article_competition(row).public_competition == "italy-serie-a"


def test_ambiguous_article_has_no_competition():
    row = _Row(title="A busy night across Europe", sport="football", league="england-premier-league")
    assert resolve_article_competition(row).public_competition is None


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


def test_competition_routes_use_resolved_not_stored_league():
    _make(
        slug="ucl-wrong-pl",
        title="Champions League Liveblog: Napoli vs Arsenal",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/ucl-wrong-pl",
    )
    _make(
        slug="serie-wrong-pl",
        title="Napoli vs Bologna — Serie A probable line-ups",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/serie-wrong-pl",
    )
    _make(
        slug="true-pl",
        title="Liverpool hold Chelsea in the Premier League",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/true-pl",
    )
    _make(
        slug="nba-wrong-euro",
        title="Lakers and 76ers meet in a heavy NBA night",
        sport="basketball",
        league="euroleague",
        country="usa",
        external_id="https://example.com/nba-wrong-euro",
    )
    _make(
        slug="euro-wrong-nba",
        title="EuroLeague shareholders face major decisions at summit",
        sport="basketball",
        league="nba",
        country="usa",
        external_id="https://example.com/euro-wrong-nba",
    )
    with TestClient(app) as client:
        ucl = client.get("/articles/by-league/uefa-champions-league").json()
        pl = client.get("/articles/by-league/premier-league").json()
        serie = client.get("/articles/by-league/serie-a").json()
        nba = client.get("/articles?sport=basketball&league=nba").json()
        euro = client.get("/articles/by-league/euroleague").json()
        assert any(row["slug"] == "ucl-wrong-pl" for row in ucl)
        assert all(row["slug"] != "ucl-wrong-pl" for row in pl)
        assert any(row["slug"] == "true-pl" for row in pl)
        assert any(row["slug"] == "serie-wrong-pl" for row in serie)
        assert all(row["slug"] != "serie-wrong-pl" for row in pl)
        assert any(row["slug"] == "nba-wrong-euro" for row in nba)
        assert all(row["slug"] != "nba-wrong-euro" for row in euro)
        assert any(row["slug"] == "euro-wrong-nba" for row in euro)
        assert all(row["slug"] != "euro-wrong-nba" for row in nba)
        for row in ucl:
            assert row.get("league") == "uefa-champions-league"
            assert "source_url" not in row


def test_related_and_neighbors_stay_in_sport():
    older = datetime.utcnow()
    bb_a = _make(
        slug="bb-one",
        title="76ers sign Dillon Jones after NBA camp",
        sport="basketball",
        league="nba",
        country="usa",
        created_at=older,
        published_at=older,
        external_id="https://example.com/bb-one",
    )
    _make(
        slug="fb-mid",
        title="Liverpool hold Chelsea in the Premier League",
        sport="football",
        league="england-premier-league",
        external_id="https://example.com/fb-mid",
    )
    _make(
        slug="bb-two",
        title="Lakers hire an assistant GM before the NBA season",
        sport="basketball",
        league="nba",
        country="usa",
        external_id="https://example.com/bb-two",
    )
    with TestClient(app) as client:
        body = client.get("/articles/bb-one").json()
        for neighbor in (body.get("previous"), body.get("next")):
            if neighbor:
                other = client.get(f"/articles/{neighbor['slug']}").json()
                assert other["sport"] == "basketball"
        related = client.get("/articles/bb-one/related").json()
        assert related
        assert all(row["sport"] == "basketball" for row in related)
        assert "source_url" not in body
        assert bb_a.slug == "bb-one"


def test_social_providers_are_off_without_credentials():
    with TestClient(app) as client:
        payload = client.get("/auth/providers").json()
        assert payload["password"] is True
        assert payload["google"] is False
        assert payload["facebook"] is False
        start = client.get("/auth/google/start")
        assert start.status_code == 503
