from collector.canonical_detail import attach_canonical_detail
from collector.detail_enrich import parse_fotmob_details, parse_mlb_live, parse_nhl_boxscore, parse_sofa_incidents
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
            "stats": {
                "Periods": {
                    "All": {"stats": [{"stats": [{"title": "Expected goals (xG)", "stats": ["1.51", "1.47"]}]}]},
                    "FirstHalf": {"stats": [{"stats": [{"title": "Expected goals (xG)", "stats": ["0.80", "0.55"]}]}]},
                    "SecondHalf": {"stats": [{"stats": [{"title": "Expected goals (xG)", "stats": ["0.71", "0.92"]}]}]},
                }
            },
            "lineup": {
                "homeTeam": {"formation": "4-3-3", "coach": {"name": "Vanoli"}, "starters": [{"id": 174543, "name": "De Bruyne", "shirtNumber": 11, "performance": {"rating": 8.1}}], "subs": []},
                "awayTeam": {"formation": "4-4-2", "starters": [{"name": "Keeper", "shirtNumber": 1}], "subs": []},
            },
            "playerStats": {
                "11": {
                    "id": 174543,
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
    assert out["statistics"][0]["label"] == "Expected goals (xG)"\n    assert out["sport_detail"]["statistics_periods"]["first_half"][0]["home"] == "0.80"\n    assert out["sport_detail"]["statistics_periods"]["second_half"][0]["away"] == "0.92"
    assert out["lineups"]["home"]["formation"] == "4-3-3"
    assert out["lineups"]["home"]["coach"] == "Vanoli"\n    assert out["lineups"]["home"]["start"][0]["image"].endswith("/playerimages/174543.png")
    assert out["player_statistics"][0]["goals"] == 1\n    assert out["player_statistics"][0]["image"].endswith("/playerimages/174543.png")
    assert out["sport_detail"]["shots"] == 2


def test_mlb_uses_real_batting_order_and_player_headshots():
    payload = {
        "liveData": {
            "boxscore": {
                "teams": {
                    "home": {
                        "battingOrder": [10],
                        "players": {
                            "ID10": {
                                "person": {"id": 10, "fullName": "Starter"},
                                "jerseyNumber": "7",
                                "position": {"abbreviation": "CF"},
                                "stats": {"batting": {"hits": 2, "atBats": 4, "runs": 1}},
                            },
                            "ID11": {
                                "person": {"id": 11, "fullName": "Bench"},
                                "jerseyNumber": "22",
                                "position": {"abbreviation": "1B"},
                                "stats": {"batting": {"hits": 0, "atBats": 0}},
                            },
                        },
                    },
                    "away": {
                        "battingOrder": [20],
                        "players": {
                            "ID20": {
                                "person": {"id": 20, "fullName": "Away Starter"},
                                "jerseyNumber": "3",
                                "position": {"abbreviation": "SS"},
                                "stats": {"batting": {"hits": 1, "atBats": 3}},
                            }
                        },
                    },
                }
            },
            "plays": {},
            "linescore": {},
        }
    }
    out = parse_mlb_live(payload)
    assert out["lineups"]["home"]["start"][0]["name"] == "Starter"
    assert out["lineups"]["home"]["bench"][0]["name"] == "Bench"
    assert "/people/10/headshot/" in out["lineups"]["home"]["start"][0]["image"]
    assert out["player_statistics"][0]["position"] == "CF"


def test_nhl_boxscore_preserves_player_media_and_positions():
    payload = {
        "playerByGameStats": {
            "homeTeam": {
                "forwards": [
                    {
                        "playerId": 8478402,
                        "name": {"default": "Connor Example"},
                        "sweaterNumber": 97,
                        "position": "C",
                        "headshot": "https://assets.nhle.com/mugs/nhl/latest/8478402.png",
                        "goals": 1,
                        "assists": 2,
                        "sog": 5,
                    }
                ]
            },
            "awayTeam": {"forwards": []},
        }
    }
    out = parse_nhl_boxscore(payload)
    player = out["player_statistics"][0]
    assert player["id"] == 8478402
    assert player["position"] == "C"
    assert player["image"].endswith("/8478402.png")
    assert out["lineups"]["home"]["start"][0]["number"] == 97


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
    tt = parse_clicktt_live(
        {
            "data": {
                "matches": [
                    {
                        "sets_home": 3,
                        "sets_guest": 1,
                        "player_home": "Mueller",
                        "player_guest": "Schmidt",
                        "sets": [{"home": 11, "away": 7}, {"home": 11, "away": 9}, {"home": 9, "away": 11}, {"home": 11, "away": 8}],
                    }
                ]
            }
        }
    )
    assert tt["sport_detail"]["meeting"] is True
    assert tt["sport_detail"]["rubbers"][0]["home_player"] == "Mueller"
    assert tt["sport_detail"]["rubbers"][0]["games"][0]["home"] == 11
    ol = parse_openliga_match({"goals": [{"goalGetterName": "Müller", "matchMinute": 12, "scoreTeam1": 1, "scoreTeam2": 0}], "matchResults": [{"resultName": "Halbzeit", "pointsTeam1": 1, "pointsTeam2": 0}]})
    assert ol["incidents"] or ol["periods"]


def test_euroleague_boxscore_quarters_and_players():
    from collector.detail_families import parse_euroleague_box

    out = parse_euroleague_box(
        {
            "ByQuarter": [
                {"Quarter1": 22, "Quarter2": 18, "Quarter3": 20, "Quarter4": 21},
                {"Quarter1": 19, "Quarter2": 20, "Quarter3": 15, "Quarter4": 18},
            ],
            "Stats": [
                {"Score": 81, "TotalRebounds": 40, "PlayersStats": [{"Player": "Larkin", "Points": 18, "TotalRebounds": 4, "Assistances": 6}]},
                {"Score": 72, "TotalRebounds": 33, "PlayersStats": [{"Player": "Baldwin", "Points": 14, "TotalRebounds": 3, "Assistances": 5}]},
            ],
        }
    )
    assert out["periods"][0]["home"] == 22
    assert out["statistics"][0]["home"] == 81
    assert out["player_statistics"][0]["name"] == "Larkin"
    merged = attach_canonical_detail({"sport": "basketball", "score": {"home": 81, "away": 72}, **out})
    assert merged["periods"][0]["home"] == 22
    assert merged["player_statistics"][0]["points"] == 18


def test_nhl_period_scores_from_scoring_goals_and_stored_incidents():
    from collector.canonical_detail import periods_from_hockey_goals
    from collector.detail_enrich import parse_nhl_landing

    parsed = parse_nhl_landing(
        {
            "homeTeam": {"score": 2, "sog": 28},
            "awayTeam": {"score": 1, "sog": 19},
            "summary": {
                "scoring": [
                    {"periodDescriptor": {"number": 1}, "goals": []},
                    {
                        "periodDescriptor": {"number": 2},
                        "goals": [{"name": {"default": "C. Eiserman"}, "timeInPeriod": "00:55", "homeScore": 0, "awayScore": 1}],
                    },
                    {
                        "periodDescriptor": {"number": 3},
                        "goals": [{"name": {"default": "N. Hischier"}, "timeInPeriod": "12:00", "homeScore": 2, "awayScore": 1}],
                    },
                ]
            },
        }
    )
    assert parsed["periods"] == [
        {"label": 1, "home": 0, "away": 0},
        {"label": 2, "home": 0, "away": 1},
        {"label": 3, "home": 2, "away": 1},
    ]
    assert parsed["incidents"][0]["type"] == "goal"
    derived = periods_from_hockey_goals(parsed["incidents"])
    assert derived[2]["home"] == 2
    event = attach_canonical_detail(
        {"sport": "ice-hockey", "score": {"home": 2, "away": 1}, "incidents": parsed["incidents"]}
    )
    assert event["periods"][0]["home"] == 0
    assert event["periods"][2]["away"] == 1
    sparse = parse_nhl_landing({"homeTeam": {"score": 3}, "awayTeam": {"score": 0}, "summary": {"scoring": [{"periodDescriptor": {"number": 1}, "goals": []}]}})
    assert "periods" not in sparse


def test_lol_series_keeps_game_identity():
    from collector.detail_families import parse_lol_event

    parsed = parse_lol_event(
        {
            "data": {
                "event": {
                    "id": "event-1",
                    "match": {
                        "id": "match-1",
                        "strategy": {"count": 5},
                        "teams": [
                            {"id": "blue-team", "name": "KT Rolster", "result": {"gameWins": 2}},
                            {"id": "red-team", "name": "T1", "result": {"gameWins": 3}},
                        ],
                        "games": [
                            {"id": "game-1", "number": 1, "state": "completed", "teams": [{"id": "blue-team", "side": "blue"}, {"id": "red-team", "side": "red"}]},
                        ],
                    },
                }
            }
        },
        windows={
            "game-1": {
                "frames": [
                    {"rfc460Timestamp": "2025-11-09T07:32:00Z", "gameState": "in_game"},
                    {"rfc460Timestamp": "2025-11-09T08:24:00Z", "gameState": "finished", "blueTeam": {"totalKills": 11}, "redTeam": {"totalKills": 25}},
                ],
                "gameMetadata": {
                    "blueTeamMetadata": {"esportsTeamId": "blue-team"},
                    "redTeamMetadata": {"esportsTeamId": "red-team"},
                },
            }
        },
    )
    game = parsed["sport_detail"]["games"][0]
    assert parsed["sport_detail"]["series_id"] == "match-1"
    assert parsed["sport_detail"]["best_of"] == 5
    assert game["id"] == "game-1"
    assert game["blue"]["name"] == "KT Rolster"
    assert game["blue"]["kills"] == 11
    assert game["red"]["side"] == "red"
    assert game["duration"] == 3120
    assert "winner" not in game
    assert "maps" not in parsed


def test_bbc_cricket_innings_and_live_flag_are_explicit():
    from collector.detail_families import match_bbc_cricket, parse_bbc_cricket_payload

    payload = {
        "eventGroups": [
            {
                "id": "e-finished",
                "status": "PostEvent",
                "startDateTime": "2020-01-01T00:00:00Z",
                "tournamentName": "Women's International Twenty20 Match",
                "groundName": "Nisshin",
                "matchSummary": {"winnerTeamName": "Pakistan Women", "resultString": "win by 31 runs"},
                "participants": {
                    "homeTeam": {"name": "Pakistan Women", "innings": [{"runs": "145", "wickets": "8", "overs": "20.0", "inningsNumber": "1", "isLive": False}]},
                    "awayTeam": {"name": "Bangladesh Women", "innings": [{"runs": "114", "wickets": "7", "overs": "20.0", "inningsNumber": "2", "isLive": False}]},
                },
            },
            {
                "id": "e-live",
                "status": "InPlay",
                "tournamentName": "Men's Australia One-Day Cup",
                "matchSummary": {"resultString": "Queensland Bulls are 4 for 0"},
                "participants": {
                    "homeTeam": {"name": "Queensland Bulls", "innings": [{"runs": "4", "wickets": "0", "overs": "1.3", "isLive": True}]},
                    "awayTeam": {"name": "New South Wales", "innings": None},
                },
            },
            {
                "id": "e-soon",
                "status": "PreEvent",
                "startDateTime": "2026-09-22T11:30:00Z",
                "tournamentName": "Men's One Day International Series",
                "participants": {
                    "homeTeam": {"name": "England", "innings": None},
                    "awayTeam": {"name": "Sri Lanka", "innings": None},
                },
            },
        ]
    }
    rows = parse_bbc_cricket_payload(payload)
    finished = match_bbc_cricket(rows, "Pakistan Women", "Bangladesh Women")
    assert finished["live"] is False
    assert finished["sport_detail"]["live"] is False
    assert finished["sport_detail"]["historical"] is False
    assert finished["innings"][0]["runs"] == 145
    assert finished["innings"][0]["wickets"] == 8
    assert finished["innings"][0]["overs"] == "20.0"
    assert finished["innings"][1]["runs"] == 114
    assert finished["sport_detail"]["result"] == "win by 31 runs"
    live = next(row for row in rows if row["id"] == "e-live")
    assert live["live"] is True
    assert live["innings"][0]["live"] is True
    soon = next(row for row in rows if row["id"] == "e-soon")
    assert soon["live"] is False
    assert soon["status"] == "scheduled"
    assert match_bbc_cricket(rows, "England", "Sri Lanka") == {}


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


def test_opendota_player_stats_and_afl_goals():
    from collector.detail_families import parse_opendota_match, parse_squiggle_game

    dota = parse_opendota_match(
        {
            "duration": 2400,
            "radiant_win": True,
            "radiant_score": 32,
            "dire_score": 18,
            "players": [
                {"personaname": "Miracle", "isRadiant": True, "kills": 12, "deaths": 2, "assists": 8, "hero_id": 1},
                {"personaname": "Yatoro", "isRadiant": False, "kills": 4, "deaths": 7, "assists": 6, "hero_id": 2},
            ],
        }
    )
    assert dota["player_statistics"][0]["kills"] == 12
    assert dota["sport_detail"]["duration"] == 2400
    afl = parse_squiggle_game({"hgoals": 15, "agoals": 10, "hbehinds": 9, "abehinds": 7, "hscore": 99, "ascore": 67, "venue": "MCG"})
    assert afl["sport_detail"]["goals"]["home"] == 15
    assert afl["sport_detail"]["behinds"]["away"] == 7
    assert afl["venue"] == "MCG"
