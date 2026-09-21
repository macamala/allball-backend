"""Production adapters use recorded real payloads, not invented matches."""

from collector.adapters import ADAPTERS, FetchRequest, FetchResult, unregister_adapter
from collector.adapters_cricsheet import CricsheetAdapter
from collector.adapters_feeds import FifaFootballAdapter, MlbAdapter, NhlAdapter
from collector.adapters_opendota import OpenDotaAdapter
from collector.adapters_openfootball import OpenFootballAdapter
from collector.adapters_openligadb import OpenLigaDbAdapter
from collector.adapters_squiggle import SquiggleAflAdapter
from collector.adapters_thesportsdb import TheSportsDbAdapter
from collector.discovery_inventory import SOURCES, sports_missing_technically_collectable_source
from collector.collect import run_cycle
from collector.gaps import SPORTS_WITH_FREE_SOURCE, sports_without_free_source
from collector.models import SportsEvent, SportsSourceCompetition
from collector.production import bootstrap_registry, register_production_adapters
from collector.verified_coverage import OPENFOOTBALL_FILES, OPENLIGADB_LEAGUES, THESPORTSDB_LEAGUES
from database import SessionLocal
from sports_registry.sports import SPORTS


OPENFOOTBALL_EN = {
    "name": "English Premier League 2026/27",
    "matches": [
        {
            "round": "Matchday 5",
            "date": "2026-09-18",
            "time": "20:00",
            "team1": "Brentford FC",
            "team2": "Chelsea FC",
            "score": None,
        },
        {
            "round": "Matchday 4",
            "date": "2026-09-12",
            "time": "17:30",
            "team1": "Arsenal FC",
            "team2": "Fulham FC",
            "score": {"ht": [1, 0], "ft": [2, 0]},
        },
    ],
}

OPENLIGA_BL1 = [
    {
        "matchID": 99001,
        "matchDateTimeUTC": "2026-09-17T04:00:00Z",
        "matchIsFinished": False,
        "team1": {"teamId": 1, "teamName": "FC Bayern München"},
        "team2": {"teamId": 2, "teamName": "1. FC Union Berlin"},
        "matchResults": [],
        "goals": [],
        "location": {"locationStadium": "Allianz Arena"},
        "leagueName": "1. Fußball-Bundesliga 2026/2027",
    }
]

TSDB_NEXT = {
    "events": [
        {
            "idEvent": "2494047",
            "strTimestamp": "2026-09-18T19:00:00",
            "strEvent": "Brentford vs Chelsea",
            "strSport": "Soccer",
            "idLeague": "4328",
            "strLeague": "English Premier League",
            "strHomeTeam": "Brentford",
            "strAwayTeam": "Chelsea",
            "intHomeScore": None,
            "intAwayScore": None,
            "strStatus": "NS",
            "idHomeTeam": "134355",
            "idAwayTeam": "133610",
            "strVenue": "Brentford Community Stadium",
        }
    ]
}

TSDB_PAST = {
    "events": [
        {
            "idEvent": "2494001",
            "strTimestamp": "2026-09-13T16:00:00",
            "strEvent": "Liverpool vs Arsenal",
            "strSport": "Soccer",
            "idLeague": "4328",
            "strLeague": "English Premier League",
            "strHomeTeam": "Liverpool",
            "strAwayTeam": "Arsenal",
            "intHomeScore": 1,
            "intAwayScore": 1,
            "strStatus": "FT",
            "idHomeTeam": "133602",
            "idAwayTeam": "133604",
        }
    ]
}

OPENDOTA = [
    {
        "match_id": 8997682537,
        "duration": 1975,
        "start_time": 1789324066,
        "radiant_team_id": 10241688,
        "radiant_name": "YBN Club",
        "dire_team_id": 10241694,
        "dire_name": "Stray Club",
        "leagueid": 20159,
        "league_name": "WINLINE Star Series Season 4",
        "radiant_score": 42,
        "dire_score": 15,
        "radiant_win": True,
    }
]


def _getter(mapping):
    def get(url, headers=None):
        for prefix, payload in mapping.items():
            if prefix in url:
                return FetchResult(ok=True, http_status=200, payload=payload)
        return FetchResult(ok=False, http_status=404, error="missing fixture")

    return get


def test_catalog_still_has_41_sports():
    assert len(SPORTS) == 41
    assert sports_without_free_source()
    assert "football" in SPORTS_WITH_FREE_SOURCE
    assert "tennis" not in SPORTS_WITH_FREE_SOURCE


