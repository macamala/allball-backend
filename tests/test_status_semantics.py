"""Global Score Centre status/time/score semantics. No league-specific patches."""

from datetime import datetime, timedelta, timezone

from collector.live_state import (
    CONFIRMED_LIVE,
    UNPROVEN_LIVE,
    canonical_status,
    reconcile_live_status,
)
from collector.normalize import normalize_event
from collector.test_support import mock_event
from sports_registry.sports import SPORTS


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_canonical_status_covers_global_model():
    assert canonical_status("1H") == "live"
    assert canonical_status("HT") == "break"
    assert canonical_status("abandoned") == "abandoned"
    assert canonical_status("WO") == "walkover"
    assert canonical_status("unknown") == "unknown"
    assert canonical_status("cancelled") == "cancelled"


def test_elapsed_time_does_not_make_live():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-1)),
        score={"home": None, "away": None},
        status_inferred=True,
        source_fetch_time=_iso(timedelta(0)),
    )
    event = normalize_event(raw, sport_id="football", competition_id="generic-league")
    event = reconcile_live_status(event, now=NOW)
    assert event["status"] == "scheduled"
    assert event["live"] is False
    assert event["live_class"] == UNPROVEN_LIVE


def test_explicit_live_without_score_is_confirmed():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-1)),
        score={"home": None, "away": None},
        source_family="thesportsdb",
        source_status="live",
        source_event_updated_at=_iso(timedelta(minutes=-5)),
        source_fetch_time=_iso(timedelta(0)),
    )
    event = reconcile_live_status(
        normalize_event(raw, sport_id="basketball", competition_id="generic-league"),
        now=NOW,
    )
    assert event["status"] == "live"
    assert event["live_class"] == CONFIRMED_LIVE
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None


def test_missing_score_is_not_zero():
    raw = mock_event(
        status="finished",
        start_time=_iso(timedelta(hours=-3)),
        score={"home": None, "away": None},
    )
    event = normalize_event(raw, sport_id="handball", competition_id="generic-league")
    assert event["score"]["home"] is None
    assert event["score"]["away"] is None


def test_real_zero_is_preserved():
    raw = mock_event(
        status="finished",
        start_time=_iso(timedelta(hours=-3)),
        score={"home": 0, "away": 0},
    )
    event = normalize_event(raw, sport_id="football", competition_id="generic-league")
    assert event["score"]["home"] == 0
    assert event["score"]["away"] == 0


def test_walkover_is_not_cancelled():
    raw = mock_event(status="walkover", start_time=_iso(timedelta(hours=-2)), score={"home": None, "away": None})
    event = normalize_event(raw, sport_id="tennis", competition_id="generic-league")
    assert event["status"] == "walkover"
    assert event["live"] is False


def test_openligadb_elapsed_live_without_progress_is_unproven():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-1)),
        score={"home": 0, "away": 0},
        source_family="openligadb",
        source_status="live",
        source_fetch_time=_iso(timedelta(0)),
    )
    event = reconcile_live_status(
        normalize_event(raw, sport_id="football", competition_id="generic-league"),
        now=NOW,
    )
    assert event["status"] == "scheduled"
    assert event["live"] is False
    assert event["live_class"] == UNPROVEN_LIVE


def test_normalize_keeps_baseball_inning_state():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-2)),
        score={"home": 3, "away": 2, "inning": 7, "inning_half": "bottom", "outs": 1},
    )
    event = normalize_event(raw, sport_id="baseball", competition_id="mlb")
    assert event["score"]["inning"] == 7
    assert event["score"]["inning_half"] == "bottom"
    assert event["score"]["outs"] == 1


def test_family_stale_uses_fetch_time_not_old_observed_at():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-3)),
        score={"home": 3, "away": 3, "inning": 10, "inning_half": "top", "outs": 0},
        source_family="mlb-statsapi",
        source_status="live",
        source_fetch_time=_iso(timedelta(seconds=-5)),
        observed_at=_iso(timedelta(minutes=-10)),
    )
    event = reconcile_live_status(
        normalize_event(raw, sport_id="baseball", competition_id="mlb"),
        now=NOW,
    )
    assert event["status"] == "live"
    assert event["live_class"] == CONFIRMED_LIVE


def test_registry_covers_required_sports():
    slugs = {row["slug"] for row in SPORTS}
    assert len(slugs) >= 41
