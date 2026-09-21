from datetime import datetime, timedelta

from collector.adapters_wta import match_to_event, wta_match_statistics
from collector.backfill import CORE_COMPETITIONS, run_bounded_backfill
from collector.detail_enrich import (
    TTL_FINISHED,
    TTL_NEGATIVE,
    _fresh,
    parse_fotmob_details,
    parse_mlb_live,
    parse_nhl_boxscore,
    parse_nhl_landing,
    parse_sofa_incidents,
    parse_sofa_lineups,
    parse_sofa_statistics,
)
from collector.merge import apply_row_fields
from collector.models import SportsEvent, SportsEventObservation
from collector.normalize import normalize_event
from collector.provider import NinkoCollectedSportsDataProvider
from collector.source_ids import merge_family_ids
from collector.test_support import mock_event
from collector.util import dump_json, load_json
from database import SessionLocal


def test_family_keyed_source_ids_merge_is_idempotent():
    first = merge_family_ids({"fotmob": "111"}, family="sofascore-web", source_event_id="222")
    second = merge_family_ids(first, family="sofascore-web", source_event_id="222")
    assert first == second
    assert first["fotmob"] == "111"
    assert first["sofascore-web"] == "222"


def test_list_ids_promote_to_family_map():
    out = merge_family_ids(["999"], family="fotmob", source_event_id="999")
    assert out["fotmob"] == "999"


def test_untyped_list_ids_bind_to_source_family():
    from collector.source_ids import families_with_ids

    ids = families_with_ids({"source_family": "fotmob", "source_event_ids": ["48101234"]})
    assert ids["fotmob"] == "48101234"
    assert "_untyped" not in ids


def test_negative_detail_ttl_is_shorter_than_finished_success():
    empty = {
        "detail_fetched_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "detail_empty": True,
        "detail_negative": True,
    }
    assert not _fresh(empty, "finished")
    success = {
        "detail_fetched_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
        "detail_empty": False,
        "detail_negative": False,
    }
    assert _fresh(success, "finished")
    assert TTL_NEGATIVE < TTL_FINISHED


def test_fotmob_sanitized_payload_maps_timeline_stats_lineups():
    payload = {
        "general": {"venueName": "Emirates", "referee": "M. Oliver", "attendance": 60000},
        "content": {
            "matchFacts": {
                "events": [
                    {"type": "Goal", "time": 12, "name": "Saka", "isHome": True, "homeScore": 1, "awayScore": 0},
                    {"type": "Card", "card": "Yellow", "time": 40, "name": "Rice", "isHome": True},
                    {"type": "Subst", "time": 70, "name": "Martinelli", "isHome": True},
                    {"type": "VAR", "time": 88, "varReason": "Offside", "isHome": False},
                ]
            },
            "stats": {"Periods": {"All": {"stats": [{"stats": [{"title": "Possession", "stats": [58, 42]}]}]}}},
            "lineup": {
                "lineup": [
                    {"formation": "4-3-3", "coach": {"name": "Arteta"}, "players": [[{"name": {"fullName": "Raya"}, "shirtNumber": 1}]]},
                    {"formation": "4-2-3-1", "players": [[{"name": {"fullName": "Sanchez"}, "shirtNumber": 1}]]},
                ]
            },
        },
    }
    out = parse_fotmob_details(payload)
    kinds = {row["type"] for row in out["incidents"]}
    assert "goal" in kinds and "yellow card" in kinds
    assert out["statistics"][0]["home"] == 58
    assert out["lineups"]["home"]["coach"] == "Arteta"
    assert out["venue"] == "Emirates"
    assert out["referee"] == "M. Oliver"


def test_fotmob_hometeam_lineup_shape_parses_starters():
    out = parse_fotmob_details(
        {
            "content": {
                "lineup": {
                    "homeTeam": {
                        "formation": "4-3-3",
                        "coach": {"name": "Paolo Vanoli"},
                        "starters": [{"name": "David de Gea", "shirtNumber": "43"}],
                        "subs": [{"name": "Pietro Comuzzo", "shirtNumber": "15"}],
                    },
                    "awayTeam": {
                        "formation": "4-3-3",
                        "coach": {"name": "Antonio Conte"},
                        "starters": [{"name": "Vanja Milinkovic-Savic", "shirtNumber": "32"}],
                        "subs": [],
                    },
                }
            }
        }
    )
    assert out["lineups"]["home"]["formation"] == "4-3-3"
    assert out["lineups"]["home"]["coach"] == "Paolo Vanoli"
    assert out["lineups"]["home"]["start"][0]["name"] == "David de Gea"


