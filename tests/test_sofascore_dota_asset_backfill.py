from datetime import datetime
from types import SimpleNamespace

import collector.sofascore_dota_asset_backfill as backfill
from collector.util import dump_json, load_json


def test_dota_asset_identity_normalizes_team_position_and_tournament_tokens():
    assert backfill._dota_name("Team avice") == "avice"
    assert backfill._dota_name("avice Team") == "avice"
    assert backfill._competition_names_compatible(
        "PGL Wallachia 2026 Season 9",
        "PGL Wallachia",
    )
    assert backfill._competition_names_compatible(
        "BetBoom Streamers Battle 15",
        "BetBoom Streamers Battle",
    )
    assert not backfill._competition_names_compatible(
        "Winline Star Series Season 4",
        "BetBoom Streamers Battle",
    )


def test_sofascore_dota_asset_backfill_only_fills_blank_identity_fields():
    backfill._next_run_at = 0.0
    canonical_start = datetime(2026, 9, 23, 16, 53, 35)
    row = SimpleNamespace(
        event_id="ninko-evt-test-dota",
        sport_id="dota-2",
        competition_id="professional",
        display_eligible=True,
        start_time=canonical_start,
        status="finished",
        score_json=dump_json({"home": 2, "away": 1}),
        participants_json=dump_json(
            {
                "home": {"id": "10271251", "name": "Team avice"},
                "away": {"id": "10271239", "name": "Team GPK"},
                "participant_a": {"id": "10271251", "name": "Team avice"},
                "participant_b": {"id": "10271239", "name": "Team GPK"},
            }
        ),
        extra_json=dump_json(
            {
                "source_family": "opendota",
                "source_competition_name": "BetBoom Streamers Battle 15",
            }
        ),
        list_extra_json=None,
    )

    sofa_row = {
        "id": 777,
        "startTimestamp": int(datetime(2026, 9, 23, 15, 0).timestamp()),
        "homeTeam": {"id": 501, "name": "avice Team"},
        "awayTeam": {"id": 502, "name": "gpk Team"},
        "tournament": {
            "name": "BetBoom Streamers Battle Group A",
            "uniqueTournament": {"id": 9090, "name": "BetBoom Streamers Battle"},
            "category": {"name": "Dota 2", "slug": "dota-2"},
        },
    }

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [row]

    class FakeDb:
        def __init__(self):
            self.info = {}
            self.commits = 0

        def query(self, *_args):
            return Query()

        def commit(self):
            self.commits += 1

    class Result:
        ok = True

        def __init__(self, payload):
            self.payload = payload

    def getter(_url):
        return Result({"events": [sofa_row]})

    db = FakeDb()
    stats = backfill.run_if_due(db, getter=getter)
    participants = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}

    assert stats["matched_rows"] == 1
    assert stats["participant_logos_filled"] == 2
    assert stats["competition_logos_filled"] == 1
    assert participants["home"]["logo"] == "https://img.sofascore.com/api/v1/team/501/image"
    assert participants["away"]["logo"] == "https://img.sofascore.com/api/v1/team/502/image"
    assert participants["participant_a"]["logo"] == participants["home"]["logo"]
    assert participants["participant_b"]["logo"] == participants["away"]["logo"]
    assert extra["competition_logo"] == (
        "https://img.sofascore.com/api/v1/unique-tournament/9090/image"
    )

    # Identity-only invariant: no fixture/result fields were modified.
    assert row.start_time == canonical_start
    assert row.status == "finished"
    assert load_json(row.score_json, {}) == {"home": 2, "away": 1}
