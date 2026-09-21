from collector.canonical_detail import attach_canonical_detail
from collector.detail_enrich import parse_fotmob_details, parse_mlb_live, parse_sofa_incidents
from collector.merge import merge_event_fields
from collector.normalize import normalize_event
from collector.tennis_score import derive_tennis_match_score
from collector.test_support import mock_event


def test_completed_sets_become_match_score_not_games():
    home, away = derive_tennis_match_score(
        [{"home": 6, "away": 3}, {"home": 6, "away": 4}],
        status="finished",
    )
    assert (home, away) == (2, 0)


def test_walkover_does_not_derive_score():
    home, away = derive_tennis_match_score([], status="finished", result_type="walkover")
    assert home is None and away is None


def test_normalize_replaces_game_score_with_sets():
    event = normalize_event(
        {
            "home": {"name": "A"},
            "away": {"name": "B"},
            "status": "finished",
            "score": {"home": 6, "away": 3},
            "periods": [{"home": 6, "away": 3}, {"home": 6, "away": 4}],
            "start_time": "2026-09-20T18:00:00Z",
        },
        sport_id="tennis",
        competition_id="wta-tour",
    )
    assert event["score"]["home"] == 2
    assert event["score"]["away"] == 0


def test_field_level_merge_keeps_complementary_sections():
    current = mock_event(
        status="finished",
        score={"home": 1, "away": 0},
        retrieved_at="2026-09-20T20:00:00Z",
        observed_at="2026-09-20T20:00:00Z",
    )
    current["incidents"] = [{"type": "goal", "minute": 12, "player": "Saka"}]
    incoming = mock_event(
        status="finished",
        score={"home": 1, "away": 0},
        retrieved_at="2026-09-20T21:00:00Z",
        observed_at="2026-09-20T21:00:00Z",
    )
    incoming["statistics"] = [{"label": "Possession", "home": 58, "away": 42}]
    incoming["lineups"] = {"home": {"start": [{"name": "Raya"}], "bench": []}, "away": {"start": [{"name": "Sanchez"}], "bench": []}}
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="src-b")
    assert merged["incidents"][0]["player"] == "Saka"
    assert merged["statistics"][0]["label"] == "Possession"
    assert merged["lineups"]["home"]["start"][0]["name"] == "Raya"


def test_newer_empty_stats_do_not_wipe_lineups():
    current = mock_event(status="finished", score={"home": 2, "away": 1})
    current["lineups"] = {"home": {"start": [{"name": "Raya"}]}}
    incoming = mock_event(status="finished", score={"home": 2, "away": 1})
    incoming["lineups"] = []
    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="src-b")
    assert merged["lineups"]["home"]["start"][0]["name"] == "Raya"


def test_fotmob_parser_maps_timeline_stats_lineups():
    payload = {
        "content": {
            "matchFacts": {
                "events": [
                    {"type": "Goal", "time": 12, "name": "Saka", "isHome": True, "homeScore": 1, "awayScore": 0},
                ]
            },
            "stats": {"Periods": {"All": {"stats": [{"stats": [{"title": "Possession", "stats": [58, 42]}]}]}}},
            "lineup": {
                "lineup": [
                    {"formation": "4-3-3", "players": [[{"name": {"fullName": "Raya"}, "shirtNumber": 1}]]},
                    {"formation": "4-2-3-1", "players": [[{"name": {"fullName": "Sanchez"}, "shirtNumber": 1}]]},
                ]
            },
        }
    }
    out = parse_fotmob_details(payload)
    assert out["incidents"][0]["player"] == "Saka"
    assert out["statistics"][0]["home"] == 58
    assert out["lineups"]["home"]["start"][0]["name"] == "Raya"


def test_sofa_and_mlb_parsers_do_not_fabricate():
    assert parse_sofa_incidents({}) == []
    assert parse_mlb_live({}) == {}


def test_attach_canonical_keeps_real_sections_only():
    event = attach_canonical_detail(
        {
            "incidents": [{"type": "goal", "minute": 12, "player": "Saka"}],
            "statistics": [{"label": "Possession", "home": 58, "away": 42}],
            "lineups": {"home": {"start": [{"name": "Raya"}], "bench": []}, "away": {"start": [{"name": "Sanchez"}], "bench": []}},
            "periods": [{"home": 1, "away": 0, "label": "1"}],
        }
    )
    assert event["timeline"]
    assert event["statistics"]
    assert event["lineups"]["home"]["start"]
    assert event["periods"]
