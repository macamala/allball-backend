from datetime import datetime
from types import SimpleNamespace

from collector.util import dump_json, load_json
from collector.wta_breadth import (
    _competition_identity,
    _event_in_window,
    _merge_country_index,
    _repair_visible_wta_countries,
    _tournament_overlaps,
    JOB_KEY,
    PUBLIC_BREADTH_STATUS,
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



def test_wta_mapping_uses_public_breadth_status():
    assert PUBLIC_BREADTH_STATUS == "single-source-breadth"



def test_wta_country_index_rejects_conflicting_identity_keys():
    target = {}
    ambiguous = set()
    _merge_country_index(target, {"name:alex smith": "USA"}, ambiguous)
    _merge_country_index(target, {"name:alex smith": "GBR"}, ambiguous)
    assert "name:alex smith" not in target
    assert "name:alex smith" in ambiguous


def test_wta_country_repair_fills_legacy_doubles_without_touching_fixture_fields():
    original_start = datetime(2026, 9, 23, 15, 59)
    row = SimpleNamespace(
        sport_id="tennis",
        competition_id="wta-tour",
        event_family="individual_match",
        primary_source_id="wta-global",
        display_eligible=True,
        start_time=original_start,
        status="finished",
        score_json=dump_json({"home": 2, "away": 0}),
        extra_json=dump_json({"source_family": "wta-json"}),
        participants_json=dump_json(
            {
                "home": {"name": "Maja Chwalinska / Barbora Krejcikova"},
                "away": {"name": "Erin Routliffe / Aldila Sutjiadi", "country_ids": ["NZL", "IDN"]},
                "participant_a": {"name": "Maja Chwalinska / Barbora Krejcikova"},
                "participant_b": {"name": "Erin Routliffe / Aldila Sutjiadi", "country_ids": ["NZL", "IDN"]},
            }
        ),
    )

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [row]

    class FakeDb:
        def __init__(self):
            self.info = {}
            self.flushed = False

        def query(self, *_args):
            return Query()

        def flush(self):
            self.flushed = True

    db = FakeDb()
    stats = _repair_visible_wta_countries(
        db,
        player_countries={
            "name:maja chwalinska": "POL",
            "name:barbora krejcikova": "CZE",
            "name:erin routliffe": "NZL",
            "name:aldila sutjiadi": "IDN",
        },
        low=datetime(2026, 9, 22),
        high=datetime(2026, 9, 28),
    )
    participants = load_json(row.participants_json, {}) or {}
    assert stats["rows_updated"] == 1
    assert stats["participant_sides_filled"] == 1
    assert participants["home"]["country_ids"] == ["POL", "CZE"]
    assert participants["participant_a"]["country_ids"] == ["POL", "CZE"]
    assert row.start_time == original_start
    assert row.status == "finished"
    assert load_json(row.score_json, {}) == {"home": 2, "away": 0}


def test_wta_country_repair_upgrade_runs_as_v7():
    assert JOB_KEY == "wta-global-breadth-v7"
