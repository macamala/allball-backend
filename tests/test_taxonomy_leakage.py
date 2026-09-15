from bot.classify import classify_article
from bot.taxonomy import compatible_competition
from editorial import classify_media_url, pick_article_image
from sport_match import belongs_to_sport
from taxonomy_resolver import resolve_article_competition


CHROME = (
    "Skip to content Home Football Tennis Basketball Formula 1. "
    "Related: Wimbledon latest, ATP Tour, Premier League live, NBA scores. "
    "More Tennis Wimbledon news from across the site."
)


class _Row:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.summary = kwargs.get("summary", "")
        self.content = kwargs.get("content", "")
        self.ai_content = kwargs.get("ai_content")
        self.league = kwargs.get("league")
        self.sport = kwargs.get("sport")


def test_wrong_tennis_feed_cannot_override_football_title_evidence():
    title = "Vardy joins Burnley & Wycombe sack Duff"
    row = _Row(
        title=title,
        summary=CHROME,
        content=CHROME + " The Championship club confirmed the appointment after the manager was sacked.",
        sport="tennis",
        league="wimbledon",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport != "tennis"
    assert resolved.public_competition != "wimbledon"
    assert not belongs_to_sport(row, "tennis", resolution=resolved)
    tags = classify_article(title, CHROME, feed_kind="league", feed_sport="tennis", feed_league="wimbledon")
    assert tags.sport != "tennis"
    assert tags.league != "wimbledon"


def test_football_article_from_tennis_feed_stays_football_or_unclassified():
    row = _Row(
        title="Liverpool hold Chelsea in the Premier League",
        summary=CHROME,
        content=CHROME,
        sport="tennis",
        league="wimbledon",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "football"
    assert resolved.public_competition == "england-premier-league"


def test_basketball_article_from_football_feed_keeps_nba():
    row = _Row(
        title="Lakers and 76ers meet in a heavy NBA night",
        summary="Related: Premier League and Champions League live.",
        content="Related Football Premier League. The Lakers hosted the 76ers.",
        sport="football",
        league="england-premier-league",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "basketball"
    assert resolved.public_competition == "nba"
    assert compatible_competition(resolved.sport, "england-premier-league") is None


def test_tennis_article_from_general_feed_still_resolves():
    row = _Row(
        title="Carlos Alcaraz wins Wimbledon quarter-final in four sets",
        summary="Alcaraz converted match point after a late break.",
        content="Alcaraz saved break point then closed out the tie-break.",
        sport=None,
        league=None,
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "tennis"
    assert resolved.public_competition == "wimbledon"


def test_incompatible_stored_sport_and_competition_are_discarded():
    row = _Row(
        title="Max Verstappen takes pole position in Formula 1 qualifying",
        summary="A clean qualifying lap put Verstappen on pole.",
        content="The Formula 1 session ended with a grid penalty debate.",
        sport="tennis",
        league="wimbledon",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "motorsport"
    assert resolved.public_competition == "formula-1"
    assert compatible_competition("motorsport", "wimbledon") is None
    assert compatible_competition("football", "nba") is None
    assert compatible_competition("tennis", "england-premier-league") is None


def test_ambiguous_entity_names_do_not_force_a_sport():
    row = _Row(
        title="Barcelona and Real Madrid prepare for a huge night",
        summary=CHROME,
        content=CHROME,
        sport="football",
        league="spain-la-liga",
    )
    resolved = resolve_article_competition(row)
    assert resolved.public_competition is None
    assert resolved.sport in {None, "football", "basketball"}


def test_stored_taxonomy_loses_to_strong_body_and_title_evidence():
    row = _Row(
        title="Arsenal train ahead of a Premier League fixture",
        summary="The Gunners return to Premier League action this weekend.",
        content="Mikel Arteta's Arsenal side worked on set pieces before the Premier League trip.",
        sport="tennis",
        league="wimbledon",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport == "football"
    assert resolved.public_competition != "wimbledon"


def test_chrome_only_body_does_not_place_article_on_a_sport_page():
    row = _Row(
        title="A busy night across Europe",
        summary=CHROME,
        content=CHROME,
        sport="tennis",
        league="wimbledon",
    )
    resolved = resolve_article_competition(row)
    assert resolved.sport is None
    assert resolved.public_competition is None
    assert not belongs_to_sport(row, "tennis", resolution=resolved)
    assert not belongs_to_sport(row, "football", resolution=resolved)


def test_promo_and_brand_graphics_are_rejected_as_heroes():
    promo = "https://ichef.bbci.co.uk/images/ic/1024xn/p0sounds-72plus-promo.jpg"
    bbc_rss_thumb = "https://ichef.bbci.co.uk/images/ic/240x135/p0p3n9ks.jpg"
    logo = "https://cdn.example.com/brand/site-logo.png"
    photo = "https://ichef.bbci.co.uk/ace/standard/976/cpsprodpb/live/match-photo.jpg"
    assert classify_media_url(promo) == "GRAPHIC"
    assert classify_media_url(bbc_rss_thumb) == "GRAPHIC"
    assert classify_media_url(logo) == "CREST_OR_LOGO"
    picked = pick_article_image(
        [
            {"url": promo, "source": "rss", "width": 1024},
            {"url": bbc_rss_thumb, "source": "rss", "width": 240, "height": 135},
            {"url": logo, "source": "og", "width": 400},
            {"url": photo, "source": "body", "width": 976, "in_article": True},
        ]
    )
    assert picked == photo
    assert pick_article_image([{"url": promo, "source": "og", "width": 1024}]) is None
    assert pick_article_image([{"url": bbc_rss_thumb, "source": "rss"}]) is None
    editorial_thumb = "https://ichef.bbci.co.uk/ace/standard/240/cpsprodpb/live/match-photo.jpg"
    assert classify_media_url(editorial_thumb) == "EDITORIAL_PHOTO"
