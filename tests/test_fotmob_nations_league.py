from collector.adapters import FetchRequest, FetchResult
from collector.adapters_fotmob import FOTMOB_LEAGUES, FotMobAdapter, _BOARD, _league_ids


def _league(match_id, league_id, home, away):
    return {
        "id": league_id,
        "name": f"Nations League {league_id}",
        "matches": [
            {
                "id": match_id,
                "home": {"name": home},
                "away": {"name": away},
                "status": {
                    "started": False,
                    "finished": False,
                    "utcTime": "2026-09-24T18:45:00Z",
                },
            }
        ],
    }


def test_nations_league_uses_all_four_fotmob_divisions():
    spec = FOTMOB_LEAGUES["uefa-nations-league"]
    assert _league_ids(spec) == ["9806", "9807", "9808", "9809"]


def test_nations_league_adapter_keeps_events_from_a_b_c_d():
    _BOARD.clear()
    payload = {
        "leagues": [
            _league(1, 9806, "Netherlands", "Germany"),
            _league(2, 9807, "Austria", "Israel"),
            _league(3, 9808, "Team C1", "Team C2"),
            _league(4, 9809, "Andorra", "Malta"),
            _league(5, 9999, "Wrong League", "Ignore Me"),
        ]
    }
    calls = {"n": 0}

    def getter(_url):
        calls["n"] += 1
        return FetchResult(
            ok=True,
            http_status=200,
            payload=payload if calls["n"] == 1 else {"leagues": []},
        )

    result = FotMobAdapter(getter=getter).fetch(
        FetchRequest(
            capability="fixtures",
            sport_id="football",
            competition_id="uefa-nations-league",
            source_config={"fotmob_league_ids": [9806, 9807, 9808, 9809]},
        )
    )
    assert result.ok is True
    assert {row["source_competition_id"] for row in result.events} == {"9806", "9807", "9808", "9809"}
    assert {row["home"]["name"] for row in result.events} == {"Netherlands", "Austria", "Team C1", "Andorra"}
