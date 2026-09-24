from collector.adapters_fotmob import parse_fotmob_table
from collector.fotmob_asset_backfill import _fill_side, _roster, _unique_match


def test_fotmob_table_preserves_team_id_and_crest():
    payload = {
        "data": {
            "table": {
                "all": [
                    {
                        "id": 9825,
                        "name": "Manchester United",
                        "idx": 1,
                        "played": 5,
                        "wins": 4,
                        "draws": 1,
                        "losses": 0,
                        "pts": 13,
                    }
                ]
            }
        }
    }
    rows = parse_fotmob_table(payload)
    assert rows[0]["team_id"] == "9825"
    assert rows[0]["logo"].endswith("/teamlogo/9825.png")

    roster = _roster(payload)
    assert roster[0]["id"] == "9825"
    assert roster[0]["name"] == "Manchester United"


def test_fotmob_roster_matches_unique_legal_name_variant():
    roster = [
        {
            "id": "9825",
            "name": "Manchester United",
            "folded": "manchester united",
            "logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9825.png",
        },
        {
            "id": "8455",
            "name": "Manchester City",
            "folded": "manchester city",
            "logo": "https://images.fotmob.com/image_resources/logo/teamlogo/8455.png",
        },
    ]
    matched = _unique_match("Manchester United FC", roster)
    assert matched["id"] == "9825"

    side, changed = _fill_side({"name": "Manchester United FC"}, roster)
    assert changed is True
    assert side["id"] == "9825"
    assert side["logo"].endswith("/teamlogo/9825.png")


def test_fotmob_roster_does_not_choose_ambiguous_alias():
    roster = [
        {"id": "1", "name": "United FC", "folded": "united", "logo": "a"},
        {"id": "2", "name": "United SC", "folded": "united", "logo": "b"},
    ]
    assert _unique_match("United", roster) is None
