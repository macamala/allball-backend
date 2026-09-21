"""Collector worker process. Not started by the API or the news scheduler.

Railway: dedicated `results-worker` service. Web must not ingest results.
Scheduler and canonical writes are fail-closed unless env flags are set.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from database import SessionLocal, engine, ensure_schema
from models import Base
import collector.models  # noqa: F401
from collector.collect import run_cycle
from collector.incremental import live_idle_seconds, run_incremental_tick
from collector.family_catalog import POLL_SECONDS
from collector.flags import (
    collection_enabled,
    flags_payload,
    keepalive_enabled,
    run_once_requested,
    scheduler_enabled,
    writes_enabled,
)
from collector.lock import (
    acquire_scheduler_lock,
    heartbeat_scheduler_lock,
    owner_identity,
    postgres_advisory_unlock,
    postgres_try_advisory,
    release_scheduler_lock,
)

STANDBY_SLEEP_SECONDS = 45
_standby_logged = False
from collector.matrix_guard import assert_frozen_matrix
from collector.models import SportsSource
from collector.production import bootstrap_registry, register_production_adapters
from collector.schedule import due_capabilities
from collector.sources import source_collectable

logger = logging.getLogger(__name__)


def enabled_source_count(db) -> int:
    return sum(1 for row in db.query(SportsSource).all() if source_collectable(row))


def _idle(interval: int) -> None:
    logger.info(
        "Results worker idle owner=%s flags=%s",
        owner_identity(),
        flags_payload(),
    )
    time.sleep(max(15, interval))


def main(once: bool = True, interval_seconds: Optional[int] = None) -> None:
    logging.basicConfig(level=logging.INFO)
    matrix = assert_frozen_matrix()
    logger.info("Frozen matrix ok checksum=%s count=%s", matrix["checksum"], matrix["competition_count"])
    register_production_adapters()
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    from collector.schema_tune import ensure_event_list_indexes

    ensure_event_list_indexes(engine)
    interval = interval_seconds
    if interval is None:
        if scheduler_enabled():
            interval = int(os.getenv("COLLECTOR_INTERVAL_SECONDS") or 20)
        else:
            interval = int(os.getenv("COLLECTOR_INTERVAL_SECONDS") or POLL_SECONDS["NEAR_LIVE"])
    owner = owner_identity()
    while True:
        if not collection_enabled() or (not scheduler_enabled() and not run_once_requested()):
            if once:
                logger.info("Results worker one-shot exit. %s", flags_payload())
                return
            _idle(interval)
            continue
        db = SessionLocal()
        held = False
        advisory = None
        try:
            global _standby_logged
            held = acquire_scheduler_lock(db, owner=owner)
            if not held:
                if not _standby_logged:
                    logger.info("Results worker is standby; backing off until the scheduler lease is free")
                    _standby_logged = True
                db.commit()
                if once:
                    return
                time.sleep(STANDBY_SLEEP_SECONDS)
                continue
            _standby_logged = False
            advisory = postgres_try_advisory(db)
            if advisory is False:
                logger.info("Results worker is standby; postgres advisory lock is held by another owner")
                release_scheduler_lock(db, owner=owner)
                db.commit()
                held = False
                if once:
                    return
                time.sleep(STANDBY_SLEEP_SECONDS)
                continue
            if not db.info.get("registry_bootstrapped"):
                bootstrap_registry(db)
                db.commit()
                db.info["registry_bootstrapped"] = True
            from collector.watch_set import rebuild_watch_set

            rebuild_watch_set(db)
            db.commit()
            try:
                from collector.backfill import run_if_due

                def _pulse() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                backfill = run_if_due(db, owner=owner, heartbeat=_pulse)
                if backfill:
                    logger.info("Bounded backfill %s", backfill.get("enrich"))
            except Exception:
                logger.exception("Bounded backfill failed")
            try:
                from collector.fotmob_crosswalk import run_date_boards_if_due

                def _pulse_boards() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                boards = run_date_boards_if_due(db, owner=owner, heartbeat=_pulse_boards)
                if boards:
                    logger.info(
                        "FotMob date boards %s",
                        {k: boards.get(k) for k in ("attached", "upstream_eligible", "unmatched", "ambiguous")},
                    )
            except Exception:
                logger.exception("FotMob date-board backfill failed")
            try:
                from collector.provider_crosswalk import run_provider_id_attach_if_due

                attached = run_provider_id_attach_if_due(db, owner=owner)
                if attached:
                    logger.info(
                        "Provider ID attach %s",
                        {key: val for key, val in (attached.get("families") or {}).items()},
                    )
            except Exception:
                logger.exception("Provider ID attach failed")
            if not collection_enabled():
                logger.info("Collection disabled; holding lock idle")
            elif enabled_source_count(db) == 0:
                logger.info("Collector idle: no collectable sources are enabled.")
            elif scheduler_enabled():
                summary = run_incremental_tick(db)
                db.commit()
                logger.info("Incremental tick %s", {k: summary.get(k) for k in (
                    "due_jobs",
                    "selected_jobs",
                    "oldest_due_age_s",
                    "families_selected",
                    "sports_selected",
                    "events_changed",
                    "periods_persisted",
                    "incidents_persisted",
                    "runners_persisted",
                    "best_of_persisted",
                    "enrichment_promoted",
                    "collapse",
                    "jobs_starved",
                    "live_jobs_due",
                    "live_jobs_selected",
                    "live_families_served",
                    "background_jobs_due",
                    "background_jobs_starved",
                    "live_families_waiting",
                    "live_families_starved",
                    "oldest_live_fetch_age_seconds",
                    "oldest_background_fetch_age_seconds",
                    "physical_requests",
                    "http",
                    "espn",
                    "wta",
                    "duration_s",
                    "enrichment",
                )})
            else:
                caps = due_capabilities(db)
                summary = run_cycle(
                    db,
                    capabilities=caps or ["fixtures"],
                    force=False,
                )
                db.commit()
                logger.info(
                    "Collector cycle wrote=%s writes_enabled=%s summary=%s",
                    summary,
                    writes_enabled(),
                    summary,
                )
            heartbeat_scheduler_lock(db, owner=owner)
            db.commit()
        except Exception:
            logger.exception("Collector cycle failed")
            db.rollback()
        finally:
            if advisory:
                try:
                    postgres_advisory_unlock(db)
                except Exception:
                    pass
            if held and (once or not scheduler_enabled()):
                try:
                    release_scheduler_lock(db, owner=owner)
                    db.commit()
                except Exception:
                    db.rollback()
            db.close()
        if once:
            return
        if scheduler_enabled():
            time.sleep(live_idle_seconds(interval))
        else:
            time.sleep(max(15, interval))


if __name__ == "__main__":
    staging = os.getenv("RESULTS_STAGING_CMD", "").strip()
    if staging:
        from collector.staging import main as staging_main

        raise SystemExit(staging_main([staging]))
    once = (not keepalive_enabled()) or run_once_requested()
    main(once=once)
