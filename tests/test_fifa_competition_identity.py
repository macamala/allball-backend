from collector.adapters_feeds import FifaFootballAdapter


def _team(team_id, name, country, team_type=0):
    return {
        "IdTeam": team_id,
        "IdCountry": country,
        "IdAssociation": country,
        "TeamType": team_type,
        "TeamName": [{"Locale": "en-gb", "Description": name}],
    }


def test_fifa_domestic_competition_is_country_qualified():
    row = {
        "IdMatch": "tun-1",
        "IdCompetition": "f4jc2cc5nq7flaoptpi5ua4k4",
        "CompetitionName": [{"Locale": "en-gb", "Description": "Ligue 1"}],
        "HomeTeam": _team("1", "Espérance de Tunisie", "TUN"),
        "AwayTeam": _team("2", "US Monastir", "TUN"),
        "Date": "2026-09-24T00:00:00Z",
        "MatchStatus": 1,
    }
    event = FifaFootballAdapter()._event(row)
    assert event is not None
    assert event["competition_key"] == "football-tun-ligue-1"
    assert event["country_id"] == "TUN"
    assert event["source_competition_id"] == "f4jc2cc5nq7flaoptpi5ua4k4"
    assert event["source_competition_name"] == "Ligue 1"


def test_fifa_international_competition_does_not_fake_country():
    row = {
        "IdMatch": "cnl-1",
        "IdCompetition": "cu0rmpyff5692eo06ltddjo8a",
        "CompetitionName": [{"Locale": "en-gb", "Description": "Concacaf Nations League"}],
        "HomeTeam": _team("1", "Bahamas", "BAH", team_type=1),
        "AwayTeam": _team("2", "Saint Martin", "MAF", team_type=1),
        "Date": "2026-09-23T20:00:00Z",
        "MatchStatus": 1,
    }
    event = FifaFootballAdapter()._event(row)
    assert event is not None
    assert event["competition_key"] == "football-concacaf-nations-league"
    assert event["country_id"] is None
