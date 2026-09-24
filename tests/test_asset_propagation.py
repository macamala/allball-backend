from collector.asset_propagation import propagate_identity_assets
from collector.models import SportsEvent
from collector.util import dump_json, load_json
from tests.test_collector_architecture import _session


def _row(event_id, participants, extra=None):
    return SportsEvent(
        event_id=event_id,
        sport_id="football",
        competition_id="test-asset-propagation",
        event_family="team_match",
        status="scheduled",
        fingerprint=f"fp-{event_id}",
        participants_json=dump_json(participants),
        extra_json=dump_json(extra or {}),
        display_eligible=True,
    )


def test_asset_propagation_fills_only_missing_identity_fields():
    db = _session()
    ids = ["ninko-evt-asset-source", "ninko-evt-asset-target"]
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.add(
            _row(
                ids[0],
                {
                    "home": {"id": "club-1", "name": "Alpha FC", "logo": "https://cdn.example/alpha.svg"},
                    "away": {"id": "club-2", "name": "Beta FC", "country_id": "RS"},
                },
                {"competition_logo": "https://cdn.example/league.svg"},
            )
        )
        db.add(
            _row(
                ids[1],
                {
                    "home": {"id": "club-1", "name": "Alpha FC"},
                    "away": {"id": "club-2", "name": "Beta FC"},
                },
            )
        )
        db.flush()

        stats = propagate_identity_assets(db)
        target = db.get(SportsEvent, ids[1])
        participants = load_json(target.participants_json, {}) or {}
        extra = load_json(target.extra_json, {}) or {}

        assert stats["rows_updated"] >= 1
        assert participants["home"]["logo"] == "https://cdn.example/alpha.svg"
        assert participants["away"]["country_id"] == "RS"
        assert extra["competition_logo"] == "https://cdn.example/league.svg"
    finally:
        db.rollback()
        db.close()
