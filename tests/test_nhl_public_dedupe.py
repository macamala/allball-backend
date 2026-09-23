from collector.provider import _public_participant_equivalent


def _evt(home, away):
    return {
        "sport": "ice-hockey",
        "competition": "NHL",
        "competition_key": "nhl",
        "home": {"name": home},
        "away": {"name": away},
        "start_time": "2026-09-23T23:00:00Z",
    }


def test_nhl_abbreviation_public_identity():
    left = _evt("OTT", "TOR")
    right = _evt("Ottawa Senators", "Toronto Maple Leafs")
    assert _public_participant_equivalent("OTT", "Ottawa Senators", left, right)
    assert _public_participant_equivalent("TOR", "Toronto Maple Leafs", left, right)


def test_nhl_abbreviation_does_not_cross_sports():
    left = {"sport": "football", "competition_key": "nhl"}
    right = {"sport": "football", "competition_key": "nhl"}
    assert not _public_participant_equivalent("OTT", "Ottawa Senators", left, right)
