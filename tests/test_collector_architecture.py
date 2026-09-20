"""Generic collector architecture tests using deterministic mock adapters only."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import app
from collector.adapters import register_adapter, unregister_adapter
from collector.catalog import sync_identity_catalog
from collector.collect import run_cycle
from collector.limits import _hits, is_rate_limited, record_hit
from collector.models import (
    SportsCollectorJob,
    SportsCompetition,
    SportsEvent,
    SportsRawIngest,
    SportsSource,
    SportsSourceCompetition,
    SportsSourceHealth,
)
from collector.provider import NinkoCollectedSportsDataProvider
from collector.sources import source_collectable
from collector.test_support import DeterministicMockAdapter, mock_event
from collector.util import dump_json
from database import SessionLocal
from sports_registry.sports import SPORTS
from sports_registry.router import get_sports_data_provider


def _session():
    return SessionLocal()


def _cleanup_adapters(*keys):
    for key in keys:
        unregister_adapter(key)


def _source(db, source_id, adapter_key, **kwargs):
    row = SportsSource(
        source_id=source_id,
        display_name=kwargs.get("display_name", source_id),
        kind=kwargs.get("kind", "test"),
        enabled=kwargs.get("enabled", True),
        requires_credentials=kwargs.get("requires_credentials", False),
        licensed=kwargs.get("licensed", False),
        sports_supported_json=dump_json(kwargs.get("sports")) if kwargs.get("sports") else None,
        capabilities_json=dump_json(kwargs.get("capabilities")) if kwargs.get("capabilities") else None,
        adapter_key=adapter_key,
        attribution_required=kwargs.get("attribution_required", False),
        attribution_text=kwargs.get("attribution_text"),
        attribution_url=kwargs.get("attribution_url"),
        license_name=kwargs.get("license_name"),
        public_branding_required=kwargs.get("public_branding_required", False),
        rate_limit_per_minute=kwargs.get("rate_limit_per_minute"),
    )
    db.add(row)
    return row


def _competition(db, competition_id, sport_id, **kwargs):
    row = SportsCompetition(
        competition_id=competition_id,
        sport_id=sport_id,
        name=kwargs.get("name", competition_id),
        slug=competition_id,
        event_model=kwargs.get("event_model", "team_match"),
        series_id=kwargs.get("series_id"),
        game_id=kwargs.get("game_id"),
        parent_sport_id=kwargs.get("parent_sport_id"),
        country_id=kwargs.get("country_id"),
        country_based=kwargs.get("country_based", False),
        identity_only=False,
        active=True,
    )
    db.add(row)
    return row


def _map(db, competition_id, source_id, priority=10, **kwargs):
    row = SportsSourceCompetition(
        competition_id=competition_id,
        source_id=source_id,
        priority=priority,
        source_competition_id=kwargs.get("source_competition_id", competition_id),
        enabled=kwargs.get("enabled", True),
        is_licensed_fallback=kwargs.get("is_licensed_fallback", False),
        upstream_family=kwargs.get("upstream_family"),
        source_config_json=kwargs.get("source_config_json"),
    )
    db.add(row)
    return row


def test_all_catalog_sports_remain_first_class():
    slugs = {row["slug"] for row in SPORTS}
    assert len(slugs) == 41
    assert "football" in slugs
    assert "rocket-league" in slugs
    assert "horse-racing" in slugs


def test_provider_stays_disconnected_without_collected_events():
    provider = get_sports_data_provider()
    assert isinstance(provider, NinkoCollectedSportsDataProvider)
    assert provider.status()["connected"] is False
    assert provider.get_events() == []
    assert provider.get_competitions("football") == []
    with TestClient(app) as client:
        scores = client.get("/sports-data/scores").json()
        assert scores["connected"] is False
        assert scores["events"] == []
        credits = client.get("/sports-data/attribution").json()
        assert credits["items"] == []
        sources = client.get("/registry/data-sources").json()
        assert sources["items"] == []


def test_identity_catalog_does_not_create_events_or_coverage():
    db = _session()
    try:
        sync_identity_catalog(db)
        db.commit()
        assert db.query(SportsCompetition).count() > 0
        assert db.query(SportsEvent).count() == 0
        provider = NinkoCollectedSportsDataProvider()
        assert provider.status()["connected"] is False
        assert provider.get_competitions() == []
    finally:
        db.close()


def test_collect_then_read_does_not_call_adapters_from_api():
    adapter = DeterministicMockAdapter("mock-primary")
    adapter.events = [mock_event(id="m-live", status="live", score={"home": 1, "away": 0})]
    register_adapter("mock-primary", lambda source_id="mock-primary": adapter)
    db = _session()
    try:
        _source(db, "mock-primary", "mock-primary", attribution_required=True, attribution_text="Mock Data CC-BY")
        _competition(db, "mock-league", "football")
        _map(db, "mock-league", "mock-primary", 10)
        db.commit()
        summary = run_cycle(db, capabilities=["live_scores"])
        db.commit()
        assert summary["live_scores"] == 1
        calls_after_collect = len(adapter.calls)
        provider = NinkoCollectedSportsDataProvider()
        events = provider.get_events(sport="football")
        assert len(events) == 1
        assert events[0]["home"]["name"] == "Mock United"
        assert events[0].get("provider") is None
        assert len(adapter.calls) == calls_after_collect
        status = provider.status()
        assert status["connected"] is True
        credits = None
        with TestClient(app) as client:
            scores = client.get("/sports-data/scores").json()
            assert scores["connected"] is True
            assert scores["events"][0]["home"]["name"] == "Mock United"
            assert "Powered by" not in str(scores)
            credits = client.get("/sports-data/attribution").json()
            assert credits["items"][0]["text"] == "Mock Data CC-BY"
    finally:
        db.close()
        _cleanup_adapters("mock-primary")


def test_priority_merge_and_licensed_fallback():
    primary = DeterministicMockAdapter("src-a")
    primary.events = [
        mock_event(
            id="same",
            venue=None,
            score={"home": 2, "away": 1},
            status="live",
            retrieved_at="2026-09-17T20:35:00Z",
            observed_at="2026-09-17T20:35:00Z",
        )
    ]
    fallback = DeterministicMockAdapter("src-b")
    fallback.events = [
        mock_event(
            id="same",
            venue="Mock Park",
            score={"home": 9, "away": 9},
            status="live",
            retrieved_at="2026-09-17T20:32:00Z",
            observed_at="2026-09-17T20:32:00Z",
        )
    ]
    licensed = DeterministicMockAdapter("src-paid")
    licensed.events = [mock_event(id="same", venue="Paid Arena")]
    register_adapter("src-a", lambda source_id="src-a": primary)
    register_adapter("src-b", lambda source_id="src-b": fallback)
    register_adapter("src-paid", lambda source_id="src-paid": licensed)
    db = _session()
    try:
        _source(db, "src-a", "src-a")
        _source(db, "src-b", "src-b")
        _source(db, "src-paid", "src-paid", licensed=True, requires_credentials=True, enabled=True)
        _competition(db, "mock-league-2", "football")
        _map(db, "mock-league-2", "src-a", 10)
        _map(db, "mock-league-2", "src-b", 20)
        _map(db, "mock-league-2", "src-paid", 90, is_licensed_fallback=True)
        db.commit()
        assert source_collectable(db.query(SportsSource).filter_by(source_id="src-paid").one()) is False
        run_cycle(db, capabilities=["live_scores"])
        db.commit()
        event = db.query(SportsEvent).one()
        from collector.util import load_json

        score = load_json(event.score_json, {})
        assert score["home"] == 2
        assert event.venue == "Mock Park"
        assert event.primary_source_id == "src-a"
        assert licensed.calls == []
    finally:
        db.close()
        _cleanup_adapters("src-a", "src-b", "src-paid")


def test_restricted_primary_uses_fallback_not_bypass():
    blocked = DeterministicMockAdapter("blocked")
    blocked.restricted = True
    backup = DeterministicMockAdapter("backup")
    backup.events = [mock_event(id="fb1", status="scheduled")]
    register_adapter("blocked", lambda source_id="blocked": blocked)
    register_adapter("backup", lambda source_id="backup": backup)
    db = _session()
    try:
        _source(db, "blocked", "blocked")
        _source(db, "backup", "backup")
        _competition(db, "mock-league-3", "football")
        _map(db, "mock-league-3", "blocked", 10)
        _map(db, "mock-league-3", "backup", 20)
        db.commit()
        run_cycle(db, capabilities=["fixtures"])
        db.commit()
        events = db.query(SportsEvent).all()
        assert len(events) == 1
        ingest = db.query(SportsRawIngest).filter_by(source_id="blocked").first()
        assert ingest.restricted is True
        health = db.query(SportsSourceHealth).filter_by(source_id="blocked").one()
        assert health.status == "failed"
        assert health.last_http_status == 403
    finally:
        db.close()
        _cleanup_adapters("blocked", "backup")


def test_retry_then_success():
    flaky = DeterministicMockAdapter("flaky")
    flaky.fail_times = 2
    flaky.events = [mock_event(id="retry-1")]
    register_adapter("flaky", lambda source_id="flaky": flaky)
    db = _session()
    try:
        _source(db, "flaky", "flaky")
        _competition(db, "mock-league-4", "football")
        _map(db, "mock-league-4", "flaky", 10)
        db.commit()
        run_cycle(db, capabilities=["fixtures"], sleeper=lambda _delay: None)
        db.commit()
        assert db.query(SportsEvent).count() == 1
        assert flaky._failures_seen == 2
    finally:
        db.close()
        _cleanup_adapters("flaky")


def test_rate_limit_skips_source():
    _hits.clear()
    db = _session()
    try:
        _source(db, "limited", "limited", rate_limit_per_minute=1)
        db.commit()
        record_hit("limited")
        assert is_rate_limited(db, "limited") is True
    finally:
        db.close()
        _hits.clear()


def test_family_fields_for_motorsport_esports_racing():
    moto = DeterministicMockAdapter("moto")
    moto.events = [
        mock_event(
            id="race-1",
            home={"name": "Driver A"},
            away={"name": "Driver B"},
            series_id="formula-2",
            session_type="race",
            status="live",
        )
    ]
    esports = DeterministicMockAdapter("esports-src")
    esports.events = [
        mock_event(
            id="cs-1",
            home={"name": "Mock Squad"},
            away={"name": "Fixture Five"},
            game_id="counter-strike",
            status="live",
        )
    ]
    racing = DeterministicMockAdapter("racing-src")
    racing.events = [
        mock_event(
            id="hr-1",
            home={"name": "Mock Runner"},
            away={"name": ""},
            country_id="gb",
            meeting_id="mock-meeting",
            race_number=3,
            status="scheduled",
        )
    ]
    register_adapter("moto", lambda source_id="moto": moto)
    register_adapter("esports-src", lambda source_id="esports-src": esports)
    register_adapter("racing-src", lambda source_id="racing-src": racing)
    db = _session()
    try:
        _source(db, "moto", "moto")
        _source(db, "esports-src", "esports-src")
        _source(db, "racing-src", "racing-src")
        _competition(db, "formula-2", "motorsport", event_model="motorsport_race", series_id="formula-2")
        _competition(
            db,
            "mock-cs-tour",
            "counter-strike",
            event_model="esports_match",
            game_id="counter-strike",
            parent_sport_id="esports",
        )
        _competition(
            db,
            "gb-mock-racing",
            "horse-racing",
            event_model="racing",
            country_id="gb",
            country_based=True,
        )
        _map(db, "formula-2", "moto", 10)
        _map(db, "mock-cs-tour", "esports-src", 10)
        _map(db, "gb-mock-racing", "racing-src", 10)
        db.commit()
        run_cycle(db, capabilities=["live_scores", "fixtures"])
        db.commit()
        moto_row = db.query(SportsEvent).filter_by(competition_id="formula-2").one()
        assert moto_row.series_id == "formula-2"
        assert moto_row.event_family == "motorsport_race"
        cs_row = db.query(SportsEvent).filter_by(competition_id="mock-cs-tour").one()
        assert cs_row.game_id == "counter-strike"
        race_row = db.query(SportsEvent).filter_by(competition_id="gb-mock-racing").one()
        assert race_row.country_id == "gb"
        assert race_row.meeting_id == "mock-meeting"
    finally:
        db.close()
        _cleanup_adapters("moto", "esports-src", "racing-src")


def test_live_status_does_not_regress_from_lower_priority():
    live = DeterministicMockAdapter("live-src")
    live.events = [
        mock_event(
            id="st1",
            status="live",
            source_status="live",
            status_inferred=False,
            source_family="live-src",
            extra={"source_family": "live-src", "source_status": "live", "status_inferred": False},
            score={"home": 1, "away": 0},
            start_time=(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    ]
    stale = DeterministicMockAdapter("stale-src")
    stale.events = [
        mock_event(
            id="st1",
            status="scheduled",
            score={"home": None, "away": None},
            start_time=(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    ]
    register_adapter("live-src", lambda source_id="live-src": live)
    register_adapter("stale-src", lambda source_id="stale-src": stale)
    db = _session()
    try:
        _source(db, "live-src", "live-src")
        _source(db, "stale-src", "stale-src")
        _competition(db, "mock-league-5", "football")
        _map(db, "mock-league-5", "live-src", 10)
        _map(db, "mock-league-5", "stale-src", 50)
        db.commit()
        run_cycle(db, capabilities=["live_scores"])
        db.commit()
        event = db.query(SportsEvent).one()
        assert event.status == "live"
        assert event.live is True
    finally:
        db.close()
        _cleanup_adapters("live-src", "stale-src")


def test_deduplicates_on_fingerprint():
    first = DeterministicMockAdapter("dup-a")
    first.events = [mock_event(id="ext-1")]
    second = DeterministicMockAdapter("dup-b")
    second.events = [mock_event(id="ext-2")]
    register_adapter("dup-a", lambda source_id="dup-a": first)
    register_adapter("dup-b", lambda source_id="dup-b": second)
    db = _session()
    try:
        _source(db, "dup-a", "dup-a")
        _source(db, "dup-b", "dup-b")
        _competition(db, "mock-league-6", "football")
        _map(db, "mock-league-6", "dup-a", 10)
        _map(db, "mock-league-6", "dup-b", 20)
        db.commit()
        run_cycle(db, capabilities=["fixtures"])
        db.commit()
        assert db.query(SportsEvent).count() == 1
    finally:
        db.close()
        _cleanup_adapters("dup-a", "dup-b")


def test_no_production_adapters_are_registered():
    from collector.adapters import ADAPTERS
    from collector.schedule import due_capabilities
    from pathlib import Path

    assert ADAPTERS == {}
    procfile = Path(__file__).resolve().parents[1] / "Procfile"
    text = procfile.read_text(encoding="utf-8")
    assert "web:" in text
    assert "python -m bot.scheduler" in text
    assert "python -m collector.worker" in text
    assert not text.split("web:")[1].splitlines()[0].__contains__("collector.worker")
    db = _session()
    try:
        assert set(due_capabilities(db)) == {
            "live_scores",
            "fixtures",
            "results",
            "standings",
            "rankings",
        }
        assert db.query(SportsCollectorJob).count() == 0
    finally:
        db.close()


def test_access_restricted_exception_falls_back_without_retry_bypass():
    from collector.adapters import AccessRestricted, FetchRequest, FetchResult

    class RaiseRestricted:
        def __init__(self, source_id="raise-blocked"):
            self.source_id = source_id
            self.calls = []

        def fetch(self, request: FetchRequest) -> FetchResult:
            self.calls.append(request)
            raise AccessRestricted("captcha")

    blocked = RaiseRestricted()
    backup = DeterministicMockAdapter("raise-backup")
    backup.events = [mock_event(id="ok-1", status="scheduled")]
    register_adapter("raise-blocked", lambda source_id="raise-blocked": blocked)
    register_adapter("raise-backup", lambda source_id="raise-backup": backup)
    db = _session()
    try:
        _source(db, "raise-blocked", "raise-blocked")
        _source(db, "raise-backup", "raise-backup")
        _competition(db, "mock-league-7", "football")
        _map(db, "mock-league-7", "raise-blocked", 10)
        _map(db, "mock-league-7", "raise-backup", 20)
        db.commit()
        run_cycle(db, capabilities=["fixtures"], sleeper=lambda _delay: None)
        db.commit()
        assert len(blocked.calls) == 1
        assert db.query(SportsEvent).count() == 1
        ingest = db.query(SportsRawIngest).filter_by(source_id="raise-blocked").one()
        assert ingest.restricted is True
    finally:
        db.close()
        _cleanup_adapters("raise-blocked", "raise-backup")