def test_sofascore_sanitized_payloads_map_incidents_stats_lineups():
    incidents = parse_sofa_incidents(
        {"incidents": [{"incidentType": "goal", "time": 9, "player": {"name": "Haaland"}, "isHome": True, "homeScore": 1, "awayScore": 0}]}
    )
    stats = parse_sofa_statistics(
        {"statistics": [{"groups": [{"statisticsItems": [{"name": "Shots", "home": "12", "away": "4"}]}]}]}
    )
    lineups = parse_sofa_lineups(
        {"home": {"formation": "4-3-3", "players": [{"player": {"name": "Ederson"}, "jerseyNumber": "31"}]}, "away": {"players": []}}
    )
    assert incidents[0]["player"] == "Haaland"
    assert stats[0]["label"] == "Shots"
    assert lineups["home"]["start"][0]["name"] == "Ederson"


def test_mlb_live_payload_maps_innings_and_box():
    payload = {
        "liveData": {
            "linescore": {
                "currentInning": 9,
                "inningHalf": "bottom",
                "innings": [{"num": 1, "home": {"runs": 0, "hits": 1, "errors": 0}, "away": {"runs": 1, "hits": 2, "errors": 0}}],
                "defense": {"pitcher": {"fullName": "P. Pitcher"}},
                "offense": {"batter": {"fullName": "B. Batter"}},
            },
            "plays": {"allPlays": [{"result": {"eventType": "home_run", "description": "Gone"}, "about": {"inning": 1}}]},
            "boxscore": {
                "teams": {
                    "home": {
                        "teamStats": {"batting": {"runs": 3, "hits": 8, "errors": 0}},
                        "players": {"ID1": {"person": {"fullName": "Slugger"}, "stats": {"batting": {"hits": 2, "atBats": 4, "rbi": 1}}}},
                    },
                    "away": {"teamStats": {"batting": {"runs": 1, "hits": 4, "errors": 1}}, "players": {}},
                }
            },
        }
    }
    out = parse_mlb_live(payload)
    assert out["periods"][0]["away"] == 1
    assert out["statistics"][0]["label"] == "Runs"
    assert out["sport_detail"]["pitcher"] == "P. Pitcher"
    assert out["incidents"][0]["description"] == "Gone"


def test_nhl_payloads_map_goals_and_rosters():
    landing = parse_nhl_landing(
        {
            "homeTeam": {"score": 3, "sog": 28},
            "awayTeam": {"score": 2, "sog": 31},
            "summary": {
                "scoring": [
                    {
                        "periodDescriptor": {"number": 1},
                        "goals": [{"name": {"default": "McDavid"}, "timeInPeriod": "05:12", "homeScore": 1, "awayScore": 0}],
                    }
                ]
            },
        }
    )
    box = parse_nhl_boxscore(
        {
            "playerByGameStats": {
                "homeTeam": {"forwards": [{"name": {"default": "McDavid"}, "goals": 1, "assists": 1, "sog": 4}]},
                "awayTeam": {"forwards": []},
            }
        }
    )
    assert landing["incidents"][0]["player"] == "McDavid"
    assert landing["statistics"][0]["label"] == "Shots"
    assert box["lineups"]["home"]["start"][0]["name"] == "McDavid"


