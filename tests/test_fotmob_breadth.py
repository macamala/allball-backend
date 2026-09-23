from collector.fotmob_crosswalk import (
    _canonical_fotmob_competition,
    _fotmob_competition_identity,
)


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
