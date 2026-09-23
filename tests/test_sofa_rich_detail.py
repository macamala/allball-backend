from collector.detail_enrich import DETAIL_FAMILIES, parse_sofa_core


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
