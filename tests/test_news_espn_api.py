from datetime import datetime, timezone

from bot import news_espn_api as espn


def test_espn_candidate_preserves_source_facts_image_time_and_sport():
    item=espn._candidate(
        {
            "headline":"Week 3 NFL update",
            "description":"A verified source report with enough factual detail about the game and the teams involved for guarded rewriting.",
            "published":"2026-09-28T03:15:00Z",
            "premium":False,
            "images":[
                {"type":"header","url":"https://a.espncdn.com/photo/test.jpg","width":1296,"height":729}
            ],
            "links":{"web":{"href":"https://www.espn.com/nfl/story/_/id/123/example"}},
        },
        {"sport":"american-football","publisher":"ESPN NFL","url":"https://example.test"},
    )
    assert item is not None
    assert item["published_at"]==datetime(2026,9,28,3,15,tzinfo=timezone.utc)
    assert item["feed"]["sport"]=="american-football"
    assert item["image"]=="https://a.espncdn.com/photo/test.jpg"
    assert item["_extracted"].startswith("A verified source report")


def test_espn_candidate_rejects_premium_or_missing_source_fields():
    source={"sport":"basketball","publisher":"ESPN NBA","url":"https://example.test"}
    assert espn._candidate({"premium":True},source) is None
    assert espn._candidate({
        "headline":"Missing timestamp",
        "description":"facts",
        "links":{"web":{"href":"https://www.espn.com/nba/story/_/id/123/example"}},
    },source) is None
