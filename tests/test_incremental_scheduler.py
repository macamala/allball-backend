from datetime import datetime, timedelta

from collector.adapters import FetchRequest, FetchResult, register_adapter
from collector.cadence import interval_for
from collector.collect import collect_competition, run_cycle
from collector.dirty import event_unchanged, observation_signature
from collector.family_caps import is_static_family, supports_live
from collector.family_health import note_family_failure, reset_family_health
from collector.flags import scheduler_enabled
from collector.incremental import (
    MAX_BACKGROUND_PHYSICAL,
    build_due_jobs,
    coalesce_jobs,
    request_identity,
    run_incremental_tick,
    select_fair_groups,
)
from collector.lock import acquire_scheduler_lock
from collector.metrics import reset_metrics
from collector.models import SportsEvent, SportsSource, SportsSourceCompetition
from collector.test_support import mock_event
from collector.urgency import classify_event
from collector.util import dump_json
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def test_urgency_promotion_and_demotion():
    now = datetime(2026, 9, 19, 12, 0, 0)
    assert classify_event("scheduled", now + timedelta(minutes=10), now=now) == "IMMINENT"
    assert classify_event("live", now - timedelta(minutes=5), now=now) == "LIVE"
    assert classify_event("finished", now - timedelta(minutes=30), now=now) == "RECENTLY_FINISHED"
    assert classify_event("finished", now - timedelta(hours=5), now=now) == "HISTORICAL"
    assert classify_event("scheduled", now + timedelta(days=3), now=now) == "NEAR_FUTURE"
    assert classify_event("scheduled", now + timedelta(days=20), now=now) == "FUTURE"
    assert classify_event("scheduled", now + timedelta(days=40), now=now) == "LONG_FUTURE"


def test_static_family_not_live_interval():
    assert supports_live("wikipedia") is False
    assert is_static_family("wikipedia") is True
    assert interval_for("wikipedia", "LIVE") >= 86400
    assert interval_for("thesportsdb", "LIVE") >= 90
    assert interval_for("openligadb", "LIVE") <= 90


def test_coalesce_shared_request_one_group():
    jobs = [
        {"job_key": "a", "request_key": "thesportsdb|http://x", "competition_id": "c1"},
        {"job_key": "b", "request_key": "thesportsdb|http://x", "competition_id": "c2"},
        {"job_key": "c", "request_key": "openligadb|http://y", "competition_id": "c3"},
    ]
    groups = coalesce_jobs(jobs)
    assert len(groups) == 2
    assert len(groups[0]) == 2


def test_kill_switch_stops_tick(monkeypatch):
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    db = _session()
    try:
        out = run_incremental_tick(db)
        assert out["stopped"] is True
        assert out["reason"] == "kill_switch"
    finally:
        db.close()


def test_second_scheduler_denied_lease():
    db = _session()
    try:
        assert acquire_scheduler_lock(db, owner="sched-a", ttl_seconds=120) is True
        db.commit()
        assert acquire_scheduler_lock(db, owner="sched-b", ttl_seconds=120) is False
    finally:
        db.close()


def test_unchanged_event_skips_second_write(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "true")
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "true")
    reset_metrics()

    class Echo:
        def fetch(self, request: FetchRequest) -> FetchResult:
            return FetchResult(
                ok=True,
                http_status=200,
                events=[
                    mock_event(
                        id="same-1",
                        home={"name": "Alpha"},
                        away={"name": "Beta"},
                        status="scheduled",
                        start_time="2026-09-19T18:00:00Z",
                    )
                ],
            )

    register_adapter("inc-echo", lambda source_id="inc-echo": Echo())
    db = _session()
    try:
        src = _source(db, "inc-echo", "inc-echo")
        src.upstream_family = "openligadb"
        _competition(db, "inc-league", "football")
        mapping = _map(db, "inc-league", "inc-echo", 10)
        db.commit()
        run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).count() == 1
        from collector.metrics import snapshot

        before = snapshot().get("unchanged_skipped") or 0
        run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).count() == 1
        after = snapshot().get("unchanged_skipped") or 0
        assert after >= before + 1
        assert db.query(SportsEvent).count() == 1
        row = db.query(SportsEvent).one()
        extra = __import__("collector.util", fromlist=["load_json"]).load_json(row.extra_json, {}) or {}
        assert extra.get("obs_signature")
    finally:
        db.close()
        _cleanup_adapters("inc-echo")


