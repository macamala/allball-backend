"""Runtime registry, failover, partial coverage, identity, and health tests."""

from collector.adapters import FetchResult, register_adapter, unregister_adapter
from collector.collect import run_cycle
from collector.coverage import event_matches_partial, filter_partial_events
from collector.models import SportsCompetitionHealth, SportsEvent, SportsSource, SportsSourceHealth
from collector.registry import build_runtime_registry, validate_registry
from collector.test_support import DeterministicMockAdapter, mock_event
from database import SessionLocal
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _source, _session


def test_registry_validates_and_loads_mapped_competitions():
    runtime = build_runtime_registry()
    errors = validate_registry(runtime)
    assert errors == []
    assert runtime["counts"]["competitions"] >= 180
    assert runtime["counts"]["families"] >= 150
    aqua = runtime["competitions"]["world-aquatics-events"]
    families = {row["source_family"]: row for row in aqua["sources"]}
    assert families["microplus-timing"]["coverage"] == "partial"
    assert "u20" in (families["microplus-timing"]["coverage_notes"] or "").lower()
    assert families["omega-timing"]["coverage"] == "full"


def test_partial_coverage_never_treated_as_full():
    constraints = {
        "allow_keywords": ["u20", "world cup"],
        "deny_keywords": ["singapore"],
    }
    allowed = {"home": {"name": "USA U20"}, "away": {"name": "ESP"}, "competition": "World Cup"}
    denied = {"home": {"name": "ESP"}, "away": {"name": "HUN"}, "venue": "Singapore"}
    assert event_matches_partial(allowed, constraints) is True
    assert event_matches_partial(denied, constraints) is False
    assert filter_partial_events([allowed, denied], constraints) == [allowed]


def test_source_family_independence_and_failover(monkeypatch):
    primary = DeterministicMockAdapter("fam-a-1")
    primary.fail_times = 3
    alt = DeterministicMockAdapter("fam-a-2")
    alt.events = [mock_event(id="alt-1")]
    independent = DeterministicMockAdapter("fam-b")
    independent.events = [mock_event(id="b-1", venue="Backup Park")]
    register_adapter("fam-a-1", lambda source_id="fam-a-1": primary)
    register_adapter("fam-a-2", lambda source_id="fam-a-2": alt)
    register_adapter("fam-b", lambda source_id="fam-b": independent)
    db = _session()
    try:
        sa = _source(db, "fam-a-1", "fam-a-1")
        sb = _source(db, "fam-a-2", "fam-a-2")
        sc = _source(db, "fam-b", "fam-b")
        sa.upstream_family = "omega-timing"
        sb.upstream_family = "omega-timing"
        sc.upstream_family = "microplus-timing"
        _competition(db, "world-aquatics-events", "water-polo")
        _map(db, "world-aquatics-events", "fam-a-1", 1)
        _map(db, "world-aquatics-events", "fam-a-2", 2)
        _map(db, "world-aquatics-events", "fam-b", 3)
        db.flush()
        from collector.models import SportsSourceCompetition

        for row in db.query(SportsSourceCompetition).all():
            if row.source_id.startswith("fam-a"):
                row.upstream_family = "omega-timing"
                row.coverage_scope = "full"
            else:
                row.upstream_family = "microplus-timing"
                row.coverage_scope = "partial"
                row.coverage_notes = "U20 World Cup only"
        db.commit()
        run_cycle(db, capabilities=["fixtures"], sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).count() == 1
        assert independent.calls == []
        assert len(alt.calls) == 1
    finally:
        db.close()
        _cleanup_adapters("fam-a-1", "fam-a-2", "fam-b")


def test_partial_fallback_not_used_outside_coverage():
    blocked = DeterministicMockAdapter("omega")
    blocked.restricted = True
    partial = DeterministicMockAdapter("microplus")
    partial.events = [
        mock_event(id="sg-1", venue="Singapore", home={"name": "ESP"}, away={"name": "HUN"})
    ]
    register_adapter("omega", lambda source_id="omega": blocked)
    register_adapter("microplus", lambda source_id="microplus": partial)
    db = _session()
    try:
        omega = _source(db, "omega", "omega")
        micro = _source(db, "microplus", "microplus")
        omega.upstream_family = "omega-timing"
        micro.upstream_family = "microplus-timing"
        _competition(db, "world-aquatics-events", "water-polo")
        _map(db, "world-aquatics-events", "omega", 1)
        _map(db, "world-aquatics-events", "microplus", 2)
        from collector.models import SportsSourceCompetition

        db.flush()
        db.query(SportsSourceCompetition).filter_by(source_id="omega").one().upstream_family = "omega-timing"
        micro_map = db.query(SportsSourceCompetition).filter_by(source_id="microplus").one()
        micro_map.upstream_family = "microplus-timing"
        micro_map.coverage_scope = "partial"
        db.commit()
        run_cycle(db, capabilities=["fixtures"], sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).count() == 0
        health = db.query(SportsCompetitionHealth).filter_by(competition_id="world-aquatics-events").one()
        assert health.last_classification in {"NO_VALID_FALLBACK", "SOURCE_CHANGED"}
        assert partial.calls == []
    finally:
        db.close()
        _cleanup_adapters("omega", "microplus")


