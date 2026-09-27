from datetime import datetime, timedelta, timezone
import json

from bot import news_html_discovery as html
from bot.classify import classify_article
from bot.news_sources import OFFICIAL_HTML_SOURCES, enabled_sources


def _article_page(title, stamp):
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "datePublished": stamp.isoformat(),
        "url": "https://example.test/news/story-one",
    }
    return (
        '<html><head><script type="application/ld+json">'
        + json.dumps(payload)
        + '</script></head><body><article><p>Fixture body.</p></article></body></html>'
    ).encode()


def test_official_html_discovers_fresh_article_into_rss_shaped_item(monkeypatch):
    now = datetime.now(timezone.utc)
    landing = b'<html><body><a href="/news/story-one">Fresh official story</a></body></html>'
    article = _article_page("Fresh official story", now - timedelta(hours=1))

    def read(url):
        return landing if url.endswith("/news") else article

    monkeypatch.setattr(html, "read_news_feed", read)
    cfg = {
        "url": "https://example.test/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "valorant",
        "publisher": "Fixture",
        "article_prefixes": ("/news/",),
    }
    rows = html.discover_official_html(cfg, 3)
    assert len(rows) == 1
    assert rows[0]["title"] == "Fresh official story"
    assert rows[0]["feed"] is cfg
    assert rows[0]["summary"] == ""
    assert rows[0]["image_candidates"] == []


def test_official_html_rejects_stale_article(monkeypatch):
    now = datetime.now(timezone.utc)
    landing = b'<a href="/news/old-story">Old story</a>'
    article = _article_page("Old story", now - timedelta(days=10))
    monkeypatch.setattr(
        html,
        "read_news_feed",
        lambda url: landing if url.endswith("/news") else article,
    )
    cfg = {
        "url": "https://example.test/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "rocket-league",
        "article_prefixes": ("/news/",),
    }
    assert html.discover_official_html(cfg, 3) == []


def test_one_catalog_contains_rss_and_all_six_html_gaps():
    sources = enabled_sources()
    html_rows = [row for row in sources if row.get("representation") == "official_html"]
    rss_rows = [row for row in sources if row.get("representation") == "rss"]
    assert rss_rows
    assert len(html_rows) == 6
    assert {row["sport"] for row in html_rows} == {
        "ea-sports-fc",
        "league-of-legends",
        "valorant",
        "call-of-duty",
        "overwatch",
        "rocket-league",
    }
    assert len(OFFICIAL_HTML_SOURCES) == 6


def test_esports_official_language_is_recognized_without_bucket_stamping():
    cases = [
        ("Fan's Guide to the LCS Championship", "LoL Esports teams prepare for the LCS Championship.", "league-of-legends"),
        ("RLCS Returns To London", "The RLCS event brings Rocket League teams back to London.", "rocket-league"),
        ("CDL Championship recap", "Call of Duty League teams completed the CDL Championship.", "call-of-duty"),
        ("OWCS season update", "Overwatch teams continue the OWCS season.", "overwatch"),
        ("FC Pro World Championship", "EA SPORTS FC competitors return for the FC Pro season.", "ea-sports-fc"),
        ("VALORANT Champions update", "VALORANT teams prepare for Champions.", "valorant"),
    ]
    for title, body, expected in cases:
        result = classify_article(title, body, feed_kind="mixed", feed_sport=expected)
        assert result.sport == expected