def test_verified_mappings_are_competition_specific():
    football_openfootball = [row for row in OPENFOOTBALL_FILES if row["sport_id"] == "football"]
    assert len(football_openfootball) >= 8
    assert {row["competition_id"] for row in THESPORTSDB_LEAGUES} >= {
        "nba",
        "nhl",
        "nfl",
        "mlb",
        "australia-afl",
    }
    assert any(row["shortcut"] == "del" for row in OPENLIGADB_LEAGUES)
    assert any(row["shortcut"] == "ucl" for row in OPENLIGADB_LEAGUES)
    assert len(OPENFOOTBALL_FILES) >= 19
    assert sports_missing_technically_collectable_source() == []
    assert any(row["source"].startswith("FIFA") for row in SOURCES)


def test_openfootball_parses_real_shaped_matches():
    adapter = OpenFootballAdapter(getter=_getter({"2026-27/en.1.json": OPENFOOTBALL_EN}))
    fixtures = adapter.fetch(FetchRequest(capability="fixtures", competition_id="england-premier-league"))
    results = adapter.fetch(FetchRequest(capability="results", competition_id="england-premier-league"))
    assert fixtures.ok
    assert fixtures.events[0]["home"]["name"] == "Brentford FC"
    assert results.events[0]["score"]["home"] == 2


def test_openligadb_live_unfinished_match():
    adapter = OpenLigaDbAdapter(getter=_getter({"getmatchdata/bl1": OPENLIGA_BL1}))
    live = adapter.fetch(FetchRequest(capability="fixtures", source_competition_id="bl1", competition_id="germany-bundesliga"))
    assert live.events[0]["home"]["name"] == "FC Bayern München"
    assert live.events[0]["status"] == "scheduled"


def test_openligadb_goals_are_live_evidence():
    payload = [
        {
            **OPENLIGA_BL1[0],
            "goals": [{"matchMinute": 12, "scoreTeam1": 1, "scoreTeam2": 0}],
        }
    ]
    adapter = OpenLigaDbAdapter(getter=_getter({"getmatchdata/bl1": payload}))
    live = adapter.fetch(FetchRequest(capability="live_scores", source_competition_id="bl1", competition_id="germany-bundesliga"))
    assert live.events[0]["status"] == "live"
    assert live.events[0]["score"]["home"] == 1


def test_thesportsdb_next_and_past():
    adapter = TheSportsDbAdapter(
        getter=_getter({"eventsnextleague.php?id=4328": TSDB_NEXT, "eventspastleague.php?id=4328": TSDB_PAST})
    )
    fixtures = adapter.fetch(FetchRequest(capability="fixtures", source_competition_id="4328", competition_id="england-premier-league"))
    results = adapter.fetch(FetchRequest(capability="results", source_competition_id="4328", competition_id="england-premier-league"))
    assert fixtures.events[0]["away"]["name"] == "Chelsea"
    assert results.events[0]["status"] == "finished"


SQUIGGLE_GAMES = {
    "games": [
        {
            "id": 38494,
            "year": 2026,
            "round": 0,
            "hteam": "Sydney",
            "ateam": "Carlton",
            "hteamid": 16,
            "ateamid": 3,
            "hscore": 132,
            "ascore": 69,
            "complete": 100,
            "date": "2026-03-05 19:30:00",
            "venue": "S.C.G.",
            "roundname": "Opening Round",
        },
        {
            "id": 39999,
            "year": 2026,
            "round": 24,
            "hteam": "Collingwood",
            "ateam": "Brisbane Lions",
            "hteamid": 4,
            "ateamid": 2,
            "hscore": None,
            "ascore": None,
            "complete": 0,
            "date": "2026-09-20 19:20:00",
            "venue": "MCG",
            "roundname": "Round 24",
        },
    ]
}

CRICSHEET_DOC = {
    "info": {
        "dates": ["2026-09-16"],
        "event": {"name": "Indian Premier League"},
        "gender": "male",
        "match_type": "T20",
        "outcome": {"winner": "Mumbai Indians", "by": {"runs": 12}},
        "teams": ["Mumbai Indians", "Chennai Super Kings"],
        "venue": "Wankhede Stadium",
    },
    "innings": [
        {"team": "Mumbai Indians", "overs": [{"deliveries": [{"runs": {"total": 1}}]}]},
        {"team": "Chennai Super Kings", "overs": [{"deliveries": [{"runs": {"total": 1}}]}]},
    ],
}


