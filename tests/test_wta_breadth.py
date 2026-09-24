from datetime import datetime

from collector.wta_breadth import (
    _competition_identity,
    _event_in_window,
    _tournament_overlaps,
)


def test_wta_dynamic_tournament_identity_is_stable():
    meta = {
        "tournamentGroup": {"id": 1060, "name": "Tokyo Open"},
        "year": 2026,
        "startDate": "2026-09-21",
        "endDate": "2026-09-27",
    }
    competition_id, name, native_id = _competition_identity(meta)
    assert competition_id == "tennis-wta-1060-tokyo-open"
    assert name == "Tokyo Open"
    assert native_id == "1060"


def test_wta_tournament_overlap_and_match_window():
    meta = {
        "startDate": "2026-09-21",
        "endDate": "2026-09-27",
    }
    assert _tournament_overlaps(
        meta,
        low=datetime(2026, 9, 23).date(),
        high=datetime(2026, 9, 28).date(),
    )
    assert _event_in_window(
        {"start_time": "2026-09-25T03:30:00Z"},
        low=datetime(2026, 9, 23),
        high=datetime(2026, 9, 29),
    )
    assert not _event_in_window(
        {"start_time": "2026-10-10T03:30:00Z"},
        low=datetime(2026, 9, 23),
        high=datetime(2026, 9, 29),
    )
