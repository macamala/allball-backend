from collector.adapters_cricsheet import _event
from collector.adapters_fotmob import parse_fotmob_table
from collector.canonical_standings import canonicalize_standing_rows, unwrap_standings
from collector.identity_events import identity_confidence
from collector.standings_enrich import parse_mlb_standings, parse_nhl_standings


def test_identity_matches_club_core_and_city_suffix():
    ajax = {
        "sport": "football",
        "competition": "netherlands-eredivisie",
        "competition_key": "netherlands-eredivisie",
        "home": {"name": "AFC Ajax"},
        "away": {"name": "Willem II Tilburg"},
        "start_time": "2026-09-20T18:00:00Z",
    }
    fotmob = {
        "sport": "football",
        "competition": "netherlands-eredivisie",
        "competition_key": "netherlands-eredivisie",
        "home": {"name": "Ajax"},
        "away": {"name": "Willem II"},
        "start_time": "2026-09-20T18:00:00Z",
    }
    assert identity_confidence(ajax, fotmob) >= 90


def test_fotmob_table_parser():
    rows = parse_fotmob_table(
        {
            "table": [
                {
                    "data": {
                        "table": {
                            "all": [
                                {"name": "Roma", "idx": 1, "played": 4, "wins": 3, "draws": 1, "losses": 0, "pts": 10, "scoresStr": "8-2"},
                                {"name": "Napoli", "idx": 2, "played": 4, "wins": 2, "draws": 2, "losses": 0, "pts": 8, "scoresStr": "6-3"},
                            ]
                        }
                    }
                }
            ]
        }
    )
    assert rows[0]["team"] == "Roma"
    assert rows[0]["points"] == 10
    canonical = canonicalize_standing_rows(rows)
    assert canonical[0]["wins"] == 3
    assert canonical[0]["won"] == 3


def test_nhl_and_mlb_standings_parsers():
    nhl = parse_nhl_standings(
        {
            "standings": [
                {
                    "teamName": {"default": "Devils"},
                    "gamesPlayed": 4,
                    "wins": 3,
                    "losses": 1,
                    "otLosses": 0,
                    "points": 6,
                    "goalFor": 12,
                    "goalAgainst": 8,
                    "conferenceName": "East",
                    "divisionName": "Metro",
                    "leagueSequence": 2,
                }
            ]
        }
    )
    assert nhl[0]["team"] == "Devils"
    assert nhl[0]["points"] == 6
    mlb = parse_mlb_standings(
        {
            "records": [
                {
                    "division": {"name": "NL Central"},
                    "teamRecords": [
                        {"team": {"name": "Cubs"}, "divisionRank": "1", "gamesPlayed": 150, "leagueRecord": {"wins": 90, "losses": 60, "pct": ".600"}}
                    ],
                }
            ]
        }
    )
    assert mlb[0]["team"] == "Cubs"
    assert unwrap_standings(mlb)[0]["wins"] == 90


def test_cricsheet_innings_are_historical_not_live():
    event = _event(
        {
            "info": {
                "teams": ["Australia", "England"],
                "dates": ["2026-09-01"],
                "match_type": "T20",
                "outcome": {"winner": "Australia", "by": {"runs": 12}},
                "event": {"name": "T20I"},
                "venue": "MCG",
            },
            "innings": [
                {
                    "team": "Australia",
                    "overs": [{"deliveries": [{"runs": {"total": 6}}, {"runs": {"total": 1}, "wickets": [{}]}]}],
                },
                {"team": "England", "overs": [{"deliveries": [{"runs": {"total": 4}}]}]},
            ],
        }
    )
    assert event["status"] == "finished"
    assert event["sport_detail"]["historical"] is True
    assert event["sport_detail"]["live"] is False
    assert event["innings"][0]["wickets"] == 1
    assert event["source_event_ids"]["cricsheet"]