def test_primary_success_records_health():
    adapter = DeterministicMockAdapter("ok-src")
    adapter.events = [mock_event(id="ok-1", status="scheduled")]
    register_adapter("ok-src", lambda source_id="ok-src": adapter)
    db = _session()
    try:
        _source(db, "ok-src", "ok-src")
        _competition(db, "ok-league", "football")
        _map(db, "ok-league", "ok-src", 10)
        db.commit()
        run_cycle(db, capabilities=["fixtures"])
        db.commit()
        health = db.query(SportsSourceHealth).filter_by(source_id="ok-src").one()
        assert health.status == "healthy"
        assert health.last_attempt_at is not None
        comp = db.query(SportsCompetitionHealth).filter_by(competition_id="ok-league").one()
        assert comp.last_classification == "WORKING_PRIMARY"
    finally:
        db.close()
        _cleanup_adapters("ok-src")


def test_timeout_empty_malformed_and_batch_isolation():
    class TimeoutAdapter:
        def __init__(self, source_id="timeout"):
            self.source_id = source_id

        def fetch(self, request):
            return FetchResult(ok=False, http_status=0, error="timed out", classification="NETWORK_FAILURE")

    class EmptyAdapter:
        def __init__(self, source_id="empty"):
            self.source_id = source_id
            self.calls = []

        def fetch(self, request):
            self.calls.append(request)
            return FetchResult(ok=True, http_status=200, events=[], parse_status="ok")

    class BoomAdapter:
        def __init__(self, source_id="boom"):
            self.source_id = source_id

        def fetch(self, request):
            raise RuntimeError("adapter exploded")

    good = DeterministicMockAdapter("good")
    good.events = [mock_event(id="good-1")]
    register_adapter("timeout", lambda source_id="timeout": TimeoutAdapter())
    register_adapter("empty", lambda source_id="empty": EmptyAdapter())
    register_adapter("boom", lambda source_id="boom": BoomAdapter())
    register_adapter("good", lambda source_id="good": good)
    db = _session()
    try:
        _source(db, "timeout", "timeout")
        _source(db, "empty", "empty")
        _source(db, "boom", "boom")
        _source(db, "good", "good")
        _competition(db, "timeout-league", "football")
        _competition(db, "empty-league", "football")
        _competition(db, "boom-league", "football")
        _competition(db, "good-league", "football")
        _map(db, "timeout-league", "timeout", 10)
        _map(db, "empty-league", "empty", 10)
        _map(db, "boom-league", "boom", 10)
        _map(db, "good-league", "good", 10)
        db.commit()
        summary = run_cycle(db, capabilities=["fixtures"], sleeper=lambda _d: None)
        db.commit()
        assert summary["fixtures"] >= 1
        assert db.query(SportsEvent).filter_by(competition_id="good-league").count() == 1
        timeout_health = db.query(SportsCompetitionHealth).filter_by(competition_id="timeout-league").one()
        assert timeout_health.last_classification == "NETWORK_FAILURE"
        empty_health = db.query(SportsCompetitionHealth).filter_by(competition_id="empty-league").one()
        assert empty_health.last_classification == "NO_CURRENT_EVENTS"
    finally:
        db.close()
        _cleanup_adapters("timeout", "empty", "boom", "good")


def test_event_identity_merges_close_times():
    first = DeterministicMockAdapter("id-a")
    first.events = [mock_event(id="ext-a", start_time="2026-09-17T15:00:00Z")]
    second = DeterministicMockAdapter("id-b")
    second.events = [mock_event(id="ext-b", start_time="2026-09-17T15:20:00Z")]
    register_adapter("id-a", lambda source_id="id-a": first)
    register_adapter("id-b", lambda source_id="id-b": second)
    db = _session()
    try:
        _source(db, "id-a", "id-a")
        _source(db, "id-b", "id-b")
        _competition(db, "id-league", "football")
        _map(db, "id-league", "id-a", 10)
        _map(db, "id-league", "id-b", 20)
        db.commit()
        run_cycle(db, capabilities=["fixtures"])
        db.commit()
        assert db.query(SportsEvent).count() == 1
        event = db.query(SportsEvent).one()
        assert "id-a" in (event.contributing_sources_json or "")
        assert "id-b" in (event.contributing_sources_json or "")
    finally:
        db.close()
        _cleanup_adapters("id-a", "id-b")


def test_internal_health_hidden_without_token():
    from fastapi.testclient import TestClient
    from app import app

    with TestClient(app) as client:
        assert client.get("/internal/collector/health").status_code == 404
        assert client.get("/health").json()["service"] == "allball-backend"
        coverage = client.get("/registry/coverage").json()
        assert coverage["counts"]["competitions"] >= 180
        assert "credential" not in str(coverage).lower() or "NINKO_SOURCE" not in str(coverage)
