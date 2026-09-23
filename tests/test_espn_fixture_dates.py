from collector.adapters_espn import _scoreboard_date_urls


def test_espn_fixture_urls_use_requested_tomorrow_before_default_board():
    url = "https://www.espn.com/soccer/scoreboard/_/league/srb.1"
    rows = _scoreboard_date_urls(
        url,
        date_from="2026-09-24",
        date_to="2026-09-24",
        capability="fixtures",
    )
    assert rows[0] == "https://www.espn.com/soccer/scoreboard/_/league/srb.1/_/date/20260924"
    assert url in rows


def test_espn_fixture_urls_cover_bounded_requested_range():
    url = "https://www.espn.com/soccer/scoreboard"
    rows = _scoreboard_date_urls(
        url,
        date_from="2026-09-24T00:00:00",
        date_to="2026-09-26T23:59:59",
        capability="fixtures",
    )
    assert rows[:3] == [
        "https://www.espn.com/soccer/scoreboard/_/date/20260924",
        "https://www.espn.com/soccer/scoreboard/_/date/20260925",
        "https://www.espn.com/soccer/scoreboard/_/date/20260926",
    ]


def test_espn_fixture_without_explicit_range_includes_tomorrow():
    url = "https://www.espn.com/soccer/scoreboard"
    rows = _scoreboard_date_urls(url, capability="fixtures")
    assert len(rows) >= 3
    assert "/_/date/" in rows[0]
    assert "/_/date/" in rows[1]
    assert rows[-1] == url
