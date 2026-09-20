from collector.adapters import FetchRequest, FetchResult
from collector.adapters_final18 import (
    ChampionDataNetballAdapter,
    ClickTtRemixAdapter,
    PgaGraphqlAdapter,
    parse_altiusrt_matches,
)


def test_pga_graphql_schedule_and_live_thru():
    schedule = {
        "data": {
            "schedule": {
                "tournaments": [
                    {
                        "id": "R2026060",
                        "tournamentName": "Tour Championship",
                        "tournamentStatus": "IN_PROGRESS",
                        "startDate": "2026-09-17",
                    }
                ]
            }
        }
    }
    board = {
        "data": {
            "leaderboardV3": {
                "id": "R2026060",
                "tournamentId": "R2026060",
                "tournamentStatus": "IN_PROGRESS",
                "players": [
                    {
                        "player": {"id": "1", "displayName": "Scottie Scheffler"},
                        "scoringData": {"position": "1", "total": "-12", "thru": "14", "currentRound": 3},
                    }
                ],
            }
        }
    }

    def poster(body):
        q = str(body.get("query") or "")
        if "leaderboardV3(" in q:
            return FetchResult(ok=True, http_status=200, payload=board)
        return FetchResult(ok=True, http_status=200, payload={"data": {"upcomingSchedule": schedule["data"]["schedule"]}})

    adapter = PgaGraphqlAdapter(poster=poster)
    events = adapter.fetch(FetchRequest(capability="snapshot", competition_id="pga-tour")).events
    live = [e for e in events if e.get("status") == "live"]
    assert live
    assert live[0]["score"]["thru"] == "14"
    assert live[0]["score"]["home"] == "-12"


def test_click_tt_remix_uses_source_live_flag():
    payload = {
        "data": {
            "meetings_excerpt": {
                "meetings": [
                    {
                        "meeting_id": "15348642",
                        "team_home": "Borussia Düsseldorf",
                        "team_away": "TTC Schwalbe Bergneustadt",
                        "team_home_id": "1",
                        "team_away_id": "2",
                        "live": True,
                        "state": "running",
                        "matches_won": "2",
                        "matches_lost": "1",
                        "date": "2026-09-20T17:00:00.000+00:00",
                        "league_name": "Tischtennis Bundesliga",
                        "league_id": "493079",
                    }
                ]
            }
        }
    }
    adapter = ClickTtRemixAdapter(
        getter=lambda url: FetchResult(
            ok=True,
            http_status=200,
            payload=payload if "tabelle" in url else {"data": {"live": True, "team_home": "Borussia Düsseldorf", "team_guest": "TTC Schwalbe", "matches_home": 2, "matches_guest": 1}},
        )
    )
    events = adapter.fetch(FetchRequest(capability="live_scores", competition_id="germany-click-tt")).events
    assert events[0]["status"] == "live"
    assert events[0]["score"]["home"] == 2


def test_altiusrt_html_does_not_infer_live_from_time():
    html = """
    <table><tr><td>01</td><td>SCO v WAL (Pool A)</td><td>7 - 1</td><td>Official</td></tr>
    <tr><td>02</td><td>TUR v CZE (Pool A)</td><td></td><td>Upcoming</td></tr></table>
    """
    events = parse_altiusrt_matches(html, "fih-eurohockey")
    by = {e["home"]["name"] + e["away"]["name"]: e for e in events}
    assert by["SCOWAL"]["status"] == "finished"
    assert by["SCOWAL"]["score"]["home"] == 7
    assert by["TURCZE"]["status"] == "scheduled"
    assert by["TURCZE"]["score"]["home"] is None


def test_championdata_maps_playing_to_live():
    comps = {"competitionDetails": {"competition": [{"id": 12000, "name": "Suncorp Super Netball"}]}}
    fixture = {
        "fixture": {
            "match": [
                {
                    "matchId": 9,
                    "matchStatus": "playing",
                    "homeSquadName": "Fever",
                    "awaySquadName": "Vixens",
                    "homeSquadScore": 21,
                    "awaySquadScore": 18,
                    "period": 2,
                    "utcStartTime": "2026-09-20T06:00:00Z",
                }
            ]
        }
    }

    def getter(url: str) -> FetchResult:
        if "competitions" in url:
            return FetchResult(ok=True, http_status=200, payload=comps)
        return FetchResult(ok=True, http_status=200, payload=fixture)

    adapter = ChampionDataNetballAdapter(getter=getter)
    events = adapter.fetch(FetchRequest(capability="live_scores", competition_id="ssn-australia")).events
    assert events[0]["status"] == "live"
    assert events[0]["score"]["period"] == 2
    assert events[0]["score"]["home"] == 21