def test_live_job_due_from_canonical_event():
    db = _session()
    try:
        src = _source(db, "live-echo", "live-echo")
        src.upstream_family = "openligadb"
        _competition(db, "live-league", "football")
        mapping = _map(
            db,
            "live-league",
            "live-echo",
            10,
            upstream_family="openligadb",
            source_config_json=dump_json({"url": "http://example.test/live"}),
        )
        db.flush()
        now = datetime.utcnow()
        db.add(
            SportsEvent(
                event_id="ninko-evt-live-1",
                sport_id="football",
                competition_id="live-league",
                event_family="team_match",
                status="live",
                start_time=now,
                fingerprint="fp-live-1",
            )
        )
        db.commit()
        jobs = build_due_jobs(db, now=now)
        live = [row for row in jobs if row["urgency"] == "LIVE"]
        assert live
        assert live[0]["capability"] == "live_scores"
        assert interval_for("openligadb", "LIVE") <= 90
    finally:
        db.close()


def test_a_fail_uses_fallback(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "true")

    class Boom:
        def fetch(self, request: FetchRequest) -> FetchResult:
            return FetchResult(ok=False, http_status=500, classification="NETWORK_FAILURE", error="down")

    class Good:
        def fetch(self, request: FetchRequest) -> FetchResult:
            return FetchResult(
                ok=True,
                http_status=200,
                events=[mock_event(id="fb-1", home={"name": "H"}, away={"name": "A"})],
            )

    register_adapter("boom-a", lambda source_id="boom-a": Boom())
    register_adapter("good-b", lambda source_id="good-b": Good())
    db = _session()
    try:
        a = _source(db, "boom-a", "boom-a")
        a.upstream_family = "family-a"
        b = _source(db, "good-b", "good-b")
        b.upstream_family = "family-b"
        _competition(db, "fail-league", "football")
        _map(db, "fail-league", "boom-a", 10)
        _map(db, "fail-league", "good-b", 20)
        for row in db.query(SportsSourceCompetition).filter_by(competition_id="fail-league").all():
            row.upstream_family = "family-a" if row.source_id == "boom-a" else "family-b"
        db.commit()
        from collector.models import SportsCompetition

        stats = collect_competition(
            db,
            db.query(SportsCompetition).filter_by(competition_id="fail-league").one(),
            "fixtures",
            sleeper=lambda _d: None,
            include_fallback=True,
        )
        db.commit()
        assert db.query(SportsEvent).count() == 1
        assert stats["written"] >= 1
    finally:
        db.close()
        _cleanup_adapters("boom-a", "good-b")


def test_date_query_filters_upcoming(monkeypatch):
    from fastapi.testclient import TestClient
    from app import app

    client = TestClient(app)
    res = client.get("/sports-data/upcoming", params={"date": "2026-09-19"})
    assert res.status_code == 200
    payload = res.json()
    assert "events" in payload
    for event in payload.get("events") or []:
        start = event.get("start_time") or ""
        assert start[:10] == "2026-09-19" or not start


def test_tsdb_cooldown_skips_due_jobs():
    reset_family_health()
    note_family_failure("thesportsdb", http_status=429, error_type="RATE_LIMITED", retry_after_s=120)
    from collector.family_health import family_rate_limited

    assert family_rate_limited("thesportsdb") is True
    db = _session()
    try:
        src = _source(db, "tsdb-src", "inc-echo")
        src.upstream_family = "thesportsdb"
        _competition(db, "tsdb-league", "football")
        mapping = _map(db, "tsdb-league", "tsdb-src", 10, upstream_family="thesportsdb")
        mapping.source_config_json = dump_json({"url": "https://www.thesportsdb.com/x"})
        now = datetime.utcnow()
        db.add(
            SportsEvent(
                event_id="ninko-evt-tsdb-live",
                sport_id="football",
                competition_id="tsdb-league",
                event_family="team_match",
                status="live",
                start_time=now,
                fingerprint="fp-tsdb-live",
            )
        )
        db.commit()
        jobs = build_due_jobs(db, now=now)
        assert all(row["family"] != "thesportsdb" or row["urgency"] != "LIVE" for row in jobs)
    finally:
        db.close()
        reset_family_health()


