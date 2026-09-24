from collector.thesportsdb_asset_backfill import _league_logo, _teams, _unique_match


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
