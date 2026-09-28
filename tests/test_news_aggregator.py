from datetime import datetime, timezone

from bot import news_aggregator as agg


def test_newsapi_candidate_preserves_source_body_image_and_time():
    item=agg._candidate({
        "title":"World sport update",
        "url":"https://example.test/sport/story",
        "body":"A complete source report with enough factual material for guarded rewriting.",
        "image":"https://example.test/photo.jpg",
        "dateTimePub":"2026-09-28T03:15:00Z",
    })
    assert item["title"]=="World sport update"
    assert item["_extracted"].startswith("A complete source report")
    assert item["image_candidates"][0]["url"]=="https://example.test/photo.jpg"
    assert item["published_at"]==datetime(2026,9,28,3,15,tzinfo=timezone.utc)
    assert item["feed"]["representation"]=="aggregator"


def test_newsapi_candidate_rejects_missing_body_or_verified_time():
    assert agg._candidate({
        "title":"No body",
        "url":"https://example.test/no-body",
        "dateTimePub":"2026-09-28T03:15:00Z",
    }) is None
    assert agg._candidate({
        "title":"No time",
        "url":"https://example.test/no-time",
        "body":"facts",
    }) is None


def test_newsapi_adapter_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("NEWS_NEWSAPI_AI_ENABLED","1")
    monkeypatch.delenv("NEWS_API_KEY",raising=False)
    assert agg.fetch_newsapi_ai_entries() == []
