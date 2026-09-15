from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from editorial import evaluate_quality, sanitize_body
from entities import extract_entities
from models import Article, Base
from related import related_score
from public_index import persist_public_article
from taxonomy_resolver import resolve_article_competition


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


LONG = (
    "The contest stayed open until the closing minutes as both sides looked for a decisive moment. "
    "Coaches later talked about concentration, the value of taking chances, and how the crowd lifted the players. "
    "It was a reminder that the season is still wide open and that every fixture can change the table. "
    "Supporters filled the stands and the night finished with a clear result that will shape the coming weeks. "
    "Players spoke about belief, recovery, and the next assignment on a crowded calendar."
)

TRAILING_CHROME = (
    LONG
    + "\n\nRequired fields are marked *\n\n"
    + "Notify me of follow-up comments by email.\n\n"
    + "Leave a Reply\n\nName *\n\nEmail *\n\nWebsite\n\nPost comment\n\n"
    + "Subscribe to our newsletter for the latest Italian football news."
)


def _make(**kwargs):
    db = SessionLocal()
    try:
        now = kwargs.get("published_at", datetime.utcnow())
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
            created_at=kwargs.get("created_at", now),
            published_at=now,
            source_url="https://example.com/hidden-source",
            view_count=kwargs.get("view_count", 0),
            is_breaking=kwargs.get("is_breaking", False),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        persist_public_article(db, article, commit=True)
        db.refresh(article)
        return article
    finally:
        db.close()


def test_phase41_taxonomy_regression_still_holds():
    ucl = type("R", (), {})()
    ucl.title = "Champions League Liveblog: Napoli vs Arsenal"
    ucl.summary = ""
    ucl.content = LONG
    ucl.ai_content = None
    ucl.league = "england-premier-league"
    ucl.sport = "football"
    assert resolve_article_competition(ucl).public_competition == "uefa-champions-league"
    for stored in ("germany-bundesliga", "fifa-world-cup"):
        ucl.league = stored
        assert resolve_article_competition(ucl).public_competition == "uefa-champions-league"
    serie = type("R", (), {})()
    serie.title = "Napoli vs Bologna — Serie A probable line-ups"
    serie.summary = ""
    serie.content = LONG
    serie.ai_content = None
    serie.league = "england-premier-league"
    serie.sport = "football"
    assert resolve_article_competition(serie).public_competition == "italy-serie-a"
    nba = type("R", (), {})()
    nba.title = "Lakers and 76ers meet in a heavy NBA night"
    nba.summary = ""
    nba.content = LONG
    nba.ai_content = None
    nba.league = "euroleague"
    nba.sport = "basketball"
    assert resolve_article_competition(nba).public_competition == "nba"


def test_trailing_chrome_is_cut_and_legitimate_paragraphs_remain():
    cleaned = sanitize_body(TRAILING_CHROME, title="Tottenham still searching for a first goal")
    assert "Required fields are marked" not in cleaned
    assert "Notify me of follow-up comments" not in cleaned
    assert "Post comment" not in cleaned
    assert "latest Italian football news" not in cleaned.lower()
    assert "decisive moment" in cleaned
    quality = evaluate_quality(
        title="De Zerbi under pressure: Tottenham still without a Premier League goal after 4 games",
        summary="Tottenham are still searching for a first Premier League goal.",
        body=TRAILING_CHROME,
        image_url="https://example.com/spurs.jpg",
    )
    assert quality["ok"] is True


def test_website_sentence_is_not_stripped():
    body = (
        LONG
        + " The club later confirmed the squad list on its official website after the match."
    )
    cleaned = sanitize_body(body, title="Tottenham name a strong squad")
    assert "official website" in cleaned


