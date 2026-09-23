from datetime import datetime, timezone

from collector.sportscore_crosswalk import _match_team_slugs, _schedule_window


def test_team_slugs_come_from_match_url():
    assert _match_team_slugs(
        {"url": "/basketball/match/minnesota-lynx-vs-indiana-fever/"}
    ) == ["minnesota-lynx", "indiana-fever"]


def test_schedule_window_accepts_near_future_and_rejects_old_rows():
    now = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)
    assert _schedule_window({"time": "2026-09-25T00:00:00+00:00"}, now=now)
    assert not _schedule_window({"time": "2026-05-25T00:00:00+00:00"}, now=now)