def test_403_marks_family_blocked():
    reset_family_health()
    note_family_failure("wiki-html", http_status=403, retry_after_s=900)
    from collector.family_health import family_access_blocked, family_rate_limited

    assert family_access_blocked("wiki-html") is True
    assert family_rate_limited("wiki-html") is True
    reset_family_health()


def test_worker_restart_recovers_due_slot():
    db = _session()
    try:
        from collector.incremental import mark_slot
        from collector.models import SportsSchedulerSlot

        now = datetime.utcnow()
        job = {
            "job_key": "refresh:restart-league:openligadb:fixtures",
            "competition_id": "restart-league",
            "family": "openligadb",
            "urgency": "TODAY",
            "reason": "restart",
            "interval": 600,
            "priority": 4,
        }
        mark_slot(db, job, status="ok", now=now - timedelta(hours=2))
        db.commit()
        slot = db.query(SportsSchedulerSlot).filter_by(job_key=job["job_key"]).one()
        assert slot.next_due_at <= now
        from collector.incremental import _due

        assert _due(slot, 600, now) is True
    finally:
        db.close()


def test_mapped_secondary_family_gets_refresh_job():
    db = _session()
    try:
        primary = _source(db, "ss-src", "sportscore")
        primary.upstream_family = "sportscore"
        secondary = _source(db, "ol-src", "openligadb")
        secondary.upstream_family = "openligadb"
        _competition(db, "germany-bundesliga", "football")
        _map(db, "germany-bundesliga", "ss-src", 10, upstream_family="sportscore")
        _map(db, "germany-bundesliga", "ol-src", 20, upstream_family="openligadb")
        now = datetime.utcnow()
        db.add(
            SportsEvent(
                event_id="ninko-evt-bl-1",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                status="scheduled",
                start_time=now + timedelta(hours=3),
                fingerprint="fp-bl-1",
            )
        )
        db.commit()
        jobs = build_due_jobs(db, now=now)
        families = {row["family"] for row in jobs if row["competition_id"] == "germany-bundesliga"}
        assert "sportscore" in families
        assert "openligadb" in families
    finally:
        db.close()


def test_fair_selection_includes_starved_openliga():
    from collector.incremental import select_fair_groups

    now = datetime(2026, 9, 19, 12, 0, 0)
    jobs = []
    for index in range(20):
        jobs.append(
            {
                "job_key": f"refresh:aaa-league-{index:02d}:sportscore:fixtures",
                "competition_id": f"aaa-league-{index:02d}",
                "family": "sportscore",
                "urgency": "TODAY",
                "priority": 4,
                "request_key": f"sportscore|{index}",
                "last_run_at": now - timedelta(seconds=30),
                "next_due_at": now - timedelta(seconds=10),
            }
        )
    jobs.append(
        {
            "job_key": "refresh:germany-bundesliga:openligadb:fixtures",
            "competition_id": "germany-bundesliga",
            "family": "openligadb",
            "urgency": "TODAY",
            "priority": 4,
            "request_key": "openligadb|bl1",
            "last_run_at": None,
            "next_due_at": None,
            "sport": "football",
        }
    )
    groups, stats = select_fair_groups(jobs, now, max_physical=12)
    families = [group[0]["family"] for group in groups]
    assert "openligadb" in families
    assert families[0] == "openligadb"
    assert families.count("sportscore") == 1
    assert stats["selected_groups"] == 2


