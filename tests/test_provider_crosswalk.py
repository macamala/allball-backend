from datetime import datetime

from collector.adapters_feeds import EuroleagueLiveAdapter
from collector.identity_events import identity_confidence
from collector.models import SportsEvent
from collector.provider_crosswalk import attach_family_id, crosswalk_family, match_keepers
from collector.source_ids import families_with_ids, merge_family_ids
from collector.standings_enrich import SQUIGGLE_STANDINGS
from collector.util import dump_json, load_json
from database import SessionLocal


def _row(**kwargs):
    start = kwargs.pop("start_time")
    extra = kwargs.pop("extra", {"source_family": "openligadb"})
    return SportsEvent(
        event_id=kwargs.pop("event_id"),
        sport_id=kwargs.get("sport_id", "rugby"),
        competition_id=kwargs.get("competition_id", "france-top-14"),
        event_family="team_match",
        fingerprint=kwargs.pop("fingerprint"),
        start_time=start,
        display_eligible=True,
        participants_json=dump_json(
            {
                "home": {"name": kwargs.get("home", "Toulouse")},
                "away": {"name": kwargs.get("away", "Bordeaux")},
            }
        ),
        extra_json=dump_json(extra),
    )


def test_compound_ids_with_separators_are_retained():
    ids = merge_family_ids(
        {"euroleague-live": "E2025:47", "jolpica-f1": "2026:5"},
        family="opendota",
        source_event_id="123456789",
    )
    assert ids["euroleague-live"] == "E2025:47"
    assert ids["jolpica-f1"] == "2026:5"
    assert ids["opendota"] == "123456789"
    mapped = families_with_ids({"source_event_ids": {"euroleague": "E2025_47"}})
    assert mapped["euroleague-live"] == "E2025_47"


def test_crosswalk_attaches_date_only_unique_pair():
    kickoff = datetime(2026, 1, 17, 20, 0, 0)
    db = SessionLocal()
    try:
        row = _row(event_id="ninko-xw-toulouse", fingerprint="xw-toulouse", start_time=kickoff)
        db.add(row)
        db.commit()
        incoming = {
            "sport": "rugby",
            "competition_key": "france-top-14",
            "home": {"name": "Toulouse"},
            "away": {"name": "Bordeaux"},
            "start_time": "2026-01-17T00:00:00Z",
            "source_family": "pulselive",
            "source_event_id": "28cd45fd-6037-4102-8ba6-35fefb554af9",
            "source_event_ids": {"pulselive": "28cd45fd-6037-4102-8ba6-35fefb554af9"},
        }
        stats = crosswalk_family(
            db,
            family="pulselive",
            source_id="world-rugby",
            events=[incoming],
            persist_missing=False,
            hours=24 * 400,
        )
        extra = load_json(db.get(SportsEvent, "ninko-xw-toulouse").extra_json, {}) or {}
        assert extra["source_event_ids"]["pulselive"] == "28cd45fd-6037-4102-8ba6-35fefb554af9"
        assert stats["attached"] == 1
        assert stats["ambiguous"] == 0
    finally:
        db.close()


def test_crosswalk_rejects_ambiguous_same_day_pair():
    start = datetime(2026, 2, 1, 15, 0, 0)
    db = SessionLocal()
    try:
        db.add(_row(event_id="ninko-xw-amb-a", fingerprint="xw-amb-a", start_time=start, home="Toulouse", away="La Rochelle"))
        db.add(
            _row(
                event_id="ninko-xw-amb-b",
                fingerprint="xw-amb-b",
                start_time=start.replace(hour=18),
                home="Toulouse",
                away="La Rochelle",
            )
        )
        db.commit()
        incoming = {
            "sport": "rugby",
            "competition_key": "france-top-14",
            "home": {"name": "Toulouse"},
            "away": {"name": "La Rochelle"},
            "start_time": "2026-02-01T00:00:00Z",
            "source_event_ids": {"pulselive": "guid-ambiguous"},
        }
        stats = crosswalk_family(db, family="pulselive", source_id="world-rugby", events=[incoming])
        assert stats["ambiguous"] == 1
        assert stats["attached"] == 0
        for suffix in ("a", "b"):
            extra = load_json(db.get(SportsEvent, f"ninko-xw-amb-{suffix}").extra_json, {}) or {}
            assert not (extra.get("source_event_ids") or {}).get("pulselive")
    finally:
        db.close()


