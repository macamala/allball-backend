import re
from datetime import datetime, timedelta

from sqlalchemy import event

from collector.adapters import FetchResult
from collector.adapters_fotmob import _BOARD, _dates, board_dates
from collector.cache import cache_set, list_cache_key
from collector.competition_presentation import metadata_for
from collector.fotmob_crosswalk import (
    DATE_BOARD_JOB,
    crosswalk_fotmob_ids,
    eligible_coverage,
    run_date_board_backfill,
)
from collector.lock import acquire_scheduler_lock
from collector.models import SportsCollectorJob, SportsEvent, SportsReadCache
from collector.provider import NinkoCollectedSportsDataProvider
from collector.util import dump_json, load_json
from database import SessionLocal, engine


def _serie_payload(match_id, home, away, utc_time, league_id=55):
    return {
        "leagues": [
            {
                "id": league_id,
                "name": "Serie A",
                "matches": [
                    {
                        "id": match_id,
                        "home": {"name": home},
                        "away": {"name": away},
                        "status": {"finished": True, "utcTime": utc_time},
                    }
                ],
            }
        ]
    }


def test_live_fotmob_dates_stay_narrow():
    assert _dates() == board_dates(past_days=3, future_days=1)
    assert len(_dates()) == 5
    assert len(board_dates(past_days=7, future_days=1)) == 9


def test_list_query_does_not_select_rich_extra_json():
    db = SessionLocal()
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        blob = dump_json({"timeline": ["x"] * 200, "statistics": {"a": 1}, "lineups": {"home": []}, "noise": "z" * 5000})
        db.add(
            SportsEvent(
                event_id="ninko-evt-lean-1",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                status="finished",
                start_time=datetime(2026, 9, 21, 12, 0, 0),
                display_eligible=True,
                extra_json=blob,
                list_extra_json=dump_json({"live_class": "FT"}),
                participants_json=dump_json({"home": {"name": "A"}, "away": {"name": "B"}}),
                score_json=dump_json({"home": 1, "away": 0}),
            )
        )
        db.commit()
        rows = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            date_from="2026-09-21T00:00:00Z",
            date_to="2026-09-21T23:59:59Z",
        )
        assert len(rows) == 1
        assert rows[0].get("timeline") in (None, [], {})
        assert rows[0].get("statistics") in (None, [], {})
        assert rows[0].get("lineups") in (None, [], {})
        selects = [item.lower() for item in statements if item.lstrip().lower().startswith("select") and "sports_events" in item.lower()]
        joined = " ".join(selects)
        assert selects
        assert not re.search(r"(?<![a-z_])extra_json", joined)
        assert "contributing_sources_json" not in joined
    finally:
        event.remove(engine, "before_cursor_execute", before)
        db.close()


def test_seven_day_list_keeps_valid_ids_without_n_plus_one():
    db = SessionLocal()
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        start = datetime(2026, 9, 14, 15, 0, 0)
        for index in range(24):
            db.add(
                SportsEvent(
                    event_id=f"ninko-evt-week-lean-{index}",
                    sport_id="football",
                    competition_id="italy-serie-a",
                    event_family="team_match",
                    status="finished",
                    start_time=start + timedelta(hours=index * 6),
                    display_eligible=True,
                    extra_json=dump_json({"timeline": [{"n": index}] * 80}),
                    list_extra_json=dump_json({"live_class": "FT"}),
                    participants_json=dump_json({"home": {"name": f"H{index}"}, "away": {"name": f"A{index}"}}),
                    score_json=dump_json({"home": 1, "away": 0}),
                )
            )
        db.commit()
        metadata_for.cache_clear()
        before_meta = metadata_for.cache_info()
        statements.clear()
        rows = NinkoCollectedSportsDataProvider().get_events(
            sport="football",
            date_from="2026-09-14T00:00:00Z",
            date_to="2026-09-21T23:59:59Z",
        )
        after_meta = metadata_for.cache_info()
        assert len(rows) == 24
        assert {row["id"] for row in rows} == {f"ninko-evt-week-lean-{i}" for i in range(24)}
        assert after_meta.misses - before_meta.misses <= 3
        assert len(statements) < 20
    finally:
        event.remove(engine, "before_cursor_execute", before)
        db.close()


def test_fotmob_multi_date_board_attaches_ids():
    db = SessionLocal()
    try:
        day_a = datetime(2026, 9, 14, 18, 0, 0)
        day_b = datetime(2026, 9, 15, 18, 0, 0)
        db.add(
            SportsEvent(
                event_id="ninko-id-date-a",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="date-a",
                start_time=day_a,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Roma"}, "away": {"name": "Lazio"}}),
                extra_json=dump_json({"source_family": "openligadb"}),
            )
        )
        db.add(
            SportsEvent(
                event_id="ninko-id-date-b",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="date-b",
                start_time=day_b,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Inter"}, "away": {"name": "Milan"}}),
                extra_json=dump_json({"source_family": "openligadb"}),
            )
        )
        db.commit()
        before = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).count()

        def getter(url):
            if "20260914" in url:
                return FetchResult(ok=True, payload=_serie_payload("4811001", "Roma", "Lazio", day_a.isoformat() + "Z"))
            if "20260915" in url:
                return FetchResult(ok=True, payload=_serie_payload("4811002", "Inter", "Milan", day_b.isoformat() + "Z"))
            return FetchResult(ok=True, payload={"leagues": []})

        _BOARD.clear()
        result = crosswalk_fotmob_ids(db, getter=getter, dates=["20260914", "20260915"])
        extra_a = load_json(db.get(SportsEvent, "ninko-id-date-a").extra_json, {}) or {}
        extra_b = load_json(db.get(SportsEvent, "ninko-id-date-b").extra_json, {}) or {}
        assert extra_a.get("source_event_ids", {}).get("fotmob") == "4811001"
        assert extra_b.get("source_event_ids", {}).get("fotmob") == "4811002"
        assert result["attached"] == 2
        assert result["upstream_eligible"] == 2
        assert result["ambiguous"] == 0
        assert db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).count() == before
        coverage = eligible_coverage(db, getter=getter, dates=["20260914", "20260915"])
        assert coverage["coverage_pct"] == 100.0
        assert coverage["canonical_with_fotmob_id"] == 2
    finally:
        db.close()