def test_wta_walkover_string_does_not_invent_sets():
    row = {
        "PlayerNameFirstA": "Gabriela",
        "PlayerNameLastA": "Dabrowski",
        "PlayerNameFirstA2": "Luisa",
        "PlayerNameLastA2": "Stefani",
        "PlayerNameFirstB": "Kaitlin",
        "PlayerNameLastB": "Quevedo",
        "PlayerNameFirstB2": "Dominika",
        "PlayerNameLastB2": "Salkova",
        "ScoreSet1A": "",
        "ScoreSet1B": "",
        "MatchState": "F",
        "ScoreString": " W/O",
        "MatchID": "LD004",
    }
    event = match_to_event(row, "wta-tour")
    assert event["result_type"] == "walkover"
    assert event["walkover"] is True
    assert event["score"]["home"] is None
    assert event["periods"] in (None, [])
    row = {
        "PlayerNameFirstA": "Iga",
        "PlayerNameLastA": "Swiatek",
        "PlayerNameFirstB": "Coco",
        "PlayerNameLastB": "Gauff",
        "ScoreSet1A": 6,
        "ScoreSet1B": 4,
        "ScoreSet2A": 6,
        "ScoreSet2B": 2,
        "MatchState": "F",
        "MatchID": "99",
        "AcesA": 5,
        "AcesB": 2,
        "DoubleFaultsA": 1,
        "DoubleFaultsB": 3,
        "SeedA": 1,
        "RankB": 3,
    }
    stats = wta_match_statistics(row)
    labels = {item["label"] for item in stats}
    assert "Aces" in labels
    event = match_to_event(row, "wta-tour")
    assert event["score"]["home"] == 2
    assert event["home"]["seed"] == 1
    assert event["statistics"][0]["label"] == "Aces"
    assert event["source_event_ids"]["wta-json"]


def test_apply_row_fields_keeps_multi_provider_ids(monkeypatch):
    db = SessionLocal()
    try:
        row = SportsEvent(
            event_id="ninko-evt-crosswalk",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            status="finished",
            extra_json=dump_json({"source_family": "fotmob", "source_event_ids": {"fotmob": "1"}}),
        )
        db.add(row)
        db.commit()
        incoming = mock_event(status="finished", score={"home": 1, "away": 0})
        incoming["source_family"] = "sofascore-web"
        incoming["source_event_id"] = "99"
        incoming["source_event_ids"] = {"sofascore-web": "99"}
        apply_row_fields(row, incoming, "sofascore-web", True)
        from collector.util import load_json

        ids = load_json(row.extra_json, {})["source_event_ids"]
        assert ids["fotmob"] == "1"
        assert ids["sofascore-web"] == "99"
    finally:
        db.close()


def test_backfill_is_bounded_and_rerunnable(monkeypatch):
    calls = []

    def fake_cycle(db, **kwargs):
        calls.append(kwargs.get("competition_id"))
        return {"ok": True}

    monkeypatch.setattr("collector.backfill.run_cycle", fake_cycle)
    monkeypatch.setattr("collector.backfill.enrich_recent_detail", lambda db, **kwargs: {"attempted": 0, "filled": 0})
    monkeypatch.setattr("collector.backfill.register_production_adapters", lambda: None)
    monkeypatch.setattr("collector.fotmob_crosswalk.crosswalk_fotmob_ids", lambda db, **kwargs: {"upstream_eligible": 0, "attached": 0})
    monkeypatch.setattr("collector.fotmob_crosswalk.eligible_coverage", lambda db, **kwargs: {"upstream_eligible": 0, "canonical_with_fotmob_id": 0, "coverage_pct": 0})
    monkeypatch.setattr("collector.wta_rewrite.rewrite_wta_result_types", lambda db: {"applied": 0})
    db = SessionLocal()
    try:
        first = run_bounded_backfill(db, competitions=["wta-tour", "mlb"])
        second = run_bounded_backfill(db, competitions=["wta-tour", "mlb"])
        assert calls == ["wta-tour", "mlb", "wta-tour", "mlb"]
        assert "wta-tour" in CORE_COMPETITIONS
        assert first["count"] == 2 and second["count"] == 2
    finally:
        db.close()


def test_event_list_query_stays_light_with_fat_extra():
    db = SessionLocal()
    try:
        blob = dump_json({"noise": "x" * 8000, "field_freshness": {"a": 1}, "source_family": "fotmob", "periods": [{"home": 1, "away": 0}]})
        start = datetime(2026, 9, 21, 12, 0, 0)
        for index in range(40):
            db.add(
                SportsEvent(
                    event_id=f"ninko-evt-perf-{index}",
                    sport_id="football",
                    competition_id="italy-serie-a",
                    event_family="team_match",
                    status="scheduled",
                    start_time=start,
                    display_eligible=True,
                    extra_json=blob,
                    list_extra_json=dump_json({"live_class": "UPCOMING"}),
                    participants_json=dump_json({"home": {"name": f"H{index}"}, "away": {"name": f"A{index}"}}),
                    score_json=dump_json({}),
                )
            )
        db.commit()
        started = datetime.utcnow()
        rows = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            date_from="2026-09-21T00:00:00Z",
            date_to="2026-09-21T23:59:59Z",
        )
        elapsed = (datetime.utcnow() - started).total_seconds()
        assert len(rows) == 40
        assert "source_family" not in rows[0]
        assert elapsed < 2.5
    finally:
        db.close()


