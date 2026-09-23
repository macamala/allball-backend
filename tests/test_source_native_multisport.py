from collector.competition_identity import correct_public_competition_id
from collector.sofascore_crosswalk import source_native_identity


def test_source_native_sofascore_basketball_identity_is_safe():
    row = {
        "tournament": {
            "uniqueTournament": {"id": 12345, "name": "National Basketball League"},
            "category": {"country": {"alpha2": "AU"}},
        }
    }
    competition_id, source_id, name, country = source_native_identity(row, "basketball")
    assert competition_id == "basketball-au-national-basketball-league-t12345"
    assert source_id == "12345"
    assert name == "National Basketball League"
    assert country == "AU"
    assert (
        correct_public_competition_id(
            stored_competition_id=competition_id,
            source_competition_name=name,
            sport_id="basketball",
            source_family="sofascore-web",
        )
        == competition_id
    )


def test_source_native_rejects_wrong_family_and_wrong_sport_prefix():
    assert (
        correct_public_competition_id(
            stored_competition_id="basketball-au-national-basketball-league-t12345",
            source_competition_name="National Basketball League",
            sport_id="basketball",
            source_family="random-provider",
        )
        is None
    )
    assert (
        correct_public_competition_id(
            stored_competition_id="football-au-national-basketball-league-t12345",
            source_competition_name="National Basketball League",
            sport_id="basketball",
            source_family="sofascore-web",
        )
        is None
    )
