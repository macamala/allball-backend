from collector.asset_propagation import propagate_identity_assets
from collector.models import SportsEvent, SportsStandingSnapshot
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



def test_standings_logo_propagates_into_matching_event_team():
    db = _session()
    event_id = "ninko-evt-standing-asset-target"
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id == event_id).delete(synchronize_session=False)
        db.query(SportsStandingSnapshot).filter(
            SportsStandingSnapshot.competition_id == "test-standing-assets"
        ).delete(synchronize_session=False)
        db.add(
            SportsStandingSnapshot(
                competition_id="test-standing-assets",
                sport_id="ice-hockey",
                season="2026",
                source_id="nhl-web",
                rows_json=dump_json({
                    "rows": [
                        {
                            "team": "New Jersey Devils",
                            "team_id": "NJD",
                            "logo": "https://assets.nhle.com/logos/nhl/svg/NJD_light.svg",
                        }
                    ]
                }),
            )
        )
        db.add(
            SportsEvent(
                event_id=event_id,
                sport_id="ice-hockey",
                competition_id="test-standing-assets",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-standing-asset-target",
                participants_json=dump_json({
                    "home": {"name": "New Jersey Devils"},
                    "away": {"name": "Boston Bruins"},
                }),
                extra_json=dump_json({}),
                display_eligible=True,
            )
        )
        db.flush()

        stats = propagate_identity_assets(db)
        target = db.get(SportsEvent, event_id)
        participants = load_json(target.participants_json, {}) or {}
        assert participants["home"]["logo"].endswith("/NJD_light.svg")
        assert stats["standing_participant_logos_filled"] >= 1
    finally:
        db.rollback()
        db.close()



def test_sofascore_native_ids_backfill_artwork_only_in_sofascore_context():
    db = _session()
    ids = ["ninko-evt-sofa-assets", "ninko-evt-not-sofa-assets"]
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id.in_(ids)).delete(synchronize_session=False)
        db.add(
            SportsEvent(
                event_id=ids[0],
                sport_id="handball",
                competition_id="test-sofa-assets",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-sofa-assets",
                primary_source_id="sofascore-global",
                participants_json=dump_json({
                    "home": {"id": "123", "name": "Alpha HC"},
                    "away": {"id": "456", "name": "Beta HC"},
                }),
                extra_json=dump_json({
                    "source_family": "sofascore-web",
                    "source_competition_id": "987",
                    "sofascore_tournament_id": "987",
                }),
                display_eligible=True,
            )
        )
        db.add(
            SportsEvent(
                event_id=ids[1],
                sport_id="handball",
                competition_id="test-other-assets-2",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-not-sofa-assets",
                primary_source_id="other-provider",
                participants_json=dump_json({
                    "home": {"id": "123", "name": "Other Alpha"},
                    "away": {"id": "456", "name": "Other Beta"},
                }),
                extra_json=dump_json({
                    "source_family": "other",
                    "source_competition_id": "987",
                }),
                display_eligible=True,
            )
        )
        db.flush()
        propagate_identity_assets(db)

        sofa = db.get(SportsEvent, ids[0])
        parts = load_json(sofa.participants_json, {}) or {}
        extra = load_json(sofa.extra_json, {}) or {}
        assert parts["home"]["logo"].endswith("/team/123/image")
        assert extra["competition_logo"].endswith("/unique-tournament/987/image")

        other = db.get(SportsEvent, ids[1])
        other_parts = load_json(other.participants_json, {}) or {}
        other_extra = load_json(other.extra_json, {}) or {}
        assert not other_parts["home"].get("logo")
        assert not other_extra.get("competition_logo")
    finally:
        db.rollback()
        db.close()



def test_international_national_team_uses_country_identity_not_fake_club_logo():
    db = _session()
    event_id = "ninko-evt-national-team-flags"
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id == event_id).delete(synchronize_session=False)
        db.add(
            SportsEvent(
                event_id=event_id,
                sport_id="football",
                competition_id="football-friendlies",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-national-team-flags",
                participants_json=dump_json({
                    "home": {"name": "Serbia"},
                    "away": {"name": "China"},
                }),
                extra_json=dump_json({}),
                display_eligible=True,
            )
        )
        db.flush()
        stats = propagate_identity_assets(db)
        row = db.get(SportsEvent, event_id)
        participants = load_json(row.participants_json, {}) or {}
        assert participants["home"]["country_id"] == "RS"
        assert participants["away"]["country_id"] == "CN"
        assert not participants["home"].get("logo")
        assert stats["national_team_countries_filled"] >= 2
    finally:
        db.rollback()
        db.close()
