from collector.competition_identity import correct_public_competition_id
from collector.models import SportsCompetition, SportsEvent, SportsSource, SportsSourceCompetition
from collector.sportscore_crosswalk import _source, quarantine_legacy_contamination, source_native_identity
from collector.util import dump_json
from tests.test_collector_architecture import _session


def test_sportscore_source_native_tennis_identity_is_stable():
    row = {
        "competition": "ATP Hangzhou, China Men Singles",
        "competition_logo": "https://example.test/tournament/123.png",
    }
    first = source_native_identity("tennis", row)
    second = source_native_identity("tennis", dict(row))
    assert first == second
    competition_id, name, _source_identity = first
    assert competition_id.startswith("tennis-ss-")
    assert name == "ATP Hangzhou, China Men Singles"
    assert (
        correct_public_competition_id(
            stored_competition_id=competition_id,
            source_competition_name=name,
            sport_id="tennis",
            source_family="sportscore",
        )
        == competition_id
    )


def test_sportscore_rejects_ambiguous_generic_without_logo():
    competition_id, name, source_identity = source_native_identity(
        "basketball", {"competition": "Club Friendship"}
    )
    assert competition_id is None
    assert name == "Club Friendship"
    assert source_identity == ""


def test_sportscore_same_label_different_logo_stays_separate():
    left = source_native_identity(
        "basketball",
        {"competition": "Club Friendship", "competition_logo": "https://x.test/a.png"},
    )[0]
    right = source_native_identity(
        "basketball",
        {"competition": "Club Friendship", "competition_logo": "https://x.test/b.png"},
    )[0]
    assert left
    assert right
    assert left != right


def test_specific_competition_identity_ignores_missing_logo():
    with_logo = source_native_identity(
        "basketball",
        {
            "competition": "Women's National Basketball Association",
            "competition_logo": "https://example.test/wnba.png",
        },
    )[0]
    without_logo = source_native_identity(
        "basketball",
        {"competition": "Women's National Basketball Association"},
    )[0]
    assert with_logo == without_logo



def test_sportscore_breadth_does_not_fall_through_branding_gate():
    db = _session()
    legacy_id = "sportscore-test-legacy-fallback"
    try:
        dedicated = db.get(SportsSource, "sportscore-global")
        if dedicated is None:
            dedicated = SportsSource(
                source_id="sportscore-global",
                display_name="SportScore Global",
                kind="dynamic",
                enabled=True,
                adapter_key="sportscore",
                attribution_required=True,
                public_branding_required=True,
                upstream_family="sportscore",
            )
            db.add(dedicated)
        else:
            dedicated.enabled = True
            dedicated.adapter_key = "sportscore"
            dedicated.public_branding_required = True

        db.query(SportsSource).filter_by(source_id=legacy_id).delete(synchronize_session=False)
        db.add(
            SportsSource(
                source_id=legacy_id,
                display_name="Legacy SportScore",
                kind="dynamic",
                enabled=True,
                adapter_key="sportscore",
                attribution_required=False,
                public_branding_required=False,
                upstream_family="sportscore",
            )
        )
        db.flush()
        assert _source(db) is None
    finally:
        db.rollback()
        db.close()


def test_unknown_legacy_sportscore_row_is_quarantined():
    db = _session()
    source_id = "sportscore-test-contamination"
    competition_id = "sportscore-test-wrong-football-bucket"
    event_id = "ninko-evt-sportscore-contamination-test"
    try:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.query(SportsSourceCompetition).filter(
            SportsSourceCompetition.competition_id == competition_id
        ).delete(synchronize_session=False)
        db.query(SportsCompetition).filter_by(competition_id=competition_id).delete(synchronize_session=False)
        db.query(SportsSource).filter_by(source_id=source_id).delete(synchronize_session=False)

        db.add(
            SportsSource(
                source_id=source_id,
                display_name="Legacy SportScore",
                kind="dynamic",
                enabled=True,
                adapter_key="sportscore",
                attribution_required=False,
                public_branding_required=False,
                upstream_family="sportscore",
            )
        )
        db.add(
            SportsCompetition(
                competition_id=competition_id,
                sport_id="football",
                name="Wrong Football Bucket",
                slug=competition_id,
                event_model="team_match",
                active=True,
            )
        )
        db.flush()
        db.add(
            SportsEvent(
                event_id=event_id,
                sport_id="",
                competition_id=competition_id,
                event_family="team_match",
                status="scheduled",
                fingerprint="sportscore-contamination-test",
                primary_source_id=source_id,
                participants_json=dump_json({
                    "home": {"name": "London Lions"},
                    "away": {"name": "Cheshire Phoenix"},
                }),
                score_json=dump_json({}),
                extra_json=dump_json({
                    "source_family": "sportscore",
                    "source_competition_name": "British Super League Basketball",
                }),
                display_eligible=True,
            )
        )
        db.flush()

        stats = quarantine_legacy_contamination(db)
        db.flush()
        row = db.get(SportsEvent, event_id)
        extra = __import__("collector.util", fromlist=["load_json"]).load_json(row.extra_json, {}) or {}
        assert stats["quarantined"] >= 1
        assert row.display_eligible is False
        assert "sportscore_legacy_contamination" in extra["quality_flags"]
    finally:
        db.rollback()
        db.close()
