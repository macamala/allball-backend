from datetime import datetime, timedelta, timezone

from collector.adapters import register_adapter
from collector.collect import collect_competition
from collector.models import SportsCompetition, SportsEvent, SportsEventObservation
from collector.provider import NinkoCollectedSportsDataProvider
from collector.test_support import DeterministicMockAdapter, mock_event
from tests.test_collector_architecture import _cleanup_adapters, _competition, _map, _session, _source


def _run(db, competition_id, family, events, status="finished"):
    adapter = DeterministicMockAdapter(family)
    adapter.events = events
    register_adapter(family, lambda source_id=family, _adapter=adapter: _adapter)
    _source(db, family, family)
    _competition(db, competition_id, "football")
    _map(db, competition_id, family, 1)
    db.commit()
    collect_competition(
        db,
        db.query(SportsCompetition).filter_by(competition_id=competition_id).one(),
        "snapshot",
        sleeper=lambda _d: None,
    )
    db.commit()
    return adapter


def test_source_fixture_reaches_parser_observation_canonical_and_public_api():
    db = _session()
    try:
        events = [
            mock_event(
                id="pipe-1",
                competition="england-premier-league",
                home={"name": "Arsenal"},
                away={"name": "Chelsea"},
                status="finished",
                score={"home": 2, "away": 1},
                start_time="2026-09-20T14:00:00Z",
            )
        ]
        _run(db, "england-premier-league", "pipe-src", events)
        assert db.query(SportsEventObservation).count() == 1
        assert db.query(SportsEvent).filter_by(competition_id="england-premier-league").count() == 1
        public = NinkoCollectedSportsDataProvider().get_events(
            competition="england-premier-league",
            date_from="2026-09-20T00:00:00Z",
            date_to="2026-09-20T23:59:59Z",
        )
        assert len(public) == 1
        assert public[0]["status"] == "finished"
        assert public[0]["score"]["home"] == 2
        assert public[0]["score"]["away"] == 1
    finally:
        db.close()
        _cleanup_adapters("pipe-src")


def test_pipeline_statuses_scheduled_live_finished_postponed_cancelled():
    db = _session()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        rows = [
            mock_event(
                id="st-sched",
                competition="england-premier-league",
                home={"name": "Everton"},
                away={"name": "Fulham"},
                status="scheduled",
                score={"home": 0, "away": 0},
                start_time=(now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            mock_event(
                id="st-live",
                competition="england-premier-league",
                home={"name": "Liverpool"},
                away={"name": "Leeds"},
                status="live",
                score={"home": 1, "away": 0},
                start_time=(now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                source_status="live",
                observed_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                source_event_updated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            mock_event(
                id="st-ft",
                competition="england-premier-league",
                home={"name": "Brighton"},
                away={"name": "Brentford"},
                status="finished",
                score={"home": 0, "away": 0},
                start_time=(now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            mock_event(
                id="st-pp",
                competition="england-premier-league",
                home={"name": "Wolves"},
                away={"name": "Burnley"},
                status="postponed",
                start_time=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
            mock_event(
                id="st-can",
                competition="england-premier-league",
                home={"name": "Nottingham Forest"},
                away={"name": "West Ham"},
                status="cancelled",
                start_time=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        ]
        _run(db, "england-premier-league", "pipe-status", rows)
        stored = {row.status for row in db.query(SportsEvent).all()}
        assert "scheduled" in stored
        assert "live" in stored
        assert "finished" in stored
        assert "postponed" in stored
        assert "cancelled" in stored
        public = NinkoCollectedSportsDataProvider().get_events(
            competition="england-premier-league",
            date_from=(now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            date_to=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        by_status = {row["status"] for row in public}
        assert {"scheduled", "finished", "postponed", "cancelled"} <= by_status
        assert "live" in by_status or any(row.get("live") for row in public)
        finished = next(row for row in public if row["status"] == "finished")
        assert finished["score"]["home"] == 0
        scheduled = next(row for row in public if row["status"] == "scheduled")
        assert scheduled["score"]["home"] in (None, "")
        live_row = next((row for row in public if row["status"] == "live" or row.get("live")), None)
        assert live_row is not None
        assert live_row["score"]["home"] == 1
    finally:
        db.close()
        _cleanup_adapters("pipe-status")


def test_public_api_uses_utc_instant_not_local_day_identity():
    start = datetime(2026, 9, 19, 23, 30, 0)
    db = _session()
    try:
        events = [
            mock_event(
                id="tz-1",
                competition="italy-serie-a",
                home={"name": "Bologna"},
                away={"name": "Torino"},
                status="finished",
                score={"home": 1, "away": 0},
                start_time="2026-09-19T23:30:00Z",
            )
        ]
        adapter = DeterministicMockAdapter("pipe-tz")
        adapter.events = events
        register_adapter("pipe-tz", lambda source_id="pipe-tz": adapter)
        _source(db, "pipe-tz", "pipe-tz")
        _competition(db, "italy-serie-a", "football")
        _map(db, "italy-serie-a", "pipe-tz", 1)
        db.commit()
        collect_competition(
            db,
            db.query(SportsCompetition).filter_by(competition_id="italy-serie-a").one(),
            "snapshot",
            sleeper=lambda _d: None,
        )
        db.commit()
        assert db.query(SportsEvent).filter_by(competition_id="italy-serie-a").count() == 1
        sydney_day = NinkoCollectedSportsDataProvider().get_events(
            competition="italy-serie-a",
            date_from="2026-09-19T14:00:00Z",
            date_to="2026-09-20T13:59:59Z",
        )
        assert len(sydney_day) == 1
        utc_next = NinkoCollectedSportsDataProvider().get_events(
            competition="italy-serie-a",
            date_from="2026-09-20T00:00:00Z",
            date_to="2026-09-20T23:59:59Z",
        )
        assert utc_next == []
        _ = start
    finally:
        db.close()
        _cleanup_adapters("pipe-tz")
