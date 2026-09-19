from datetime import datetime

from collector.adapters_espn import parse_espn_scoreboard
from collector.adapters_openligadb import _to_event
from collector.display import sanitize_participant_name
from collector.enrichment import (
    incidents_from_openliga_goals,
    is_display_eligible,
    periods_from_linescores,
    quality_flags_for_name,
)


def test_openliga_fixtures_keeps_finished_matchday_events():
    from collector.adapters import FetchRequest, FetchResult
    from collector.adapters_openligadb import OpenLigaDbAdapter

    payload = [
        {
            "matchID": 83183,
            "team1": {"teamName": "FC Bayern München"},
            "team2": {"teamName": "1. FC Union Berlin"},
            "matchIsFinished": True,
            "matchDateTimeUTC": "2026-09-19T13:30:00Z",
            "leagueShortcut": "bl1",
            "leagueName": "Bundesliga",
            "matchResults": [
                {"resultTypeKind": "HalfTime", "resultName": "Halbzeit", "pointsTeam1": 3, "pointsTeam2": 0},
                {"resultTypeKind": "After90Minutes", "resultName": "Endergebnis", "pointsTeam1": 7, "pointsTeam2": 0},
            ],
            "goals": [{"matchMinute": 18, "goalGetterName": "J. Musiala", "scoreTeam1": 1, "scoreTeam2": 0}],
        }
    ]

    class Getter:
        def __call__(self, url, timeout=20):
            return FetchResult(ok=True, http_status=200, payload=payload)

    adapter = OpenLigaDbAdapter(getter=Getter())
    result = adapter.fetch(
        FetchRequest(capability="fixtures", sport_id="football", competition_id="germany-bundesliga", source_competition_id="bl1")
    )
    assert result.ok
    assert len(result.events) == 1
    assert result.events[0]["status"] == "finished"
    assert result.events[0]["periods"][0]["label"] == "HT"
    assert result.events[0]["incidents"][0]["player"] == "J. Musiala"


def test_openliga_keeps_goals_and_halftime():
    match = {
        "matchID": 1,
        "team1": {"teamName": "Bayern"},
        "team2": {"teamName": "Mainz"},
        "matchIsFinished": True,
        "matchDateTimeUTC": "2026-09-19T13:30:00",
        "leagueSeason": 2026,
        "group": {"groupName": "4. Spieltag"},
        "matchResults": [
            {"resultTypeKind": "HalfTime", "pointsTeam1": 3, "pointsTeam2": 0},
            {"resultTypeKind": "After90Minutes", "pointsTeam1": 7, "pointsTeam2": 0},
        ],
        "goals": [
            {
                "matchMinute": 18,
                "goalGetterName": "J. Musiala",
                "scoreTeam1": 1,
                "scoreTeam2": 0,
                "isPenalty": False,
                "isOwnGoal": False,
            }
        ],
    }
    event = _to_event(
        match,
        {"shortcut": "bl1", "competition_id": "germany-bundesliga", "name": "Bundesliga", "sport_id": "football"},
    )
    assert event["round"] == "4. Spieltag"
    assert event["periods"][0]["label"] == "HT"
    assert event["periods"][1]["home"] == 7
    assert event["incidents"][0]["player"] == "J. Musiala"
    assert event["incidents"][0]["type"] == "goal"
    assert event["incidents"][0]["score_after"]["home"] == 1
    assert incidents_from_openliga_goals(match)[0]["type"] == "goal"


