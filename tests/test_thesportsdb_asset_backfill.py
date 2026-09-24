from collector.thesportsdb_asset_backfill import (
    TSDB_BY_COMP,
    TSDB_LOGO_BY_COMP,
    _league_logo,
    _public_visibility_clause,
    _teams,
    _unique_match,
)


def test_tsdb_team_catalog_extracts_badges_and_country():
    roster = _teams(
        {
            "teams": [
                {
                    "idTeam": "1",
                    "strTeam": "Boston Bruins",
                    "strBadge": "https://cdn.example/boston.png",
                    "strCountry": "USA",
                }
            ]
        }
    )
    assert roster[0]["id"] == "1"
    assert roster[0]["name"] == "Boston Bruins"
    assert roster[0]["logo"].endswith("boston.png")
    assert roster[0]["country_id"] == "USA"


def test_tsdb_team_catalog_uses_strict_unique_alias_matching():
    roster = [
        {"id": "1", "name": "Cardiff City", "folded": "cardiff city", "logo": "a", "country_id": "England"},
        {"id": "2", "name": "Swansea City", "folded": "swansea city", "logo": "b", "country_id": "Wales"},
    ]
    assert _unique_match("Cardiff City FC", roster)["id"] == "1"
    assert _unique_match("Unknown United", roster) is None


def test_tsdb_league_logo_extracts_badge():
    assert _league_logo(
        {"leagues": [{"strLeague": "NHL", "strBadge": "https://cdn.example/nhl.png"}]}
    ).endswith("nhl.png")


def test_tsdb_non_team_competition_artwork_catalogue_is_asset_only():
    assert TSDB_LOGO_BY_COMP["formula-1"]["source_competition_id"] == "4370"
    assert TSDB_LOGO_BY_COMP["formula-2"]["source_competition_id"] == "4486"
    assert TSDB_LOGO_BY_COMP["european-challenge-tour"]["source_competition_id"] == "4758"

    # These competition identities are allowed to fetch league artwork, but
    # they must never enter the team-roster badge path.
    assert "formula-1" not in TSDB_BY_COMP
    assert "formula-2" not in TSDB_BY_COMP
    assert "european-challenge-tour" not in TSDB_BY_COMP


def test_tsdb_asset_visibility_includes_null_legacy_rows():
    clause = str(_public_visibility_clause()).lower()
    assert "display_eligible is true" in clause or "display_eligible = true" in clause
    assert "display_eligible is null" in clause
