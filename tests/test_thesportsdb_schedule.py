from collector.thesportsdb_schedule import JOB_KEY, TARGET_SPORTS


def test_known_league_schedule_targets_main_team_sports():
    assert JOB_KEY == "thesportsdb-known-league-fixtures-v1"
    assert set(TARGET_SPORTS) == {"handball", "volleyball", "ice-hockey", "baseball"}
