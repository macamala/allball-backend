import json

from collector.detail_enrich import parse_fiba_game_detail
from collector.fiba_breadth import game_to_event


def _flight(node):
    body = "a:" + json.dumps({"root": node}, separators=(",", ":"))
    outer = json.dumps([1, body])
    return f"<script>self.__next_f.push({outer})</script>"


def test_fiba_event_keeps_official_game_detail_url():
    event = game_to_event(
        {
            "gameId": 135067,
            "gameDateTime": "2026-09-25T10:00:00Z",
            "teamA": {"organisationId": 34, "code": "CAN", "officialName": "Canada"},
            "teamB": {"organisationId": 134, "code": "SEN", "officialName": "Senegal"},
            "competition": {"officialName": "FIBA Test"},
        },
        {
            "slug": "fiba-test-2026",
            "name": "FIBA Test",
            "country": "Canada",
            "city": "Toronto",
            "gender": "M",
        },
    )
    assert event["extra"]["fiba_game_url"] == (
        "https://www.fiba.basketball/en/events/fiba-test-2026/games/135067-CAN-SEN"
    )
    assert event["extra"]["fiba_home_code"] == "CAN"
    assert event["extra"]["fiba_away_code"] == "SEN"


def test_fiba_rich_detail_parses_periods_boxscore_roster_and_pbp():
    node = {
        "game": {
            "gameId": 135067,
            "teamA": {"code": "CAN"},
            "teamB": {"code": "SEN"},
        },
        "playersTeamA": [
            {
                "personId": "101",
                "firstName": "Alice",
                "lastName": "Guard",
                "position": "PG",
                "uniformNumber": "4",
                "isCaptain": True,
            }
        ],
        "playersTeamB": [
            {
                "personId": "202",
                "firstName": "Beth",
                "lastName": "Wing",
                "position": "SF",
                "uniformNumber": "8",
                "isCaptain": False,
            }
        ],
        "gameDetails": {
            "c": [
                {
                    "Id": "T_CAN",
                    "Score": 72,
                    "Stats": {"PTS": 72, "REB": 40, "AS": 18, "TO": 10},
                    "Children": [{
                        "Id": "P_101",
                        "Stats": {
                            "Starter": True,
                            "HasPlayed": True,
                            "PTS": 20,
                            "REB": 5,
                            "AS": 8,
                            "ST": 2,
                            "BS": 1,
                            "TO": 3,
                            "PF": 2,
                            "FGM": 7,
                            "FGA": 12,
                            "FG3M": 3,
                            "FG3A": 6,
                            "FTM": 3,
                            "FTA": 4,
                            "EFF": 27,
                            "PM": 9,
                        },
                    }],
                },
                {
                    "Id": "T_SEN",
                    "Score": 57,
                    "Stats": {"PTS": 57, "REB": 31, "AS": 12, "TO": 15},
                    "Children": [{
                        "Id": "P_202",
                        "Stats": {
                            "Starter": False,
                            "HasPlayed": True,
                            "PTS": 11,
                            "REB": 4,
                            "AS": 2,
                            "ST": 1,
                            "BS": 0,
                            "TO": 1,
                            "PF": 3,
                            "FGM": 5,
                            "FGA": 9,
                            "FG3M": 1,
                            "FG3A": 3,
                            "FTM": 0,
                            "FTA": 0,
                            "EFF": 12,
                            "PM": -4,
                        },
                    }],
                },
            ]
        },
        "playByPlay": {
            "items": {
                "Q1": {
                    "name": "Q1",
                    "scoreA": 22,
                    "scoreB": 14,
                    "items": [{
                        "order": 1,
                        "act": "shot",
                        "ac": "P3",
                        "txt": "Alice Guard 3pt made",
                        "pId": "101",
                        "SA": 3,
                        "SB": 0,
                        "Time": "09:42",
                    }],
                },
                "Q2": {
                    "name": "Q2",
                    "scoreA": 40,
                    "scoreB": 30,
                    "items": [{
                        "order": 2,
                        "act": "foul",
                        "txt": "Personal foul",
                        "pId": "202",
                        "SA": 40,
                        "SB": 30,
                        "Time": "00:12",
                    }],
                },
            }
        },
    }

    out = parse_fiba_game_detail(_flight(node))
    assert out["periods"] == [
        {"label": "Q1", "home": 22, "away": 14},
        {"label": "Q2", "home": 18, "away": 16},
    ]
    assert any(row["label"] == "Rebounds" and row["home"] == 40 and row["away"] == 31 for row in out["statistics"])
    assert out["lineups"]["home"]["start"][0]["name"] == "Alice Guard"
    assert out["lineups"]["away"]["bench"][0]["name"] == "Beth Wing"
    alice = next(row for row in out["player_statistics"] if row["name"] == "Alice Guard")
    assert alice["points"] == 20
    assert alice["assists"] == 8
    assert alice["plus_minus"] == 9
    assert out["incidents"][0]["minute"] == "09:42"
    assert out["incidents"][0]["score_after"] == {"home": 3, "away": 0}
    assert out["sport_detail"]["play_by_play_actions"] == 2
