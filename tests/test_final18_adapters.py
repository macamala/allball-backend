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
    assert len(events) == 1
    assert events[0]["id"] == "pga:R2026060"
    assert events[0]["status"] == "live"
    assert events[0]["score"]["home"] == "-12"
    assert events[0]["classification"][0]["player"] == "Scottie Scheffler"
    assert events[0]["classification"][0]["thru"] == "14"
    assert ":" not in events[0]["id"].split("pga:", 1)[-1]


def test_click_tt_remix_is_terms_blocked():
    called = []
    adapter = ClickTtRemixAdapter(getter=lambda url: called.append(url) or FetchResult(ok=True, http_status=200, payload={}))
    result = adapter.fetch(FetchRequest(capability="live_scores", competition_id="germany-click-tt"))
    assert called == []
    assert result.restricted is True
    assert result.events == []
    assert result.empty_reason == "TERMS"


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
