"""Sport-aware stale-live reconciliation. No competition/team/id hardcoding."""

from datetime import datetime, timedelta, timezone

from collector.adapters import register_adapter
from collector.collect import run_cycle
from collector.live_horizon import live_horizon
from collector.live_state import public_live_visible, reconcile_live_status
from collector.merge import merge_event_fields
from collector.normalize import normalize_event
from collector.provider import NinkoCollectedSportsDataProvider
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _iso(delta: timedelta) -> str:
    return (NOW + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(raw, sport="football", competition="generic-league"):
    return normalize_event(raw, sport_id=sport, competition_id=competition)


def test_old_stale_live_becomes_stale_not_finished():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-12)),
        score={"home": 1, "away": 0},
        source_family="thesportsdb",
        source_status="live",
        status_inferred=False,
        source_event_updated_at=_iso(timedelta(hours=-12)),
        source_fetch_time=_iso(timedelta(hours=-12)),
    )
    event = reconcile_live_status(_norm(raw), now=NOW)
    assert event["status"] == "stale"
    assert event["live"] is False
    assert event["score"]["home"] == 1
    assert canonical_source_live(event)
    assert not public_live_visible(event, now=NOW)


def canonical_source_live(event):
    from collector.live_state import is_live

    return is_live(event.get("source_status") or "")


def test_fresh_live_stays_live():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-1)),
        score={"home": 0, "away": 0},
        source_event_updated_at=_iso(timedelta(minutes=-10)),
        source_fetch_time=_iso(timedelta(0)),
        source_family="thesportsdb",
        source_status="live",
    )
    event = reconcile_live_status(_norm(raw), now=NOW)
    assert event["status"] == "live"
    assert public_live_visible(event, now=NOW)


def test_fresh_finished_stays_finished():
    raw = mock_event(
        status="finished",
        start_time=_iso(timedelta(hours=-3)),
        score={"home": 2, "away": 1},
        source_event_updated_at=_iso(timedelta(hours=-1)),
    )
    event = reconcile_live_status(_norm(raw), now=NOW)
    assert event["status"] == "finished"
    assert event["score"]["home"] == 2


def test_a_live_b_finished_canonical_finished():
    start = _iso(timedelta(hours=-2))
    live = _norm(
        mock_event(
            status="live",
            start_time=start,
            score={"home": 1, "away": 0},
            source_fetch_time=_iso(timedelta(0)),
        )
    )
    finished = _norm(
        mock_event(
            status="finished",
            start_time=start,
            score={"home": 2, "away": 1},
            source_event_updated_at=_iso(timedelta(minutes=-5)),
            source_fetch_time=_iso(timedelta(0)),
        )
    )
    merged = merge_event_fields(live, finished, incoming_is_higher_priority=False, incoming_source_id="b")
    merged = reconcile_live_status(merged, counterparts=[live, finished], now=NOW)
    assert merged["status"] == "finished"
    assert merged["score"]["home"] == 2
    assert not public_live_visible(merged, now=NOW)


def test_a_stale_live_b_unavailable_is_stale_not_fabricated_finished():
    live = _norm(
        mock_event(
            status="live",
            start_time=_iso(timedelta(hours=-12)),
            score={"home": 0, "away": 0},
            source_family="thesportsdb",
            source_status="live",
            status_inferred=False,
            source_event_updated_at=_iso(timedelta(hours=-12)),
            source_fetch_time=_iso(timedelta(hours=-12)),
        )
    )
    event = reconcile_live_status(live, counterparts=[], now=NOW)
    assert event["status"] == "stale"
    assert event["score"]["home"] == 0
    assert event["status_reconciliation"] == "horizon_exceeded_source_still_live"


def test_tennis_long_duration_stays_live():
    raw = mock_event(
        status="live",
        start_time=_iso(timedelta(hours=-11)),
        score={"home": 1, "away": 1},
        source_event_updated_at=_iso(timedelta(minutes=-10)),
        source_family="wta-json",
        source_status="live",
    )
    event = reconcile_live_status(_norm(raw, sport="tennis", competition="generic-tour"), now=NOW)
    assert live_horizon(sport_id="tennis") > timedelta(hours=8)
    assert event["status"] == "live"
    assert public_live_visible(event, now=NOW)


def test_future_scheduled_not_stale():
    raw = mock_event(status="scheduled", start_time=_iso(timedelta(days=2)))
    event = reconcile_live_status(_norm(raw), now=NOW)
    assert event["status"] == "scheduled"
    assert not public_live_visible(event, now=NOW)


def test_postponed_not_finished():
    raw = mock_event(status="postponed", start_time=_iso(timedelta(hours=-20)))
    event = reconcile_live_status(_norm(raw), now=NOW)
    assert event["status"] == "postponed"


def test_live_api_excludes_stale_row():
    adapter = DeterministicMockAdapter("stale-live-src")
    adapter.events = [
        mock_event(
            id="old-live",
            status="live",
            start_time=_iso(timedelta(hours=-12)),
            score={"home": 1, "away": 0},
        )
    ]
    register_adapter("stale-live-src", lambda source_id="stale-live-src": adapter)
    db = _session()
    try:
        _source(db, "stale-live-src", "stale-live-src")
        _competition(db, "england-premier-league", "football")
        _map(db, "england-premier-league", "stale-live-src", 10)
        db.commit()
        run_cycle(db, capabilities=["live_scores"])
        db.commit()
        provider = NinkoCollectedSportsDataProvider()
        live = provider.get_events(status="live")
        all_events = provider.get_events()
        assert live == []
        assert len(all_events) == 1
        assert all_events[0]["status"] in {"stale", "scheduled"}
        assert all_events[0]["score"]["home"] == 1
    finally:
        db.close()
        _cleanup_adapters("stale-live-src")
