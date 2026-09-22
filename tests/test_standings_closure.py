from collector.adapters_cricsheet import _event
from collector.adapters_fotmob import parse_fotmob_table
from collector.canonical_standings import canonicalize_standing_rows, unwrap_standings
from collector.identity_events import identity_confidence
from collector.standings_enrich import TTL_SECONDS, _fresh, parse_jolpica_standings, parse_mlb_standings, parse_nhl_standings, parse_squiggle_standings


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


def test_standings_ttl_skips_empty_snapshot():
    assert TTL_SECONDS >= 60
    assert _fresh(None) is False


def test_afl_snapshot_without_percentage_is_stale():
    from types import SimpleNamespace
    from datetime import datetime

    from collector.util import dump_json

    cached = SimpleNamespace(
        competition_id="australia-afl",
        captured_at=datetime.utcnow(),
        rows_json=dump_json([{"position": 1, "team": "Fremantle", "played": 23, "wins": 19, "points": 76}]),
    )
    assert _fresh(cached) is False


def test_afl_and_f1_standings_parsers():
    afl = parse_squiggle_standings(
        {
            "standings": [
                {
                    "rank": 1,
                    "name": "Fremantle",
                    "pts": 76,
                    "wins": 19,
                    "losses": 4,
                    "draws": 0,
                    "played": 23,
                    "percentage": 137.21,
                    "for": 2286,
                    "against": 1666,
                }
            ]
        }
    )
    assert afl[0]["team"] == "Fremantle"
    assert afl[0]["points"] == 76
    assert afl[0]["percentage"] == 137.21
    assert "goals_for" not in afl[0]
    canonical = canonicalize_standing_rows(afl, sport="australian-rules")
    assert canonical[0]["percentage"] == 137.21
    assert "goals_for" not in canonical[0]
    assert canonical[0]["draws"] == 0
    f1 = parse_jolpica_standings(
        {
            "MRData": {
                "StandingsTable": {
                    "StandingsLists": [
                        {
                            "DriverStandings": [
                                {
                                    "position": "1",
                                    "points": "186",
                                    "wins": "5",
                                    "Driver": {"givenName": "Lando", "familyName": "Norris"},
                                    "Constructors": [{"name": "McLaren"}],
                                }
                            ]
                        }
                    ]
                }
            }
        }
    )
    assert f1[0]["team"] == "Lando Norris"
    assert f1[0]["points"] == "186"


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


def test_production_verified_does_not_require_standings():
    from collector.rich_capability import build_rows

    rows = {row["competition"]: row for row in build_rows()}
    ligue = rows["france-ligue-1"]
    assert ligue["production_verified"] is True
    assert ligue["standings"] != "PROVEN"
    afl = rows["australia-afl"]
    assert afl["production_verified"] is True
    assert afl["sport_detail"] == "PROVEN"


def test_euroleague_standings_have_no_draws():
    from collector.standings_enrich import parse_euroleague_standings

    xml = """<standings><group name="Regular Season" round="RS">
      <team><name>Olympiacos Piraeus</name><ranking>1</ranking><totalgames>38</totalgames>
      <wins>26</wins><losses>12</losses><ptsfavour>3406</ptsfavour><ptsagainst>3144</ptsagainst></team>
      </group></standings>"""
    rows = canonicalize_standing_rows(parse_euroleague_standings(xml), sport="basketball")
    assert rows[0]["team"] == "Olympiacos Piraeus"
    assert rows[0]["wins"] == 26
    assert rows[0]["points_for"] == 3406
    assert rows[0]["win_pct"] == 0.684
    assert "draws" not in rows[0]
    assert "goals_for" not in rows[0]


def test_volleyball_standings_keep_sets():
    from collector.standings_enrich import parse_dataproject_standings, parse_legavolley_standings

    html = """
    <table class="rs-standings-table">
      <tr data-termin="1-1-1" data-teamname="Early"><td>9</td><td>Early</td><td>1</td><td>1</td><td>1</td><td>0</td><td>3</td><td>0</td></tr>
      <tr data-termin="1-1-2" data-teamname="ZAKSA"><td>1</td><td>ZAKSA</td><td>6</td><td>2</td><td>2</td><td>0</td><td>6</td><td>1</td></tr>
    </table>
    """
    rows = canonicalize_standing_rows(parse_dataproject_standings(html), sport="volleyball")
    assert rows[0]["team"] == "ZAKSA"
    assert rows[0]["sets_for"] == 6
    assert rows[0]["points"] == 6
    assert "draws" not in rows[0]
    assert "goals_for" not in rows[0]
    lega = """<table Id="GareGiornata"><tr><span class="pos">1</span>&nbsp;&nbsp; Sir Susa Scai Perugia
      <td>6</td><td>2</td><td>2</td><td>0</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>0</td><td>6</td><td>1</td></tr></table>"""
    superlega = canonicalize_standing_rows(parse_legavolley_standings(lega), sport="volleyball")
    assert superlega[0]["team"] == "Sir Susa Scai Perugia"
    assert superlega[0]["sets_for"] == 6
    assert superlega[0]["wins"] == 2


