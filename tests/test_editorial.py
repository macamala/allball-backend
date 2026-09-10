from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import app
from database import SessionLocal, engine, ensure_schema
from editorial import (
    attach_inline_media,
    evaluate_quality,
    maybe_related_insert,
    public_media_items,
    sanitize_body,
    sanitize_title,
    to_blocks,
)
from models import Article, ArticleMedia, Base


def setup_module():
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)


ARSENAL_DIRTY = (
    "Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering "
    "--> Menu ESPN Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering "
    "play Moreno: Odegaard goals a 'necessity' for Arsenal (1:43) NAPLES, Italy -- "
    "This was about to turn into one of those nights when Arsenal fans hark back to the missed "
    "opportunities of the summer transfer window until Martin Ødegaard intervened. "
    "The Gunners had created and wasted a plethora of chances before some smart interplay "
    "on the edge of the box involving substitutes Bruno Guimaraes and Christos Tzolis. "
    "The 27-year-old fired the winning goal on 75 minutes as Arsenal took the three points. "
    "Unai Emery's side will now look ahead to the next Premier League fixture with confidence."
)


def test_strips_menu_espn_cdata_and_truncation():
    dirty = "<![CDATA[Villa won the match.]]> Menu ESPN more Villa news [+1234 chars]"
    cleaned = sanitize_body(dirty, title="Villa won the match")
    assert "Menu ESPN" not in cleaned
    assert "<![CDATA" not in cleaned
    assert "]]>" not in cleaned
    assert "[+" not in cleaned
    assert "Villa" in cleaned
    assert "[" not in sanitize_body("Jones joined the 76ers after two seasons. [...]")


def test_strips_duplicated_title_and_nav_garbage():
    title = "Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering"
    cleaned = sanitize_body(ARSENAL_DIRTY, title=title)
    assert "Menu ESPN" not in cleaned
    assert "play Moreno" not in cleaned
    assert cleaned.lower().count(title.lower()) <= 1
    assert "Ødegaard" in cleaned or "Odegaard" in cleaned or "winning goal" in cleaned


def test_sanitize_title_removes_cdata():
    title = "<![CDATA[Chaves perto de garantir internacional]]>"
    cleaned = sanitize_title(title)
    assert "CDATA" not in cleaned.upper()
    assert "Chaves" in cleaned


def test_quality_gate_blocks_contaminated_from_premium():
    quality = evaluate_quality(
        title="Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering",
        summary=ARSENAL_DIRTY,
        body=ARSENAL_DIRTY,
        image_url="https://example.com/photo.jpg",
    )
    assert quality["ok"] is False
    assert "navigation" in quality["flags"]


def test_quality_gate_blocks_foreign_language_from_premium():
    title = "Třetí komerční pauza v extralize. Moc mi to nesedí do úprav pravidel, říká eso Liberce"
    body = (
        "Extraligový hokej zavádí třetí komerční pauzu během jedné třetiny a fanoušci mezi sebou řeší, "
        "zda už to není příliš. A nejen oni, logicky i ti, jichž se to výrazně týká. Hráči. "
        "Další vnější zásah může zápasu sebrat přirozený spád, narušit tempo, prodloužit jeho trvání. "
        "Faktem je, že novinku si přály kluby a vedení soutěže požadavek odsouhlasilo."
    )
    quality = evaluate_quality(
        title=title,
        summary=body,
        body=body,
        image_url="https://example.com/hockey.jpg",
    )
    assert quality["ok"] is False
    assert "non_english" in quality["flags"]


def test_quality_gate_allows_clean_english_story():
    body = (
        "Aston Villa earned a late point against Arsenal in the Premier League. "
        "Unai Emery's side defended with discipline after the break and created "
        "enough chances to take something from the match. The result keeps both "
        "clubs in the mix as the season gathers pace in England."
    )
    quality = evaluate_quality(
        title="Aston Villa earn a point against Arsenal",
        summary="Villa hold Arsenal after a disciplined display.",
        body=body,
        image_url="https://example.com/villa.jpg",
    )
    assert quality["ok"] is True


def test_hero_quality_unusable_image_is_flagged():
    quality = evaluate_quality(
        title="Aston Villa earn a point against Arsenal",
        body="Aston Villa earned a late point against Arsenal in the Premier League. "
             "Unai Emery's side defended with discipline after the break and created "
             "enough chances to take something from the match. The result keeps both "
             "clubs in the mix as the season gathers pace in England.",
        image_url="",
    )
    assert "unusable_image" in quality["flags"]


