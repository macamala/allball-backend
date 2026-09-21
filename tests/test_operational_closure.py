from datetime import datetime, timedelta

from collector.adapters import FetchResult
from collector.backfill import JOB_KEY, run_bounded_backfill, run_if_due
from collector.cache import (
    cache_set,
    flush_list_invalidations,
    list_cache_key,
    note_list_invalidation,
)
from collector.fotmob_crosswalk import crosswalk_fotmob_ids
from collector.id_backfill import attach_observation_ids
from collector.lock import acquire_scheduler_lock, acquire_write_lock
from collector.merge import apply_row_fields
from collector.models import SportsCollectorJob, SportsEvent, SportsEventObservation, SportsReadCache
from collector.source_ids import merge_family_ids
from collector.util import dump_json, load_json
from collector.wta_rewrite import rewrite_wta_result_types
from database import SessionLocal
from tests.test_collector_architecture import _session


def test_backfill_requires_scheduler_owner():
    db = _session()
    try:
        assert run_if_due(db, owner="worker-b") is None
        acquire_scheduler_lock(db, owner="worker-a", ttl_seconds=120)
        db.commit()
        assert run_if_due(db, owner="worker-b") is None
    finally:
        db.close()


def test_pending_backfill_survives_restart(monkeypatch):
    calls = []

    def fake_cycle(db, **kwargs):
        calls.append(kwargs.get("competition_id"))
        return {"ok": True}

    monkeypatch.setattr("collector.backfill.run_cycle", fake_cycle)
    monkeypatch.setattr("collector.backfill.enrich_recent_detail", lambda db, **kwargs: {"attempted": 0, "filled": 0})
    monkeypatch.setattr("collector.backfill.register_production_adapters", lambda: None)
    monkeypatch.setattr("collector.fotmob_crosswalk.crosswalk_fotmob_ids", lambda db, **kwargs: {})
    monkeypatch.setattr("collector.fotmob_crosswalk.eligible_coverage", lambda db, **kwargs: {})
    monkeypatch.setattr("collector.wta_rewrite.rewrite_wta_result_types", lambda db: {})
    monkeypatch.setattr("collector.id_backfill.attach_observation_ids", lambda db, **kwargs: {})
    monkeypatch.setattr("collector.id_backfill.copy_complementary_ids", lambda db, **kwargs: 0)
    monkeypatch.setattr("collector.id_backfill.coverage_counts", lambda db, **kwargs: {})
    db = SessionLocal()
    try:
        job = SportsCollectorJob(
            job_key=JOB_KEY,
            last_status="running",
            last_error=dump_json(
                {
                    "state": "running",
                    "next_index": 1,
                    "comp_list": ["wta-tour", "italy-serie-a", "mlb"],
                }
            ),
        )
        db.add(job)
        db.commit()
        run_bounded_backfill(db)
        assert calls == ["italy-serie-a", "mlb"]
        saved = db.get(SportsCollectorJob, JOB_KEY)
        payload = load_json(saved.last_error, {}) or {}
        assert payload.get("state") == "done"
        assert saved.last_run_at is not None
    finally:
        db.close()


def test_standby_does_not_collect(monkeypatch):
    monkeypatch.setenv("RESULTS_SCHEDULER_ENABLED", "true")
    from collector.incremental import run_incremental_tick

    db_a = _session()
    db_b = _session()
    try:
        assert acquire_write_lock(db_a, owner="writer-a", ttl_seconds=120) is True
        db_a.commit()
        out = run_incremental_tick(db_b)
        assert out.get("reason") == "write_lock_held"
        assert out.get("stopped") is True
    finally:
        db_a.close()
        db_b.close()


def test_wta_walkover_canonical_rewrite(monkeypatch):
    start = datetime(2026, 9, 14, 18, 0, 0)
    db = SessionLocal()
    try:
        row = SportsEvent(
            event_id="ninko-evt-wo-test",
            sport_id="tennis",
            competition_id="wta-tour",
            event_family="individual_match",
            fingerprint="wo-test",
            start_time=start,
            status="finished",
            score_json=dump_json({"home": 2, "away": 0}),
            participants_json=dump_json({"home": {"name": "Player A"}, "away": {"name": "Player B"}}),
            extra_json=dump_json({"source_family": "wta-json", "source_event_ids": {"wta-json": "901-1"}}),
            display_eligible=True,
        )
        db.add(row)
        db.commit()

        def fake_fetch(self, request):
            return FetchResult(
                ok=True,
                http_status=200,
                events=[
                    {
                        "home": {"name": "Player A"},
                        "away": {"name": "Player B"},
                        "status": "finished",
                        "score": {"home": None, "away": None},
                        "start_time": start.isoformat() + "Z",
                        "source_family": "wta-json",
                        "source_event_id": "901-1",
                        "source_event_ids": {"wta-json": "901-1"},
                        "result_type": "walkover",
                        "walkover": True,
                        "competition": "wta-tour",
                        "competition_key": "wta-tour",
                        "sport": "tennis",
                    }
                ],
            )

        monkeypatch.setattr("collector.adapters_wta.WtaJsonAdapter.fetch", fake_fetch)
        out = rewrite_wta_result_types(db)
        db.commit()
        assert out["applied"] == 1
        extra = load_json(db.get(SportsEvent, "ninko-evt-wo-test").extra_json, {}) or {}
        assert extra.get("result_type") == "walkover"
        assert extra.get("walkover") is True
    finally:
        db.close()


