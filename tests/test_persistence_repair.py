from collector.collect import _upsert_details, run_cycle
from collector.ids import bound_source_key
from collector.lock import acquire_write_lock, release_write_lock, write_lock_status
from collector.models import SportsEvent, SportsEventDetail, SportsIdMap, SportsIngestionRun
from collector.validate_store import validate_store
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def test_bound_source_key_collision_and_stability():
    prefix = "x" * 90
    a = bound_source_key("wiki", prefix + "alpha")
    b = bound_source_key("wiki", prefix + "beta")
    assert a != b
    assert len(a) <= 80
    assert len(b) <= 80
    assert bound_source_key("wiki", prefix + "alpha") == a
    short = bound_source_key("wiki", "short-id")
    assert short == "short-id"


def test_duplicate_details_same_session_one_row():
    from collector.models import SportsEvent

    db = _session()
    try:
        event = SportsEvent(
            event_id="ninko-evt-detail-dup",
            sport_id="football",
            competition_id="test-league",
            event_family="team_match",
            fingerprint="fp-detail-dup",
        )
        db.add(event)
        _upsert_details(db, "ninko-evt-detail-dup", {"lineups": {"home": ["A"]}}, True)
        _upsert_details(db, "ninko-evt-detail-dup", {"lineups": {"home": ["A", "B"]}}, True)
        db.commit()
        assert db.query(SportsEventDetail).filter_by(event_id="ninko-evt-detail-dup").count() == 1
    finally:
        db.close()


def test_write_lock_second_process_refused():
    db_a = _session()
    db_b = _session()
    try:
        assert acquire_write_lock(db_a, owner="writer-a", ttl_seconds=120) is True
        db_a.commit()
        assert acquire_write_lock(db_b, owner="writer-b", ttl_seconds=120) is False
        status = write_lock_status(db_a)
        assert status["held"] is True
        assert status["owner_id"] == "writer-a"
        release_write_lock(db_a, owner="writer-a")
        db_a.commit()
        assert acquire_write_lock(db_b, owner="writer-b", ttl_seconds=120) is True
    finally:
        db_a.close()
        db_b.close()


def test_long_source_event_id_persists_distinct_keys():
    from collector.identity import remember_mapping

    db = _session()
    try:
        prefix = "wikipedia-owcs-world-finals-" + ("q" * 80)
        remember_mapping(db, entity_kind="event", ninko_id="e1", source_id="wiki", source_entity_id=prefix + "one")
        remember_mapping(db, entity_kind="event", ninko_id="e2", source_id="wiki", source_entity_id=prefix + "two")
        db.commit()
        rows = db.query(SportsIdMap).filter_by(entity_kind="event", source_id="wiki").all()
        assert len(rows) == 2
        assert rows[0].source_entity_id != rows[1].source_entity_id
        assert all(len(row.source_entity_id) <= 200 for row in rows)
        assert {row.source_entity_id_original for row in rows} == {prefix + "one", prefix + "two"}
    finally:
        db.close()


def test_persist_failure_isolates_and_rerun_is_idempotent(monkeypatch):
    import collector.collect as collect_mod
    from collector.adapters import FetchRequest, FetchResult, register_adapter
    from collector.test_support import mock_event

    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "true")

    class Echo:
        def fetch(self, request: FetchRequest) -> FetchResult:
            return FetchResult(
                ok=True,
                http_status=200,
                events=[
                    mock_event(
                        id=f"row-{i}",
                        home={"name": f"H{i}"},
                        away={"name": f"A{i}"},
                        competition="fail-league",
                    )
                    for i in range(8)
                ],
            )

    register_adapter("fail-echo", lambda source_id="fail-echo": Echo())
    db = _session()
    try:
        _source(db, "fail-echo", "fail-echo")
        _competition(db, "fail-league", "football")
        _map(db, "fail-league", "fail-echo", 10)
        db.commit()
        collect_mod.persist_fail_after = 5
        try:
            run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
            db.commit()
        finally:
            collect_mod.persist_fail_after = None
        first = db.query(SportsEvent).count()
        assert first == 4
        assert first < 8
        collect_mod.persist_fail_after = None
        run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
        db.commit()
        second = db.query(SportsEvent).count()
        assert second == 8
        report = validate_store(db)
        assert report["duplicate_canonical_identities"] == 0
        assert report["duplicate_source_identities"] == 0
        assert report["orphan_details"] == 0
    finally:
        db.close()
        _cleanup_adapters("fail-echo")


def test_incomplete_run_marked_on_next_cycle(monkeypatch):
    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "false")
    db = _session()
    try:
        db.add(SportsIngestionRun(scope="cycle", status="running"))
        db.commit()
        run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
        db.commit()
        stale = db.query(SportsIngestionRun).filter_by(status="INCOMPLETE").count()
        assert stale >= 1
    finally:
        db.close()