def test_fotmob_ambiguous_match_is_rejected():
    start = datetime.utcnow().replace(microsecond=0)
    db = SessionLocal()
    try:
        for suffix in ("a", "b"):
            db.add(
                SportsEvent(
                    event_id=f"ninko-id-amb-{suffix}",
                    sport_id="football",
                    competition_id="italy-serie-a",
                    event_family="team_match",
                    fingerprint=f"amb-{suffix}",
                    start_time=start,
                    display_eligible=True,
                    participants_json=dump_json({"home": {"name": "Roma"}, "away": {"name": "Lazio"}}),
                    extra_json=dump_json({"source_family": "openligadb"}),
                )
            )
        db.commit()
        payload = _serie_payload("4811777", "Roma", "Lazio", start.isoformat() + "Z")
        _BOARD.clear()
        result = crosswalk_fotmob_ids(db, getter=lambda url: FetchResult(ok=True, payload=payload), dates=["20260921"])
        assert result["ambiguous"] == 1
        assert result["attached"] == 0
        for suffix in ("a", "b"):
            extra = load_json(db.get(SportsEvent, f"ninko-id-amb-{suffix}").extra_json, {}) or {}
            assert not extra.get("source_event_ids", {}).get("fotmob")
    finally:
        db.close()


def test_fotmob_date_board_checkpoint_is_restart_safe():
    db = SessionLocal()
    try:
        acquire_scheduler_lock(db, owner="worker-a", ttl_seconds=120)
        start = datetime.utcnow().replace(microsecond=0)
        db.add(
            SportsEvent(
                event_id="ninko-id-ckpt",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="ckpt-1",
                start_time=start,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Napoli"}, "away": {"name": "Juventus"}}),
                extra_json=dump_json({}),
            )
        )
        db.add(
            SportsCollectorJob(
                job_key=DATE_BOARD_JOB,
                last_status="running",
                last_error=dump_json(
                    {
                        "state": "running",
                        "dates": ["20260914", "20260921"],
                        "next_index": 1,
                        "upstream_total": 0,
                        "attached": 0,
                    }
                ),
            )
        )
        db.commit()
        urls = []

        def getter(url):
            urls.append(url)
            return FetchResult(
                ok=True,
                payload=_serie_payload("4811888", "Napoli", "Juventus", start.isoformat() + "Z"),
            )

        result = run_date_board_backfill(db, getter=getter, owner="worker-a")
        assert result is not None
        assert sum("20260914" in url for url in urls) <= 1
        assert any("20260921" in url for url in urls)
        extra = load_json(db.get(SportsEvent, "ninko-id-ckpt").extra_json, {}) or {}
        assert extra.get("source_event_ids", {}).get("fotmob") == "4811888"
        saved = db.get(SportsCollectorJob, DATE_BOARD_JOB)
        payload = load_json(saved.last_error, {}) or {}
        assert payload.get("state") == "done"
        assert payload.get("next_index") == 2
    finally:
        db.close()


def test_fotmob_id_attach_does_not_flush_list_cache():
    db = SessionLocal()
    try:
        start = datetime.utcnow().replace(microsecond=0)
        key = list_cache_key(None, None, None, "2026-09-15", "2026-09-21", True)
        cache_set(db, key, [{"id": "cached"}], "upcoming_fixtures")
        db.add(
            SportsEvent(
                event_id="ninko-id-cache-keep",
                sport_id="football",
                competition_id="italy-serie-a",
                event_family="team_match",
                fingerprint="cache-keep",
                start_time=start,
                display_eligible=True,
                participants_json=dump_json({"home": {"name": "Roma"}, "away": {"name": "Lazio"}}),
                extra_json=dump_json({}),
            )
        )
        db.commit()
        payload = _serie_payload("4811999", "Roma", "Lazio", start.isoformat() + "Z")
        _BOARD.clear()
        crosswalk_fotmob_ids(db, getter=lambda url: FetchResult(ok=True, payload=payload), dates=["20260921"])
        db.commit()
        assert db.query(SportsReadCache).filter_by(cache_key=key).first() is not None
    finally:
        db.close()


def test_date_board_backfill_requires_owner():
    db = SessionLocal()
    try:
        assert run_date_board_backfill(db, owner="worker-b") is None
        acquire_scheduler_lock(db, owner="worker-a", ttl_seconds=120)
        db.commit()
        assert run_date_board_backfill(db, owner="worker-b") is None
    finally:
        db.close()