def test_source_event_ids_union_on_canonical_merge():
    merged = merge_family_ids({"openligadb": "10"}, {"fotmob": "20"}, family="wta-json", source_event_id="30")
    assert merged == {"openligadb": "10", "fotmob": "20", "wta-json": "30"}
    again = merge_family_ids(merged, {"fotmob": "20"})
    assert again["fotmob"] == "20"
    assert len(again) == 3


def test_fotmob_id_survives_secondary_provider_collapse():
    db = SessionLocal()
    start = datetime(2026, 9, 20, 18, 0, 0)
    try:
        keeper = SportsEvent(
            event_id="ninko-id-fm-keep",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            fingerprint="fm-keep",
            start_time=start,
            display_eligible=True,
            status="finished",
            score_json=dump_json({"home": 1, "away": 0}),
            participants_json=dump_json({"home": {"name": "Inter"}, "away": {"name": "Milan"}}),
            extra_json=dump_json({"display_eligible": True, "source_family": "openligadb", "source_event_ids": {"openligadb": "99"}}),
        )
        loser = SportsEvent(
            event_id="ninko-id-fm-lose",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            fingerprint="fm-lose",
            start_time=start,
            display_eligible=True,
            status="finished",
            score_json=dump_json({"home": 1, "away": 0}),
            participants_json=dump_json({"home": {"name": "Inter"}, "away": {"name": "Milan"}}),
            extra_json=dump_json({"display_eligible": True, "source_family": "fotmob", "source_event_id": "48101234", "source_event_ids": {"fotmob": "48101234"}}),
        )
        db.add_all([keeper, loser])
        db.commit()
        from collector.canonical_collapse import _collapse_pair

        assert _collapse_pair(db, "ninko-id-fm-keep", "ninko-id-fm-lose") is True
        db.commit()
        extra = load_json(db.get(SportsEvent, "ninko-id-fm-keep").extra_json, {}) or {}
        ids = extra.get("source_event_ids") or {}
        assert ids.get("fotmob") == "48101234"
        assert ids.get("openligadb") == "99"
        assert db.get(SportsEvent, "ninko-id-fm-lose").canonical_event_id == "ninko-id-fm-keep"
    finally:
        db.close()


def test_observation_ids_follow_collapsed_loser():
    db = SessionLocal()
    start = datetime.utcnow()
    try:
        keeper = SportsEvent(
            event_id="ninko-id-obs-keep",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            fingerprint="obs-keep",
            start_time=start,
            extra_json=dump_json({"source_family": "openligadb"}),
        )
        loser = SportsEvent(
            event_id="ninko-id-obs-lose",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            fingerprint="obs-lose",
            start_time=start,
            canonical_event_id="ninko-id-obs-keep",
            extra_json=dump_json({"source_family": "fotmob"}),
        )
        db.add_all([keeper, loser])
        db.add(
            SportsEventObservation(
                event_id="ninko-id-obs-lose",
                source_id="fotmob",
                source_family="fotmob",
                source_event_id="555001",
                retrieved_at=datetime.utcnow(),
            )
        )
        db.commit()
        attach_observation_ids(db)
        extra = load_json(db.get(SportsEvent, "ninko-id-obs-keep").extra_json, {}) or {}
        assert extra.get("source_event_ids", {}).get("fotmob") == "555001"
    finally:
        db.close()


def test_fotmob_crosswalk_attaches_without_duplicate():
    start = datetime.utcnow().replace(microsecond=0)
    db = SessionLocal()
    try:
        db.add(
            SportsEvent(
                event_id="ninko-id-xw-1",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="xw-1",
                start_time=start,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Roma"}, "away": {"name": "Lazio"}}),
                extra_json=dump_json({"source_family": "openligadb"}),
            )
        )
        db.commit()
        before = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).count()
        payload = {
            "leagues": [
                {
                    "id": 55,
                    "name": "Serie A",
                    "matches": [
                        {
                            "id": "4810999",
                            "home": {"name": "Roma"},
                            "away": {"name": "Lazio"},
                            "status": {"finished": True, "utcTime": start.isoformat() + "Z"},
                        }
                    ],
                }
            ]
        }
        from collector.adapters_fotmob import _BOARD

        _BOARD.clear()
        result = crosswalk_fotmob_ids(db, getter=lambda url: FetchResult(ok=True, payload=payload))
        after = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).count()
        extra = load_json(db.get(SportsEvent, "ninko-id-xw-1").extra_json, {}) or {}
        assert extra.get("source_event_ids", {}).get("fotmob") == "4810999"
        assert after == before
        assert result["attached"] >= 1
    finally:
        db.close()


