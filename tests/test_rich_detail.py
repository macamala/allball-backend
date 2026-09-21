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


def test_fotmob_parser_maps_infobox_player_stats_and_xg():
    from collector.detail_enrich import parse_fotmob_details

    payload = {
        "general": {"homeTeam": {"id": 1}, "awayTeam": {"id": 2}},
        "content": {
            "matchFacts": {
                "events": {"events": [{"type": "Substitution", "time": 60, "name": "In", "isHome": True}]},
                "infoBox": {
                    "Stadium": {"name": "Artemio Franchi"},
                    "Referee": {"text": "Daniele Doveri"},
                    "Attendance": 38000,
                },
            },
            "stats": {"Periods": {"All": {"stats": [{"stats": [{"title": "Expected goals (xG)", "stats": ["1.51", "1.47"]}]}]}}},
            "lineup": {
                "homeTeam": {"formation": "4-3-3", "coach": {"name": "Vanoli"}, "starters": [{"name": "De Bruyne", "shirtNumber": 11, "performance": {"rating": 8.1}}], "subs": []},
                "awayTeam": {"formation": "4-4-2", "starters": [{"name": "Keeper", "shirtNumber": 1}], "subs": []},
            },
            "playerStats": {
                "11": {
                    "name": "De Bruyne",
                    "teamId": 1,
                    "shirtNumber": 11,
                    "stats": [{"title": "Top stats", "stats": {"FotMob rating": {"stat": {"value": 8.1}}, "Goals": {"stat": {"value": 1}}}}],
                }
            },
            "shotmap": {"shots": [{"isOnTarget": True}, {"isOnTarget": False}]},
        },
    }
    out = parse_fotmob_details(payload)
    assert out["venue"] == "Artemio Franchi"
    assert out["referee"] == "Daniele Doveri"
    assert out["attendance"] == 38000
    assert out["statistics"][0]["label"] == "Expected goals (xG)"
    assert out["lineups"]["home"]["formation"] == "4-3-3"
    assert out["lineups"]["home"]["coach"] == "Vanoli"
    assert out["player_statistics"][0]["goals"] == 1
    assert out["sport_detail"]["shots"] == 2


def test_rugby_and_squiggle_and_jolpica_parsers():
    from collector.detail_families import parse_jolpica_results, parse_rugby_detail, parse_squiggle_game

    rugby = parse_rugby_detail(
        {"venue": {"name": "Murrayfield"}, "attendance": 12000},
        {"teamStats": [{"stats": {"Tries": 2, "Conversions": 1}, "playerStats": [{"player": {"name": {"display": "A"}}, "stats": {"Tries": 1}}]}, {"stats": {"Tries": 1, "Conversions": 0}, "playerStats": []}]},
        {"officials": [{"official": {"name": {"display": "Ref A"}}}]},
    )
    assert rugby["venue"] == "Murrayfield"
    assert rugby["statistics"][0]["label"] in {"Tries", "Conversions"}
    assert rugby["referee"] == "Ref A"
    afl = parse_squiggle_game({"hgoals": 12, "agoals": 9, "hbehinds": 8, "abehinds": 6, "hscore": 80, "ascore": 60, "venue": "MCG"})
    assert afl["periods"][0]["home"] == 12
    f1 = parse_jolpica_results({"MRData": {"RaceTable": {"Races": [{"Circuit": {"circuitName": "Monza"}, "Results": [{"position": "1", "Driver": {"givenName": "Max", "familyName": "Verstappen"}, "status": "Finished"}]}]}}})
    assert f1["classification"][0]["name"] == "Max Verstappen"
    from collector.detail_families import parse_championdata_match, parse_clicktt_live, parse_openliga_match

    cd = parse_championdata_match({"homeSquadScoreQ1": 15, "awaySquadScoreQ1": 12, "homeSquadScoreQ2": 14, "awaySquadScoreQ2": 18})
    assert cd["periods"][0]["home"] == 15
    tt = parse_clicktt_live({"matches": [{"sets_home": 3, "sets_guest": 1}]})
    assert tt["periods"][0]["home"] == 3
    ol = parse_openliga_match({"goals": [{"goalGetterName": "Müller", "matchMinute": 12, "scoreTeam1": 1, "scoreTeam2": 0}], "matchResults": [{"resultName": "Halbzeit", "pointsTeam1": 1, "pointsTeam2": 0}]})
    assert ol["incidents"] or ol["periods"]


def test_nhl_period_scores_from_score_by_period():
    from collector.detail_enrich import parse_nhl_landing

    out = parse_nhl_landing(
        {
            "homeTeam": {"score": 3, "sog": 30, "scoreByPeriod": [1, 0, 2]},
            "awayTeam": {"score": 2, "sog": 22, "scoreByPeriod": [0, 1, 1]},
            "summary": {"scoring": [], "penalties": []},
        }
    )
    assert out["periods"][0] == {"label": 1, "home": 1, "away": 0}
    assert out["statistics"][0]["label"] == "Shots"


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
