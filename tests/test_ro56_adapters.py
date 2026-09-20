from collector.adapters import FetchRequest, FetchResult
from collector.adapters_feeds import PULSELIVE_COMP_TOKENS, WorldRugbyAdapter
from collector.adapters_ro56 import CflScoreboardAdapter, F1LiveTimingIndexAdapter, LolEsportsAdapter


def test_pulselive_tokens_cover_rugby_family():
    assert "super rugby" in PULSELIVE_COMP_TOKENS["super-rugby"]
    assert "top 14" in PULSELIVE_COMP_TOKENS["france-top-14"]
    assert "premiership" in PULSELIVE_COMP_TOKENS["premiership-rugby"]


def test_world_rugby_filters_by_competition_token():
    payload = {
        "content": [
            {
                "matchId": "1",
                "status": "L",
                "scores": [10, 7],
                "clock": "34:12",
                "teams": [{"id": "a", "name": "Chiefs"}, {"id": "b", "name": "Blues"}],
                "competition": {"name": "Super Rugby Pacific"},
                "time": {"label": "2026-09-20T07:00:00Z"},
            },
            {
                "matchId": "2",
                "status": "U",
                "scores": [None, None],
                "teams": [{"id": "c", "name": "Toulouse"}, {"id": "d", "name": "Racing"}],
                "competition": {"name": "Top 14"},
                "time": {"label": "2026-09-20T18:00:00Z"},
            },
        ]
    }
    adapter = WorldRugbyAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    super_events = adapter.fetch(FetchRequest(capability="snapshot", competition_id="super-rugby")).events
    assert len(super_events) == 1
    assert super_events[0]["status"] == "live"
    assert super_events[0]["score"]["home"] == 10
    assert super_events[0]["score"]["clock"] == "34:12"
    top14 = adapter.fetch(FetchRequest(capability="snapshot", competition_id="france-top-14")).events
    assert len(top14) == 1
    assert top14[0]["competition"] == "Top 14"


def test_cfl_scoreboard_maps_live_clock():
    payload = [
        {
            "id": 1,
            "status": "complete",
            "name": "Week 1",
            "tournaments": [
                {
                    "id": 9,
                    "status": "live",
                    "activePeriod": 3,
                    "possession": "home",
                    "homeSquad": {"id": 1, "name": "Argonauts", "score": 17},
                    "awaySquad": {"id": 2, "name": "Roughriders", "score": 14},
                }
            ],
        }
    ]
    adapter = CflScoreboardAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    events = adapter.fetch(FetchRequest(capability="live_scores", competition_id="cfl")).events
    assert events[0]["status"] == "live"
    assert events[0]["score"]["period"] == 3
    assert events[0]["score"]["possession"] == "home"


def test_lol_esports_maps_worlds_state():
    leagues = {"data": {"leagues": [{"id": "w1", "slug": "worlds", "name": "Worlds"}]}}
    schedule = {
        "data": {
            "schedule": {
                "events": [
                    {
                        "startTime": "2026-10-01T12:00:00Z",
                        "state": "inProgress",
                        "league": {"name": "Worlds"},
                        "match": {
                            "id": "m1",
                            "teams": [
                                {"code": "T1", "name": "T1", "result": {"gameWins": 1}},
                                {"code": "GEN", "name": "Gen.G", "result": {"gameWins": 0}},
                            ],
                        },
                    }
                ]
            }
        }
    }

    def getter(url: str) -> FetchResult:
        if "getLeagues" in url:
            return FetchResult(ok=True, http_status=200, payload=leagues)
        return FetchResult(ok=True, http_status=200, payload=schedule)

    adapter = LolEsportsAdapter(getter=getter)
    events = adapter.fetch(FetchRequest(capability="snapshot", competition_id="lol-world-championship")).events
    assert events[0]["status"] == "live"
    assert events[0]["score"]["home"] == 1


def test_f1_index_does_not_infer_live_from_time():
    payload = {
        "Year": 2026,
        "Meetings": [
            {
                "Key": 1,
                "Name": "Bahrain",
                "Sessions": [{"Type": "Race", "StartDate": "2026-03-08T15:00:00", "EndDate": "2026-03-08T17:00:00"}],
            }
        ],
    }
    adapter = F1LiveTimingIndexAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    events = adapter.fetch(FetchRequest(capability="snapshot", competition_id="formula-1")).events
    assert events[0]["status"] == "scheduled"
    assert events[0]["score"]["home"] is None
