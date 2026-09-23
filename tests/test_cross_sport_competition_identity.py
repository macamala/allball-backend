from collector.competition_identity import (
    correct_public_competition_id,
    unique_label_competition,
)


def test_basketball_super_league_never_maps_to_rugby_super_league():
    assert unique_label_competition("Super League", sport_id="basketball") is None
    assert (
        correct_public_competition_id(
            stored_competition_id="basketball-ss-1234567890-super-league",
            source_competition_name="Super League",
            sport_id="basketball",
            source_family="sportscore",
        )
        == "basketball-ss-1234567890-super-league"
    )


def test_cross_sport_source_id_is_rejected():
    from collector.competition_identity import resolve_competition

    resolved = resolve_competition(
        mapping_competition_id="wnba",
        source_competition_id="4533",
        source_competition_name="German Handball-Bundesliga",
        source_family="thesportsdb",
        sport_id="basketball",
    )
    assert resolved["accepted"] is False