def test_squiggle_parses_afl_season():
    adapter = SquiggleAflAdapter(getter=_getter({"q=games": SQUIGGLE_GAMES}))
    results = adapter.fetch(FetchRequest(capability="results", competition_id="australia-afl"))
    fixtures = adapter.fetch(FetchRequest(capability="fixtures", competition_id="australia-afl"))
    assert results.events[0]["home"]["name"] == "Sydney"
    assert results.events[0]["score"]["home"] == 132
    assert fixtures.events[0]["away"]["name"] == "Brisbane Lions"


def test_cricsheet_parses_match_document():
    adapter = CricsheetAdapter(getter=_getter({"recently_added_7_json.zip": [CRICSHEET_DOC]}))
    results = adapter.fetch(FetchRequest(capability="results"))
    assert results.events[0]["competition"] == "Indian Premier League"
    assert results.events[0]["home"]["name"] == "Mumbai Indians"
    assert results.events[0]["sport"] == "cricket"


def test_fifa_and_nhl_public_json_shapes():
    fifa_payload = {
        "Results": [
            {
                "IdMatch": "1",
                "CompetitionName": [{"Locale": "en-gb", "Description": "Premium liiga"}],
                "MatchStatus": 1,
                "Winner": None,
                "Date": "2026-09-17T16:00:00Z",
                "Stadium": {"Name": [{"Description": "Lillekula"}]},
                "HomeTeam": {"IdTeam": "a", "TeamName": [{"Description": "FC Levadia Tallinn"}], "Score": None},
                "AwayTeam": {"IdTeam": "b", "TeamName": [{"Description": "Tammeka Tartu"}], "Score": None},
            }
        ]
    }
    fifa = FifaFootballAdapter(
        getter=_getter({"live/football": fifa_payload, "calendar/matches": {"Results": []}})
    )
    fixtures = fifa.fetch(FetchRequest(capability="fixtures"))
    assert fixtures.events[0]["home"]["name"] == "FC Levadia Tallinn"


def test_fifa_named_competition_does_not_keep_unrelated_calendar():
    payload = {
        "Results": [
            {
                "IdMatch": "lib",
                "CompetitionName": [{"Description": "CONMEBOL Libertadores"}],
                "MatchStatus": 1,
                "Winner": None,
                "Date": "2026-09-18T00:00:00Z",
                "HomeTeam": {"IdTeam": "a", "TeamName": [{"Description": "CR Flamengo"}], "Score": 0},
                "AwayTeam": {"IdTeam": "b", "TeamName": [{"Description": "Atlético Bucaramanga"}], "Score": 0},
            }
        ]
    }
    fifa = FifaFootballAdapter(getter=_getter({"live/football": payload, "calendar/matches": {"Results": []}}))
    afcon = fifa.fetch(FetchRequest(capability="snapshot", competition_id="africa-cup-of-nations"))
    umbrella = fifa.fetch(FetchRequest(capability="snapshot", competition_id="fifa-connected-competitions"))
    assert afcon.events == []
    assert umbrella.events[0]["home"]["name"] == "CR Flamengo"
    assert umbrella.events[0]["status"] == "scheduled"


