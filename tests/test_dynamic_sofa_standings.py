from datetime import datetime

from database import SessionLocal
from collector.models import SportsCompetition, SportsEvent, SportsSourceCompetition
from collector.standings_enrich import (
    dynamic_standings_supported,
    fotmob_standings_context,
    parse_sofa_dynamic_standings,
    sofa_standings_context,
)
from collector.util import dump_json


def test_parse_sofa_dynamic_standings_maps_common_team_fields():
    payload = {
        "standings": [
            {
                "name": "Regular Season",
                "rows": [
                    {
                        "position": 1,
                        "team": {"id": 1, "name": "Alpha FC"},
                        "matches": 8,
                        "wins": 6,
                        "draws": 1,
                        "losses": 1,
                        "scoresFor": 19,
                        "scoresAgainst": 8,
                        "scoreDiff": 11,
                        "points": 19,
                    }
                ],
            }
        ]
    }
    rows = parse_sofa_dynamic_standings(payload, sport_id="football")
    assert rows[0]["position"] == 1
    assert rows[0]["team"] == "Alpha FC"
    assert rows[0]["played"] == 8
    assert rows[0]["wins"] == 6
    assert rows[0]["draws"] == 1
    assert rows[0]["losses"] == 1
    assert rows[0]["goals_for"] == 19
    assert rows[0]["goals_against"] == 8
    assert rows[0]["goal_difference"] == 11
    assert rows[0]["points"] == 19


def test_dynamic_context_uses_persisted_sofa_tournament_and_season():
    db = SessionLocal()
    try:
        db.add(
            SportsCompetition(
                competition_id="football-au-test-t123",
                sport_id="football",
                name="Test League",
                slug="football-au-test-t123",
                event_model="team_match",
                active=True,
            )
        )
        db.add(
            SportsEvent(
                event_id="evt-sofa-1",
                sport_id="football",
                competition_id="football-au-test-t123",
                event_family="team_match",
                status="scheduled",
                start_time=datetime(2026, 9, 24),
                participants_json=dump_json({"home": {"name": "A"}, "away": {"name": "B"}}),
                score_json=dump_json({}),
                extra_json=dump_json({
                    "sofascore_tournament_id": "123",
                    "sofascore_season_id": "456",
                    "source_season_name": "2026/27",
                }),
                display_eligible=True,
            )
        )
        db.commit()

        context = sofa_standings_context(db, "football-au-test-t123")
        assert context == {
            "tournament_id": "123",
            "season_id": "456",
            "season_name": "2026/27",
            "sport_id": "football",
        }
        assert dynamic_standings_supported(db, "football-au-test-t123") is True
    finally:
        db.close()



def test_dynamic_fotmob_mapping_exposes_standings_context():
    db = SessionLocal()
    try:
        db.add(
            SportsCompetition(
                competition_id="football-gha-premier-league",
                sport_id="football",
                name="Premier League",
                slug="football-gha-premier-league",
                event_model="team_match",
                active=True,
            )
        )
        db.add(
            SportsSourceCompetition(
                competition_id="football-gha-premier-league",
                source_id="fotmob-global",
                priority=900,
                source_competition_id="522",
                enabled=True,
                source_config_json=dump_json({
                    "fotmob_league_id": "522",
                    "fotmob_league_name": "Premier League",
                }),
                upstream_family="fotmob",
            )
        )
        db.commit()

        context = fotmob_standings_context(db, "football-gha-premier-league")
        assert context == {
            "league_id": "522",
            "league_name": "Premier League",
            "sport_id": "football",
        }
        assert dynamic_standings_supported(db, "football-gha-premier-league") is True
    finally:
        db.close()
