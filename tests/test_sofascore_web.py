from collector.adapters import FetchRequest, FetchResult
from collector.adapters_sofascore import SofaScoreWebAdapter, sofa_event
import collector.adapters_sofascore as sofa_mod


def test_sofa_event_live_clock_not_inferred_when_scheduled():
    live = sofa_event(
        {
            "id": 1,
            "homeTeam": {"id": 1, "name": "Storm"},
            "awayTeam": {"id": 2, "name": "Roosters"},
            "status": {"type": "inprogress", "description": "2nd half"},
            "homeScore": {"current": 12},
            "awayScore": {"current": 6},
            "time": {"played": 54, "period": 2},
            "startTimestamp": 1758351600,
            "tournament": {"name": "NRL Premiership, Playoffs", "uniqueTournament": {"id": 9, "name": "NRL"}, "category": {"name": "Rugby League"}},
        },
        "nrl",
        "rugby-league",
    )
    assert live["status"] == "live"
    assert live["score"]["home"] == 12
    assert live["score"]["clock"] == 54
    scheduled = sofa_event(
        {
            "id": 2,
            "homeTeam": {"name": "A"},
            "awayTeam": {"name": "B"},
            "status": {"type": "notstarted"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 0},
            "tournament": {"name": "NRL"},
        },
        "nrl",
        "rugby-league",
    )
    assert scheduled["status"] == "scheduled"
    assert scheduled["score"]["home"] is None


def test_sofascore_adapter_filters_nrl_from_shared_rugby_board():
    sofa_mod._BOARD.clear()
    payload = {
        "events": [
            {
                "id": 11,
                "homeTeam": {"name": "Storm"},
                "awayTeam": {"name": "Roosters"},
                "status": {"type": "inprogress"},
                "homeScore": {"current": 18},
                "awayScore": {"current": 12},
                "tournament": {"name": "NRL Premiership, Playoffs", "uniqueTournament": {"name": "NRL"}, "category": {"name": "Rugby League"}},
            },
            {
                "id": 12,
                "homeTeam": {"name": "Toulouse"},
                "awayTeam": {"name": "Racing"},
                "status": {"type": "notstarted"},
                "tournament": {"name": "Top 14", "uniqueTournament": {"name": "Top 14"}, "category": {"name": "France"}},
            },
        ]
    }
    adapter = SofaScoreWebAdapter(getter=lambda url: FetchResult(ok=True, http_status=200, payload=payload))
    nrl = adapter.fetch(FetchRequest(capability="live_scores", competition_id="nrl")).events
    assert len(nrl) == 1
    assert nrl[0]["home"]["name"] == "Storm"
    top = adapter.fetch(FetchRequest(capability="snapshot", competition_id="france-top-14")).events
    assert len(top) == 1
    assert top[0]["status"] == "scheduled"