def test_crosswalk_rejects_women_vs_men():
    start = datetime(2026, 3, 1, 14, 0, 0)
    men = _row(event_id="ninko-xw-men", fingerprint="xw-men", start_time=start, home="Toulouse", away="La Rochelle")
    incoming = {
        "sport": "rugby",
        "competition_key": "france-top-14",
        "home": {"name": "Toulouse Women"},
        "away": {"name": "La Rochelle Women"},
        "start_time": "2026-03-01T14:00:00Z",
        "source_event_ids": {"pulselive": "guid-women"},
    }
    best, n_ok, protected = match_keepers(incoming, [men])
    assert best is None
    assert n_ok == 0
    assert protected == 1


def test_attach_unions_existing_family_ids():
    start = datetime(2026, 4, 1, 12, 0, 0)
    row = _row(
        event_id="ninko-xw-union",
        fingerprint="xw-union",
        start_time=start,
        extra={"source_family": "fotmob", "source_event_ids": {"fotmob": "4810"}},
    )
    changed = attach_family_id(row, "pulselive", "guid-union")
    assert changed
    ids = families_with_ids(load_json(row.extra_json, {}))
    assert ids["fotmob"] == "4810"
    assert ids["pulselive"] == "guid-union"


def test_euroleague_xml_child_tags_keep_gamecode():
    xml = """
    <games>
      <game>
        <gamenumber>47</gamenumber>
        <gamecode>E2025_47</gamecode>
        <hometeam>Olympiacos</hometeam>
        <awayteam>Monaco</awayteam>
        <homescore>89</homescore>
        <awayscore>80</awayscore>
        <played>true</played>
        <date>Oct 17, 2025</date>
        <time>19:00</time>
      </game>
    </games>
    """
    events = EuroleagueLiveAdapter()._from_results_xml(xml, "E2025")
    assert events
    assert events[0]["source_event_ids"]["euroleague-live"] == "E2025:47"
    assert events[0]["home"]["name"] == "Olympiacos"
    assert events[0]["start_time"].startswith("2025-10-17T19:00")


def test_squiggle_standings_url_is_season_scoped():
    assert "year={year}" in SQUIGGLE_STANDINGS
    assert SQUIGGLE_STANDINGS.format(year=2025).endswith("year=2025")


def test_attach_keeps_euroleague_compound_id():
    start = datetime(2025, 10, 17, 19, 0, 0)
    row = _row(
        event_id="ninko-xw-el",
        fingerprint="xw-el",
        start_time=start,
        sport_id="basketball",
        competition_id="euroleague",
        home="Olympiacos",
        away="Monaco",
        extra={"source_family": "openligadb"},
    )
    changed = attach_family_id(row, "euroleague-live", "E2025:47")
    assert changed
    ids = families_with_ids(load_json(row.extra_json, {}))
    assert ids["euroleague-live"] == "E2025:47"


def test_crosswalk_matches_same_calendar_day_with_clock_skew():
    db = SessionLocal()
    try:
        row = _row(
            event_id="ninko-xw-el-clock",
            fingerprint="xw-el-clock",
            start_time=datetime(2025, 10, 17, 16, 0, 0),
            sport_id="basketball",
            competition_id="euroleague",
            home="Olympiacos",
            away="Monaco",
        )
        db.add(row)
        db.commit()
        incoming = {
            "sport": "basketball",
            "competition_key": "euroleague",
            "home": {"name": "Olympiacos"},
            "away": {"name": "Monaco"},
            "start_time": "2025-10-17T19:00:00Z",
            "source_event_ids": {"euroleague-live": "E2025:47"},
        }
        stats = crosswalk_family(
            db,
            family="euroleague-live",
            source_id="euroleague-live",
            events=[incoming],
            persist_missing=False,
        )
        extra = load_json(db.get(SportsEvent, "ninko-xw-el-clock").extra_json, {}) or {}
        assert extra["source_event_ids"]["euroleague-live"] == "E2025:47"
        assert stats["canonical_matched"] == 1
    finally:
        db.close()