def test_normalize_keeps_family_source_ids():
    event = normalize_event(
        {
            "home": {"name": "A"},
            "away": {"name": "B"},
            "status": "scheduled",
            "start_time": "2026-09-21T18:00:00Z",
            "source_family": "fotmob",
            "source_event_id": "55",
            "extra": {"source_event_ids": {"fotmob": "55"}},
        },
        sport_id="football",
        competition_id="italy-serie-a",
    )
    assert event["source_event_ids"]["fotmob"] == "55"


def test_merge_keeps_fotmob_and_sofa_ids():
    current = mock_event(status="finished", score={"home": 1, "away": 0})
    current["source_family"] = "fotmob"
    current["source_event_id"] = "111"
    current["source_event_ids"] = {"fotmob": "111"}
    incoming = mock_event(status="finished", score={"home": 1, "away": 0})
    incoming["source_family"] = "sofascore-web"
    incoming["source_event_id"] = "222"
    incoming["source_event_ids"] = {"sofascore-web": "222"}
    from collector.merge import merge_event_fields

    merged = merge_event_fields(current, incoming, incoming_is_higher_priority=True, incoming_source_id="sofascore-web")
    assert merged["source_event_ids"]["fotmob"] == "111"
    assert merged["source_event_ids"]["sofascore-web"] == "222"


def test_fotmob_and_sofa_detail_merge_into_event_detail():
    db = SessionLocal()
    try:
        row = SportsEvent(
            event_id="ninko-evt-fotmob-rich",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            status="finished",
            extra_json=dump_json({"source_family": "fotmob", "source_event_ids": {"fotmob": "4810", "sofascore-web": "99"}}),
        )
        db.add(row)
        db.commit()

        class Result:
            def __init__(self, payload):
                self.ok = True
                self.payload = payload

        def getter(url):
            if "matchDetails" in url:
                return Result(
                    {
                        "content": {
                            "stats": {"Periods": {"All": {"stats": [{"stats": [{"title": "Possession", "stats": [60, 40]}]}]}}},
                            "lineup": {"lineup": [{"formation": "4-3-3", "coach": {"name": "X"}, "players": [[{"name": {"fullName": "A"}, "shirtNumber": 1}]]}, {"players": []}]},
                            "matchFacts": {"events": [{"type": "Goal", "time": 10, "name": "A", "isHome": True}]},
                        }
                    }
                )
            if "incidents" in url:
                return Result({"incidents": [{"incidentType": "goal", "time": 12, "player": {"name": "B"}, "isHome": True}]})
            if "statistics" in url:
                return Result({"statistics": []})
            if "lineups" in url:
                return Result({})
            return Result({})

        from collector.detail_enrich import enrich_event_row
        from collector.models import SportsEventDetail

        enrich_event_row(db, row, getter=getter)
        db.commit()
        detail = db.get(SportsEventDetail, row.event_id)
        assert load_json(detail.incidents_json)
        assert load_json(detail.statistics_json)
        assert load_json(detail.lineups_json)
    finally:
        db.close()


def test_walkover_stays_public_without_invented_score():
    event = normalize_event(
        {
            "home": {"name": "A"},
            "away": {"name": "B"},
            "status": "finished",
            "result_type": "walkover",
            "walkover": True,
            "score": {"home": None, "away": None},
            "start_time": "2026-09-18T15:48:00Z",
        },
        sport_id="tennis",
        competition_id="wta-tour",
    )
    assert event["result_type"] == "walkover"
    assert event["score"]["home"] is None


def test_racing_finished_without_result_becomes_scheduled():
    db = SessionLocal()
    try:
        row = SportsEvent(
            event_id="ninko-evt-race-blank",
            sport_id="horse-racing",
            competition_id="bha-meetings",
            event_family="racing",
            status="scheduled",
            extra_json=dump_json({}),
        )
        db.add(row)
        db.commit()
        incoming = mock_event(status="finished", score={"home": None, "away": None})
        incoming["event_family"] = "racing"
        apply_row_fields(row, incoming, "bha", True)
        assert row.status == "scheduled"
    finally:
        db.close()


