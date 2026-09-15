from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from bot.classify import classify_article
from database import SessionLocal, engine, ensure_schema
from editorial import classify_media_url, sanitize_body, suitable_for_lead_hero, to_blocks
from models import Article, Base
from public_index import persist_public_article
from sport_match import belongs_to_sport
from taxonomy_audit import audit_article_sample
from taxonomy_resolver import MIN_SPORT_CONFIDENCE, resolve_article_competition


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


BASKETBALL_BODY = (
    "The visiting side closed the fourth quarter with a 12-4 run. "
    "Their starting shooting guard finished with 18 points, seven rebounds and five assists, "
    "while the EuroLeague and Liga ACB calendar now turns toward the next tip-off. "
    "Coaches talked about shot selection, the paint, and how the box score reflected a complete team win. "
    "It was a reminder that basketball nights like this still decide domestic titles."
)

FOOTBALL_BODY = (
    "The home side scored twice before half-time and the goalkeeper kept a clean sheet. "
    "A late substitution in midfield protected the lead as the Premier League table tightened. "
    "Supporters filled the stands and the night finished with a clear result that will shape the coming weeks. "
    "Players spoke about belief, recovery, and the next assignment on a crowded calendar."
)

LONG = FOOTBALL_BODY


class _Row:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.summary = kwargs.get("summary", "")
        self.content = kwargs.get("content", "")
        self.ai_content = kwargs.get("ai_content")
        self.league = kwargs.get("league")
        self.sport = kwargs.get("sport")
        self.image_url = kwargs.get("image_url")


