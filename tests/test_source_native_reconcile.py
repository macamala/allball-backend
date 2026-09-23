from types import SimpleNamespace

from collector.enrichment import quality_flags_for_event
from collector.source_native_reconcile import _safe_public_key


def test_team_match_does_not_flag_absent_optional_aliases():
    flags = quality_flags_for_event({
        "sport": "football",
        "home": {"name": "Arsenal"},
        "away": {"name": "Chelsea"},
        "score": {"home": 1, "away": 0},
    })
    assert "participant_a:empty_name" not in flags
    assert "participant_b:empty_name" not in flags


def test_fifa_ligue_one_is_country_qualified():
    row = SimpleNamespace(competition_id="football-ligue-1", country_id="TUN")
    assert _safe_public_key(
        row,
        {"source_family": "fifa-digital", "source_competition_name": "Ligue 1"},
    ) == "football-tun-ligue-1"


def test_ghana_premier_league_does_not_collapse_to_england():
    row = SimpleNamespace(competition_id="england-premier-league", country_id="GHA")
    assert _safe_public_key(
        row,
        {"source_family": "fifa-digital", "source_competition_name": "Premier League"},
    ) == "football-gha-premier-league"
