from datetime import datetime

from collector.adapters_feeds import EuroleagueLiveAdapter
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
