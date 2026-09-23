from collector import worker


def _resolved_once():
    return worker.run_once_requested() or (
        not worker.scheduler_enabled() and not worker.keepalive_enabled()
    )


def test_scheduler_mode_stays_alive_even_with_legacy_keepalive_off(monkeypatch):
    monkeypatch.setattr(worker, "scheduler_enabled", lambda: True)
    monkeypatch.setattr(worker, "run_once_requested", lambda: False)
    monkeypatch.setattr(worker, "keepalive_enabled", lambda: False)
    assert _resolved_once() is False


def test_explicit_run_once_still_wins(monkeypatch):
    monkeypatch.setattr(worker, "scheduler_enabled", lambda: True)
    monkeypatch.setattr(worker, "run_once_requested", lambda: True)
    monkeypatch.setattr(worker, "keepalive_enabled", lambda: True)
    assert _resolved_once() is True
