"""Live watch set, scheduler lanes, and integrity failure modes."""

from datetime import datetime, timedelta

from collector.incremental import MAX_BACKGROUND_PHYSICAL, MAX_LIVE_PHYSICAL, select_fair_groups
from collector.merge import merge_event_fields
from collector.models import SportsEvent, SportsLiveWatch
from collector.status_transitions import allowed_status_transition, apply_or_reject
from collector.util import dump_json
from collector.watch_set import in_kickoff_watch_window, rebuild_watch_set
from collector.live_state import CONFIRMED_LIVE, reconcile_live_status
from tests.test_collector_architecture import _session


NOW = datetime(2026, 9, 19, 12, 0, 0)


def _event(db, **kwargs):
    row = SportsEvent(
        event_id=kwargs.get("event_id", "ninko-evt-watch-1"),
        sport_id=kwargs.get("sport_id", "football"),
        competition_id=kwargs.get("competition_id", "germany-2-bundesliga"),
        event_family="team_match",
        status=kwargs.get("status", "scheduled"),
        start_time=kwargs.get("start_time", NOW),
        score_json=dump_json(kwargs.get("score") or {"home": None, "away": None}),
        extra_json=dump_json(kwargs.get("extra") or {"start_precision": "EXACT_TIME"}),
        fingerprint=kwargs.get("fingerprint", kwargs.get("event_id", "ninko-evt-watch-1")),
        display_eligible=True,
        live=kwargs.get("live", False),
    )
    db.add(row)
    db.flush()
    return row


def test_kickoff_passed_without_source_live_stays_scheduled():
    event = {
        "status": "scheduled",
        "start_time": (NOW - timedelta(hours=1)).isoformat() + "Z",
        "source_status": "scheduled",
        "status_inferred": False,
        "source_family": "openligadb",
        "score": {"home": None, "away": None},
        "sport": "football",
    }
    out = reconcile_live_status(event, now=NOW)
    assert out["status"] == "scheduled"
    assert out.get("live") is False


def test_candidate_enters_watch_set_still_scheduled():
    db = _session()
    try:
        start = NOW + timedelta(minutes=3)
        _event(db, start_time=start, extra={"start_precision": "EXACT_TIME", "live_class": None})
        db.commit()
        summary = rebuild_watch_set(db, now=NOW)
        assert summary["watched"] == 1
        watch = db.query(SportsLiveWatch).one()
        assert watch.reason == "KICKOFF_WINDOW"
        row = db.query(SportsEvent).one()
        assert row.status == "scheduled"
    finally:
        db.close()


def test_date_only_never_enters_exact_time_watch():
    db = _session()
    try:
        _event(
            db,
            start_time=datetime(2026, 9, 19, 0, 0, 0),
            extra={"start_precision": "DATE_ONLY"},
        )
        db.commit()
        row = db.query(SportsEvent).one()
        assert in_kickoff_watch_window(row, now=NOW) is False
        rebuild_watch_set(db, now=NOW)
        assert db.query(SportsLiveWatch).count() == 0
    finally:
        db.close()


def test_explicit_live_enters_watch_and_stays_live():
    db = _session()
    try:
        _event(
            db,
            status="live",
            live=True,
            extra={"start_precision": "EXACT_TIME", "live_class": CONFIRMED_LIVE, "source_status": "live"},
        )
        db.commit()
        rebuild_watch_set(db, now=NOW)
        assert db.query(SportsLiveWatch).one().reason == "EXPLICIT_LIVE"
    finally:
        db.close()


def test_live_score_zero_zero_preserved():
    current = {"status": "live", "score": {"home": 0, "away": 0}, "source_fetch_time": "2026-09-19T12:00:00Z"}
    incoming = {
        "status": "live",
        "score": {"home": 0, "away": 0, "minute": 12},
        "source_fetch_time": "2026-09-19T12:01:00Z",
    }
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="openligadb")
    assert merged["score"]["home"] == 0
    assert merged["score"]["away"] == 0
    assert merged["score"]["minute"] == 12


def test_atomic_score_status_period_bundle():
    current = {"status": "live", "score": {"home": 0, "away": 0, "period": 1}, "periods": [{"home": 0, "away": 0}]}
    incoming = {
        "status": "break",
        "score": {"home": 1, "away": 0, "period": 1, "minute": 45},
        "periods": [{"home": 1, "away": 0}],
        "source_fetch_time": "2026-09-19T12:02:00Z",
    }
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="wta-json")
    assert merged["status"] == "break"
    assert merged["score"]["home"] == 1
    assert merged["periods"][0]["home"] == 1
    assert merged["field_freshness"]["score"]["source"] == "wta-json"


def test_newer_finished_beats_stale_live():
    current = {"status": "live", "observed_at": "2026-09-19T10:00:00Z", "score": {"home": 1, "away": 0}}
    incoming = {"status": "finished", "observed_at": "2026-09-19T12:00:00Z", "score": {"home": 2, "away": 0}}
    assert allowed_status_transition(current, incoming) is True
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=False, incoming_source_id="openligadb")
    assert merged["status"] == "finished"


def test_stale_live_cannot_overwrite_finished():
    current = {"status": "finished", "observed_at": "2026-09-19T12:00:00Z", "score": {"home": 2, "away": 0}}
    incoming = {"status": "live", "observed_at": "2026-09-19T10:00:00Z", "score": {"home": 1, "away": 0}}
    rejected = apply_or_reject(current, incoming)
    assert rejected["status"] == "finished"


def test_live_lane_not_starved_by_discovery():
    now = NOW
    jobs = []
    for i in range(40):
        jobs.append(
            {
                "job_key": f"discover:{i}:wiki",
                "family": f"wiki-{i}",
                "urgency": "DISCOVERY_ACTIVE",
                "competition_id": f"c{i}",
                "priority": 10,
                "last_run_at": now - timedelta(hours=2),
                "next_due_at": now - timedelta(hours=1),
            }
        )
    jobs.append(
        {
            "job_key": "refresh:live:wta-json:live_scores",
            "family": "wta-json",
            "urgency": "LIVE",
            "competition_id": "wta-tour",
            "priority": 1,
            "last_run_at": now - timedelta(minutes=2),
            "next_due_at": now - timedelta(seconds=1),
        }
    )
    selected, stats = select_fair_groups(jobs, now)
    keys = [job["job_key"] for group in selected for job in group]
    assert "refresh:live:wta-json:live_scores" in keys
    assert stats["live_groups_selected"] >= 1
    assert len(selected) <= MAX_LIVE_PHYSICAL + MAX_BACKGROUND_PHYSICAL


def test_worker_restart_rebuilds_watch_set():
    db = _session()
    try:
        _event(
            db,
            event_id="ninko-evt-live-1",
            fingerprint="fp-live-1",
            status="live",
            live=True,
            extra={"start_precision": "EXACT_TIME", "live_class": CONFIRMED_LIVE},
        )
        _event(
            db,
            event_id="ninko-evt-soon-1",
            fingerprint="fp-soon-1",
            start_time=NOW + timedelta(minutes=2),
            extra={"start_precision": "EXACT_TIME"},
        )
        db.commit()
        rebuild_watch_set(db, now=NOW)
        assert db.query(SportsLiveWatch).count() == 2
    finally:
        db.close()