def test_blocks_do_not_invent_headings_or_quotes():
    body = "Villa scored late. The visitors could not find an equalizer before the whistle."
    blocks = to_blocks(body, title="Villa scored late")
    types = {block["type"] for block in blocks}
    assert "heading" not in types
    assert "quote" not in types
    assert all(block["type"] == "paragraph" for block in blocks)


def test_image_url_backward_compatible_media():
    media = public_media_items("https://example.com/hero.jpg", media_rows=[])
    assert len(media) == 1
    assert media[0]["is_hero"] is True
    assert media[0]["url"] == "https://example.com/hero.jpg"
    assert "credit" not in media[0]


def test_article_media_ordering_hero_and_inline():
    class Row:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    rows = [
        Row(id=2, media_type="image", url="https://example.com/inline.jpg", caption="Second", sort_order=2, is_hero=False),
        Row(id=1, media_type="image", url="https://example.com/hero.jpg", caption="Hero", sort_order=0, is_hero=True),
    ]
    media = public_media_items("https://example.com/legacy.jpg", rows)
    assert media[0]["is_hero"] is True
    assert media[0]["url"].endswith("hero.jpg")
    blocks = attach_inline_media(
        [{"type": "paragraph", "text": "One."}, {"type": "paragraph", "text": "Two."}],
        media,
    )
    assert blocks[0]["type"] == "paragraph"
    assert any(block.get("type") == "media" and not block.get("is_hero") for block in blocks)
    assert sum(1 for block in blocks if block.get("type") == "media") == 1


def test_no_media_returns_empty():
    assert public_media_items("", []) == []


def test_related_insert_only_for_long_articles():
    short = [{"type": "paragraph", "text": "One."}, {"type": "paragraph", "text": "Two."}]
    long = [{"type": "paragraph", "text": f"Paragraph {i}."} for i in range(6)]
    related = {"slug": "other-story", "title": "Other story"}
    assert maybe_related_insert(short, related) == short
    inserted = maybe_related_insert(long, related)
    related_blocks = [block for block in inserted if block.get("type") == "related"]
    assert len(related_blocks) == 1
    assert related_blocks[0]["article"]["slug"] == "other-story"


CLEAN_BODY = (
    "Aston Villa earned a late point against Arsenal in the Premier League. "
    "Unai Emery's side defended with discipline after the break and created "
    "enough chances to take something from the match. The result keeps both "
    "clubs in the mix as the season gathers pace in England. Supporters left "
    "encouraged by the performance even if the finishing was wasteful at times."
)


def _make_article(**kwargs):
    db = SessionLocal()
    try:
        article = Article(
            external_id=kwargs.get("external_id", "https://example.com/" + kwargs["slug"]),
            title=kwargs.get("title", "Clean editorial story"),
            slug=kwargs["slug"],
            sport=kwargs.get("sport", "football"),
            league=kwargs.get("league", "england-premier-league"),
            country=kwargs.get("country", "england"),
            summary=kwargs.get("summary", "Villa hold Arsenal after a disciplined display."),
            content=kwargs.get("content", CLEAN_BODY),
            image_url=kwargs.get("image_url"),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            published_at=kwargs.get("published_at", datetime.utcnow()),
            source_url=kwargs.get("source_url", "https://example.com/hidden-source"),
        )
        db.add(article)
        db.commit()
        db.refresh(article)
        return article
    finally:
        db.close()


def test_public_article_strips_contamination_and_hides_source():
    title = "Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering"
    _make_article(
        slug="editorial-odegaard-dirty",
        title=title,
        content=ARSENAL_DIRTY + " <![CDATA[More text.]]> [+1234 chars]",
        image_url="https://example.com/odegaard.jpg",
        external_id="https://example.com/editorial-odegaard-dirty",
    )
    with TestClient(app) as client:
        res = client.get("/articles/editorial-odegaard-dirty")
        assert res.status_code == 200
        body = res.json()
        blob = " ".join(
            [
                body.get("title") or "",
                body.get("content") or "",
                " ".join(block.get("text") or "" for block in body.get("blocks") or []),
            ]
        )
        assert "source_url" not in body
        assert "https://example.com/hidden-source" not in str(body)
        assert "Menu ESPN" not in blob
        assert "<![CDATA" not in blob
        assert "[+" not in blob
        assert "winning goal" in blob or "Ødegaard" in blob or "Odegaard" in blob