def test_nhl_mlb_public_json_shapes():
    nhl = NhlAdapter(
        getter=_getter(
            {
                "schedule/now": {
                    "gameWeek": [
                        {
                            "games": [
                                {
                                    "id": 2026010001,
                                    "gameState": "FUT",
                                    "startTimeUTC": "2026-09-19T00:00:00Z",
                                    "homeTeam": {"id": 1, "abbrev": "DAL"},
                                    "awayTeam": {"id": 2, "abbrev": "STL"},
                                    "venue": {"default": "American Airlines Center"},
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    upcoming = nhl.fetch(FetchRequest(capability="fixtures"))
    assert upcoming.events[0]["home"]["name"] == "DAL"
    mlb = MlbAdapter(
        getter=_getter(
            {
                "schedule?sportId=1": {
                    "dates": [
                        {
                            "games": [
                                {
                                    "gamePk": 1,
                                    "gameDate": "2026-09-17T17:10:00Z",
                                    "status": {"abstractGameState": "Final"},
                                    "teams": {
                                        "home": {"team": {"id": 1, "name": "Cleveland Guardians"}, "score": 5},
                                        "away": {"team": {"id": 2, "name": "Detroit Tigers"}, "score": 2},
                                    },
                                    "venue": {"name": "Progressive Field"},
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    done = mlb.fetch(FetchRequest(capability="results"))
    assert done.events[0]["home"]["name"] == "Cleveland Guardians"
    live_mlb = MlbAdapter(
        getter=_getter(
            {
                "schedule?sportId=1": {
                    "dates": [
                        {
                            "games": [
                                {
                                    "gamePk": 2,
                                    "gameDate": "2026-09-20T17:10:00Z",
                                    "status": {
                                        "abstractGameState": "Live",
                                        "detailedState": "In Progress",
                                    },
                                    "teams": {
                                        "home": {"team": {"id": 1, "name": "Cleveland Guardians"}, "score": 3},
                                        "away": {"team": {"id": 2, "name": "Detroit Tigers"}, "score": 2},
                                    },
                                    "venue": {"name": "Progressive Field"},
                                    "linescore": {
                                        "currentInning": 5,
                                        "inningState": "Top",
                                        "outs": 1,
                                        "innings": [{"num": 1, "home": {"runs": 1}, "away": {"runs": 0}}],
                                    },
                                }
                            ]
                        }
                    ]
                }
            }
        )
    )
    live = live_mlb.fetch(FetchRequest(capability="live_scores"))
    assert live.events[0]["status"] == "live"
    assert live.events[0]["score"]["inning"] == 5
    assert live.events[0]["score"]["inning_half"] == "top"


def test_opendota_pro_match():
    adapter = OpenDotaAdapter(getter=_getter({"proMatches": OPENDOTA}))
    results = adapter.fetch(FetchRequest(capability="results"))
    assert results.events[0]["game_id"] == "dota-2"
    assert results.events[0]["competition_key"] == "professional"
    assert "WINLINE" in (results.events[0].get("extra") or {}).get("league_name", "")


def test_bootstrap_and_collect_with_injected_adapters():
    register_production_adapters()
    db = SessionLocal()
    original = None
    try:
        bootstrap_registry(db)
        db.commit()
        assert db.query(SportsSourceCompetition).count() >= 20
        original = dict(ADAPTERS)

        class _Empty:
            def fetch(self, request):
                return FetchResult(ok=True, http_status=200, events=[])

        injected = {
            "openfootball-json": lambda source_id="openfootball": OpenFootballAdapter(
                getter=_getter({"2026-27/en.1.json": OPENFOOTBALL_EN})
            ),
            "openligadb": lambda source_id="openligadb": OpenLigaDbAdapter(
                getter=_getter(
                    {
                        "getmatchdata/bl1": OPENLIGA_BL1,
                        "getmatchdata/bl2": [],
                        "getmatchdata/bl3": [],
                        "getmatchdata/dfb": [],
                        "getmatchdata/del": [],
                        "getmatchdata/ucl": [],
                        "getmatchdata/fbl1": [],
                        "getmatchdata/fbl2": [],
                        "getmatchdata/del2": [],
                        "getmatchdata/CHL": [],
                        "getmatchdata/PDCWM": [],
                        "getbltable": [],
                    }
                )
            ),
            "thesportsdb": lambda source_id="thesportsdb": TheSportsDbAdapter(
                getter=_getter(
                    {
                        "eventsnextleague.php": TSDB_NEXT,
                        "eventspastleague.php": TSDB_PAST,
                        "lookuptable.php": {"table": []},
                    }
                )
            ),
            "opendota": lambda source_id="opendota": OpenDotaAdapter(getter=_getter({"proMatches": OPENDOTA})),
            "squiggle-afl": lambda source_id="squiggle": SquiggleAflAdapter(
                getter=_getter({"q=games": SQUIGGLE_GAMES})
            ),
            "cricsheet-json": lambda source_id="cricsheet": CricsheetAdapter(
                getter=_getter({"recently_added_7_json.zip": [CRICSHEET_DOC]})
            ),
        }
        empty = lambda source_id="x", _empty=_Empty: _empty()
        for key in list(ADAPTERS):
            ADAPTERS[key] = empty
        ADAPTERS.update(injected)

        summary = run_cycle(db, capabilities=["fixtures", "results"], sleeper=lambda _d: None, force=True)
        db.commit()
        assert sum(summary.values()) > 0
        assert db.query(SportsEvent).count() > 0
        names = {event.sport_id for event in db.query(SportsEvent).all()}
        assert "football" in names
        assert "dota-2" in names
        assert "australian-rules" in names
        assert "cricket" in names
    finally:
        db.close()
        if original is not None:
            ADAPTERS.clear()
            ADAPTERS.update(original)
