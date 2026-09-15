from editorial import (
    lift_hero_caption,
    sanitize_body,
    split_photo_caption,
    to_blocks,
)


DE_ZERBI_OPENER = (
    "BRENTFORD, ENGLAND - AUGUST 22: Roberto De Zerbi, Manager of Tottenham Hotspur "
    "reacts during the Premier League 2026/27 match between Brentford and Tottenham "
    "Hotspur at Gtech Community Stadium on August 22, 2026 in Brentford, England. "
    "(Photo by Ryan Pierse/Getty Images) Roberto De Zerbi’s Tottenham were jeered off "
    "at full-time after a second successive goalless draw left them without a win or a "
    "goal in the Premier League this season."
)

UCL_SOCIAL = (
    "Como completed a stunning Champions League debut with a 4-1 win over RB Leipzig. "
    "Watch now on TNT Sports & HBO Max pic.twitter.com/abcd1234xyz "
    "Football on TNT Sports (@footballontnt) September 10, 2026"
)


def test_getty_caption_is_split_from_first_paragraph():
    caption, body = split_photo_caption(DE_ZERBI_OPENER)
    assert caption
    assert "Getty Images" in caption
    assert "jeered off" not in caption
    assert body.startswith("Roberto De Zerbi")
    assert "Getty Images" not in body


def test_to_blocks_lifts_caption_and_keeps_prose():
    blocks = to_blocks(DE_ZERBI_OPENER, title="De Zerbi under pressure")
    types = [block["type"] for block in blocks]
    assert types[0] == "caption"
    assert "Photo by" in blocks[0]["text"]
    prose = " ".join(block["text"] for block in blocks if block["type"] == "paragraph")
    assert "jeered off" in prose
    assert "Getty Images" not in prose


def test_hero_caption_moves_to_media_not_prose():
    blocks = to_blocks(DE_ZERBI_OPENER)
    media = [{"url": "https://example.com/hero.jpg", "caption": "", "is_hero": True}]
    rest, media = lift_hero_caption(blocks, media)
    assert rest[0]["type"] == "paragraph"
    assert "Getty Images" not in (media[0].get("caption") or "")
    assert "Photo by" not in (media[0].get("caption") or "")
    prose = " ".join(block.get("text") or "" for block in rest)
    assert "Getty Images" not in prose
    assert "jeered off" in rest[0]["text"]


def test_twitter_chrome_is_removed_from_public_body():
    cleaned = sanitize_body(UCL_SOCIAL, title="Como 4-1 RB Leipzig")
    assert "pic.twitter.com" not in cleaned.lower()
    assert "@footballontnt" not in cleaned.lower()
    assert "Watch now on" not in cleaned
    assert "Champions League debut" in cleaned


def test_sanitize_body_omits_photo_caption():
    cleaned = sanitize_body(DE_ZERBI_OPENER, title="De Zerbi under pressure")
    assert "Getty Images" not in cleaned
    assert "Photo by" not in cleaned
    assert "jeered off" in cleaned


def test_legitimate_website_sentence_survives():
    body = (
        "Como completed a stunning Champions League debut with a 4-1 win over RB Leipzig. "
        "The club later confirmed the squad list on its official website after the match."
    )
    cleaned = sanitize_body(body, title="Como 4-1 RB Leipzig")
    assert "official website" in cleaned
    assert "4-1" in cleaned
