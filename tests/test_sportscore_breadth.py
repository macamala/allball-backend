from collector.adapters import FetchRequest, FetchResult
from collector.detail_enrich import fetch_family_detail, parse_sportscore_detail
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



def test_sportscore_detail_maps_match_centre_fields_without_tracker_ids():
    payload = {
        "match": {
            "home_ht_score": 0,
            "away_ht_score": 2,
            "incidents": [
                {"time": 14, "type": "Goal", "side": "away", "player": "Kevin Viveros", "is_goal": True, "home_score": 0, "away_score": 1},
                {"time": 20, "type": "Yellow card", "side": "home", "player": "Adonis Frias", "is_card": True},
                {"time": 45, "type": "Substitution", "side": "home", "is_sub": True, "player_in": "Benja", "player_out": "Gustavo"},
            ],
            "lineups": {
                "home_formation": "4-2-3-1",
                "away_formation": "3-4-2-1",
                "confirmed": True,
                "home_xi": [{"name": "Home Starter", "number": 5, "position": "M", "captain": True, "rating": "7.2"}],
                "home_subs": [{"name": "Home Sub", "number": 11, "position": "F", "captain": False, "rating": "0.0"}],
                "away_xi": [{"name": "Away Starter", "number": 1, "position": "G", "captain": False, "rating": "0.0"}],
                "away_subs": [],
            },
            "stats": [
                {"label": "Shots", "home": 11, "away": 8},
                {"name": "Possession", "values": ["56%", "44%"]},
            ],
            "tracker": {"id": "do-not-expose", "profile": "hidden"},
        }
    }
    out = parse_sportscore_detail(payload)
    assert out["periods"] == [{"label": "HT", "home": 0, "away": 2}]
    assert out["incidents"][0]["family"] == "goal"
    assert out["incidents"][0]["score_after"] == {"home": 0, "away": 1}
    assert out["incidents"][2]["family"] == "substitution"
    assert out["incidents"][2]["player_in"] == "Benja"
    assert out["lineups"]["home"]["formation"] == "4-2-3-1"
    assert out["lineups"]["home"]["start"][0]["captain"] is True
    assert "rating" not in out["lineups"]["home"]["bench"][0]
    assert out["statistics"] == [
        {"label": "Shots", "home": 11, "away": 8},
        {"label": "Possession", "home": "56%", "away": "44%"},
    ]
    assert "tracker" not in out
    assert "do-not-expose" not in str(out)


def test_sportscore_fetch_family_detail_uses_match_slug_and_sport():
    seen = []

    def getter(url):
        seen.append(url)
        return _ok(
            {
                "match": {
                    "home_ht_score": 1,
                    "away_ht_score": 0,
                    "incidents": [{"time": 8, "type": "Goal", "side": "home", "is_goal": True, "home_score": 1, "away_score": 0}],
                    "lineups": None,
                    "stats": [],
                }
            }
        )

    out = fetch_family_detail(
        "sportscore",
        "red-star-vs-partizan-abc123",
        getter=getter,
        sport="football",
    )
    assert out["periods"][0] == {"label": "HT", "home": 1, "away": 0}
    assert out["incidents"][0]["family"] == "goal"
    assert len(seen) == 1
    assert "sport=football" in seen[0]
    assert "slug=red-star-vs-partizan-abc123" in seen[0]

    seen.clear()
    assert fetch_family_detail("sportscore", "x", getter=getter, sport="motorsport") == {}
    assert seen == []