def test_espn_linescores_become_periods():
    payload = {
        "leagues": [{"name": "MLB"}],
        "events": [
            {
                "id": "9",
                "date": "2026-09-19T17:00:00Z",
                "competitions": [
                    {
                        "id": "9",
                        "status": {"displayClock": "0:00", "period": 9, "type": {"state": "post"}},
                        "venue": {"fullName": "Great American Ball Park"},
                        "competitors": [
                            {
                                "homeAway": "home",
                                "score": "6",
                                "hits": 10,
                                "errors": 0,
                                "winner": True,
                                "team": {"displayName": "Reds"},
                                "linescores": [{"value": 2, "period": 1}, {"value": 3, "period": 6}],
                            },
                            {
                                "homeAway": "away",
                                "score": "4",
                                "hits": 8,
                                "errors": 1,
                                "team": {"displayName": "Cubs"},
                                "linescores": [{"value": 1, "period": 1}, {"value": 0, "period": 6}],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    events = parse_espn_scoreboard(payload)
    assert len(events) == 1
    assert events[0]["home"]["name"] == "Reds"
    assert events[0]["periods"][0]["home"] == 2
    assert events[0]["periods"][0]["away"] == 1
    assert events[0]["periods"][0]["period"] == 1
    assert events[0]["periods"][0]["label"] == "1"
    assert events[0]["score"]["hits"]["home"] == 10
    assert events[0]["venue"] == "Great American Ball Park"


def test_espn_tennis_groupings_use_athlete_names():
    payload = {
        "events": [
            {
                "id": "tourney",
                "groupings": [
                    {
                        "competitions": [
                            {
                                "id": "m1",
                                "status": {"type": {"state": "in"}, "period": 2},
                                "competitors": [
                                    {
                                        "homeAway": "home",
                                        "score": "1",
                                        "athlete": {"displayName": "Ilia Simakin"},
                                        "linescores": [{"value": 6, "period": 1}, {"value": 3, "period": 2}],
                                    },
                                    {
                                        "homeAway": "away",
                                        "score": "0",
                                        "athlete": {"displayName": "Hunter Heck"},
                                        "linescores": [{"value": 4, "period": 1}, {"value": 2, "period": 2}],
                                    },
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    events = parse_espn_scoreboard(payload)
    assert events[0]["home"]["name"] == "Ilia Simakin"
    assert events[0]["status"] == "live"
    assert events[0]["periods"][0]["home"] == 6


def test_espn_fitt_lnescrs_become_basketball_quarters():
    payload = {
        "page": {
            "content": {
                "scoreboard": {
                    "league": {"name": "WNBA", "sport": "basketball"},
                    "evts": [
                        {
                            "id": "401857195",
                            "completed": True,
                            "date": "2026-09-19T02:00:00Z",
                            "status": {"state": "post", "description": "Final"},
                            "lnescrs": {"awy": [25, 28, 26, 24], "hme": [19, 31, 23, 12], "lbls": [1, 2, 3, 4]},
                            "competitors": [
                                {"isHome": True, "displayName": "Portland Fire", "score": "85", "winner": True},
                                {"isHome": False, "displayName": "Golden State Valkyries", "score": "103"},
                            ],
                        }
                    ],
                }
            }
        }
    }
    events = parse_espn_scoreboard(payload, sport="basketball")
    assert len(events) == 1
    assert events[0]["home"]["name"] == "Portland Fire"
    assert events[0]["score"]["home"] == 85
    assert [row["label"] for row in events[0]["periods"]] == ["Q1", "Q2", "Q3", "Q4"]
    assert events[0]["periods"][0]["home"] == 19
    assert events[0]["periods"][0]["away"] == 25


def test_espn_fitt_mlb_rhe_is_not_innings():
    from collector.enrichment import periods_from_espn_lnescrs, rhe_from_espn_lnescrs

    lnescrs = {"awy": ["4", 9, 1], "hme": ["6", 8, 0], "lbls": ["R", "H", "E"]}
    assert periods_from_espn_lnescrs(lnescrs, sport="baseball") is None
    rhe = rhe_from_espn_lnescrs(lnescrs)
    assert rhe["hits"]["home"] == 8
    assert rhe["errors"]["away"] == 1


def test_espn_fitt_hockey_so_label():
    from collector.enrichment import periods_from_espn_lnescrs

    rows = periods_from_espn_lnescrs(
        {"awy": [1, 2, 0, 1], "hme": [1, 2, 0, 0], "lbls": [1, 2, 3, "SO"]},
        sport="ice-hockey",
    )
    assert [row["label"] for row in rows] == ["P1", "P2", "P3", "SO"]


def test_wta_discovery_uses_current_window_not_ao_archive():
    from collector.adapters import FetchResult
    from collector import adapters_wta

    adapters_wta._CALENDAR_CACHE.update({"at": 0.0, "rows": []})
    adapters_wta._MATCH_CACHE.clear()
    pages = {
        "https://api.wtatennis.com/tennis/tournaments?page=0&pageSize=1": {
            "pageInfo": {"numEntries": 151},
            "content": [],
        },
        "https://api.wtatennis.com/tennis/tournaments?page=1&pageSize=50": {
            "content": [
                {
                    "tournamentGroup": {"id": 901, "name": "AUSTRALIAN OPEN"},
                    "year": 2026,
                    "startDate": "2026-01-12",
                    "endDate": "2026-01-25",
                    "status": "past",
                }
            ]
        },
        "https://api.wtatennis.com/tennis/tournaments?page=2&pageSize=50": {
            "content": [
                {
                    "tournamentGroup": {"id": 2075, "name": "GUADALAJARA 500"},
                    "year": 2026,
                    "startDate": "2026-09-13",
                    "endDate": "2026-09-19",
                    "status": "inProgress",
                    "city": "GUADALAJARA",
                    "surface": "Hard",
                    "level": "WTA 500",
                }
            ]
        },
        "https://api.wtatennis.com/tennis/tournaments/2075/2026/matches": {
            "matches": [
                {
                    "MatchID": "RS100",
                    "MatchState": "F",
                    "MatchTimeStamp": "2026-09-18T18:00:00Z",
                    "PlayerNameFirstA": "Player",
                    "PlayerNameLastA": "One",
                    "PlayerNameFirstB": "Player",
                    "PlayerNameLastB": "Two",
                    "ScoreSet1A": "6",
                    "ScoreSet1B": "3",
                    "ScoreSet2A": "6",
                    "ScoreSet2B": "2",
                    "DrawLevelType": "S",
                }
            ]
        },
    }

    def getter(url: str):
        return FetchResult(ok=True, http_status=200, payload=pages.get(url) or {})

    now = datetime(2026, 9, 19, 12, 0, 0)
    found = adapters_wta.discover_current_tournaments(getter, now=now)
    ids = {(row.get("tournamentGroup") or {}).get("id") for row in found}
    assert 2075 in ids
    assert 901 not in ids
    adapter = adapters_wta.WtaJsonAdapter(getter=getter)
    from collector.adapters import FetchRequest

    result = adapter.fetch(FetchRequest(capability="fixtures", competition_id="wta-tour"))
    assert result.events
    assert result.events[0]["periods"][0]["label"] == "Set 1"
    assert result.events[0]["periods"][0]["home"] == 6
    assert result.events[0]["tournament_id"] == 2075
    assert result.events[0]["score"]["home"] == 2



def test_junk_participant_names_are_quarantined():
    assert "name_is_date" in quality_flags_for_name("19.09.2026")
    assert "name_is_date" in quality_flags_for_name("2026-09-19")
    assert is_display_eligible({"home": {"name": "19.09.2026"}, "away": {"name": "ALU SC"}}) is False
    assert is_display_eligible({"home": {"name": "Arsenal"}, "away": {"name": "Villa"}}) is True
    assert sanitize_participant_name("19.09.2026") == ""
    assert sanitize_participant_name("Wsf1") == "Winner of SF1"


def test_periods_from_linescores_helper():
    rows = periods_from_linescores(
        {"linescores": [{"value": 21, "period": 1}]},
        {"linescores": [{"value": 19, "period": 1}]},
    )
    assert rows[0]["home"] == 21
    assert rows[0]["away"] == 19
    assert rows[0]["period"] == 1


def test_identity_requires_ids_or_strict_sides():
    from collector.identity import identity_confidence, should_merge_enrichment

    a = {
        "sport": "football",
        "event_family": "team_match",
        "competition_key": "bl1",
        "home": {"name": "Bayern"},
        "away": {"name": "Mainz"},
        "start_time": "2026-09-19T13:30:00Z",
        "source_event_ids": {"openligadb": "1"},
    }
    b = {**a, "source_event_ids": {"openligadb": "1"}}
    c = {**a, "source_event_ids": {}, "home": {"name": "Bayern"}, "away": {"name": "Augsburg"}}
    assert identity_confidence(a, b) == 100
    assert should_merge_enrichment(a, b) is True
    assert should_merge_enrichment(a, c) is False


def test_unchanged_skip_does_not_drop_missing_periods():
    from collector.dirty import event_unchanged, observation_signature
    from collector.util import dump_json

    incoming_core = {
        "status": "finished",
        "score": {"home": 7, "away": 0},
        "home": {"name": "Bayern"},
        "away": {"name": "Union"},
    }

    class Row:
        extra_json = dump_json({"obs_signature": observation_signature(incoming_core)})

    incoming = {
        **incoming_core,
        "periods": [{"code": "HT", "home": 3, "away": 0}],
        "incidents": [{"type": "goal", "minute": 18, "player": "Musiala"}],
    }
    assert event_unchanged(Row(), incoming_core) is True
    assert event_unchanged(Row(), incoming) is False


def test_wta_keeps_individual_set_scores():
    from collector.adapters_wta import match_to_event

    event = match_to_event(
        {
            "PlayerNameFirstA": "Iga",
            "PlayerNameLastA": "Swiatek",
            "PlayerNameFirstB": "Aryna",
            "PlayerNameLastB": "Sabalenka",
            "MatchState": "F",
            "ScoreSet1A": "6",
            "ScoreSet1B": "4",
            "ScoreSet2A": "3",
            "ScoreSet2B": "6",
            "ScoreSet3A": "6",
            "ScoreSet3B": "2",
            "MatchID": "w1",
        },
        "wta-tour",
    )
    assert event["score"] == {"home": 2, "away": 1}
    assert event["periods"][0]["label"] == "Set 1"
    assert event["periods"][0]["home"] == 6
    assert event["periods"][0]["away"] == 4
    assert event["periods"][0]["winner"] == "home"
    assert event["periods"][1]["winner"] == "away"
    assert len(event["periods"]) == 3


def test_gbgb_groups_full_field():
    from collector.adapters_official import parse_gbgb

    events = parse_gbgb(
        {
            "items": [
                {
                    "trackName": "Newcastle",
                    "raceNumber": 12,
                    "raceDate": "17/09/2026",
                    "raceTime": "21:04",
                    "dogName": "A Dog",
                    "resultPosition": 1,
                    "trapNumber": "3",
                    "trainerName": "Smith",
                    "raceId": 1,
                    "meetingId": 99,
                },
                {
                    "trackName": "Newcastle",
                    "raceNumber": 12,
                    "raceDate": "17/09/2026",
                    "raceTime": "21:04",
                    "dogName": "B Dog",
                    "resultPosition": 2,
                    "trapNumber": "1",
                    "raceId": 1,
                    "meetingId": 99,
                },
            ]
        }
    )
    assert len(events) == 1
    assert events[0]["winner"] == "A Dog"
    assert len(events[0]["runners"]) == 2
    assert events[0]["runners"][0]["trap"] == "3"


def test_promote_observation_enrichment_does_not_touch_quarantine_or_scores():
    from datetime import datetime

    from collector.canonical_collapse import promote_observation_enrichment
    from collector.models import SportsEvent
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.util import dump_json
    from database import SessionLocal

    db = SessionLocal()
    try:
        kickoff = datetime(2026, 9, 19, 13, 30, 0)
        db.add(
            SportsEvent(
                event_id="ninko-evt-keep-enr",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-keep-enr",
                start_time=kickoff,
                display_eligible=True,
                score_json=dump_json({"home": 0, "away": 0}),
                participants_json=dump_json({"home": {"name": "Bayern"}, "away": {"name": "Mainz"}}),
                extra_json=dump_json({"display_eligible": True, "collapsed_from": ["ninko-evt-obs-enr"]}),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-obs-enr",
                sport_id="football",
                competition_id="germany-bundesliga",
                event_family="team_match",
                fingerprint="fp-obs-enr",
                start_time=kickoff,
                display_eligible=False,
                canonical_event_id="ninko-evt-keep-enr",
                score_json=dump_json({"home": 7, "away": 0}),
                participants_json=dump_json({"home": {"name": "Bayern"}, "away": {"name": "Mainz"}}),
                extra_json=dump_json(
                    {
                        "display_eligible": False,
                        "collapse_role": "observation_only",
                        "periods": [{"code": "HT", "home": 3, "away": 0}],
                        "incidents": [{"type": "goal", "minute": 18, "player": "Musiala", "score_after": {"home": 1, "away": 0}}],
                        "season": 2026,
                    }
                ),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-evt-q-enr",
                sport_id="football",
                competition_id="unknown-league",
                event_family="team_match",
                fingerprint="fp-q-enr",
                start_time=kickoff,
                display_eligible=False,
                extra_json=dump_json(
                    {
                        "display_eligible": False,
                        "periods": [{"code": "FAKE", "home": 9, "away": 9}],
                    }
                ),
            )
        )
        db.commit()
        result = promote_observation_enrichment(db)
        assert result["copied"] == 1
        event = NinkoCollectedSportsDataProvider().get_event("ninko-evt-keep-enr")
        assert event["score"]["home"] == 0
        assert event["periods"][0]["home"] == 3
        assert event["incidents"][0]["player"] == "Musiala"
        assert event["incidents"][0].get("provenance") is None
        assert event["competition"] == "germany-bundesliga"
        from collector.models import SportsEvent as EventRow

        quarantined = db.query(EventRow).filter_by(event_id="ninko-evt-q-enr").one()
        assert quarantined.display_eligible is False
        assert quarantined.canonical_event_id is None
    finally:
        db.close()
