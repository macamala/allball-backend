from collector.competition_presentation import (
    metadata_for,
    validate_frozen_metadata,
)


def test_frozen_180_have_valid_public_metadata():
    report = validate_frozen_metadata()
    assert report["matrix_ok"] is True
    assert report["count"] == 180
    assert report["valid_sport"] == 180
    assert report["valid_display_name"] == 180
    assert report["valid_geography"] == 180
    assert report["sport_as_geography"] == 0
    assert report["failures"] == []
    assert report["ok"] is True


def test_england_not_collapsed_to_uk():
    row = metadata_for("england-premier-league", "football")
    assert row["geography_label"] == "England"
    assert row["country_code"] == "england"
    assert row["display_name"] == "Premier League"
    assert row["scope_type"] == "DOMESTIC"
    scotland = metadata_for("scotland-premiership", "football")
    assert scotland["geography_label"] == "Scotland"


def test_continental_and_world_scope():
    ucl = metadata_for("uefa-champions-league", "football")
    assert ucl["geography_label"] == "Europe"
    assert ucl["scope_type"] == "CONTINENTAL"
    assert ucl["country_code"] is None
    lib = metadata_for("copa-libertadores", "football")
    assert lib["geography_label"] == "South America"
    worlds = metadata_for("lol-world-championship", "league-of-legends")
    assert worlds["geography_label"] == "World"
    assert worlds["scope_type"] == "WORLD"
    atp = metadata_for("atp-tour", "tennis")
    assert atp["geography_label"] == "World"
    nba = metadata_for("nba", "basketball")
    assert nba["geography_label"] == "USA"


def test_no_sport_name_as_geography():
    for key, sport in (
        ("italy-serie-a", "football"),
        ("nba", "basketball"),
        ("wta-tour", "tennis"),
        ("mlb", "baseball"),
    ):
        row = metadata_for(key, sport)
        assert row["geography_label"].lower() not in {sport, "football", "basketball", "tennis"}