def test_euroleague_bc_baloncesto_identity_normalization():
    canonical = {
        "sport": "basketball",
        "competition": "euroleague",
        "competition_key": "euroleague",
        "home": {"name": "Olympiacos BC"},
        "away": {"name": "Real Madrid Baloncesto"},
        "start_time": "2025-10-17T16:00:00Z",
    }
    provider = {
        "sport": "basketball",
        "competition": "euroleague",
        "competition_key": "euroleague",
        "home": {"name": "Olympiacos"},
        "away": {"name": "Real Madrid"},
        "start_time": "2025-10-17T19:00:00Z",
        "source_event_ids": {"euroleague-live": "E2025:47"},
    }
    assert identity_confidence(canonical, provider) >= 90
    dotted = dict(canonical)
    dotted["home"] = {"name": "Olympiacos B.C."}
    assert identity_confidence(dotted, provider) >= 90
    piraeus = dict(provider)
    piraeus["home"] = {"name": "OLYMPIACOS PIRAEUS"}
    piraeus["away"] = {"name": "REAL MADRID"}
    assert identity_confidence(canonical, piraeus) >= 90


def test_basketball_club_suffix_does_not_false_merge():
    celtics = {
        "sport": "basketball",
        "competition": "nba",
        "competition_key": "nba",
        "home": {"name": "Boston Celtics"},
        "away": {"name": "Miami Heat"},
        "start_time": "2025-10-17T23:00:00Z",
    }
    boston = {
        "sport": "basketball",
        "competition": "nba",
        "competition_key": "nba",
        "home": {"name": "Boston"},
        "away": {"name": "Miami"},
        "start_time": "2025-10-17T23:00:00Z",
    }
    assert identity_confidence(celtics, boston) == 0
    football = {
        "sport": "football",
        "competition": "spain-la-liga",
        "competition_key": "spain-la-liga",
        "home": {"name": "Real Madrid"},
        "away": {"name": "Barcelona"},
        "start_time": "2025-10-17T19:00:00Z",
    }
    euro = {
        "sport": "basketball",
        "competition": "euroleague",
        "competition_key": "euroleague",
        "home": {"name": "Real Madrid"},
        "away": {"name": "Barcelona"},
        "start_time": "2025-10-17T19:00:00Z",
    }
    assert identity_confidence(football, euro) == 0


def test_opendota_owned_mapping_stays_public():
    from collector.competition_identity import correct_public_competition_id, resolve_competition

    resolved = resolve_competition(
        mapping_competition_id="professional",
        source_competition_name="PGL Wallachia",
        source_family="opendota",
        sport_id="dota-2",
    )
    assert resolved["accepted"] is True
    assert (
        correct_public_competition_id(
            stored_competition_id="professional",
            source_competition_name="The International",
            sport_id="dota-2",
            source_family="opendota",
        )
        == "professional"
    )


def test_cricsheet_historical_direct_event_keeps_frozen_id():
    from collector.competition_identity import correct_public_competition_id

    assert (
        correct_public_competition_id(
            stored_competition_id="t20-internationals",
            source_competition_name="ICC Men's T20 World Cup",
            sport_id="cricket",
            source_family="cricsheet",
        )
        == "t20-internationals"
    )


def test_cricsheet_attach_copies_innings_onto_keeper():
    start = datetime(2026, 9, 14, 0, 0, 0)
    row = _row(
        event_id="ninko-xw-cricket",
        fingerprint="xw-cricket",
        start_time=start,
        sport_id="cricket",
        competition_id="t20-internationals",
        home="India",
        away="Australia",
    )
    innings = [
        {"label": "India", "runs": 178, "wickets": 6, "overs": 20},
        {"label": "Australia", "runs": 164, "wickets": 8, "overs": 20},
    ]
    incoming = {
        "sport": "cricket",
        "competition_key": "t20-internationals",
        "home": {"name": "India"},
        "away": {"name": "Australia"},
        "start_time": "2026-09-14T00:00:00Z",
        "source_event_ids": {"cricsheet": "1482210"},
        "innings": innings,
        "sport_detail": {"result": "India won", "historical": True, "live": False},
    }
    best, n_ok, _protected = match_keepers(incoming, [row])
    assert n_ok == 1
    assert attach_family_id(best, "cricsheet", "1482210", incoming=incoming)
    extra = load_json(best.extra_json, {}) or {}
    assert extra["innings"][0]["runs"] == 178
    assert extra["sport_detail"]["result"] == "India won"


