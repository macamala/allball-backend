from bot.textutil import clean_text, looks_like_garbage, strip_truncation_markers
from bot.quality import quality_check
from bot.rewrite_ai import parse_ai_output


def test_strips_publisher_footer():
    raw = "The 76ers signed Dillon Jones. The post 76ers sign Dillon Jones appeared first on TalkBasket.net ."
    cleaned = clean_text(raw)
    assert "TalkBasket" not in cleaned
    assert "76ers signed Dillon Jones" in cleaned
    raw = "Villa won at home. … [+1773 chars]"
    cleaned = strip_truncation_markers(raw)
    assert "[+" not in cleaned
    assert "chars]" not in cleaned
    assert "Villa won at home" in cleaned


def test_clean_text_removes_html_cdata_and_truncation():
    raw = "<![CDATA[<p>Bayern won the match.</p>]]> more text [+5260 chars]"
    cleaned = clean_text(raw)
    assert "<p>" not in cleaned
    assert "CDATA" not in cleaned.upper()
    assert "[+" not in cleaned
    assert "Bayern won the match" in cleaned


def test_garbage_html_is_rejected():
    assert looks_like_garbage("<html><script>function(){}</script></html>")
    ok, reason = quality_check("Ok title here", "<html><script>x</script></html>", "football")
    assert ok is False
    assert reason in {"garbage", "insufficient-facts"}


def test_parse_ai_english_story():
    raw = (
        "Aston Villa earn a point against Arsenal\n\n"
        "Unai Emery's side held Arsenal in the Premier League.\n\n"
        "Aston Villa earned a draw at Villa Park. The result keeps both clubs in the mix.\n"
    )
    parsed = parse_ai_output(raw)
    assert "Aston Villa" in parsed["title"]
    assert parsed["body"]
    assert "[+" not in parsed["body"]
