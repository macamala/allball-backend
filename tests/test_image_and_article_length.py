from bot.extract import _json_ld_article_body, extract_from_url, paragraphs_from_html
from bot.fetch_sources import _ai_story, select_facts, source_article_facts
from bot.media_url import image_url_for_display, upgrade_hero_image_url
from bot.quality import (
    is_dramatic_shortening,
    needs_full_source_repair,
    quality_check,
    word_count,
)
from bot.rewrite_ai import SYSTEM_PROMPT, parse_ai_output
from editorial import to_blocks
import json


def _words(n, seed="Arsenal"):
    return " ".join(f"{seed}{i}" for i in range(n))


def test_featured_card_does_not_use_240_when_larger_variant_exists():
    thumb = "https://ichef.example.com/ace/standard/240/cpsprodpb/live/photo.jpg"
    featured = image_url_for_display(thumb, "featured")
    assert "/1280/" in featured
    assert "/240/" not in featured
    assert image_url_for_display(thumb, "hero") == upgrade_hero_image_url(thumb)
    assert "/1600/" in image_url_for_display(thumb, "hero")


def test_small_cards_do_not_request_1600():
    thumb = "https://ichef.example.com/ace/standard/240/cpsprodpb/live/photo.jpg"
    huge = "https://ichef.example.com/ace/standard/1920/cpsprodpb/live/photo.jpg"
    assert "/320/" in image_url_for_display(thumb, "thumb")
    assert "/1600/" not in image_url_for_display(thumb, "thumb")
    assert "/1600/" not in image_url_for_display(huge, "thumb")
    assert "/320/" in image_url_for_display(huge, "thumb")
    card = image_url_for_display(thumb, "card")
    assert "/800/" in card
    assert "/1600/" not in card


def test_full_size_urls_remain_unchanged():
    full = "https://cdn.example.com/wp-content/uploads/2026/09/goal.jpg"
    assert image_url_for_display(full, "featured") == full
    assert image_url_for_display(full, "thumb") == full
    assert upgrade_hero_image_url(full) == full


def test_feed_summary_does_not_override_extracted_article():
    extracted = (
        "Aston Villa earned a late point against Arsenal in the Premier League. "
        "Unai Emery's side defended with discipline after the break and created chances."
    )
    rss = "Villa drew with Arsenal. Read the full story on the source site."
    facts, origin = source_article_facts(
        extracted, rss, "https://www.bbc.co.uk/sport/football/articles/example"
    )
    assert origin == "source"
    assert "Read the full story" not in facts
    assert "Unai Emery" in facts
    assert extracted in select_facts(extracted, rss)


def test_rss_is_not_used_when_source_page_exists_but_extract_failed():
    rss = "Manchester City beat Arsenal in a two-sentence RSS description of the derby."
    facts, origin = source_article_facts(
        "", rss, "https://www.bbc.co.uk/sport/football/articles/example"
    )
    assert origin == "missing-source"
    assert facts == ""


def test_substantial_source_cannot_silently_become_summary(monkeypatch):
    source = _words(300, "City") + " scored after a long build-up in Manchester."
    tiny = (
        "Title race latest\n\n"
        "City stay top.\n\n"
        "Manchester City remain top of the Premier League after a routine win."
    )

    def fake_write(*args, **kwargs):
        return tiny

    monkeypatch.setattr("bot.fetch_sources.write_ninkosports_story", fake_write)
    parsed, reason = _ai_story("City stay top", source, "football", "england-premier-league", 6000)
    assert parsed is None
    assert reason == "too-short"
    assert is_dramatic_shortening(source, parse_ai_output(tiny)["body"]) is True


def test_short_breaking_story_is_allowed():
    source = (
        "Real Madrid announced that the midfielder will miss Saturday's match with a knock. "
        "The club said further scans will take place tomorrow morning in Madrid."
    )
    output = (
        "Real Madrid will be without the midfielder on Saturday after a knock. "
        "Further scans are scheduled for tomorrow."
    )
    assert word_count(source) < 180
    assert is_dramatic_shortening(source, output) is False
    ok, reason = quality_check("Real Madrid midfielder to miss Saturday", output, "football")
    assert ok is True
    assert reason == "ok"


def test_paragraph_structure_preserved_from_source_html():
    html = """
    <html><body><article>
      <p>Aston Villa earned a late point against Arsenal in the Premier League.</p>
      <p>Unai Emery's side defended with discipline after the break and created chances.</p>
      <h3>What the result means for the table</h3>
      <p>The draw keeps both clubs in the mix as the season gathers pace in England.</p>
      <blockquote>We had to stay in the contest until the last minutes, said the manager.</blockquote>
    </article></body></html>
    """
    text = paragraphs_from_html(html)
    parts = [part for part in text.split("\n\n") if part.strip()]
    assert len(parts) >= 4
    assert parts[0].startswith("Aston Villa")
    blocks = to_blocks(text, title="Villa earn a late point")
    paras = [block["text"] for block in blocks if block["type"] == "paragraph"]
    assert len(paras) >= 4


def test_og_description_is_not_used_as_article_body(monkeypatch):
    html = """
    <html><head>
      <meta property="og:description" content="Villa drew with Arsenal in a two-line teaser.">
    </head><body>
      <nav><p>Home News Sport Earth Reel Worklife Travel Culture Future Music</p></nav>
    </body></html>
    """

    class _Resp:
        status_code = 200
        text = html

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _Resp()

    monkeypatch.setattr("bot.extract.httpx.Client", _Client)
    text, _image = extract_from_url("https://example.com/villa")
    assert "two-line teaser" not in text


def test_json_ld_article_body_used_when_paragraphs_are_thin():
    body = (
        "Erling Haaland scored twice as Manchester City beat Arsenal at the Etihad. "
        "The visitors created early chances but could not match City's intensity after the break. "
        "Pep Guardiola said the performance was built on defensive discipline and quick transitions. "
        "The result keeps City at the top of the Premier League table after a demanding week. "
        "Arsenal remain close enough to stay in the title conversation as the season unfolds in England. "
        "Further fixtures this month will test both squads as injuries begin to shape selection. "
        "City will now turn toward a midweek European match before another league away trip."
    )
    html = (
        '<script type="application/ld+json">{"@type":"NewsArticle","articleBody":'
        + json.dumps(body)
        + "}</script>"
    )
    extracted = _json_ld_article_body(html)
    assert "Erling Haaland scored twice" in extracted
    assert "Pep Guardiola" in extracted


def test_rewrite_prompt_forbids_hallucinated_filler():
    lower = SYSTEM_PROMPT.lower()
    assert "do not invent" in lower
    assert "do not pad" in lower
    assert "350-700" in SYSTEM_PROMPT.replace("–", "-")
    assert "2-6 short paragraphs" not in lower


def test_needs_full_source_repair_is_selective():
    stub = _words(80, "Race")
    full = _words(400, "Title") + " The champions still have work to do in May."
    assert needs_full_source_repair(stub, full) is True
    assert needs_full_source_repair(full, full) is False
    assert needs_full_source_repair(stub, _words(90, "Tiny")) is False
