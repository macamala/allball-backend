"""Sanitized fixtures from the public responses probed for this pass."""

from collector.rich_public import (
    parse_altius_match,
    parse_championdata_detail,
    parse_gri_results,
    parse_ibu_results,
    parse_letour_rankings,
    parse_letrot_race,
    parse_liiga_bundle,
    parse_wec_summary,
    parse_world_aquatics,
)


def test_championdata_nrl_maps_team_and_player_stats():
    parsed = parse_championdata_detail(
        {
            "matchStats": {
                "matchInfo": {"homeSquadId": 1, "awaySquadId": 2, "venueName": "Penrith Park"},
                "teamStats": {
                    "team": [
                        {"squadId": 1, "tries": 7, "tackles": 322, "lineBreaks": 11, "tryAssists": 5, "metresGained": 1640, "score": 38},
                        {"squadId": 2, "tries": 2, "tackles": 301, "lineBreaks": 4, "tryAssists": 1, "metresGained": 1210, "score": 10},
                    ]
                },
                "playerInfo": {"player": [{"playerId": 9, "displayName": "Nathan Cleary", "squadId": 1}]},
                "playerStats": {"player": [{"playerId": 9, "squadId": 1, "tries": 1, "tackles": 20, "lineBreaks": 2, "metresGained": 84, "tryAssists": 1}]},
                "teamPeriodStats": {
                    "team": [
                        {"squadId": 1, "period": 1, "score": 12},
                        {"squadId": 2, "period": 1, "score": 0},
                    ]
                },
            }
        }
    )
    assert parsed["statistics"][0] == {"label": "Tries", "home": 7, "away": 2}
    assert parsed["player_statistics"][0]["name"] == "Nathan Cleary"
    assert parsed["player_statistics"][0]["line_breaks"] == 2
    assert "playerId" not in parsed["player_statistics"][0]
    assert parsed["periods"][0]["home"] == 12
    assert parsed["sport_detail"]["tries"]["home"] == 7
    assert parsed["venue"] == "Penrith Park"


def test_championdata_netball_does_not_invent_tries():
    parsed = parse_championdata_detail(
        {
            "matchStats": {
                "matchInfo": {"homeSquadId": 4, "awaySquadId": 5},
                "teamStats": {
                    "team": [
                        {"squadId": 4, "goals": 60, "goalAssists": 40, "goalMisses": 8},
                        {"squadId": 5, "goals": 52, "goalAssists": 33, "goalMisses": 11},
                    ]
                },
                "playerInfo": {"player": [{"playerId": 3, "displayName": "Goal Attack", "squadId": 4}]},
                "playerStats": {"player": [{"playerId": 3, "squadId": 4, "goals": 28, "goalAssists": 4}]},
            }
        }
    )
    labels = [row["label"] for row in parsed["statistics"]]
    assert "Tries" not in labels
    assert parsed["statistics"][0]["home"] == 60
    assert parsed["player_statistics"][0]["goals"] == 28
    assert "sport_detail" not in parsed


def test_liiga_periods_goals_and_shots_drop_ids():
    parsed = parse_liiga_bundle(
        {
            "game": {
                "periods": [{"index": 1, "homeTeamGoals": 2, "awayTeamGoals": 1, "category": "NORMAL"}],
                "homeTeam": {
                    "goals": 3,
                    "goalEvents": [
                        {
                            "gameTime": 125,
                            "scorerPlayer": {"firstName": "Vili", "lastName": "Alitalo"},
                            "assistantPlayers": [],
                            "homeTeamScore": 1,
                            "awayTeamScore": 0,
                        }
                    ],
                    "penaltyEvents": [],
                },
                "awayTeam": {"goals": 4, "goalEvents": [], "penaltyEvents": []},
                "iceRink": {"name": "Helsinki Hall"},
            },
            "homeTeamPlayers": [{"id": 7, "firstName": "Vili", "lastName": "Alitalo", "line": 1, "role": "forward"}],
            "awayTeamPlayers": [{"id": 8, "firstName": "A", "lastName": "Goalie", "role": "goalie"}],
        },
        {"homeTeam": [{"goals": 3, "shots": 28, "penaltyMinutes": 4}], "awayTeam": [{"goals": 4, "shots": 31, "penaltyMinutes": 2}]},
        [{"period": 1, "shotX": 10, "shotY": 20, "shooterId": 7, "eventType": "shot"}],
    )
    assert parsed["periods"][0] == {"label": 1, "home": 2, "away": 1}
    assert parsed["incidents"][0]["player"] == "Vili Alitalo"
    assert parsed["incidents"][0]["family"] == "goal"
    assert parsed["sport_detail"]["shots"][0]["player"] == "Vili Alitalo"
    assert "shooterId" not in parsed["sport_detail"]["shots"][0]
    assert "A Goalie" in parsed["sport_detail"]["goalies"]
    assert parsed["venue"] == "Helsinki Hall"