def test_homepage_dedupes_hero_from_latest_and_keeps_quality():
    now = datetime.utcnow()
    hero = _make(
        slug="p42-hero-zenga",
        title="Zenga: Juventus don’t have a striker worth 15 Serie A goals per season",
        league="italy-serie-a",
        published_at=now,
        external_id="https://example.com/p42-hero-zenga",
        view_count=40,
    )
    _make(
        slug="p42-pl-spurs",
        title="De Zerbi under pressure: Tottenham still without a Premier League goal after 4 games",
        league="england-premier-league",
        published_at=now - timedelta(minutes=3),
        external_id="https://example.com/p42-pl-spurs",
        view_count=12,
    )
    _make(
        slug="p42-nba",
        title="Lakers and 76ers meet in a heavy NBA night",
        sport="basketball",
        league="nba",
        country="usa",
        published_at=now - timedelta(minutes=4),
        external_id="https://example.com/p42-nba",
        view_count=9,
    )
    _make(
        slug="p42-ucl",
        title="Champions League Liveblog: Napoli vs Arsenal",
        league="england-premier-league",
        published_at=now - timedelta(minutes=5),
        external_id="https://example.com/p42-ucl",
        view_count=3,
    )
    with TestClient(app) as client:
        home = client.get("/portal/home?featured_limit=5&latest_limit=8").json()
        featured_ids = [row["id"] for row in home["featured"]]
        latest_ids = [row["id"] for row in home["latest"]]
        assert hero.id in featured_ids or hero.slug in [row["slug"] for row in home["featured"] + home["latest"]]
        if featured_ids:
            assert featured_ids[0] not in latest_ids
        assert len(set(featured_ids) & set(latest_ids)) == 0
        assert "source_url" not in str(home)
        assert "score" not in home["featured"][0]
        sports = {row["sport"] for row in home["featured"]}
        if len(home["featured"]) >= 3:
            assert "basketball" in sports or any(row["league"] == "uefa-champions-league" for row in home["featured"])
        most_read = home["most_read"]
        assert all(row.get("id") for row in most_read)
        if most_read and featured_ids:
            if len(most_read) > 0 and any(row["id"] != featured_ids[0] for row in most_read):
                assert featured_ids[0] not in [row["id"] for row in most_read] or len(most_read) == 1


def test_homepage_does_not_fill_with_one_club_when_alternatives_exist():
    now = datetime.utcnow()
    for idx in range(5):
        _make(
            slug=f"p42-juve-{idx}",
            title=f"Juventus latest Serie A update number {idx} from Turin",
            league="italy-serie-a",
            published_at=now - timedelta(minutes=idx),
            external_id=f"https://example.com/p42-juve-{idx}",
        )
    _make(
        slug="p42-div-spurs",
        title="Tottenham still searching for a Premier League spark under De Zerbi",
        league="england-premier-league",
        published_at=now - timedelta(minutes=1),
        external_id="https://example.com/p42-div-spurs",
    )
    _make(
        slug="p42-div-nba",
        title="Knicks sign a veteran guard before the NBA opener",
        sport="basketball",
        league="nba",
        country="usa",
        published_at=now - timedelta(minutes=2),
        external_id="https://example.com/p42-div-nba",
    )
    with TestClient(app) as client:
        home = client.get("/portal/home?featured_limit=5").json()
        featured = home["featured"]
        juve = [row for row in featured if "Juventus" in row["title"]]
        assert len(juve) <= 2
        leagues = {row.get("league") for row in featured}
        sports = {row.get("sport") for row in featured}
        assert len(leagues) >= 2 or "basketball" in sports


def test_most_read_is_truthful_and_hidden_when_empty():
    with TestClient(app) as client:
        payload = client.get("/articles/most-read").json()
        for row in payload:
            assert "source_url" not in row
        home = client.get("/portal/home").json()
        for row in home["most_read"]:
            assert row["id"]


def test_related_prefers_team_and_competition_over_same_sport_only():
    now = datetime.utcnow()
    source = _make(
        slug="p42-rel-spurs",
        title="De Zerbi under pressure: Tottenham still without a Premier League goal after 4 games",
        league="england-premier-league",
        published_at=now,
        external_id="https://example.com/p42-rel-spurs",
    )
    tottenham = _make(
        slug="p42-rel-spurs-two",
        title="Tottenham look for a first Premier League goal at home",
        league="england-premier-league",
        published_at=now - timedelta(hours=1),
        external_id="https://example.com/p42-rel-spurs-two",
    )
    juve = _make(
        slug="p42-rel-juve",
        title="Zenga: Juventus don’t have a striker worth 15 Serie A goals per season",
        league="italy-serie-a",
        published_at=now - timedelta(minutes=10),
        external_id="https://example.com/p42-rel-juve",
    )
    tennis = _make(
        slug="p42-rel-tennis",
        title="Alcaraz prepares for the US Open quarter-finals",
        sport="tennis",
        league="us-open",
        country="usa",
        published_at=now - timedelta(minutes=5),
        external_id="https://example.com/p42-rel-tennis",
    )
    src_res = resolve_article_competition(source)
    tot_res = resolve_article_competition(tottenham)
    juve_res = resolve_article_competition(juve)
    assert related_score(source, src_res, tottenham, tot_res) > related_score(
        source, src_res, juve, juve_res
    )
    with TestClient(app) as client:
        related = client.get("/articles/p42-rel-spurs/related").json()
        slugs = [row["slug"] for row in related]
        assert "p42-rel-tennis" not in slugs
        assert all(row["sport"] == "football" for row in related)
        assert any("Tottenham" in row["title"] or "De Zerbi" in row["title"] for row in related)
        juve_idx = next((i for i, slug in enumerate(slugs) if slug == "p42-rel-juve"), None)
        tot_idx = next((i for i, slug in enumerate(slugs) if "spurs" in slug and slug != "p42-rel-spurs"), 0)
        if juve_idx is not None:
            assert tot_idx < juve_idx
        body = client.get("/articles/p42-rel-spurs").json()
        assert "source_url" not in body
        for neighbor in (body.get("previous"), body.get("next")):
            if neighbor:
                other = client.get(f"/articles/{neighbor['slug']}").json()
                assert other["sport"] == "football"