def test_empty_standings_fetch_does_not_wipe_snapshot():
    from datetime import datetime, timedelta

    from collector.models import SportsEvent, SportsStandingSnapshot
    from collector.standings_enrich import load_standings, wrap_standings
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            SportsEvent(
                event_id="ninko-std-epl",
                sport_id="football",
                competition_id="england-premier-league",
                event_family="team_match",
                fingerprint="std-epl",
                status="finished",
                display_eligible=True,
            )
        )
        payload = wrap_standings(
            [{"position": 1, "team": "Manchester City", "played": 4, "wins": 3, "draws": 1, "losses": 0, "points": 10, "goals_for": 8, "goals_against": 2}],
            competition="england-premier-league",
            season="2026",
            sport="football",
            source="fotmob",
        )
        db.add(
            SportsStandingSnapshot(
                competition_id="england-premier-league",
                season="2026",
                sport_id="football",
                source_id="fotmob",
                rows_json=dump_json(payload),
                captured_at=datetime.utcnow() - timedelta(hours=3),
            )
        )
        db.commit()

        class Empty:
            ok = True
            payload = {}

        rows = load_standings(db, "england-premier-league", getter=lambda url, headers=None: Empty())
        assert rows[0]["team"] == "Manchester City"
        assert db.query(SportsStandingSnapshot).filter_by(competition_id="england-premier-league").count() == 1
    finally:
        db.close()


def test_standings_season_identity_is_isolated():
    from collector.models import SportsEvent, SportsStandingSnapshot
    from collector.standings_enrich import _store_standings, load_standings, wrap_standings
    from collector.util import load_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        db.add(
            SportsEvent(
                event_id="ninko-std-afl",
                sport_id="australian-rules",
                competition_id="australia-afl",
                event_family="team_match",
                fingerprint="std-afl",
                status="finished",
                display_eligible=True,
            )
        )
        db.commit()
        older = wrap_standings(
            [{"position": 1, "team": "Adelaide", "played": 23, "wins": 18, "losses": 5, "draws": 0, "points": 72, "percentage": 139.3}],
            competition="australia-afl",
            season="2025",
            sport="australian-rules",
            source="squiggle-afl",
        )
        current = wrap_standings(
            [{"position": 1, "team": "Fremantle", "played": 23, "wins": 19, "losses": 4, "draws": 0, "points": 76, "percentage": 137.2}],
            competition="australia-afl",
            season="2026",
            sport="australian-rules",
            source="squiggle-afl",
        )
        _store_standings(db, "australia-afl", older)
        _store_standings(db, "australia-afl", current)
        db.commit()

        class Empty:
            ok = False
            payload = None

        rows = load_standings(db, "australia-afl", getter=lambda url, headers=None: Empty())
        assert rows[0]["team"] == "Fremantle"
        stored = db.query(SportsStandingSnapshot).filter_by(competition_id="australia-afl").all()
        seasons = {row.season: load_json(row.rows_json, {}).get("rows", [{}])[0].get("team") for row in stored}
        assert seasons["2025"] == "Adelaide"
        assert seasons["2026"] == "Fremantle"
    finally:
        db.close()


def test_afl_sport_detail_replaces_crossed_scoring():
    from collector.canonical_detail import attach_canonical_detail

    event = attach_canonical_detail(
        {
            "sport": "australian-rules",
            "venue": "Sydney Cricket Ground",
            "round": "150",
            "stage": "150",
            "score": {"home": 71, "away": 83},
            "sport_detail": {"goals": {"home": 10, "away": 12}, "behinds": {"home": 11, "away": 11}, "stage": "150"},
            "statistics": [{"label": "Goals", "home": 15, "away": 10}, {"label": "Behinds", "home": 21, "away": 13}],
            "periods": [{"label": "G", "home": 15, "away": 10}],
        }
    )
    assert event["sport_detail"]["goals"] == {"home": 10, "away": 12}
    assert event["sport_detail"]["score"] == {"home": 71, "away": 83}
    assert event["sport_detail"]["venue"] == "Sydney Cricket Ground"
    assert "stage" not in event["sport_detail"]
    assert "stage" not in event
    assert "round" not in event
    assert event["statistics"][0]["home"] == 10
    assert event["periods"][1]["label"] == "B"


def test_clicktt_live_payload_exposes_players_and_sets():
    from collector.detail_families import parse_clicktt_live

    parsed = parse_clicktt_live(
        {
            "data": {
                "match": [
                    {
                        "match_name": "1-2",
                        "sets_home": 3,
                        "sets_guest": 1,
                        "set1_home": 2,
                        "set1_guest": 11,
                        "set2_home": 11,
                        "set2_guest": 2,
                        "set5_home": 0,
                        "set5_guest": 0,
                        "mm_player11": {"firstname": "Bastian", "lastname": "Steger"},
                        "mm_player21": {"firstname": "Tom", "lastname": "Jarvis"},
                    }
                ]
            }
        }
    )
    rubber = parsed["sport_detail"]["rubbers"][0]
    assert rubber["home_player"] == "Bastian Steger"
    assert rubber["away_player"] == "Tom Jarvis"
    assert rubber["games"][0] == {"label": 1, "home": 2, "away": 11}
    assert len(rubber["games"]) == 2
    assert "home_players" not in rubber

    doubles = parse_clicktt_live(
        {
            "data": {
                "match": [
                    {
                        "sets_home": 3,
                        "sets_guest": 2,
                        "set1_home": 11,
                        "set1_guest": 8,
                        "mm_player11": {"firstname": "Anna", "lastname": "One"},
                        "mm_player12": {"firstname": "Bea", "lastname": "Two"},
                        "mm_player21": {"firstname": "Cara", "lastname": "Three"},
                        "mm_player22": {"firstname": "Dora", "lastname": "Four"},
                    }
                ]
            }
        }
    )["sport_detail"]["rubbers"][0]
    assert doubles["home_players"] == ["Anna One", "Bea Two"]
    assert doubles["away_players"] == ["Cara Three", "Dora Four"]
