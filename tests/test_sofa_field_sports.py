from collector.adapters_sofascore import event_family_for_sport, sofa_field_event
from collector.detail_enrich import parse_sofa_standings


def test_sofascore_event_models_are_sport_native():
    assert event_family_for_sport("mma") == "combat"
    assert event_family_for_sport("golf") == "tournament"
    assert event_family_for_sport("motorsport") == "motorsport_race"
    assert event_family_for_sport("tennis") == "individual_match"
    assert event_family_for_sport("rugby") == "team_match"


def test_sofa_field_event_builds_meta_event_without_fake_pair_score():
    row = {
        "id": 991,
        "tournament": {"uniqueTournament": {"id": 44, "name": "Formula 1"}},
        "roundInfo": {"name": "Japanese Grand Prix - Qualifying"},
        "status": {"type": "notstarted"},
        "startTimestamp": 1790100000,
    }
    event = sofa_field_event(row, "motorsport-int-formula-1-t44", "motorsport")
    assert event["event_family"] == "motorsport_race"
    assert event["tournament"] == "Japanese Grand Prix - Qualifying"
    assert event["score"] == {"home": None, "away": None}


def test_sofa_standings_flattens_classification_rows():
    payload = {
        "standings": [{
            "rows": [
                {"position": 1, "player": {"name": "Driver One", "country": {"alpha2": "AU"}}, "time": "1:20.123"},
                {"position": 2, "player": {"name": "Driver Two"}, "gap": "+0.210"},
            ]
        }]
    }
    rows = parse_sofa_standings(payload)
    assert rows[0]["position"] == 1
    assert rows[0]["name"] == "Driver One"
    assert rows[0]["nation"] == "AU"
    assert rows[1]["gap"] == "+0.210"
