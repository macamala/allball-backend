from collector.provider import _list_public_event


def test_score_list_keeps_competition_and_team_artwork():
    payload = {
        "id": "ninko-evt-assets",
        "sport": "football",
        "competition": "test-league",
        "competition_key": "test-league",
        "competition_name": "Test League",
        "competition_logo": "https://cdn.example/league.svg",
        "event_family": "team_match",
        "home": {"id": "1", "name": "Alpha", "logo": "https://cdn.example/alpha.svg"},
        "away": {"id": "2", "name": "Beta", "logo": "https://cdn.example/beta.svg"},
        "start_time": "2026-09-25T10:00:00Z",
        "status": "scheduled",
        "score": {"home": None, "away": None},
        "country_id": "RS",
        "scope_type": "DOMESTIC",
    }
    public = _list_public_event(payload)
    assert public["competition_logo"] == "https://cdn.example/league.svg"
    assert public["home"]["logo"] == "https://cdn.example/alpha.svg"
    assert public["away"]["logo"] == "https://cdn.example/beta.svg"
    assert public["country_id"] == "RS"
