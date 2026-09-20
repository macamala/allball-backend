import os

from collector.flags import collection_enabled, scheduler_enabled, writes_enabled
from collector.lock import acquire_scheduler_lock, lock_status, release_scheduler_lock
from collector.matrix_guard import FROZEN_CHECKSUM, matrix_status
from tests.test_collector_architecture import _session


def test_matrix_checksum_frozen():
    status = matrix_status()
    assert status["checksum"] == FROZEN_CHECKSUM
    assert status["competition_count"] == 180
    assert status["clean_full_180"] is True


def test_matrix_checksum_ignores_host_newlines(tmp_path):
    from collector.matrix_guard import MATRIX_PATH, matrix_checksum

    raw = MATRIX_PATH.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    lf_path = tmp_path / "lf.json"
    crlf_path = tmp_path / "crlf.json"
    lf_path.write_bytes(lf)
    crlf_path.write_bytes(crlf)
    assert matrix_checksum(lf_path) == FROZEN_CHECKSUM
    assert matrix_checksum(crlf_path) == FROZEN_CHECKSUM
    assert lf != crlf


def test_flags_fail_closed(monkeypatch):
    monkeypatch.delenv("RESULTS_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("RESULTS_SCHEDULER_ENABLED", raising=False)
    monkeypatch.delenv("RESULTS_COLLECTION_ENABLED", raising=False)
    assert writes_enabled() is False
    assert scheduler_enabled() is False
    assert collection_enabled() is False


def test_scheduler_lock_second_worker_blocked():
    db = _session()
    try:
        assert acquire_scheduler_lock(db, owner="worker-a", ttl_seconds=120) is True
        db.commit()
        assert acquire_scheduler_lock(db, owner="worker-b", ttl_seconds=120) is False
        status = lock_status(db)
        assert status["held"] is True
        assert status["owner_id"] == "worker-a"
        release_scheduler_lock(db, owner="worker-a")
        db.commit()
        assert acquire_scheduler_lock(db, owner="worker-b", ttl_seconds=120) is True
    finally:
        db.close()


def test_writes_disabled_skips_canonical_events(monkeypatch):
    from collector.adapters import FetchRequest, FetchResult, register_adapter
    from collector.collect import run_cycle
    from collector.models import SportsEvent
    from collector.test_support import mock_event
    from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _source

    monkeypatch.setenv("RESULTS_COLLECTION_ENABLED", "true")
    monkeypatch.setenv("RESULTS_WRITE_ENABLED", "false")

    class Echo:
        def fetch(self, request: FetchRequest) -> FetchResult:
            return FetchResult(
                ok=True,
                http_status=200,
                events=[mock_event(id="dry-1", home={"name": "A"}, away={"name": "B"})],
            )

    register_adapter("dry-echo", lambda source_id="dry-echo": Echo())
    db = _session()
    try:
        _source(db, "dry-echo", "dry-echo")
        _competition(db, "dry-league", "football")
        _map(db, "dry-league", "dry-echo", 10)
        db.commit()
        summary = run_cycle(db, capabilities=["fixtures"], force=True, sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).count() == 0
        assert "fixtures" in summary
    finally:
        db.close()
        _cleanup_adapters("dry-echo")


def test_smoke_html_200_is_reachable_not_network(monkeypatch):
    from collector import staging

    def fake_probe(url, timeout=20):
        return {
            "http_status": 200,
            "content_type": "text/html",
            "final_url": url,
            "redirects": 0,
            "latency_ms": 10,
            "transport": "REACHABLE",
            "body": b"<!doctype html><html><body>ok</body></html>",
        }

    monkeypatch.setattr(staging, "probe_url", fake_probe)
    monkeypatch.setattr(
        staging,
        "_matrix_families",
        lambda: {"skidskytte-web": {"url": "https://www.skidskytte.se", "access": "html"}},
    )
    report = staging.smoke()
    row = report["families"]["skidskytte-web"]
    assert row["transport"] == "REACHABLE"
    assert row["parser_expectation"] == "HTML_EXPECTED"
    assert row["bucket"] != "network_error"
    assert row["bucket"] == "reachable"


def test_smoke_json_parse_failure_is_parser_not_network(monkeypatch):
    from collector import staging

    def fake_probe(url, timeout=20):
        return {
            "http_status": 200,
            "content_type": "application/json",
            "final_url": url,
            "redirects": 0,
            "latency_ms": 10,
            "transport": "REACHABLE",
            "body": b"<html>not json</html>",
        }

    monkeypatch.setattr(staging, "probe_url", fake_probe)
    monkeypatch.setattr(
        staging,
        "_matrix_families",
        lambda: {"openligadb": {"url": "https://api.openligadb.de/x", "access": "json"}},
    )
    report = staging.smoke()
    row = report["families"]["openligadb"]
    assert row["transport"] == "REACHABLE"
    assert row["bucket"] == "parser_error"
