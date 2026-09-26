from datetime import datetime, timezone
import pytest
from bot.extract import parse_feed_datetime

UTC = timezone.utc

@pytest.mark.parametrize("entry, expected", [
    ({"published": "Sat, 26 Sep 2026 08:30:00 +1000"}, datetime(2026,9,25,22,30,tzinfo=UTC)),
    ({"published": "2026-09-19T09:15:12Z", "updated": "Sat, 26 Sep 2026 10:00:00 GMT"}, datetime(2026,9,19,9,15,12,tzinfo=UTC)),
    ({"published": "2026-09-26T08:30:00+10:00"}, datetime(2026,9,25,22,30,tzinfo=UTC)),
    ({"published": "2026-09-26T08:30:00.123456-04:00"}, datetime(2026,9,26,12,30,0,123456,tzinfo=UTC)),
    ({"published": "2026-09-19T09:15:12", "updated": "Sat, 26 Sep 2026 10:00:00 GMT"}, datetime(2026,9,19,9,15,12)),
    ({"published": "2026-09-19"}, datetime(2026,9,19)),
    ({"published_parsed": (2026,9,19,9,15,12,5,262,0), "updated": "Sat, 26 Sep 2026 10:00:00 GMT"}, datetime(2026,9,19,9,15,12,tzinfo=UTC)),
    ({"published": "invalid", "published_parsed": (2026,9,19,9,15,12,5,262,0)}, datetime(2026,9,19,9,15,12,tzinfo=UTC)),
    ({"updated_parsed": (2026,9,26,5,0,0,5,269,0)}, datetime(2026,9,26,5,tzinfo=UTC)),
    ({"created_parsed": [2026,9,26,5,0,0,5,269,0]}, datetime(2026,9,26,5,tzinfo=UTC)),
    ({"updated": "2026-09-20T11:22:33Z"}, datetime(2026,9,20,11,22,33,tzinfo=UTC)),
    ({"created": " 2026-09-20T11:22:33Z "}, datetime(2026,9,20,11,22,33,tzinfo=UTC)),
    ({"published": "2026-12-01T12:00:00Z"}, datetime(2026,12,1,12,tzinfo=UTC)),
    ({}, None), (None, None), ([], None),
    ({"published": "bad", "published_parsed": (2026,99,99,0,0,0)}, None),
    ({"published": 1000, "published_parsed": "bad"}, None),
    ({"published_parsed": (2026,9)}, None),
    ({"published": "not a date", "updated": "Sat, 26 Sep 2026 10:00:00 GMT"}, datetime(2026,9,26,10,tzinfo=UTC)),
])
def test_news_dates(entry, expected):
    before = repr(entry)
    value = parse_feed_datetime(entry)
    assert value == expected
    assert (value.tzinfo if value else None) == (expected.tzinfo if expected else None)
    assert repr(entry) == before
