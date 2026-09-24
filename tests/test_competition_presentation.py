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



def test_source_native_football_country_codes_get_public_geography():
    from collector.competition_presentation import attach_competition_metadata

    cases = [
        ("football-tun-ligue-1", "TUN", "Tunisia", "tn"),
        ("football-alg-ligue-1", "ALG", "Algeria", "dz"),
        ("football-nga-npfl", "NGA", "Nigeria", "ng"),
    ]
    for key, source_country, label, country_id in cases:
        event = {
            "sport": "football",
            "competition_key": key,
            "competition": key,
            "country_id": source_country,
        }
        out = attach_competition_metadata(event)
        assert out["geography_label"] == label
        assert out["country_id"] == country_id
        assert out["scope_type"] == "DOMESTIC"
        assert out["country_based"] is True



def test_dynamic_competition_country_inference_is_unambiguous():
    bulgaria = metadata_for(
        "basketball-ss-5ae6c1f64a-bulgaria-national-basketball-league",
        "basketball",
    )
    assert bulgaria["geography_label"] == "Bulgaria"
    assert bulgaria["country_code"] == "bg"
    assert bulgaria["scope_type"] == "DOMESTIC"

    singapore = metadata_for(
        "basketball-ss-2a56bda5dc-singapore-nbl-division-1",
        "basketball",
    )
    assert singapore["geography_label"] == "Singapore"
    assert singapore["country_code"] == "sg"

    cross_border = metadata_for(
        "basketball-ss-10dc5bd3fc-estonia-and-latvia-basketball-league",
        "basketball",
    )
    assert cross_border["country_code"] is None
    assert cross_border["scope_type"] != "DOMESTIC"


def test_unknown_registry_row_is_not_declared_domestic_without_country():
    row = metadata_for("basketball-ss-deadbeef-unknown-league", "basketball")
    assert row["country_code"] is None
    assert row["scope_type"] == ""