def test_previous_next_prefers_same_competition_then_sport():
    older = datetime.utcnow() - timedelta(hours=3)
    _make(
        slug="p42-nav-pl-old",
        title="Liverpool hold Chelsea in the Premier League",
        league="england-premier-league",
        published_at=older,
        created_at=older,
        external_id="https://example.com/p42-nav-pl-old",
    )
    _make(
        slug="p42-nav-serie",
        title="Sassuolo vs Juventus in Serie A",
        league="italy-serie-a",
        published_at=older + timedelta(hours=1),
        created_at=older + timedelta(hours=1),
        external_id="https://example.com/p42-nav-serie",
    )
    _make(
        slug="p42-nav-pl-new",
        title="De Zerbi under pressure: Tottenham still without a Premier League goal after 4 games",
        league="england-premier-league",
        published_at=older + timedelta(hours=2),
        created_at=older + timedelta(hours=2),
        external_id="https://example.com/p42-nav-pl-new",
    )
    with TestClient(app) as client:
        body = client.get("/articles/p42-nav-pl-new").json()
        prev_slug = (body.get("previous") or {}).get("slug")
        assert prev_slug
        assert prev_slug != "p42-nav-serie"
        prev = client.get(f"/articles/{prev_slug}").json()
        assert prev["sport"] == "football"
        assert prev.get("league") == "england-premier-league"
        nxt = client.get("/articles/p42-nav-pl-old").json()
        nxt_slug = (nxt.get("next") or {}).get("slug")
        if nxt_slug:
            nxt_body = client.get(f"/articles/{nxt_slug}").json()
            assert nxt_body["sport"] == "football"
            assert nxt_body.get("league") != "italy-serie-a"


def test_entities_tottenham_not_juventus():
    spurs = extract_entities("De Zerbi under pressure: Tottenham still without a Premier League goal after 4 games")
    juve = extract_entities("Zenga: Juventus don’t have a striker worth 15 Serie A goals per season")
    assert "tottenham" in spurs.teams
    assert "juventus" not in spurs.teams
    assert "juventus" in juve.teams
    assert "tottenham" not in juve.teams


def test_sport_sections_do_not_leak_football_into_tennis():
    _make(
        slug="p42-iso-fb",
        title="Liverpool hold Chelsea in the Premier League",
        league="england-premier-league",
        external_id="https://example.com/p42-iso-fb",
    )
    with TestClient(app) as client:
        home = client.get("/portal/home").json()
        tennis = home.get("by_sport", {}).get("tennis") or []
        motorsport = home.get("by_sport", {}).get("motorsport") or []
        assert all("Liverpool" not in row["title"] for row in tennis)
        assert all("Liverpool" not in row["title"] for row in motorsport)
        football = client.get("/articles/by-sport/tennis").json()
        assert all(row["sport"] == "tennis" for row in football)


def test_editorial_score_accepts_date_only_published_at():
    from datetime import date

    from homepage_compose import editorial_score

    article = type("A", (), {})()
    article.published_at = date(2026, 9, 14)
    article.created_at = date(2026, 9, 13)
    article.image_url = "https://example.com/x.jpg"
    article.is_breaking = False
    article.view_count = 4
    resolution = type("R", (), {})()
    resolution.sport = "football"
    resolution.public_competition = "england-premier-league"
    resolution.sport_confidence = 0.9
    resolution.competition_confidence = 0.8
    ranked = editorial_score(
        article,
        resolution,
        {"word_count": 80, "ok": True},
        extract_entities("Liverpool hold Chelsea in the Premier League"),
    )
    assert ranked.score > 0
