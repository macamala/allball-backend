from collector.html_parse import _dict_event


def test_generic_json_preserves_team_identity_assets():
    event = _dict_event(
        {
            "id": "m1",
            "homeTeam": {
                "id": 10,
                "name": "Alpha",
                "teamIconUrl": "https://cdn.example/alpha.png",
                "countryCode": "RS",
            },
            "awayTeam": {
                "id": 20,
                "name": "Beta",
                "badge": "https://cdn.example/beta.png",
                "countryCode": "HR",
            },
            "status": "scheduled",
            "startDate": "2026-09-24T10:00:00Z",
        }
    )
    assert event["home"]["id"] == "10"
    assert event["home"]["logo"] == "https://cdn.example/alpha.png"
    assert event["home"]["country_id"] == "RS"
    assert event["away"]["id"] == "20"
    assert event["away"]["logo"] == "https://cdn.example/beta.png"
    assert event["away"]["country_id"] == "HR"
