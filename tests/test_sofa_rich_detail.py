from collector.detail_enrich import DETAIL_FAMILIES, parse_sofa_core, parse_sofa_lineups


def test_sofa_core_exposes_match_metadata_and_periods():
    payload = {
        "event": {
            "venue": {"stadium": {"name": "National Stadium"}},
            "referee": {"name": "Ref Name"},
            "roundInfo": {"name": "Quarterfinal"},
            "winnerCode": 1,
            "bestOf": 3,
            "status": {"description": "Ended", "type": "finished"},
            "homeScore": {"period1": 1, "period2": 2},
            "awayScore": {"period1": 0, "period2": 1},
        }
    }
    out = parse_sofa_core(payload)
    assert out["venue"] == "National Stadium"
    assert out["winner"] == "home"
    assert out["round"] == "Quarterfinal"
    assert out["sport_detail"]["referee"] == "Ref Name"
    assert out["sport_detail"]["best_of"] == 3
    assert out["periods"] == [
        {"label": "1", "home": 1, "away": 0},
        {"label": "2", "home": 2, "away": 1},
    ]


def test_branding_required_sportscore_is_not_a_rich_detail_fallback():
    assert "sportscore" not in DETAIL_FAMILIES



def test_sofa_lineups_preserve_player_identity_assets():
    out = parse_sofa_lineups(
        {
            "confirmed": True,
            "home": {
                "formation": "4-2-3-1",
                "players": [
                    {
                        "player": {
                            "id": 123,
                            "name": "Player One",
                            "country": {"alpha3": "SRB"},
                        },
                        "jerseyNumber": "9",
                        "position": "F",
                        "rating": 8.1,
                        "captain": True,
                    }
                ],
            },
            "away": {"players": [{"player": {"id": 456, "name": "Player Two"}, "substitute": True}]},
        }
    )
    player = out["home"]["start"][0]
    assert out["confirmed"] is True
    assert player["id"] == 123
    assert player["country_id"] == "SRB"
    assert player["captain"] is True
    assert player["image"].endswith("/player/123/image")
