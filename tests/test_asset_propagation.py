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



def test_fotmob_native_ids_backfill_artwork_only_in_fotmob_context():
    db = _session()
    ids = ["ninko-evt-fotmob-asset", "ninko-evt-other-asset"]
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.add(
            SportsEvent(
                event_id=ids[0],
                sport_id="football",
                competition_id="test-fotmob-assets",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-fotmob-assets",
                primary_source_id="fotmob-global",
                participants_json=dump_json({
                    "home": {"id": "9825", "name": "Alpha FC"},
                    "away": {"id": "8650", "name": "Beta FC"},
                }),
                extra_json=dump_json({
                    "source_family": "fotmob",
                    "source_competition_id": "47",
                    "display_eligible": True,
                }),
                display_eligible=True,
            )
        )
        db.add(
            SportsEvent(
                event_id=ids[1],
                sport_id="football",
                competition_id="test-other-assets",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-other-assets",
                primary_source_id="other-provider",
                participants_json=dump_json({
                    "home": {"id": "9825", "name": "Other Alpha"},
                    "away": {"id": "8650", "name": "Other Beta"},
                }),
                extra_json=dump_json({
                    "source_family": "other",
                    "source_competition_id": "47",
                    "display_eligible": True,
                }),
                display_eligible=True,
            )
        )
        db.flush()
        propagate_identity_assets(db)

        fotmob = db.get(SportsEvent, ids[0])
        parts = load_json(fotmob.participants_json, {}) or {}
        extra = load_json(fotmob.extra_json, {}) or {}
        assert parts["home"]["logo"].endswith("/teamlogo/9825.png")
        assert extra["competition_logo"].endswith("/leaguelogo/47.png")

        other = db.get(SportsEvent, ids[1])
        other_parts = load_json(other.participants_json, {}) or {}
        other_extra = load_json(other.extra_json, {}) or {}
        assert not other_parts["home"].get("logo")
        assert not other_extra.get("competition_logo")
    finally:
        db.rollback()
        db.close()