def test_never_run_families_rotate_through_physical_cap():
    now = datetime(2026, 9, 19, 12, 0, 0)
    family_names = [f"family-{index:02d}" for index in range(13)]
    jobs = [
        {
            "job_key": f"refresh:{name}:fixtures",
            "competition_id": name,
            "family": name,
            "urgency": "TODAY",
            "priority": 4,
            "request_key": f"{name}|url",
            "last_run_at": None,
            "next_due_at": None,
        }
        for name in family_names
    ]
    seen = set()
    for _ in range(3):
        groups, stats = select_fair_groups(jobs, now, max_physical=12)
        assert stats["selected_groups"] == MAX_BACKGROUND_PHYSICAL
        seen.update(group[0]["family"] for group in groups)
    assert len(seen) >= MAX_BACKGROUND_PHYSICAL


def test_fair_selection_prefers_live_over_future():
    from collector.incremental import select_fair_groups

    now = datetime(2026, 9, 19, 12, 0, 0)
    jobs = [
        {
            "job_key": "refresh:far:espn-html:fixtures",
            "competition_id": "aaa-far",
            "family": "espn-html",
            "urgency": "FUTURE",
            "priority": 6,
            "request_key": "espn-html|far",
            "last_run_at": None,
        },
        {
            "job_key": "refresh:live:openligadb:live_scores",
            "competition_id": "zzz-live",
            "family": "openligadb",
            "urgency": "LIVE",
            "priority": 1,
            "request_key": "openligadb|live",
            "last_run_at": now - timedelta(seconds=5),
            "next_due_at": now - timedelta(seconds=1),
        },
    ]
    groups, _stats = select_fair_groups(jobs, now, max_physical=1)
    assert groups[0][0]["family"] == "openligadb"
    assert groups[0][0]["urgency"] == "LIVE"


