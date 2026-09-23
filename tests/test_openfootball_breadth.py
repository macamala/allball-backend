from datetime import date

from collector.openfootball_breadth import current_season_tokens, discover_current_paths, parse_football_txt


def test_current_season_tokens_roll_across_year():
    assert current_season_tokens(date(2026, 9, 23)) == ("2026", "2026-27")
    assert current_season_tokens(date(2027, 2, 1)) == ("2027", "2026-27")


def test_discovery_keeps_current_files_only():
    payload = {"tree": [
        {"type": "blob", "path": "2026-27/1-premierleague.txt"},
        {"type": "blob", "path": "brazil/2026_br1.txt"},
        {"type": "blob", "path": "archive/2026_old.txt"},
        {"type": "blob", "path": "more/2026_squads.txt"},
        {"type": "blob", "path": "2025-26/1-premierleague.txt"},
    ]}
    paths = discover_current_paths(payload, today=date(2026, 9, 23))
    assert "2026-27/1-premierleague.txt" in paths
    assert "brazil/2026_br1.txt" in paths
    assert "archive/2026_old.txt" not in paths
    assert "more/2026_squads.txt" not in paths
    assert "2025-26/1-premierleague.txt" not in paths


def test_parser_handles_finished_scheduled_and_inherited_date():
    text = """= English Premier League 2026/27

▪ Matchday 5
  Sun Sep 20 2026
    14:00  AFC Bournemouth         v Liverpool FC             0-1 (0-0)
           Leeds United FC         v Crystal Palace FC        0-0
  Sat Oct 10
    12:30  Arsenal FC              v Leeds United FC
"""
    competition_id, name, events = parse_football_txt(
        text,
        repo="england",
        path="2026-27/1-premierleague.txt",
        today=date(2026, 9, 23),
    )
    assert competition_id == "england-premier-league"
    assert name == "English Premier League"
    assert len(events) == 3
    assert events[0]["status"] == "finished"
    assert events[0]["score"]["away"] == 1
    assert events[1]["start_date"] == "2026-09-20"
    assert events[2]["status"] == "scheduled"
    assert events[2]["start_date"] == "2026-10-10"
    assert events[2]["start_precision"] == "day"


def test_parser_strips_country_tags():
    text = """= Copa Libertadores 2026
▪ Group, Matchday 1
  Tue Apr 7 2026
    19:00  CS Independiente Rivadavia (ARG) v Club Bolívar (BOL)       1-0 (0-0)
"""
    _competition_id, _name, events = parse_football_txt(
        text,
        repo="south-america",
        path="copa-libertadores/2026_copal.txt",
        today=date(2026, 9, 23),
    )
    assert events[0]["home"]["name"] == "CS Independiente Rivadavia"
    assert events[0]["away"]["name"] == "Club Bolívar"