def test_multisport_club_basketball_overrides_stored_football():
    row = _Row(
        title="Real Madrid hold off Valencia in a tense Liga ACB night",
        summary="The hosts needed a late three-pointer after a box-score battle in Madrid.",
        content=BASKETBALL_BODY,
        sport="football",
        league="spain-la-liga",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "basketball"
    assert resolved.sport_confidence >= MIN_SPORT_CONFIDENCE
    assert resolved.public_competition in {"liga-acb", "euroleague"}
    assert belongs_to_sport(row, "football", strict=True) is False
    assert belongs_to_sport(row, "basketball", strict=True) is True


def test_ambiguous_club_without_sport_evidence_stays_unknown():
    row = _Row(
        title="Barcelona hold a private session ahead of a busy week",
        summary="Players reported for treatment and recovery work.",
        content="Staff said the group looked sharp in a closed session before travelling.",
        sport="football",
        league="spain-la-liga",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport is None
    assert belongs_to_sport(row, "football", strict=True) is False


def test_qualifying_offer_is_basketball_not_motorsport():
    row = _Row(
        title="Pistons forward can sign the one-year qualifying offer",
        summary="The NBA side must decide before training camp.",
        content="The qualifying offer would keep him on the roster through summer workouts.",
        sport="motorsport",
        league="formula-1",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "basketball"
    assert resolved.public_competition == "nba"
    assert belongs_to_sport(row, "motorsport", strict=True) is False


def test_qualifying_lap_is_motorsport():
    row = _Row(
        title="Verstappen sets the pace in a wet qualifying session",
        summary="The Formula 1 grid will be decided on Saturday.",
        content="A clean qualifying lap put him on pole position before the Grand Prix.",
        sport="football",
        league="england-premier-league",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "motorsport"
    assert resolved.public_competition == "formula-1"


def test_us_open_golf_is_not_tennis():
    row = _Row(
        title="Low round holds the lead at the US Open",
        summary="A late birdie on the 18th fairway changed the PGA leaderboard.",
        content="He saved par from a greenside bunker and talked about the Oakmont greens.",
        sport="tennis",
        league="us-open",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport != "tennis"
    assert belongs_to_sport(row, "tennis", strict=True) is False


def test_us_open_tennis_stays_tennis():
    row = _Row(
        title="Alcaraz reaches another US Open semi-final",
        summary="The ATP star won in four sets at Flushing Meadows.",
        content="A break point in the fourth set decided a Grand Slam classic under the lights.",
        sport="football",
        league="england-premier-league",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "tennis"
    assert resolved.public_competition == "us-open"


def test_nba_mention_inside_euroleague_context():
    row = _Row(
        title="EuroLeague has expansion plans regardless of NBA",
        summary="Shareholders discussed the basketball calendar in Barcelona.",
        content=BASKETBALL_BODY,
        sport="basketball",
        league="nba",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "basketball"
    assert resolved.public_competition == "euroleague"


def test_champions_league_wrong_stored_league():
    row = _Row(
        title="UCL | Perfect Champions League debut for the hosts",
        summary="The UEFA Champions League night ended 4-1 in front of a packed stadium.",
        content=FOOTBALL_BODY + " The Champions League table now looks very different.",
        sport="football",
        league="italy-serie-a",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "football"
    assert resolved.public_competition == "uefa-champions-league"


def test_tottenham_story_resolves_premier_league():
    row = _Row(
        title="Tottenham manager sets out Premier League plan",
        summary="The new Tottenham head coach spoke after training in north London.",
        content=FOOTBALL_BODY,
        sport="basketball",
        league="nba",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "football"
    assert resolved.public_competition == "england-premier-league"


def test_crest_url_is_not_lead_hero():
    crest = "https://cdn.example.com/clubs/team-logo.png"
    photo = "https://cdn.example.com/photos/match-night.jpg"
    assert classify_media_url(crest) == "CREST_OR_LOGO"
    assert suitable_for_lead_hero(crest) is False
    assert classify_media_url(photo) == "EDITORIAL_PHOTO"
    assert suitable_for_lead_hero(photo) is True
    assert classify_media_url(None) == "MISSING"


def test_sanitizer_strips_category_and_duplicate_openers():
    title = "Hosts complete a stunning European debut"
    body = (
        "Basketball\n\n"
        "Domestic Leagues "
        f"{title} "
        "The visiting side could not recover after half-time and the hosts closed the night "
        "with a complete team performance in front of a loud home crowd. "
        "Coaches later talked about concentration and how the next assignment already looms.\n\n"
        "Required fields are marked *\n"
        "Notify me of follow-up comments by email."
    )
    cleaned = sanitize_body(body, title=title)
    assert "required fields" not in cleaned.lower()
    assert "domestic leagues" not in cleaned.lower()
    assert cleaned.lower().count(title.lower()) <= 1
    assert classify_media_url("https://cdn.example.com/uploads/2026/01/valencia-696x464.webp") == "CREST_OR_LOGO"
    assert classify_media_url("https://cdn.example.com/photos/getty-match-night-1600x900.jpg") == "EDITORIAL_PHOTO"
    blocks = to_blocks(body, title=title)
    assert blocks
    assert all("required fields" not in (block.get("text") or "").lower() for block in blocks)


def test_ingest_uses_same_evidence_for_ambiguous_clubs():
    result = classify_article(
        "Real Madrid basketball beat Valencia in Liga ACB",
        BASKETBALL_BODY,
        feed_kind="mixed",
        feed_sport="football",
        feed_league="spain-la-liga",
    )
    assert result.sport == "basketball"
    silent = classify_article(
        "Barcelona hold a private session ahead of a busy week",
        "Staff said the group looked sharp in a closed session before travelling.",
        feed_kind="mixed",
        feed_sport="football",
        feed_league="spain-la-liga",
    )
    assert silent.sport != "basketball"


def test_acceptance_fixtures_are_not_special_cased_in_production():
    root = Path(__file__).resolve().parents[1]
    forbidden = (
        "Barcelona claims Catalan crown",
        "Dario Brizuela",
        "Como 4-1 RB Leipzig",
        "Dillon Jones",
    )
    skipped = {"tests", ".git", "__pycache__", "venv", ".venv"}
    for path in root.rglob("*.py"):
        if any(part in skipped for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path} contains fixture hardcoding"


# Fixture titles belong only in tests. They prove the general resolver.
def test_regression_fixtures_follow_general_rules():
    basketball = _Row(
        title="Barcelona claims Catalan crown, loses Dario Brizuela injured",
        summary="The shooting guard left an ACB basketball night with an injury concern.",
        content=BASKETBALL_BODY,
        sport="football",
        league="spain-la-liga",
        image_url="https://cdn.example.com/clubs/crest-logo.png",
    )
    football = _Row(
        title="UCL | Como 4-1 RB Leipzig: Perfect Champions League debut",
        summary="The UEFA Champions League night ended in a convincing win.",
        content=FOOTBALL_BODY,
        sport="football",
        league="italy-serie-a",
    )
    premier = _Row(
        title="De Zerbi set for Tottenham talks as Premier League plan takes shape",
        summary="Tottenham are preparing a new Premier League direction.",
        content=FOOTBALL_BODY,
        sport="basketball",
        league="nba",
    )
    nba = _Row(
        title="76ers sign Dillon Jones after NBA camp",
        summary="The NBA roster move came after summer workouts.",
        content="The 76ers added the forward after NBA summer league and training camp.",
        sport="football",
        league="england-premier-league",
    )
    assert resolve_article_competition(basketball).sport == "basketball"
    assert classify_media_url(basketball.image_url) == "CREST_OR_LOGO"
    assert resolve_article_competition(football).public_competition == "uefa-champions-league"
    assert resolve_article_competition(premier).public_competition == "england-premier-league"
    resolved_nba = resolve_article_competition(nba)
    assert resolved_nba.sport == "basketball"
    assert resolved_nba.public_competition == "nba"


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
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        persist_public_article(db, article, commit=True)
        db.refresh(article)
        return article
    finally:
        db.close()


def test_sport_pages_use_resolved_taxonomy_not_stored_sport():
    _make(
        slug="acb-on-football",
        title="Real Madrid hold off Valencia in a tense Liga ACB night",
        summary="A late three-pointer decided the basketball game.",
        content=BASKETBALL_BODY,
        sport="football",
        league="spain-la-liga",
        external_id="https://example.com/acb-on-football",
    )
    _make(
        slug="ucl-on-serie",
        title="UCL | Perfect Champions League debut for the hosts",
        summary="The UEFA Champions League night ended 4-1.",
        content=FOOTBALL_BODY,
        sport="football",
        league="italy-serie-a",
        external_id="https://example.com/ucl-on-serie",
    )
    with TestClient(app) as client:
        football = client.get("/articles/by-sport/football").json()
        basketball = client.get("/articles/by-sport/basketball").json()
        ucl = client.get("/articles/by-league/uefa-champions-league").json()
        assert all(row["slug"] != "acb-on-football" for row in football)
        assert any(row["slug"] == "acb-on-football" for row in basketball)
        assert all(row.get("sport") == "basketball" for row in basketball)
        assert all(row.get("sport") == "football" for row in football)
        assert any(row["slug"] == "ucl-on-serie" for row in ucl)
        assert all(row.get("league") == "uefa-champions-league" for row in ucl)
        home = client.get("/portal/home").json()
        for bucket in home["featured"] + home["latest"]:
            if bucket.get("slug") == "acb-on-football":
                assert bucket["sport"] == "basketball"
        related = client.get("/articles/acb-on-football/related").json()
        assert all(row["sport"] == "basketball" for row in related)


def test_historical_sample_audit_counts():
    articles = []
    for idx in range(250):
        articles.append(
            _Row(
                title=f"Liverpool hold Chelsea in the Premier League {idx}",
                summary="A late goal decided a Premier League night.",
                content=FOOTBALL_BODY,
                sport="football",
                league="england-premier-league",
            )
        )
    for idx in range(120):
        articles.append(
            _Row(
                title=f"Lakers and 76ers meet in a heavy NBA night {idx}",
                summary="The Eastern Conference remains tight.",
                content="The NBA game went to the final possession with 28 points and 11 rebounds.",
                sport="football",
                league="nba",
            )
        )
    for idx in range(70):
        articles.append(
            _Row(
                title=f"Alcaraz reaches another US Open semi-final {idx}",
                summary="The ATP star won in four sets.",
                content="A break point in the fourth set decided a Grand Slam classic.",
                sport="tennis",
                league="us-open",
            )
        )
    for idx in range(60):
        articles.append(
            _Row(
                title=f"Verstappen sets the pace in a wet qualifying session {idx}",
                summary="The Formula 1 grid will be decided on Saturday.",
                content="A clean qualifying lap put him on pole position before the Grand Prix.",
                sport="motorsport",
                league="formula-1",
            )
        )
    counts = audit_article_sample(articles)
    assert counts["total_candidates"] == 500
    assert counts["resolved_football"] >= 250
    assert counts["resolved_basketball"] >= 120
    assert counts["resolved_tennis"] >= 70
    assert counts["resolved_motorsport"] >= 60
    assert counts["sport_disagreements"] >= 120
    assert counts["unknown"] == 0
