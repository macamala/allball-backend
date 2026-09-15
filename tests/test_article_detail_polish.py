from bot.fetch_sources import _extract_image_url
from bot.media_url import (
    image_stem,
    pick_source_image,
    upgrade_hero_image_url,
    width_from_url,
)
from bot.site_chrome import strip_leading_cms_chrome
from editorial import public_media_items, sanitize_body, to_blocks


def test_hero_upgrades_cdn_width_token_not_unrelated_url():
    thumb = "https://ichef.example.com/ace/standard/240/cpsprodpb/live/photo.jpg"
    hero = upgrade_hero_image_url(thumb)
    assert hero == "https://ichef.example.com/ace/standard/1600/cpsprodpb/live/photo.jpg"
    assert image_stem(thumb) == image_stem(hero)
    full = "https://cdn.example.com/wp-content/uploads/2026/09/goal.jpg"
    assert upgrade_hero_image_url(full) == full
    query = "https://cdn.example.com/photo.jpg?w=320&crop=faces"
    assert "w=1600" in upgrade_hero_image_url(query)
    assert width_from_url(thumb) == 240


def test_public_detail_uses_upgraded_hero_cards_keep_stored():
    stored = "https://ichef.example.com/ace/standard/240/cpsprodpb/live/match.jpg"
    media = public_media_items(stored, media_rows=[])
    assert media[0]["is_hero"] is True
    assert "/1600/" in media[0]["url"]
    assert "/240/" not in media[0]["url"]


def test_pick_largest_same_image_not_a_different_photo():
    thumb = "https://ichef.example.com/ace/standard/240/cpsprodpb/live/hero.jpg"
    large = "https://ichef.example.com/ace/standard/1920/cpsprodpb/live/hero.jpg"
    other = "https://ichef.example.com/ace/standard/1920/cpsprodpb/live/other.jpg"
    picked = pick_source_image(
        [
            (thumb, 240),
            (large, 1920),
            (other, 1920),
        ]
    )
    assert picked == large


def test_extract_image_url_prefers_largest_same_stem():
    entry = {
        "media_content": [
            {"url": "https://ichef.example.com/ace/standard/240/cpsprodpb/live/hero.jpg", "width": "240"},
            {"url": "https://ichef.example.com/ace/standard/800/cpsprodpb/live/hero.jpg", "width": "800"},
        ],
        "media_thumbnail": [
            {"url": "https://ichef.example.com/ace/standard/240/cpsprodpb/live/hero.jpg", "width": "240"},
        ],
        "summary": '<img src="https://ichef.example.com/ace/standard/240/cpsprodpb/live/hero.jpg" />',
    }
    assert _extract_image_url(entry).endswith("/800/cpsprodpb/live/hero.jpg")


def test_cms_kicker_and_duplicate_title_are_stripped_without_word_deletes():
    title = "Is the Premier League already a two-team title race?"
    raw = (
        "Top Scorers Gossip Is the Premier League already a two-team title race? "
        "Haaland scores a controversial winner as Man City win the derby. "
        "Four games is far too soon to be talking about who is in or out of the title race."
    )
    body = sanitize_body(raw, title=title)
    assert "Top Scorers" not in body
    assert not body.lower().startswith("gossip")
    assert title not in body
    assert "Haaland scores a controversial winner" in body
    gossip_prose = (
        "Persistent gossip swirling around the club will not distract the manager. "
        "The board wants a calm week on the training ground."
    )
    kept = sanitize_body(gossip_prose, title="Club stay calm amid transfer talk")
    assert "Persistent gossip swirling around the club" in kept


def test_image_caption_prefix_is_dropped_from_prose():
    title = "Hearts take the derby honours"
    raw = "Image caption, Hearts beat Hibs in a frantic Edinburgh derby after a late winner."
    body = sanitize_body(raw, title=title)
    assert "Image caption" not in body
    assert "Hearts beat Hibs" in body


def test_stored_paragraphs_are_preserved_not_packed_by_length():
    title = "Como complete a Champions League debut"
    raw = (
        "The Stadio Sinigaglia hosted this special match after summer renovation work.\n\n"
        "RB Leipzig missed several regulars, but the visitors still created early chances."
    )
    blocks = to_blocks(raw, title=title)
    paras = [block["text"] for block in blocks if block["type"] == "paragraph"]
    assert len(paras) == 2
    assert paras[0].startswith("The Stadio Sinigaglia")
    assert paras[1].startswith("RB Leipzig missed")


def test_flat_blob_splits_on_sentences_not_character_count():
    title = "Villa earn a late point"
    raw = (
        "Aston Villa earned a late point against Arsenal in the Premier League. "
        "Unai Emery's side defended with discipline after the break."
    )
    blocks = to_blocks(raw, title=title)
    paras = [block["text"] for block in blocks if block["type"] == "paragraph"]
    assert len(paras) == 2
    assert "Aston Villa earned a late point" in paras[0]
    assert "Unai Emery" in paras[1]


def test_comments_form_chrome_is_removed_as_a_whole_phrase():
    title = "Who has made the team of the week?"
    raw = (
        "After every round of matches this season, the pundit will give his team of the week. "
        "Give us your thoughts using the comments form at the bottom of this page. "
        "Gianluigi Donnarumma is one of the best goalkeepers in the world."
    )
    body = sanitize_body(raw, title=title)
    assert "comments form" not in body.lower()
    assert "bottom of this page" not in body.lower()
    assert "Gianluigi Donnarumma" in body
    assert "pundit will give his team" in body
    text = "Manchester United beat Liverpool after a late header in the derby."
    assert strip_leading_cms_chrome(text, title="A late header decides the derby") == text
