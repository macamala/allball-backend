from collector.adapters import FetchRequest, FetchResult
from collector.adapters_final18 import GbgbMeetingJsonAdapter, PgaGraphqlAdapter
from collector.adapters_sofascore import SofaScoreWebAdapter
from collector.coverage_capability import annotate_record
from collector.family_caps import family_caps, supports_live
from collector.family_catalog import adapter_key_for
from collector.family_health import family_blocks_live_path
from collector.registry import build_runtime_registry
import collector.adapters_sofascore as sofa_mod


def test_fotmob_and_pga_adapters_are_wired():
    runtime = build_runtime_registry()
    families = {(row["competition_id"], row["source_family"]) for row in runtime["mappings"] if row.get("enabled")}
    assert ("italy-serie-a", "fotmob") in families
    assert ("nz-national-league", "sofascore-web") in families
    assert ("nz-national-league", "fotmob") not in families
    assert ("pga-tour", "pga-graphql") in families
    assert ("ssn-australia", "championdata-netball") in families
    assert ("gbgb-meetings", "gbgb-meeting-json") in families
    assert adapter_key_for("click-tt") == "click-tt-remix"
    assert adapter_key_for("pga-graphql") == "pga-graphql"


def test_rapid_result_families_are_not_live():
    for family in ("gbgb-meeting-json", "gri-web", "hrnsw-web", "usta-web", "letrot-web", "standardbred-canada-web"):
        assert supports_live(family) is False
        assert family_caps(family).get("capability_class") == "RAPID_RESULT"


def test_europeantour_blocked_from_live_path():
    assert family_caps("europeantour-web").get("production_status") == "ACCESS_BLOCKED"
    assert family_blocks_live_path("europeantour-web") is True


def test_gbgb_finished_race_is_never_live():
    payload = {
        "items": [{"meetingId": 1}],
    }
    meeting = [
        {
            "meetingId": 1,
            "trackName": "Yarmouth",
            "races": [
                {
                    "raceId": 9,
                    "raceNumber": 1,
                    "raceTime": "14:32:00",
                    "traps": [{"dogName": "Swift Winner", "resultPosition": 1, "trapNumber": 1}],
                }
            ],
        }
    ]

    def getter(url):
        if "meeting" in url:
            return FetchResult(ok=True, http_status=200, payload=meeting)
        return FetchResult(ok=True, http_status=200, payload=payload)

    events = GbgbMeetingJsonAdapter(getter=getter).fetch(FetchRequest(capability="snapshot", competition_id="gbgb-meetings")).events
    assert events
    assert all(row["status"] != "live" for row in events)
    assert events[0]["status"] == "finished"


def test_pga_uses_post_upcoming_schedule_not_get():
    calls = []

    def poster(body):
        calls.append(body)
        q = str(body.get("query") or "")
        if "leaderboardV3" in q:
            return FetchResult(ok=True, http_status=200, payload={"data": {"leaderboardV3": {"id": "R1", "players": []}}})
        return FetchResult(
            ok=True,
            http_status=200,
            payload={"data": {"upcomingSchedule": {"tournaments": [{"id": "R1", "tournamentName": "Biltmore", "tournamentStatus": "IN_PROGRESS"}]}}},
        )

    events = PgaGraphqlAdapter(poster=poster).fetch(FetchRequest(capability="live_scores", competition_id="pga-tour")).events
    assert any("upcomingSchedule" in str(body.get("query")) for body in calls)
    assert events[0]["status"] == "live"
    assert events[0]["extra"]["status_inferred"] is False


def test_sofascore_nz_unique_id_local_board_mapping():
    sofa_mod._BOARD.clear()
    payload = {
        "events": [
            {
                "id": 1,
                "homeTeam": {"name": "Auckland"},
                "awayTeam": {"name": "Wellington"},
                "status": {"type": "inprogress"},
                "homeScore": {"current": 1},
                "awayScore": {"current": 0},
                "tournament": {
                    "name": "National League",
                    "uniqueTournament": {"id": 594, "name": "New Zealand National League"},
                    "category": {"name": "New Zealand"},
                },
            },
            {
                "id": 2,
                "homeTeam": {"name": "Wrong"},
                "awayTeam": {"name": "League"},
                "status": {"type": "inprogress"},
                "homeScore": {"current": 2},
                "awayScore": {"current": 2},
                "tournament": {
                    "name": "Championship",
                    "uniqueTournament": {"id": 8870, "name": "Championship"},
                    "category": {"name": "England"},
                },
            },
        ]
    }
    urls = []

    def getter(url):
        urls.append(url)
        return FetchResult(ok=True, http_status=200, payload=payload)

    adapter = SofaScoreWebAdapter(getter=getter)
    events = adapter.fetch(FetchRequest(capability="live_scores", competition_id="nz-national-league")).events
    assert len(events) == 1
    assert events[0]["home"]["name"] == "Auckland"
    assert all("unique-tournament" not in url for url in urls)


def test_matrix_capability_annotation():
    live = annotate_record({"competition": "pga-tour"}, [{"family": "pga-graphql"}])
    assert live["capability"] == "LIVE"
    rapid = annotate_record({"competition": "gbgb-meetings"}, [{"family": "gbgb-meeting-json"}])
    assert rapid["capability"] == "RAPID_RESULT"
    blocked = annotate_record({"competition": "european-challenge-tour"}, [{"family": "europeantour-web"}])
    assert blocked["capability"] == "ACCESS_BLOCKED"
    results = annotate_record({"competition": "ettu-events"}, [{"family": "ettu-web"}])
    assert results["capability"] == "RESULTS_ONLY"
