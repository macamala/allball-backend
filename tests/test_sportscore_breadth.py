from collector.adapters import FetchRequest, FetchResult
from collector.adapters_sportscore import (
    _MATCH_CACHE,
    _STANDINGS_CACHE,
    _TEAM_CACHE,
    SportScoreAdapter,
    match_to_event,
)


def _ok(payload):
    return FetchResult(ok=True, http_status=200, payload=payload)


def test_sportscore_event_keeps_match_slug_for_detail():
    event = match_to_event(
        {
            "home": "Red Star",
            "away": "Partizan",
            "competition": "Serbia Superliga",
            "time": "2026-09-22T18:00:00Z",
            "url": "https://sportscore.com/football/red-star-vs-partizan-abc123/",
            "home_score": 2,
            "away_score": 1,
            "status": "finished",
        },
        "serbia-superliga",
    )
    assert event is not None
    assert event["source_event_id"] == "red-star-vs-partizan-abc123"
    assert event["source_event_ids"]["sportscore"] == "red-star-vs-partizan-abc123"
    assert event["extra"]["source_event_ids"]["sportscore"] == "red-star-vs-partizan-abc123"
    assert event["competition_key"] == "serbia-superliga"


def test_sportscore_fixture_pass_expands_all_standings_teams_and_dedupes():
    _MATCH_CACHE.clear()
    _STANDINGS_CACHE.clear()
    _TEAM_CACHE.clear()
    calls = []

    def getter(url):
        calls.append(url)
        if "/matches/" in url:
            # The target league is intentionally absent from the global top-50 board.
            return _ok(
                {
                    "matches": [
                        {
                            "home": "Other A",
                            "away": "Other B",
                            "competition": "Other League",
                            "time": "2026-09-22T10:00:00Z",
                        }
                    ]
                }
            )
        if "/standings/" in url:
            return _ok(
                {
                    "tables": [
                        {
                            "rows": [
                                {"team_slug": f"team-{index}"}
                                for index in range(1, 7)
                            ]
                        }
                    ]
                }
            )
        if "/team/" in url:
            team_slug = url.split("slug=", 1)[1].split("&", 1)[0]
            return _ok(
                {
                    "matches": [
                        {
                            "slug": "red-star-vs-partizan-abc123",
                            "url": "https://sportscore.com/football/red-star-vs-partizan-abc123/",
                            "home": "Red Star",
                            "away": "Partizan",
                            "competition": "Serbia Superliga",
                            "time": "2026-09-22T18:00:00Z",
                            "home_score": 2,
                            "away_score": 1,
                            "status": "finished",
                            "_from_team": team_slug,
                        }
                    ]
                }
            )
        raise AssertionError(url)

    adapter = SportScoreAdapter(getter=getter)
    result = adapter.fetch(
        FetchRequest(
            capability="fixtures",
            sport_id="football",
            competition_id="serbia-superliga",
        )
    )

    assert result.ok is True
    assert len(result.events) == 1
    assert result.events[0]["source_event_id"] == "red-star-vs-partizan-abc123"

    team_calls = [url for url in calls if "/team/" in url]
    assert len(team_calls) == 6
    assert all("limit=30" in url for url in team_calls)


def test_sportscore_live_pass_does_not_fan_out_uncached_team_schedules():
    _MATCH_CACHE.clear()
    _STANDINGS_CACHE.clear()
    _TEAM_CACHE.clear()
    calls = []

    def getter(url):
        calls.append(url)
        if "/matches/" in url:
            return _ok({"matches": []})
        raise AssertionError("live path should not fan out to standings/team schedules")

    adapter = SportScoreAdapter(getter=getter)
    result = adapter.fetch(
        FetchRequest(
            capability="live_scores",
            sport_id="football",
            competition_id="serbia-superliga",
        )
    )
    assert result.ok is True
    assert result.events == []
    assert len(calls) == 1
