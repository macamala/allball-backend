"""Complementary A/B merge, aliases, recovery, and isolation."""

from collector.adapters import FetchRequest, register_adapter
from collector.adapters_generic import GenericHttpAdapter
from collector.adapters_omega import parse_omega_xml
from collector.collect import collect_competition
from collector.merge import merge_event_fields
from collector.models import SportsCompetition, SportsEvent, SportsSourceHealth
from collector.registry import build_runtime_registry
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def test_omega_xml_parses_home_away_score():
    xml = """
    <Results>
      <Game Id="1" Home="ESP" Away="HUN" HomeScore="15" AwayScore="13" Date="2025-07-24"/>
    </Results>
    """
    events = parse_omega_xml(xml, "world-aquatics-events")
    assert events
    assert events[0]["home"]["name"] == "ESP"
    assert events[0]["score"]["home"] == 15


def test_tournamentsoftware_follows_tournament_id():
    from collector.adapters import FetchResult

    class Getter:
        def __init__(self):
            self.urls = []

        def __call__(self, url, timeout=None):
            self.urls.append(url)
            html = "<table><tr><td>Viktor Axelsen</td><td>21-19</td><td>Kodai Naraoka</td></tr></table>"
            return FetchResult(ok=True, http_status=200, payload=html)

    getter = Getter()
    adapter = GenericHttpAdapter(text_getter=getter)
    listing = '<html><a href="/sport/tournament?id=ABCDEF12-3456-7890-ABCD-EF1234567890">Open</a></html>'
    events = adapter._follow_tournament_ids(
        listing,
        "https://www.tournamentsoftware.com/sport/tournaments",
        FetchRequest(capability="snapshot", competition_id="bwf-and-national-events", upstream_family="tournamentsoftware"),
        set(),
    )
    assert any("matches?id=" in url for url in getter.urls)
    assert events
    assert events[0]["home"]["name"]


def test_venue_fill_and_finished_score_from_b():
    current = mock_event(status="scheduled", venue=None, score={"home": None, "away": None})
    incoming = mock_event(
        status="finished",
        venue="Mock Park",
        score={"home": 2, "away": 1},
        retrieved_at="2026-09-17T18:00:00Z",
    )
    merged = merge_event_fields(
        {**current, "retrieved_at": "2026-09-17T12:00:00Z", "field_sources": {}},
        incoming,
        incoming_is_higher_priority=False,
        incoming_source_id="src-b",
    )
    assert merged["venue"] == "Mock Park"
    assert merged["score"]["home"] == 2
    assert merged["status"] == "finished"
    assert merged["field_sources"]["venue"] == "src-b"
    assert merged["field_sources"]["score"] == "src-b"


def test_stale_finished_cannot_overwrite_newer():
    current = mock_event(
        status="finished",
        score={"home": 2, "away": 1},
        retrieved_at="2026-09-17T20:00:00Z",
    )
    incoming = mock_event(
        status="finished",
        score={"home": 9, "away": 9},
        retrieved_at="2026-09-17T10:00:00Z",
    )
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=False,
        incoming_source_id="src-b",
    )
    assert merged["score"]["home"] == 2


def test_live_vs_live_fresher_score_wins():
    current = mock_event(
        status="live",
        score={"home": 1, "away": 0},
        retrieved_at="2026-09-17T20:31:00Z",
        observed_at="2026-09-17T20:31:00Z",
        source_event_updated_at="2026-09-17T20:31:00Z",
    )
    incoming = mock_event(
        status="live",
        venue="Mock Park",
        score={"home": 1, "away": 1},
        retrieved_at="2026-09-17T20:34:00Z",
        observed_at="2026-09-17T20:34:00Z",
        source_event_updated_at="2026-09-17T20:34:00Z",
    )
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=False,
        incoming_source_id="src-b",
    )
    assert merged["score"]["away"] == 1
    assert merged["venue"] == "Mock Park"


def test_older_live_does_not_replace_newer_live():
    current = mock_event(
        status="live",
        score={"home": 1, "away": 0},
        retrieved_at="2026-09-17T20:35:00Z",
        observed_at="2026-09-17T20:35:00Z",
        source_event_updated_at="2026-09-17T20:35:00Z",
    )
    incoming = mock_event(
        status="live",
        venue="Mock Park",
        score={"home": 1, "away": 1},
        retrieved_at="2026-09-17T20:32:00Z",
        observed_at="2026-09-17T20:32:00Z",
        source_event_updated_at="2026-09-17T20:32:00Z",
    )
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=False,
        incoming_source_id="src-b",
    )
    assert merged["score"]["away"] == 0
    assert merged["venue"] == "Mock Park"


def test_stale_finished_cannot_override_newer_live():
    current = mock_event(
        status="live",
        score={"home": 1, "away": 0},
        retrieved_at="2026-09-17T20:40:00Z",
        observed_at="2026-09-17T20:40:00Z",
        source_event_updated_at="2026-09-17T20:40:00Z",
    )
    incoming = mock_event(
        status="finished",
        score={"home": 2, "away": 1},
        retrieved_at="2026-09-17T20:10:00Z",
        observed_at="2026-09-17T20:10:00Z",
        source_event_updated_at="2026-09-17T20:10:00Z",
    )
    merged = merge_event_fields(
        current,
        incoming,
        incoming_is_higher_priority=True,
        incoming_source_id="src-a",
    )
    assert merged["status"] == "live"
    assert merged["score"]["home"] == 1