def test_click_tt_source_aliases_cover_registry_id():
    from collector.source_ids import source_id_aliases

    aliases = source_id_aliases("click-tt-remix")
    assert "click-tt" in aliases
    assert "click-tt-remix" in aliases


def test_dataproject_volleyball_identity_attach():
    start = datetime(2026, 1, 10, 18, 0, 0)
    row = _row(
        event_id="ninko-xw-plusliga",
        fingerprint="xw-plusliga",
        start_time=start,
        sport_id="volleyball",
        competition_id="plusliga",
        home="Aluron CMC Warta Zawiercie",
        away="Jastrzebski Wegiel",
    )
    incoming = {
        "sport": "volleyball",
        "competition_key": "plusliga",
        "home": {"name": "Aluron CMC Warta Zawiercie Volley"},
        "away": {"name": "Jastrzebski Wegiel"},
        "start_time": "2026-01-10T18:00:00Z",
        "source_event_ids": {"dataproject-web": "88421"},
        "score": {"home": 3, "away": 0},
        "periods": [
            {"label": 1, "home": 25, "away": 19},
            {"label": 2, "home": 25, "away": 21},
            {"label": 3, "home": 25, "away": 14},
        ],
    }
    best, n_ok, _protected = match_keepers(incoming, [row])
    assert n_ok == 1
    assert best is row
    changed = attach_family_id(best, "dataproject-web", "88421", incoming=incoming)
    assert changed
    extra = load_json(best.extra_json, {}) or {}
    assert extra["source_event_ids"]["dataproject-web"] == "88421"
    assert extra["periods"][0]["home"] == 25


def test_clicktt_meeting_identity():
    start = datetime(2026, 9, 12, 18, 0, 0)
    row = _row(
        event_id="ninko-xw-clicktt",
        fingerprint="xw-clicktt",
        start_time=start,
        sport_id="table-tennis",
        competition_id="germany-click-tt",
        home="Saarbrücken",
        away="Mühlhausen",
    )
    incoming = {
        "sport": "table-tennis",
        "competition_key": "germany-click-tt",
        "home": {"name": "1. FC Saarbrücken TT", "id": "101"},
        "away": {"name": "TTC Mühlhausen", "id": "202"},
        "start_time": "12.09.2026 18:00",
        "source_event_ids": {"click-tt-remix": "778899"},
        "score": {"home": 3, "away": 1},
    }
    best, n_ok, _protected = match_keepers(incoming, [row])
    assert n_ok == 1
    assert best is row


def test_squiggle_parser_accepts_string_and_amp_query():
    from collector.adapters_squiggle import _games_url, parse_squiggle_payload

    rows, meta = parse_squiggle_payload('{"games":[{"id":1,"hteam":"Pies","ateam":"Cats"}]}', "games")
    assert meta["shape"] == "dict"
    assert rows[0]["hteam"] == "Pies"
    html_rows, html_meta = parse_squiggle_payload("<html><body>blocked</body></html>", "games")
    assert html_rows == []
    assert html_meta.get("content_type_guess") == "text/html"
    assert "year=" in _games_url(2026, amp=True)
    assert ";year=" in _games_url(2026, amp=False)


def test_crosswalk_historical_ingest_under_persist_flag(monkeypatch):
    db = SessionLocal()
    ingested = {"n": 0}

    def fake_ingest(session, incoming, source_id):
        ingested["n"] += 1
        return True

    monkeypatch.setattr("collector.provider_crosswalk._ingest", fake_ingest)
    try:
        incoming = {
            "sport": "dota-2",
            "competition_key": "professional",
            "home": {"name": "Team Liquid"},
            "away": {"name": "Team Spirit"},
            "start_time": "2026-09-01T12:00:00Z",
            "source_event_ids": {"opendota": "888001122"},
        }
        stats = crosswalk_family(
            db,
            family="opendota",
            source_id="opendota",
            events=[incoming],
            persist_missing=True,
        )
        assert stats["ingested"] == 1
        assert stats["unmatched"] == 1
        assert ingested["n"] == 1
        stats_off = crosswalk_family(
            db,
            family="opendota",
            source_id="opendota",
            events=[incoming],
            persist_missing=False,
        )
        assert stats_off["ingested"] == 0
    finally:
        db.close()
