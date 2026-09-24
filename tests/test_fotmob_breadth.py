from collector.fotmob_crosswalk import (
    _canonical_fotmob_competition,
    _ensure_dynamic_fotmob_mapping,
    _fotmob_competition_identity,
    repair_legacy_dynamic_source_bindings,
)
from collector.models import SportsCompetition, SportsEvent, SportsSource, SportsSourceCompetition
from collector.util import dump_json
from tests.test_collector_architecture import _session


def test_country_context_maps_dynamic_colombia_primera_to_canonical():
    assert _canonical_fotmob_competition("Primera A", "COL") == "colombia-primera-a"


def test_unique_usl_label_maps_without_hardcoded_fotmob_league_id():
    assert _canonical_fotmob_competition("USL Championship", "USA") == "usa-usl-championship"


def test_generic_ghana_premier_league_does_not_collapse_to_england():
    assert _canonical_fotmob_competition("Premier League", "GHA") is None
    competition_id, league_id, name, country = _fotmob_competition_identity(
        {"_league": {"id": 522, "name": "Premier League", "ccode": "GHA"}}
    )
    assert competition_id == "football-gha-premier-league"
    assert league_id == "522"
    assert name == "Premier League"
    assert country == "GHA"



def test_dynamic_fotmob_mapping_uses_dedicated_global_source():
    db = _session()
    competition_id = "test-fotmob-global-source"
    legacy_source_id = "fotmob-test-specific-source"
    try:
        db.query(SportsSourceCompetition).filter(
            SportsSourceCompetition.competition_id == competition_id
        ).delete(synchronize_session=False)
        db.query(SportsCompetition).filter_by(competition_id=competition_id).delete(synchronize_session=False)
        db.query(SportsSource).filter_by(source_id=legacy_source_id).delete(synchronize_session=False)

        global_source = db.get(SportsSource, "fotmob-global")
        if global_source is None:
            global_source = SportsSource(
                source_id="fotmob-global",
                display_name="FotMob Global Date Board",
                kind="dynamic",
                enabled=True,
                adapter_key="fotmob",
                attribution_required=False,
                public_branding_required=False,
                upstream_family="fotmob",
            )
            db.add(global_source)
        else:
            global_source.enabled = True
            global_source.adapter_key = "fotmob"

        legacy_source = SportsSource(
            source_id=legacy_source_id,
            display_name="Competition-specific FotMob source",
            kind="dynamic",
            enabled=True,
            adapter_key="fotmob",
            attribution_required=False,
            public_branding_required=False,
            upstream_family="fotmob",
        )
        db.add(legacy_source)
        db.flush()

        db.add(
            SportsSourceCompetition(
                competition_id=competition_id,
                source_id=legacy_source_id,
                priority=900,
                source_competition_id="999001",
                enabled=True,
                coverage_scope="full",
                coverage_notes="FotMob source-native daily-board breadth",
                upstream_family="fotmob",
            )
        )
        db.flush()

        mapping = _ensure_dynamic_fotmob_mapping(
            db,
            competition_id=competition_id,
            league_id="999001",
            league_name="Test Global League",
            ccode="TST",
        )
        db.flush()

        assert mapping is not None
        assert mapping.source_id == "fotmob-global"
        assert mapping.priority == 40
        legacy = (
            db.query(SportsSourceCompetition)
            .filter_by(competition_id=competition_id, source_id=legacy_source_id)
            .one()
        )
        assert legacy.enabled is False
    finally:
        db.rollback()
        db.close()



def test_repair_legacy_dynamic_source_binding_updates_existing_events():
    db = _session()
    competition_id = "test-fotmob-rebind-existing"
    legacy_source_id = "fotmob-test-rebind-specific"
    event_id = "ninko-evt-test-fotmob-rebind"
    try:
        db.query(SportsEvent).filter_by(event_id=event_id).delete(synchronize_session=False)
        db.query(SportsSourceCompetition).filter(
            SportsSourceCompetition.competition_id == competition_id
        ).delete(synchronize_session=False)
        db.query(SportsCompetition).filter_by(competition_id=competition_id).delete(synchronize_session=False)
        db.query(SportsSource).filter_by(source_id=legacy_source_id).delete(synchronize_session=False)

        global_source = db.get(SportsSource, "fotmob-global")
        if global_source is None:
            db.add(
                SportsSource(
                    source_id="fotmob-global",
                    display_name="FotMob Global Date Board",
                    kind="dynamic",
                    enabled=True,
                    adapter_key="fotmob",
                    attribution_required=False,
                    public_branding_required=False,
                    upstream_family="fotmob",
                )
            )
        else:
            global_source.enabled = True
            global_source.adapter_key = "fotmob"

        db.add(
            SportsSource(
                source_id=legacy_source_id,
                display_name="Legacy competition FotMob source",
                kind="dynamic",
                enabled=True,
                adapter_key="fotmob",
                attribution_required=False,
                public_branding_required=False,
                upstream_family="fotmob",
            )
        )
        db.add(
            SportsCompetition(
                competition_id=competition_id,
                sport_id="football",
                name="Test Rebind League",
                official_name="Test Rebind League",
                slug=competition_id,
                country_id="TST",
                event_model="team_match",
                country_based=True,
                active=True,
                news_taxonomy=False,
                identity_only=False,
            )
        )
        db.flush()

        legacy = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=legacy_source_id,
            priority=900,
            source_competition_id="999002",
            enabled=True,
            coverage_scope="full",
            coverage_notes="FotMob source-native daily-board breadth",
            upstream_family="fotmob",
            source_config_json=dump_json({
                "fotmob_league_id": "999002",
                "fotmob_league_name": "Test Rebind League",
            }),
        )
        db.add(legacy)
        db.add(
            SportsEvent(
                event_id=event_id,
                sport_id="football",
                competition_id=competition_id,
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-test-fotmob-rebind",
                primary_source_id=legacy_source_id,
                participants_json=dump_json({
                    "home": {"name": "Alpha"},
                    "away": {"name": "Beta"},
                }),
                extra_json=dump_json({
                    "source_family": "fotmob",
                    "source_competition_id": "999002",
                    "source_competition_name": "Test Rebind League",
                    "quality_flags": ["competition_attribution_mismatch"],
                    "display_eligible": False,
                }),
                display_eligible=False,
            )
        )
        db.flush()

        stats = repair_legacy_dynamic_source_bindings(db)
        db.flush()
        db.expire_all()

        repaired = db.get(SportsEvent, event_id)
        legacy_after = (
            db.query(SportsSourceCompetition)
            .filter_by(competition_id=competition_id, source_id=legacy_source_id)
            .one()
        )
        assert stats["mappings"] >= 1
        assert stats["events"] >= 1
        assert repaired.primary_source_id == "fotmob-global"
        assert legacy_after.enabled is False
    finally:
        db.rollback()
        db.close()
