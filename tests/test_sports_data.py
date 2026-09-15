"""Sports-data and predictions foundation: honest empties, no fake fixtures."""

from fastapi.testclient import TestClient

from app import app
from prediction_engine import (
    MODEL_VERSION,
    UnconfiguredPredictionEngine,
    apply_result,
    market_for_sport,
)
from sports_provider import DisconnectedSportsDataProvider, normalize_legacy_match


def test_sports_data_is_empty_not_fake():
    with TestClient(app) as client:
        scores = client.get("/sports-data/scores").json()
        assert scores["connected"] is False
        assert scores["matches"] == []
        assert scores["events"] == []
        assert scores["live"] == []
        assert scores["finished"] == []
        standings = client.get("/sports-data/standings?league=premier-league").json()
        assert standings["rows"] == []
        match = client.get("/sports-data/matches/abc").json()
        assert match["header"] is None
        assert match["event"] is None
        team = client.get("/sports-data/teams/arsenal").json()
        assert team["available"] is False
        events = client.get("/sports-data/events?sport=football").json()
        assert events["connected"] is False
        assert events["events"] == []
        competitions = client.get("/sports-data/competitions?sport=football").json()
        assert competitions["competitions"] == []
        blob = str(scores) + str(events) + str(competitions)
        assert "Arsenal" not in blob
        assert "Liverpool" not in blob


def test_predictions_are_empty_not_fake():
    with TestClient(app) as client:
        listing = client.get(
            "/predictions?sport=football&competition=uefa-champions-league&period=this-week"
        ).json()
        assert listing["connected"] is False
        assert listing["items"] == []
        assert listing["count"] == 0
        assert listing["performance_available"] is False
        assert listing["market"] == "1x2"
        assert "Arsenal" not in str(listing)
        assert "Liverpool" not in str(listing)
        basketball = client.get("/predictions?sport=basketball").json()
        assert basketball["market"] == "winner"
        tennis = client.get("/predictions?sport=tennis").json()
        assert tennis["market"] == "winner"
        detail = client.get("/predictions/evt-123").json()
        assert detail["prediction"] is None
        assert detail["event"] is None
        assert detail["evidence"] == []
        perf = client.get("/predictions/performance").json()
        assert perf["available"] is False
        assert perf["windows"]["last_7_days"] is None


def test_sitemap_includes_predictions_hub_only():
    with TestClient(app) as client:
        sitemap = client.get("/sitemap.xml")
        assert sitemap.status_code == 200
        assert "/predictions" in sitemap.text
        assert "/predictions/football/champions-league" not in sitemap.text


def test_prediction_engine_does_not_invent_odds():
    engine = UnconfiguredPredictionEngine()
    event = normalize_legacy_match(
        {
            "id": "evt-1",
            "sport": "football",
            "home": "Home FC",
            "away": "Away FC",
            "status": "scheduled",
        }
    )
    assert engine.predict(event) is None
    assert market_for_sport("football") == "1x2"
    assert market_for_sport("basketball") == "winner"
    assert market_for_sport("tennis") == "winner"
    assert market_for_sport("motorsport") is None
    assert MODEL_VERSION.startswith("ninko-")


def test_disconnected_provider_has_no_fixtures():
    provider = DisconnectedSportsDataProvider()
    assert provider.status()["connected"] is False
    assert provider.get_events() == []
    assert provider.get_live_events() == []
    assert provider.get_event("any") is None
    assert provider.get_standings("nba") == []
    assert provider.get_team_form("t1") is None


def test_apply_result_does_not_rewrite_probabilities():
    class Row:
        predicted_outcome = "home"
        home_win_pct = 52.0
        draw_pct = 27.0
        away_win_pct = 21.0
        evidence_json = '[{"type":"recent_form","facts":{"wins":4,"matches":5}}]'
        evaluated_at = None
        actual_outcome = None
        was_correct = None

    row = apply_result(Row(), "away")
    assert row.home_win_pct == 52.0
    assert row.draw_pct == 27.0
    assert row.away_win_pct == 21.0
    assert row.actual_outcome == "away"
    assert row.was_correct is False
    assert "recent_form" in row.evidence_json