def test_fotmob_crosswalk_rejects_women_false_match():
    start = datetime.utcnow().replace(microsecond=0)
    db = SessionLocal()
    try:
        db.add(
            SportsEvent(
                event_id="ninko-id-xw-men",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="xw-men",
                start_time=start,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Roma Women"}, "away": {"name": "Lazio Women"}}),
                extra_json=dump_json({"source_family": "openligadb"}),
            )
        )
        db.commit()
        payload = {
            "leagues": [
                {
                    "id": 55,
                    "name": "Serie A",
                    "matches": [
                        {
                            "id": "4810888",
                            "home": {"name": "Roma"},
                            "away": {"name": "Lazio"},
                            "status": {"finished": True, "utcTime": start.isoformat() + "Z"},
                            "_league": {"id": 55},
                        }
                    ],
                }
            ]
        }
        from collector.adapters_fotmob import _BOARD

        _BOARD.clear()
        result = crosswalk_fotmob_ids(db, getter=lambda url: FetchResult(ok=True, payload=payload))
        extra = load_json(db.get(SportsEvent, "ninko-id-xw-men").extra_json, {}) or {}
        assert not extra.get("source_event_ids", {}).get("fotmob")
        assert result["attached"] == 0
    finally:
        db.close()


def test_scoreboard_write_invalidates_overlapping_list_only():
    db = SessionLocal()
    try:
        today = list_cache_key(None, None, None, "2026-09-21", "2026-09-21", True)
        week = list_cache_key(None, None, None, "2026-09-15", "2026-09-21", True)
        other = list_cache_key("tennis", None, None, "2026-09-10", "2026-09-10", True)
        cache_set(db, today, [{"id": "a"}], "events")
        cache_set(db, week, [{"id": "a"}], "events")
        cache_set(db, other, [{"id": "b"}], "events")
        db.commit()
        note_list_invalidation(db, sport="football", competition="italy-serie-a", start_time="2026-09-21T18:00:00Z")
        note_list_invalidation(db, sport="football", competition="italy-serie-a", start_time="2026-09-21T20:00:00Z")
        deleted = flush_list_invalidations(db)
        db.commit()
        keys = {row.cache_key for row in db.query(SportsReadCache).all()}
        assert today not in keys
        assert week not in keys
        assert other in keys
        assert deleted == 2
    finally:
        db.close()


def test_rich_detail_only_does_not_invalidate_list():
    db = SessionLocal()
    try:
        key = list_cache_key(None, None, None, "2026-09-21", "2026-09-21", True)
        cache_set(db, key, [{"id": "a"}], "events")
        db.commit()
        note_list_invalidation(
            db,
            sport="football",
            competition="italy-serie-a",
            start_time="2026-09-21T18:00:00Z",
            scoreboard_visible=False,
        )
        assert flush_list_invalidations(db) == 0
        assert db.query(SportsReadCache).filter_by(cache_key=key).first() is not None
    finally:
        db.close()


def test_batch_invalidation_coalesces(monkeypatch):
    db = SessionLocal()
    try:
        key = list_cache_key("football", None, None, "2026-09-21", "2026-09-21", True)
        cache_set(db, key, [{"id": "a"}], "events")
        db.commit()
        row = SportsEvent(
            event_id="ninko-id-cache-1",
            sport_id="football",
            competition_id="italy-serie-a",
            event_family="team_match",
            fingerprint="cache-1",
            start_time=datetime(2026, 9, 21, 18, 0, 0),
            status="scheduled",
            score_json=dump_json({"home": None, "away": None}),
            participants_json=dump_json({"home": {"name": "A"}, "away": {"name": "B"}}),
            extra_json=dump_json({}),
        )
        db.add(row)
        db.flush()
        for home in range(5):
            apply_row_fields(
                row,
                {
                    "status": "live",
                    "live": True,
                    "score": {"home": home, "away": 0},
                    "start_time": "2026-09-21T18:00:00Z",
                    "home": {"name": "A"},
                    "away": {"name": "B"},
                    "source_family": "fotmob",
                },
                "fotmob",
                True,
            )
        deleted = flush_list_invalidations(db)
        db.commit()
        assert deleted == 1
        assert db.query(SportsReadCache).filter_by(cache_key=key).first() is None
    finally:
        db.close()
