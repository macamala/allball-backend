from datetime import datetime, timezone

from bot import news_newsapi_org as newsapi


def test_newsapi_org_candidate_is_discovery_only():
    item=newsapi._candidate({
        "title":"World sport update",
        "description":"Verified publisher summary with enough factual context for guarded source extraction and rewriting.",
        "url":"https://publisher.example/sport/story",
        "urlToImage":"https://publisher.example/photo.jpg",
        "publishedAt":"2026-09-28T03:15:00Z",
        "source":{"name":"Publisher"},
    })
    assert item is not None
    assert item["published_at"]==datetime(2026,9,28,3,15,tzinfo=timezone.utc)
    assert item["feed"]["kind"]=="mixed"
    assert item["feed"]["sport"] is None
    assert item["image_candidates"][0]["url"]=="https://publisher.example/photo.jpg"


def test_newsapi_org_window_starts_at_sydney_midnight(monkeypatch):
    monkeypatch.setenv("NEWS_EDITORIAL_TIMEZONE","Australia/Sydney")
    start,end=newsapi._window(datetime(2026,9,28,6,0,tzinfo=timezone.utc))
    assert start=="2026-09-27T14:00:00Z"
    assert end=="2026-09-28T06:00:00Z"
