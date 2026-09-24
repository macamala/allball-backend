from collector.adapters_wta import match_to_event
from collector.integrity import audit_event_detail_consistency
from collector.wta_orientation import orient_wta_match, tennis_sets_agree_with_match_score


def _singles(*, a_sets, b_sets, winner=None, state="F", **extra):
    row = {
        "MatchID": extra.get("MatchID", "RS1"),
        "EventID": extra.get("EventID", 99),
        "MatchState": state,
        "PlayerNameFirstA": extra.get("first_a", "Iga"),
        "PlayerNameLastA": extra.get("last_a", "Swiatek"),
        "PlayerNameFirstB": extra.get("first_b", "Aryna"),
        "PlayerNameLastB": extra.get("last_b", "Sabalenka"),
        **{f"ScoreSet{i}A": str(a) for i, a in enumerate(a_sets, start=1)},
        **{f"ScoreSet{i}B": str(b) for i, b in enumerate(b_sets, start=1)},
    }
    if winner is not None:
        row["Winner"] = winner
    return row


def test_straight_set_home_a_win():
    event = match_to_event(_singles(a_sets=(6, 6), b_sets=(4, 3)), "wta-tour")
    assert event["home"]["name"] == "Iga Swiatek"
    assert event["participant_a"]["name"] == "Iga Swiatek"
    assert event["score"] == {"home": 2, "away": 0}
    assert [row["winner"] for row in event["periods"]] == ["home", "home"]
    assert tennis_sets_agree_with_match_score(event["score"], event["periods"])


def test_straight_set_away_b_win():
    event = match_to_event(_singles(a_sets=(3, 2), b_sets=(6, 6), winner="B"), "wta-tour")
    assert event["away"]["name"] == "Aryna Sabalenka"
    assert event["score"] == {"home": 0, "away": 2}
    assert [row["winner"] for row in event["periods"]] == ["away", "away"]
    assert event.get("orientation_conflict") is None
    assert tennis_sets_agree_with_match_score(event["score"], event["periods"])


def test_three_set_match_keeps_a_b_games():
    event = match_to_event(_singles(a_sets=(6, 3, 6), b_sets=(4, 6, 2)), "wta-tour")
    assert event["score"] == {"home": 2, "away": 1}
    assert event["periods"][1]["home"] == 3
    assert event["periods"][1]["away"] == 6
    assert event["periods"][1]["winner"] == "away"


def test_doubles_uses_a_and_b_pairs():
    row = {
        "MatchID": "MD1",
        "MatchState": "F",
        "PlayerNameFirstA": "Gabriela",
        "PlayerNameLastA": "Dabrowski",
        "PlayerNameFirstA2": "Luisa",
        "PlayerNameLastA2": "Stefani",
        "PlayerNameFirstB": "Kaitlin",
        "PlayerNameLastB": "Quevedo",
        "PlayerNameFirstB2": "Dominika",
        "PlayerNameLastB2": "Salkova",
        "ScoreSet1A": "6",
        "ScoreSet1B": "4",
        "ScoreSet2A": "6",
        "ScoreSet2B": "4",
    }
    event = match_to_event(row, "wta-tour")
    assert event["home"]["name"] == "Gabriela Dabrowski / Luisa Stefani"
    assert event["away"]["name"] == "Kaitlin Quevedo / Dominika Salkova"
    assert event["score"] == {"home": 2, "away": 0}
    assert event["periods"][0]["home"] == 6
    assert event["periods"][0]["away"] == 4
    assert event["periods"][0]["winner"] == "home"
    assert event["periods"][0]["complete"] is True

def test_doubles_preserve_both_member_countries():
    row = {
        "MatchID": "MD2",
        "MatchState": "F",
        "PlayerNameFirstA": "Gabriela",
        "PlayerNameLastA": "Dabrowski",
        "PlayerNameFirstA2": "Luisa",
        "PlayerNameLastA2": "Stefani",
        "CountryCodeA": "CA",
        "CountryCodeA2": "BR",
        "PlayerNameFirstB": "Erin",
        "PlayerNameLastB": "Routliffe",
        "PlayerNameFirstB2": "Aldila",
        "PlayerNameLastB2": "Sutjiadi",
        "PlayerIDB": "11",
        "PlayerIDB2": "12",
        "ScoreSet1A": "6",
        "ScoreSet1B": "4",
        "ScoreSet2A": "6",
        "ScoreSet2B": "4",
    }
    event = match_to_event(
        row,
        "wta-tour",
        player_countries={"id:11": "NZ", "id:12": "ID"},
    )
    assert event["home"]["country_ids"] == ["CA", "BR"]
    assert event["away"]["country_ids"] == ["NZ", "ID"]



def test_zero_values_are_stored_not_inferred():
    event = match_to_event(_singles(a_sets=(0, 0), b_sets=(0, 0), state="P"), "wta-tour")
    assert event["status"] == "live"
    assert event["score"] == {"home": None, "away": None}
    assert event["periods"][0]["home"] == 0
    assert event["periods"][0]["winner"] is None
    assert event["periods"][0]["complete"] is False


def test_retirement_does_not_invent_match_score_from_incomplete_set():
    event = match_to_event(_singles(a_sets=(6, 2), b_sets=(3, 1), state="R"), "wta-tour")
    assert event["status"] == "finished"
    assert event["result_type"] == "retirement"
    assert event["score"] == {"home": None, "away": None}
    assert len(event["periods"]) == 2
    assert event["periods"][0]["complete"] is True
    assert event["periods"][1]["complete"] is False


def test_winner_disagreement_is_flagged_not_rotated():
    oriented = orient_wta_match(_singles(a_sets=(6, 6), b_sets=(2, 1), winner="B"))
    assert oriented["score"] == {"home": 2, "away": 0}
    assert oriented["orientation_conflict"] is True
    assert oriented["periods"][0]["home"] == 6


