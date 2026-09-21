from collector.merge import merge_event_fields
from collector.normalize import normalize_event
from collector.test_support import mock_event


def test_scheduled_null_null_remains_null():
    event = normalize_event(
        {
            "home": {"name": "Alpha"},
            "away": {"name": "Beta"},
            "status": "scheduled",
            "score": {"home": None, "away": None},
            "start_time": "2026-09-20T18:00:00Z",
        },
        sport_id="football",
        competition_id="england-premier-league",
    )
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None


def test_scheduled_provider_zero_zero_becomes_null():
    event = normalize_event(
        {
            "home": {"name": "Alpha"},
            "away": {"name": "Beta"},
            "status": "scheduled",
            "score": {"home": 0, "away": 0},
            "start_time": "2026-09-20T18:00:00Z",
        },
        sport_id="football",
        competition_id="england-premier-league",
    )
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None


def test_real_zero_zero_finished_preserved():
    event = normalize_event(
        {
            "home": {"name": "Alpha"},
            "away": {"name": "Beta"},
            "status": "finished",
            "score": {"home": 0, "away": 0},
            "start_time": "2026-09-20T18:00:00Z",
        },
        sport_id="football",
        competition_id="england-premier-league",
    )
    assert event["score"]["home"] == 0
    assert event["score"]["away"] == 0


def test_null_observation_cannot_erase_trusted_score():
    current = mock_event(
        status="finished",
        score={"home": 2, "away": 1, "period": 2},
        retrieved_at="2026-09-20T20:00:00Z",
        observed_at="2026-09-20T20:00:00Z",
    )
    incoming = mock_event(
        status="finished",
        score={"home": None, "away": None},
        retrieved_at="2026-09-20T21:00:00Z",
        observed_at="2026-09-20T21:00:00Z",
    )
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="src-b")
    assert merged["score"]["home"] == 2
    assert merged["score"]["away"] == 1
    assert merged["score"]["period"] == 2


def test_scored_finished_beats_stale_scheduled():
    current = mock_event(
        status="scheduled",
        score={"home": None, "away": None},
        retrieved_at="2026-09-20T21:00:00Z",
        observed_at="2026-09-20T21:00:00Z",
    )
    incoming = mock_event(
        status="finished",
        score={"home": 3, "away": 2},
        retrieved_at="2026-09-20T19:00:00Z",
        observed_at="2026-09-20T19:00:00Z",
    )
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=False, incoming_source_id="src-b")
    assert merged["status"] == "finished"
    assert merged["score"]["home"] == 3
    assert merged["score"]["away"] == 2


def test_complementary_provider_score_merge():
    current = mock_event(
        status="live",
        score={"home": None, "away": None, "clock": "67"},
        retrieved_at="2026-09-20T20:10:00Z",
        observed_at="2026-09-20T20:10:00Z",
    )
    incoming = mock_event(
        status="live",
        score={"home": 2, "away": 1},
        retrieved_at="2026-09-20T20:09:00Z",
        observed_at="2026-09-20T20:09:00Z",
    )
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=False, incoming_source_id="src-b")
    assert merged["status"] == "live"
    assert merged["score"]["home"] == 2
    assert merged["score"]["away"] == 1
    assert merged["score"]["clock"] == "67"


def test_period_set_inning_preserved_when_newer_score_is_null():
    current = mock_event(
        status="live",
        score={"home": 1, "away": 0, "set": 2, "inning": 5, "quarter": 3},
        retrieved_at="2026-09-20T20:00:00Z",
        observed_at="2026-09-20T20:00:00Z",
    )
    incoming = mock_event(
        status="live",
        score={"home": None, "away": None, "clock": "12:01"},
        retrieved_at="2026-09-20T20:02:00Z",
        observed_at="2026-09-20T20:02:00Z",
    )
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="src-a")
    assert merged["score"]["home"] == 1
    assert merged["score"]["set"] == 2
    assert merged["score"]["inning"] == 5
    assert merged["score"]["quarter"] == 3
    assert merged["score"]["clock"] == "12:01"