def test_list_payload_omits_rich_match_centre_sections():
    db = SessionLocal()
    try:
        row = SportsEvent(
            event_id="ninko-evt-list-slim",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            status="finished",
            start_time=datetime(2026, 9, 21, 12, 0, 0),
            display_eligible=True,
            extra_json=dump_json({"incidents": [{"type": "goal"}] * 50, "statistics": [{"label": "x"}], "lineups": {"home": {}}, "winner": None, "live_class": "FT"}),
            list_extra_json=dump_json({"live_class": "FT", "result_type": None}),
            participants_json=dump_json({"home": {"name": "A"}, "away": {"name": "B"}}),
            score_json=dump_json({"home": 1, "away": 0}),
        )
        db.add(row)
        db.commit()
        public = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            date_from="2026-09-21T00:00:00Z",
            date_to="2026-09-21T23:59:59Z",
        )
        assert len(public) == 1
        assert public[0].get("incidents") in (None, [])
        assert public[0].get("statistics") in (None, [])
        assert public[0].get("lineups") in (None, [], {})
        assert public[0]["score"]["home"] == 1
    finally:
        db.close()


def test_gbgb_without_placing_is_scheduled():
    from collector.adapters_official import parse_gbgb

    events = parse_gbgb(
        {
            "items": [
                {
                    "trackName": "Oxford",
                    "raceNumber": 3,
                    "raceDate": "21/09/2026",
                    "raceTime": "14:00",
                    "greyhoundName": "",
                    "resultPosition": None,
                }
            ]
        }
    )
    assert not events or events[0]["status"] == "scheduled"


def test_fotmob_id_backfill_from_observations():
    from collector.id_backfill import attach_observation_ids, copy_complementary_ids

    db = SessionLocal()
    try:
        start = datetime.utcnow()
        keeper = SportsEvent(
            event_id="ninko-evt-id-keeper",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            status="finished",
            start_time=start,
            extra_json=dump_json({"source_family": "openligadb"}),
            participants_json=dump_json({"home": {"name": "Inter"}, "away": {"name": "Milan"}}),
        )
        sibling = SportsEvent(
            event_id="ninko-evt-id-fotmob",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            status="finished",
            start_time=start,
            extra_json=dump_json({"source_family": "fotmob", "source_event_ids": {"fotmob": "481099"}}),
            participants_json=dump_json({"home": {"name": "Inter"}, "away": {"name": "Milan"}}),
        )
        db.add_all([keeper, sibling])
        db.add(
            SportsEventObservation(
                event_id="ninko-evt-id-keeper",
                source_id="fotmob-board",
                source_family="fotmob",
                source_event_id="481099",
                retrieved_at=datetime.utcnow(),
            )
        )
        db.commit()
        updated = attach_observation_ids(db, hours=24)
        assert updated["rows_updated"] >= 1
        copied = copy_complementary_ids(db, hours=24)
        extra = load_json(db.get(SportsEvent, "ninko-evt-id-keeper").extra_json, {})
        assert extra["source_event_ids"]["fotmob"] == "481099"
        extra2 = load_json(db.get(SportsEvent, "ninko-evt-id-fotmob").extra_json, {})
        assert extra2["source_event_ids"]["fotmob"] == "481099"
        assert copied >= 0
    finally:
        db.close()


def test_seven_day_list_returns_all_valid_rows():
    db = SessionLocal()
    try:
        start = datetime(2026, 9, 18, 12, 0, 0)
        for index in range(12):
            db.add(
                SportsEvent(
                    event_id=f"ninko-evt-week-{index}",
                    sport_id="football",
                    competition_id="italy-serie-a",
                    event_family="team_match",
                    status="finished",
                    start_time=start + timedelta(hours=index),
                    display_eligible=True,
                    extra_json=dump_json({}),
                    list_extra_json=dump_json({"live_class": "FT"}),
                    participants_json=dump_json({"home": {"name": f"H{index}"}, "away": {"name": f"A{index}"}}),
                    score_json=dump_json({"home": 1, "away": 0}),
                )
            )
        db.commit()
        rows = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            date_from="2026-09-18T00:00:00Z",
            date_to="2026-09-25T00:00:00Z",
        )
        assert len(rows) == 12
        assert all(row.get("incidents") in (None, []) for row in rows)
    finally:
        db.close()