def test_source_event_id_includes_tournament():
    tournament = {"tournamentGroup": {"id": 2075, "name": "GUADALAJARA 500"}, "year": 2026, "surface": "Hard", "level": "WTA 500"}
    event = match_to_event(_singles(a_sets=(6, 6), b_sets=(4, 2), MatchID="RS100"), "wta-tour", tournament)
    assert event["source_event_id"] == "2075:2026:RS100"
    assert event["tournament_id"] == 2075
    assert event["tournament_name"] == "GUADALAJARA 500"
    assert event["surface"] == "Hard"
    assert event["category"] == "WTA 500"


def test_audit_flags_score_period_contradiction():
    flags = audit_event_detail_consistency(
        {
            "id": "ninko-evt-x",
            "sport": "tennis",
            "home": {"name": "A"},
            "away": {"name": "B"},
            "participant_a": {"name": "C"},
            "participant_b": {"name": "B"},
            "score": {"home": 2, "away": 0},
            "periods": [
                {"home": 3, "away": 6, "winner": "away"},
                {"home": 2, "away": 6, "winner": "away"},
            ],
        },
        route_id="ninko-evt-x",
    )
    classes = {row["class"] for row in flags}
    assert "tennis_score_period_orientation" in classes
    assert "participant_a_home_mismatch" in classes


def test_reused_match_id_does_not_merge_different_pairs():
    from collector.adapters import FetchRequest, FetchResult, register_adapter
    from collector.collect import collect_competition
    from collector.models import SportsEvent
    from collector.util import load_json
    from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source

    calls = {"n": 0}

    class WtaEcho:
        def fetch(self, request: FetchRequest) -> FetchResult:
            calls["n"] += 1
            if calls["n"] == 1:
                events = [
                    {
                        "id": "RS100",
                        "source_event_id": "RS100",
                        "home": {"name": "Francesca Jones"},
                        "away": {"name": "Alja Senica"},
                        "status": "finished",
                        "score": {"home": 0, "away": 2},
                        "periods": [{"home": 2, "away": 6}, {"home": 3, "away": 6}],
                        "start_time": "2026-09-15T10:03:00Z",
                        "source_family": "wta-json",
                    }
                ]
            else:
                events = [
                    {
                        "id": "RS100",
                        "source_event_id": "RS100",
                        "home": {"name": "Oksana Selekhmeteva"},
                        "away": {"name": "Nastasja Schunk"},
                        "status": "finished",
                        "score": {"home": 2, "away": 1},
                        "periods": [{"home": 5, "away": 7}, {"home": 6, "away": 3}, {"home": 6, "away": 3}],
                        "start_time": "2026-09-15T10:03:00Z",
                        "source_family": "wta-json",
                    }
                ]
            return FetchResult(ok=True, http_status=200, events=events)

    register_adapter("wta-json", lambda source_id="wta-json": WtaEcho())
    db = _session()
    try:
        src = _source(db, "wta-json", "wta-json")
        src.upstream_family = "wta-json"
        comp = _competition(db, "wta-tour", "tennis", event_model="individual_match")
        _map(db, "wta-tour", "wta-json", 1, upstream_family="wta-json")
        db.commit()
        collect_competition(db, comp, "fixtures", sleeper=lambda _d: None)
        db.commit()
        collect_competition(db, comp, "fixtures", sleeper=lambda _d: None)
        db.commit()
        rows = db.query(SportsEvent).all()
        names = {
            ((load_json(row.participants_json, {}) or {}).get("home") or {}).get("name")
            for row in rows
        }
        assert "Francesca Jones" in names
        assert "Oksana Selekhmeteva" in names
        assert len(rows) == 2
        jones = next(
            row
            for row in rows
            if ((load_json(row.participants_json, {}) or {}).get("home") or {}).get("name") == "Francesca Jones"
        )
        score = load_json(jones.score_json, {}) or {}
        extra = load_json(jones.extra_json, {}) or {}
        assert score.get("away") == 2
        assert extra.get("periods")[0]["away"] == 6
    finally:
        db.close()
        _cleanup_adapters("wta-json")


def test_wta_country_lookup_normalizes_diacritics_for_doubles():
    from collector.adapters_wta import _player_country_map

    players = {
        "entries": [
            {"player": {"id": 1, "firstName": "Maja", "lastName": "Chwalińska", "countryCode": "POL"}},
            {"player": {"id": 2, "firstName": "Barbora", "lastName": "Krejčíková", "countryCode": "CZE"}},
            {"player": {"id": 3, "firstName": "Erin", "lastName": "Routliffe", "countryCode": "NZL"}},
            {"player": {"id": 4, "firstName": "Aldila", "lastName": "Sutjiadi", "countryCode": "IDN"}},
        ]
    }
    row = {
        "MatchID": "MD-country",
        "MatchState": "F",
        "PlayerNameFirstA": "Maja",
        "PlayerNameLastA": "Chwalinska",
        "PlayerNameFirstA2": "Barbora",
        "PlayerNameLastA2": "Krejcikova",
        "PlayerNameFirstB": "Erin",
        "PlayerNameLastB": "Routliffe",
        "PlayerNameFirstB2": "Aldila",
        "PlayerNameLastB2": "Sutjiadi",
        "ScoreSet1A": "6",
        "ScoreSet1B": "4",
        "ScoreSet2A": "6",
        "ScoreSet2B": "4",
    }
    event = match_to_event(
        row,
        "wta-tour",
        player_countries=_player_country_map(players),
    )
    assert event["home"]["country_ids"] == ["POL", "CZE"]
    assert event["away"]["country_ids"] == ["NZL", "IDN"]