def test_incremental_tick_promotes_new_observation(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "true")
    from collector.canonical_collapse import promote_observation_enrichment
    from collector.incremental import run_incremental_tick
    from collector.models import SportsEvent
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json

    db = _session()
    try:
        kickoff = datetime(2026, 9, 19, 13, 30, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-keep-tick",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-keep-tick",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 2, "away": 0}),
                participants_json=dump_json({"home": {"name": "Bayern"}, "away": {"name": "Union"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "collapsed_from": ["ninko-evt-obs-tick"],
                        "start_precision": "EXACT_TIME",
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-obs-tick",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-obs-tick",
                start_time=kickoff,
                display_eligible=False,
                canonical_event_id="ninko-evt-keep-tick",
                score_json=dump_json({"home": 9, "away": 9}),
                participants_json=dump_json({"home": {"name": "X"}, "away": {"name": "Y"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": False,
                        "collapse_role": "observation_only",
                        "periods": [{"code": "HT", "home": 3, "away": 0}, {"code": "FT", "home": 7, "away": 0}],
                        "incidents": [{"type": "goal", "minute": 18, "player": "Musiala"}],
                    }
                ),
            )
        )
        db.commit()
        monkeypatch.setattr("collector.incremental.build_due_jobs", lambda *args, **kwargs: [])
        result = run_incremental_tick(db)
        db.commit()
        assert result["enrichment"]["copied"] == 1
        event = NinkoCollectedSportsDataProvider().get_event("ninko-evt-keep-tick")
        assert event["score"]["home"] == 2
        assert event["competition"] == "germany-bundesliga"
        assert event["home"]["name"] == "Bayern"
        assert event["periods"][0]["code"] == "HT"
        assert event["incidents"][0]["player"] == "Musiala"
        assert event.get("start_precision") == "EXACT_TIME"
        assert promote_observation_enrichment(db)["copied"] == 0
    finally:
        db.close()


def test_tick_collapses_duplicate_then_promotes_periods(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "true")
    from collector.incremental import run_incremental_tick
    from collector.models import SportsEvent
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json

    db = _session()
    try:
        kickoff = datetime(2026, 9, 18, 18, 30, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-keep-dup",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-keep-dup",
                start_time=kickoff,
                display_eligible=True,
                primary_source_id="sportscore",
                score_json=dump_json({"home": 7, "away": 0}),
                participants_json=dump_json(
                    {"home": {"name": "FC Bayern München"}, "away": {"name": "1. FC Union Berlin"}}
                ),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "sportscore",
                        "collapsed_from": ["ninko-evt-old-obs"],
                        "start_precision": "EXACT_TIME",
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-ol-dup",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-ol-dup",
                start_time=kickoff,
                display_eligible=True,
                primary_source_id="openligadb",
                score_json=dump_json({"home": 7, "away": 0}),
                participants_json=dump_json(
                    {"home": {"name": "FC Bayern München"}, "away": {"name": "1. FC Union Berlin"}}
                ),
                extra_json=dump_json(
                    {
                        "display_eligible": True,
                        "source_family": "openligadb",
                        "periods": [{"code": "HT", "home": 3, "away": 0}, {"code": "FT", "home": 7, "away": 0}],
                        "incidents": [{"type": "goal", "minute": 18, "player": "J. Musiala"}],
                    }
                ),
            )
        )
        db.commit()
        monkeypatch.setattr("collector.incremental.build_due_jobs", lambda *args, **kwargs: [])
        result = run_incremental_tick(db)
        db.commit()
        assert result["collapse"]["collapsed"] >= 1
        event = NinkoCollectedSportsDataProvider().get_event("ninko-evt-keep-dup")
        assert event["id"] == "ninko-evt-keep-dup"
        assert event["score"]["home"] == 7
        assert event["periods"][0]["code"] == "HT"
        assert event["incidents"][0]["player"] == "J. Musiala"
        hidden = db.query(SportsEvent).filter_by(event_id="ninko-evt-ol-dup").one()
        assert hidden.canonical_event_id == "ninko-evt-keep-dup"
        assert hidden.display_eligible is False
    finally:
        db.close()


def test_two_logical_jobs_one_request_key():
    jobs = [
        {"job_key": "r1", "request_key": "openligadb|http://shared", "competition_id": "c1"},
        {"job_key": "r2", "request_key": "openligadb|http://shared", "competition_id": "c2"},
    ]
    groups = coalesce_jobs(jobs)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_live_family_reserved_against_many_live_urls():
    now = datetime(2026, 9, 19, 12, 0, 0)
    jobs = []
    for index in range(20):
        jobs.append(
            {
                "job_key": f"refresh:ss-{index}:sportscore:live_scores",
                "family": "sportscore",
                "urgency": "LIVE",
                "competition_id": f"ss-{index}",
                "priority": 1,
                "request_key": f"sportscore|http://ss/{index}",
                "last_run_at": now - timedelta(seconds=90),
                "next_due_at": now - timedelta(seconds=10),
            }
        )
    jobs.append(
        {
            "job_key": "refresh:mlb:mlb-statsapi:live_scores",
            "family": "mlb-statsapi",
            "urgency": "LIVE",
            "competition_id": "mlb",
            "priority": 1,
            "request_key": "mlb-statsapi|http://statsapi",
            "last_run_at": now - timedelta(seconds=90),
            "next_due_at": now - timedelta(seconds=10),
        }
    )
    groups, stats = select_fair_groups(jobs, now)
    families = {group[0]["family"] for group in groups}
    assert "mlb-statsapi" in families
    assert stats["live_families_starved"] == 0
    assert stats["live_families_waiting"] == 2
    assert len(groups) <= 12


def test_imminent_does_not_displace_confirmed_live():
    now = datetime(2026, 9, 19, 12, 0, 0)
    jobs = [
        {
            "job_key": "refresh:mlb:mlb-statsapi:live_scores",
            "family": "mlb-statsapi",
            "urgency": "LIVE",
            "competition_id": "zzz-mlb",
            "priority": 1,
            "request_key": "mlb-statsapi|live",
            "last_run_at": now - timedelta(seconds=50),
            "next_due_at": now - timedelta(seconds=1),
        }
    ]
    for index in range(20):
        jobs.append(
            {
                "job_key": f"refresh:soon-{index}:wiki:fixtures",
                "family": f"imminent-{index}",
                "urgency": "IMMINENT",
                "competition_id": f"aaa-{index}",
                "priority": 3,
                "request_key": f"imminent-{index}|url",
                "last_run_at": now - timedelta(seconds=200),
                "next_due_at": now - timedelta(seconds=10),
            }
        )
    groups, _stats = select_fair_groups(jobs, now)
    assert groups[0][0]["family"] == "mlb-statsapi"
    assert any(group[0]["urgency"] == "LIVE" for group in groups)