def test_featured_excludes_contaminated_and_weak_hero():
    now = datetime.utcnow()
    _make_article(
        slug="editorial-featured-dirty",
        title="Who needs a forward? Arsenal might, but not while Ødegaard keeps delivering",
        content=ARSENAL_DIRTY,
        image_url="https://example.com/dirty.jpg",
        published_at=now,
        created_at=now,
        external_id="https://example.com/editorial-featured-dirty",
    )
    _make_article(
        slug="editorial-featured-clean",
        title="Aston Villa earn a point against Arsenal",
        content=CLEAN_BODY,
        image_url="https://example.com/villa-hero.jpg",
        published_at=now + timedelta(minutes=1),
        created_at=now + timedelta(minutes=1),
        external_id="https://example.com/editorial-featured-clean",
    )
    with TestClient(app) as client:
        featured = client.get("/articles/featured?limit=8").json()
        slugs = [row["slug"] for row in featured]
        assert "editorial-featured-dirty" not in slugs
        assert "editorial-featured-clean" in slugs
        home = client.get("/portal/home").json()
        featured_home = [row["slug"] for row in body_featured(home)]
        assert "editorial-featured-dirty" not in featured_home


def body_featured(home):
    return home.get("featured") or []


def test_article_media_ordering_and_image_url_compat():
    article = _make_article(
        slug="editorial-media-story",
        title="Aston Villa earn a point against Arsenal",
        content=CLEAN_BODY + "\n\n" + "\n\n".join(
            [
                "The visitors could not find a late equalizer despite late pressure.",
                "Emery rotated his midfield after the interval to keep the tempo high.",
                "Both sets of supporters recognized a contest that stayed tight until the whistle.",
                "The next fixture will test whether that defensive shape can travel.",
            ]
        ),
        image_url="https://example.com/legacy-hero.jpg",
        external_id="https://example.com/editorial-media-story",
    )
    db = SessionLocal()
    try:
        db.add_all(
            [
                ArticleMedia(
                    article_id=article.id,
                    media_type="image",
                    url="https://example.com/true-hero.jpg",
                    caption="Match night",
                    credit="INTERNAL CREDIT MUST STAY PRIVATE",
                    sort_order=0,
                    is_hero=True,
                    provider_media_id="prov-1",
                ),
                ArticleMedia(
                    article_id=article.id,
                    media_type="image",
                    url="https://example.com/inline-two.jpg",
                    caption="Second image",
                    credit="secret-credit",
                    sort_order=2,
                    is_hero=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
    with TestClient(app) as client:
        body = client.get("/articles/editorial-media-story").json()
        assert "source_url" not in body
        media = body["media"]
        assert media[0]["is_hero"] is True
        assert media[0]["url"] == "https://example.com/true-hero.jpg"
        assert media[0]["url"] != "https://example.com/legacy-hero.jpg"
        assert "credit" not in media[0]
        assert "provider_media_id" not in media[0]
        inline = [block for block in body["blocks"] if block.get("type") == "media"]
        assert len(inline) == 1
        assert inline[0]["url"] == "https://example.com/inline-two.jpg"
        assert inline[0].get("is_hero") is False
        related = [block for block in body["blocks"] if block.get("type") == "related"]
        assert len(related) <= 1
        if related:
            assert related[0]["article"]["slug"]
            assert "source_url" not in related[0]["article"]


def test_article_with_no_media_and_legacy_image_only():
    _make_article(
        slug="editorial-no-media",
        title="Aston Villa earn a point against Arsenal",
        content=CLEAN_BODY,
        image_url=None,
        external_id="https://example.com/editorial-no-media",
    )
    _make_article(
        slug="editorial-legacy-image",
        title="Aston Villa earn a point against Arsenal",
        content=CLEAN_BODY,
        image_url="https://example.com/only-hero.jpg",
        external_id="https://example.com/editorial-legacy-image",
    )
    with TestClient(app) as client:
        empty = client.get("/articles/editorial-no-media").json()
        assert empty["media"] == []
        assert empty["image_url"] is None
        legacy = client.get("/articles/editorial-legacy-image").json()
        assert len(legacy["media"]) == 1
        assert legacy["media"][0]["is_hero"] is True
        assert legacy["image_url"] == "https://example.com/only-hero.jpg"
        assert not any(block.get("type") == "media" for block in legacy["blocks"])