def test_alias_merge_one_canonical_event():
    primary = DeterministicMockAdapter("alias-a")
    primary.events = [
        mock_event(
            id="ucl-1",
            home={"name": "Man Utd"},
            away={"name": "PSG"},
            start_time="2026-09-18T19:00:00Z",
            competition="alias-ucl",
        )
    ]
    fallback = DeterministicMockAdapter("alias-b")
    fallback.events = [
        mock_event(
            id="ucl-1-b",
            home={"name": "Manchester United"},
            away={"name": "Paris Saint Germain"},
            start_time="2026-09-18T19:05:00Z",
            venue="Old Trafford",
            competition="alias-ucl",
        )
    ]
    register_adapter("alias-a", lambda source_id="alias-a": primary)
    register_adapter("alias-b", lambda source_id="alias-b": fallback)
    db = _session()
    try:
        _source(db, "alias-a", "alias-a")
        _source(db, "alias-b", "alias-b")
        _competition(db, "alias-ucl", "football")
        _map(db, "alias-ucl", "alias-a", 1)
        _map(db, "alias-ucl", "alias-b", 2)
        db.commit()
        collect_competition(
            db,
            db.query(SportsCompetition).filter_by(competition_id="alias-ucl").one(),
            "snapshot",
            sleeper=lambda _d: None,
        )
        db.commit()
        rows = db.query(SportsEvent).filter_by(competition_id="alias-ucl").all()
        assert len(rows) == 1
        assert rows[0].venue == "Old Trafford"
    finally:
        db.close()
        _cleanup_adapters("alias-a", "alias-b")


def test_failover_b_then_a_and_recovery():
    a = DeterministicMockAdapter("rec-a")
    a.fail_times = 1
    a.events = [mock_event(id="rec-1", competition="rec-league", home={"name": "Alpha"}, away={"name": "Beta"})]
    b = DeterministicMockAdapter("rec-b")
    b.events = [mock_event(id="rec-1b", competition="rec-league", home={"name": "Alpha"}, away={"name": "Beta"}, venue="Park")]
    register_adapter("rec-a", lambda source_id="rec-a": a)
    register_adapter("rec-b", lambda source_id="rec-b": b)
    db = _session()
    try:
        _source(db, "rec-a", "rec-a")
        _source(db, "rec-b", "rec-b")
        _competition(db, "rec-league", "football")
        _map(db, "rec-league", "rec-a", 1)
        _map(db, "rec-league", "rec-b", 2)
        db.commit()
        collect_competition(db, db.query(SportsCompetition).filter_by(competition_id="rec-league").one(), "snapshot", sleeper=lambda _d: None)
        db.commit()
        assert db.query(SportsEvent).filter_by(competition_id="rec-league").count() == 1
        collect_competition(db, db.query(SportsCompetition).filter_by(competition_id="rec-league").one(), "snapshot", sleeper=lambda _d: None)
        db.commit()
        health = db.query(SportsSourceHealth).filter_by(source_id="rec-a").one()
        assert health.status in {"healthy", "empty"}
        assert health.consecutive_failures == 0
    finally:
        db.close()
        _cleanup_adapters("rec-a", "rec-b")


def test_unrelated_competition_does_not_leak():
    a = DeterministicMockAdapter("iso-a")
    a.events = [mock_event(id="iso-1", competition="iso-one", home={"name": "One FC"}, away={"name": "Two FC"})]
    b = DeterministicMockAdapter("iso-b")
    b.events = [mock_event(id="iso-2", competition="iso-two", home={"name": "Three FC"}, away={"name": "Four FC"})]
    register_adapter("iso-a", lambda source_id="iso-a": a)
    register_adapter("iso-b", lambda source_id="iso-b": b)
    db = _session()
    try:
        _source(db, "iso-a", "iso-a")
        _source(db, "iso-b", "iso-b")
        _competition(db, "iso-one", "football")
        _competition(db, "iso-two", "football")
        _map(db, "iso-one", "iso-a", 1)
        _map(db, "iso-two", "iso-b", 1)
        db.commit()
        collect_competition(db, db.query(SportsCompetition).filter_by(competition_id="iso-one").one(), "snapshot", sleeper=lambda _d: None)
        collect_competition(db, db.query(SportsCompetition).filter_by(competition_id="iso-two").one(), "snapshot", sleeper=lambda _d: None)
        db.commit()
        one = db.query(SportsEvent).filter_by(competition_id="iso-one").all()
        two = db.query(SportsEvent).filter_by(competition_id="iso-two").all()
        assert len(one) == 1
        assert len(two) == 1
        assert one[0].event_id != two[0].event_id
    finally:
        db.close()
        _cleanup_adapters("iso-a", "iso-b")


def test_opendota_enabled_for_professional():
    runtime = build_runtime_registry()
    enabled = [
        row
        for row in runtime["mappings"]
        if row.get("source_family") == "opendota" and row.get("enabled")
    ]
    assert enabled
    assert any(row.get("competition_id") == "professional" for row in enabled)
