from database import SessionLocal as _session
from collector.adapters_fotmob import FOTMOB_LEAGUES, asset_league_ids, parse_fotmob_table
from collector.fotmob_asset_backfill import _fill_side, _roster, _unique_match


def test_asset_only_fotmob_aliases_resolve_without_enabling_duplicate_ingestion():
    assert asset_league_ids("football-tun-ligue-1") == ["544"]
    assert asset_league_ids("football-alg-ligue-1") == ["516"]
    assert asset_league_ids("football-mar-botola-pro") == ["530"]
    assert asset_league_ids("tunisia-ligue-1") == ["544"]

    assert "football-tun-ligue-1" not in FOTMOB_LEAGUES
    assert "football-alg-ligue-1" not in FOTMOB_LEAGUES
    assert "football-mar-botola-pro" not in FOTMOB_LEAGUES



def test_fotmob_table_preserves_team_id_and_crest():
    payload = {
        "data": {
            "table": {
                "all": [
                    {
                        "id": 9825,
                        "name": "Manchester United",
                        "idx": 1,
                        "played": 5,
                        "wins": 4,
                        "draws": 1,
                        "losses": 0,
                        "pts": 13,
                    }
                ]
            }
        }
    }
    rows = parse_fotmob_table(payload)
    assert rows[0]["team_id"] == "9825"
    assert rows[0]["logo"].endswith("/teamlogo/9825.png")

    roster = _roster(payload)
    assert roster[0]["id"] == "9825"
    assert roster[0]["name"] == "Manchester United"


def test_fotmob_roster_matches_unique_legal_name_variant():
    roster = [
        {
            "id": "9825",
            "name": "Manchester United",
            "folded": "manchester united",
            "logo": "https://images.fotmob.com/image_resources/logo/teamlogo/9825.png",
        },
        {
            "id": "8455",
            "name": "Manchester City",
            "folded": "manchester city",
            "logo": "https://images.fotmob.com/image_resources/logo/teamlogo/8455.png",
        },
    ]
    matched = _unique_match("Manchester United FC", roster)
    assert matched["id"] == "9825"

    side, changed = _fill_side({"name": "Manchester United FC"}, roster)
    assert changed is True
    assert side["id"] == "9825"
    assert side["logo"].endswith("/teamlogo/9825.png")


def test_fotmob_roster_does_not_choose_ambiguous_alias():
    roster = [
        {"id": "1", "name": "United FC", "folded": "united", "logo": "a"},
        {"id": "2", "name": "United SC", "folded": "united", "logo": "b"},
    ]
    assert _unique_match("United", roster) is None



def test_dynamic_fotmob_source_competition_id_becomes_roster_candidate():
    from collector.fotmob_asset_backfill import _candidate_competitions
    from collector.models import SportsEvent
    from collector.util import dump_json
    import time

    db = _session()
    event_id = "ninko-evt-dynamic-fotmob-roster"
    try:
        db.query(SportsEvent).filter(SportsEvent.event_id == event_id).delete(synchronize_session=False)
        db.add(
            SportsEvent(
                event_id=event_id,
                sport_id="football",
                competition_id="football-test-dynamic-league",
                event_family="team_match",
                status="scheduled",
                fingerprint="fp-dynamic-fotmob-roster",
                participants_json=dump_json({
                    "home": {"name": "Alpha FC"},
                    "away": {"name": "Beta FC"},
                }),
                extra_json=dump_json({
                    "source_family": "fotmob",
                    "source_competition_id": "123456",
                    "display_eligible": True,
                }),
                display_eligible=True,
            )
        )
        db.flush()
        rows = dict(_candidate_competitions(db, time.monotonic()))
        assert rows["football-test-dynamic-league"] == ["123456"]
    finally:
        db.rollback()
        db.close()