def test_ibu_classification_keeps_shooting_string():
    rows = parse_ibu_results(
        {
            "Results": [
                {
                    "Rank": "1",
                    "Name": "BOTN Johan-Olav",
                    "Nat": "NOR",
                    "TotalTime": "37:15.6",
                    "Behind": "0.0",
                    "Shootings": "0+0+0+0",
                    "IBUId": "hidden",
                }
            ]
        },
        "Men's 15km Mass Start",
    )
    assert rows[0]["nation"] == "NOR"
    assert rows[0]["shootings"] == "0+0+0+0"
    assert rows[0]["race"] == "Men's 15km Mass Start"
    assert "IBUId" not in rows[0]


def test_world_aquatics_reads_nested_heats():
    parsed = parse_world_aquatics(
        {
            "Sports": [
                {
                    "DisciplineList": [
                        {
                            "Heats": [
                                {
                                    "Name": "Final",
                                    "Results": [
                                        {"Rank": 1, "FullName": "A Diver", "NAT": "CHN", "TotalPoints": "400.50", "Lane": 4, "BiographyId": "nope"}
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )
    row = parsed["classification"][0]
    assert row["name"] == "A Diver"
    assert row["nation"] == "CHN"
    assert row["lane"] == 4
    assert "BiographyId" not in row


def test_letour_rank_row():
    html = """
    <tr class="rankingTables__row">
      <td class="rankingTables__row__position"><span>1</span></td>
      <td><img alt="Tadej POGACAR"><span>Tadej POGACAR</span></td>
      <td>1</td>
      <td>UAE Team Emirates</td>
      <td>4:12:01</td>
      <td>+0:00</td>
      <td>10</td>
    </tr>
    """
    row = parse_letour_rankings(html)["classification"][0]
    assert row["name"] == "Tadej POGACAR"
    assert row["position"] == "1"
    assert row["team"] == "UAE Team Emirates"
    assert row["gap"] == "+0:00"


def test_wec_summary_table():
    html = """
    <table class="table table-sm table-standing table-striped m-0">
      <thead><tr><th>Pos.</th><th>Competitors</th><th>N°</th><th>Team / Drivers</th><th>Laps</th><th>Gap</th><th>Best lap</th></tr></thead>
      <tbody><tr><td>1</td><td>Hypercar</td><td>8</td><td>Toyota / Buemi</td><td>220</td><td>-</td><td>1:30.1</td></tr></tbody>
    </table>
    """
    row = parse_wec_summary(html)["classification"][0]
    assert row["position"] == "1"
    assert row["car"] == "8"
    assert row["name"] == "Toyota / Buemi"
    assert row["laps"] == "220"
    assert row["fastest_lap"] == "1:30.1"


def test_gri_race_block():
    html = """
    <h4>Race 1 - Sprint (Grade : AA0) Flat 525</h4>
    <table><tr><td>1.</td><td></td><td>TOOLMAKER KING</td><td>78</td><td>28.41</td><td>2/5</td><td>Ld 1</td></tr></table>
    """
    row = parse_gri_results(html)["classification"][0]
    assert row["name"] == "TOOLMAKER KING"
    assert row["race"] == "1"
    assert row["time"] == "28.41"
    assert row["category"] == "AA0"


def test_letrot_runner_without_fake_live():
    html = '<table><tr><td>13</td><td>ELFO BREED</td><td>1\'14"2</td></tr></table>'
    parsed = parse_letrot_race(html)
    assert parsed["classification"][0]["name"] == "Elfo Breed"
    assert "live" not in parsed


def test_altius_goal_and_card():
    html = """
    <script>
    var blob = {"events":[
      {"seconds":"130.28","event":"goal","player_id":9,"type":"PC"},
      {"seconds":"1127.17","event":"card","player_id":9,"type":"G"}
    ]};
    {"id":9,"name":"Casey Smith","shirtnumber":"11"}
    </script>
    """
    parsed = parse_altius_match(html)
    assert parsed["incidents"][0]["type"] == "penalty corner"
    assert parsed["incidents"][0]["player"] == "Casey Smith"
    assert parsed["incidents"][1]["type"] == "green"
    assert parsed["incidents"][0]["minute"] == 2
