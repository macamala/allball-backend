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
RUN_ONCE_LOCK_RETRIES = 3
_standby_logged = False
_creators_collected = False
_breadth_logged_at = 0.0
_fifa_identity_reconciled = False


def _collect_official_creators(db) -> None:
    """Create UFC bouts and World Athletics discipline events once per process."""
    global _creators_collected
    if _creators_collected or not writes_enabled():
        return
    _creators_collected = True
    from collector.adapters import FetchRequest
    from collector.adapters_final import UfcOfficialAdapter
    from collector.collect import _consume_result, collect_competition
    from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition

    ufc = db.query(SportsCompetition).filter_by(competition_id="ufc").first()
    ufc_source = db.query(SportsSource).filter_by(upstream_family="ufc-web").first()
    ufc_mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id="ufc", source_id=ufc_source.source_id)
        .first()
        if ufc_source is not None
        else None
    )
    if ufc is not None and ufc_source is not None and ufc_mapping is not None:
        fetched = UfcOfficialAdapter().fetch(FetchRequest(capability="fixtures", sport_id="mma", competition_id="ufc"))
        logger.info(
            "Official creator ufc fetch ok=%s status=%s events=%s error=%s",
            fetched.ok,
            fetched.http_status,
            len(fetched.events or []),
            fetched.error,
        )
        if fetched.events:
            logger.info(
                "Official creator ufc %s",
                _consume_result(
                    db,
                    source=ufc_source,
                    mapping=ufc_mapping,
                    competition=ufc,
                    capability="fixtures",
                    result=fetched,
                ),
            )
    else:
        logger.info("Official creator ufc registry missing")
    gri = db.query(SportsCompetition).filter_by(competition_id="ireland-gri-meetings").first()
    if gri is None:
        gri = SportsCompetition(
            competition_id="ireland-gri-meetings",
            sport_id="greyhound-racing",
            name="Greyhound Racing Ireland",
            official_name="Greyhound Racing Ireland",
            slug="ireland-gri-meetings",
            country_id="ie",
            region_id="europe",
            event_model="racing",
            active=True,
            news_taxonomy=False,
            identity_only=False,
        )
        db.add(gri)
        db.flush()
        logger.info("Official creator ireland-gri-meetings competition created")
    gri_source = db.query(SportsSource).filter_by(upstream_family="gri-web").first()
    if gri_source is None:
        gri_source = db.query(SportsSource).filter_by(adapter_key="gri-web").first()
    if gri_source is not None:
        gri_mapping = (
            db.query(SportsSourceCompetition)
            .filter_by(competition_id="ireland-gri-meetings", source_id=gri_source.source_id)
            .first()
        )
        if gri_mapping is None:
            db.add(
                SportsSourceCompetition(
                    competition_id="ireland-gri-meetings",
                    source_id=gri_source.source_id,
                    priority=1,
                    enabled=True,
                    upstream_family="gri-web",
                    source_competition_id="ireland-gri-meetings",
                    coverage_scope="full",
                    source_config_json='{"url":"https://www.grireland.ie/results/"}',
                )
            )
            db.flush()
            logger.info("Official creator ireland-gri-meetings mapping created source=%s", gri_source.source_id)
    else:
        logger.info("Official creator ireland-gri-meetings source missing")
    for competition_id, family in (
        ("ireland-gri-meetings", "gri-web"),
        ("wa-calendar", "world-athletics-web"),
        ("biathlon", "ibu-web"),
        ("germany-click-tt", "ttbl-web"),
        ("world-aquatics-events", "world-aquatics-api"),
        ("ettu-events", "ettu-news-results"),
    ):
        competition = db.query(SportsCompetition).filter_by(competition_id=competition_id).first()
        if competition is None:
            continue
        try:
            stats = collect_competition(
                db,
                competition,
                "fixtures",
                source_family=family,
                include_fallback=False,
            )
            logger.info("Official creator %s %s", competition_id, {k: stats.get(k) for k in ("written", "merged", "rejected")})
            if competition_id == "ireland-gri-meetings":
                db.commit()
                logger.info("Official creator ireland-gri-meetings committed")
        except Exception:
            logger.exception("Official creator %s failed", competition_id)
            db.rollback()
    try:
        from collector.adapters import FetchResult
        from collector.http import fetch_text
        from collector.source_family_closeout import collect_wst_tournament

        wst = db.query(SportsCompetition).filter_by(competition_id="wst-events").first()
        wst_source = db.query(SportsSource).filter_by(upstream_family="wst-web").first()
        wst_mapping = (
            db.query(SportsSourceCompetition)
            .filter_by(competition_id="wst-events", source_id=wst_source.source_id)
            .order_by(SportsSourceCompetition.priority.asc())
            .first()
            if wst_source is not None
            else None
        )
        if wst is not None and wst_source is not None and wst_mapping is not None:
            wst_events = collect_wst_tournament(lambda url: fetch_text(url, timeout=25))
            logger.info("Official creator wst events=%s", len(wst_events))
            if wst_events:
                logger.info(
                    "Official creator wst %s",
                    _consume_result(
                        db,
                        source=wst_source,
                        mapping=wst_mapping,
                        competition=wst,
                        capability="fixtures",
                        result=FetchResult(
                            ok=True,
                            http_status=200,
                            events=wst_events,
                            parse_status="ok",
                            parse_reason="tournaments.snooker.web.gc.wstservices.co.uk/v2/{tournament}",
                        ),
                    ),
                )
                db.commit()
        else:
            logger.info("Official creator wst registry missing")
    except Exception:
        logger.exception("Official creator wst failed")
        db.rollback()
    _collect_zero_event_proofs(db)
    db.commit()


def _ensure_mapping(db, competition_id: str, families: tuple):
    from collector.models import SportsCompetition, SportsSource, SportsSourceCompetition

    competition = db.query(SportsCompetition).filter_by(competition_id=competition_id).first()
    if competition is None:
        return None, None, None
    source = None
    for family in families:
        source = db.query(SportsSource).filter_by(upstream_family=family).first()
        if source is not None:
            break
    if source is None:
        source = db.query(SportsSource).filter(SportsSource.adapter_key.in_(families)).first()
    if source is None:
        return competition, None, None
    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(competition_id=competition_id, source_id=source.source_id)
        .first()
    )
    if mapping is None:
        mapping = SportsSourceCompetition(
            competition_id=competition_id,
            source_id=source.source_id,
            priority=1,
            enabled=True,
            upstream_family=source.upstream_family,
            source_competition_id=competition_id,
            coverage_scope="full",
        )
        db.add(mapping)
        db.flush()
    return competition, source, mapping


def _collect_zero_event_proofs(db) -> None:
    """Persist the bounded official proofs. One pass per process, no historical backfill."""
    from collector.adapters import FetchRequest, FetchResult
    from collector.adapters_feeds import FifaFootballAdapter, WorldRugbyAdapter
    from collector.adapters_final18 import PgaGraphqlAdapter
    from collector.collect import _consume_result
    from collector.http import fetch_text
    from collector.zero_event_closeout import zero_event_collectors

    def _store(competition_id: str, families: tuple, result: FetchResult) -> None:
        competition, source, mapping = _ensure_mapping(db, competition_id, families)
        if competition is None or source is None or mapping is None:
            logger.info("Zero-event proof %s registry missing", competition_id)
            return
        if not result.events and not result.standings:
            logger.info("Zero-event proof %s empty %s", competition_id, result.parse_reason)
            return
        logger.info(
            "Zero-event proof %s %s",
            competition_id,
            _consume_result(
                db,
                source=source,
                mapping=mapping,
                competition=competition,
                capability="snapshot",
                result=result,
            ),
        )

    try:
        fifa = FifaFootballAdapter().fetch(FetchRequest(capability="snapshot", competition_id="fifa-connected-competitions"))
        finished = [
            row
            for row in fifa.events or []
            if "world cup" in str(row.get("competition") or "").lower()
            and row.get("status") == "finished"
            and (row.get("score") or {}).get("home") is not None
        ]

        def _match_number(row: dict) -> int:
            try:
                return int(row.get("round") or 0)
            except (TypeError, ValueError):
                return 0

        knockout = [row for row in finished if _match_number(row) >= 100]
        fifa.events = knockout or finished[:8]
        for row in fifa.events:
            row["source_competition_id"] = "fifa-connected-competitions"
        _store("fifa-connected-competitions", ("fifa-digital", "fifa"), fifa)
    except Exception:
        logger.exception("Zero-event proof fifa failed")
    try:
        rugby = WorldRugbyAdapter().fetch(FetchRequest(capability="snapshot", competition_id="internationals-rwc"))
        _store("internationals-rwc", ("pulselive",), rugby)
    except Exception:
        logger.exception("Zero-event proof rugby failed")
    try:
        pga = PgaGraphqlAdapter().fetch(FetchRequest(capability="snapshot", competition_id="pga-tour"))
        _store("pga-tour", ("pga-graphql", "pga-tour-web"), pga)
    except Exception:
        logger.exception("Zero-event proof pga failed")

    def getter(url: str) -> str:
        fetched = fetch_text(url, timeout=25)
        return fetched.payload if fetched.ok and isinstance(fetched.payload, str) else ""

    families = {
        "cdl-majors": ("cdl-web",),
        "pll": ("pll-web",),
        "atp-tour": ("sportscore", "bbc-sport"),
        "ehf-competitions": ("ehf-web", "sofascore-web"),
        "fivb-competitions": ("fivb-web", "volleyballworld"),
        "nascar-truck": ("thesportsdb", "espn-html"),
        "nascar-arca": ("thesportsdb", "espn-html"),
        "nz-national-league": ("thesportsdb", "sofascore-web"),
        "africa-cup-of-nations": ("caf-web", "thesportsdb", "fifa-digital"),
    }
    try:
        collected = zero_event_collectors(getter)
    except Exception:
        logger.exception("Zero-event proof collectors failed")
        return
    for competition_id, payload in collected.items():
        try:
            _store(
                competition_id,
                families[competition_id],
                FetchResult(
                    ok=bool(payload.get("events") or payload.get("standings")),
                    http_status=200,
                    events=payload.get("events") or [],
                    standings=payload.get("standings") or [],
                    parse_reason=payload.get("note") or "",
                    parse_status="ok" if payload.get("events") else "empty",
                ),
            )
        except Exception:
            logger.exception("Zero-event proof %s failed", competition_id)
    try:
        from collector.canonical_collapse import _collapse_pair
        from collector.models import SportsEvent
        from collector.util import load_json, slugify

        rows = (
            db.query(SportsEvent)
            .filter(SportsEvent.competition_id == "world-aquatics-events")
            .filter(SportsEvent.canonical_event_id.is_(None))
            .all()
        )
        groups = {}
        for row in rows:
            extra = load_json(row.extra_json, {}) or {}
            participants = load_json(row.participants_json, {}) or {}
            if isinstance(participants, dict):
                home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
                away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
            else:
                home = extra.get("home") if isinstance(extra.get("home"), dict) else {}
                away = extra.get("away") if isinstance(extra.get("away"), dict) else {}
            named = [slugify(home.get("name") or ""), slugify(away.get("name") or "")]
            score = load_json(row.score_json, {}) or {}
            if score.get("home") is None or score.get("away") is None or len(named) < 2:
                continue
            pair = tuple(sorted([
                (named[0], str(score.get("home"))),
                (named[1], str(score.get("away"))),
            ]))
            groups.setdefault(pair, []).append((row, extra))
        for key, items in groups.items():
            if len(items) < 2 or not key:
                continue
            ranked = sorted(items, key=lambda item: 1 if item[1].get("periods") else 0, reverse=True)
            keeper = ranked[0][0]
            for loser, _extra in ranked[1:]:
                if _collapse_pair(db, keeper.event_id, loser.event_id):
                    logger.info("World Aquatics duplicate %s -> %s", loser.event_id, keeper.event_id)
        db.commit()
    except Exception:
        logger.exception("World Aquatics duplicate collapse failed")
from collector.matrix_guard import assert_frozen_matrix
from collector.models import SportsSource
from collector.production import bootstrap_registry, register_production_adapters
from collector.schedule import due_capabilities
from collector.sources import source_collectable

logger = logging.getLogger(__name__)


def enabled_source_count(db) -> int:
    return sum(1 for row in db.query(SportsSource).all() if source_collectable(row))


def _maybe_log_breadth(db, *, force: bool = False) -> None:
    global _breadth_logged_at
    now_audit = time.monotonic()
    if not force and now_audit - _breadth_logged_at < 300:
        return
    try:
        from collector.breadth_audit import (
            fifa_competition_samples,
            tomorrow_football_snapshot,
            tomorrow_public_football_snapshot,
            tomorrow_public_multisport_snapshot,
        )

        snapshot = tomorrow_football_snapshot(db)
        logger.info("TOMORROW_FOOTBALL_BREADTH %s", snapshot)
        public_snapshot = tomorrow_public_football_snapshot()
        logger.info("TOMORROW_FOOTBALL_PUBLIC %s", public_snapshot)
        logger.info("TOMORROW_MULTISPORT_PUBLIC %s", tomorrow_public_multisport_snapshot())
        from collector.breadth_audit import sportscore_breadth_probe
        logger.info("SPORTSCORE_BREADTH_PROBE %s", sportscore_breadth_probe())
        from collector.breadth_audit import sportscore_team_schedule_probe
        logger.info("SPORTSCORE_TEAM_SCHEDULE_PROBE %s", sportscore_team_schedule_probe())
        logger.info("FIFA_COMPETITION_SAMPLES %s", fifa_competition_samples())
        _breadth_logged_at = now_audit
    except Exception:
        logger.exception("Tomorrow football breadth audit failed")


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
    standby_attempts = 0
    while True:
        if not collection_enabled() or (not scheduler_enabled() and not run_once_requested()):
            if once:
                logger.info("Results worker one-shot exit. %s", flags_payload())
                return
            _idle(interval)
            continue
        db = SessionLocal()
        _maybe_log_breadth(db, force=_breadth_logged_at == 0.0)
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
                    standby_attempts += 1
                    if standby_attempts >= RUN_ONCE_LOCK_RETRIES:
                        logger.info("Results worker one-shot could not acquire scheduler lease after %s attempts", standby_attempts)
                        return
                time.sleep(STANDBY_SLEEP_SECONDS)
                continue
            _standby_logged = False
            standby_attempts = 0
            advisory = postgres_try_advisory(db)
            if advisory is False:
                logger.info("Results worker is standby; postgres advisory lock is held by another owner")
                release_scheduler_lock(db, owner=owner)
                db.commit()
                held = False
                if once:
                    standby_attempts += 1
                    if standby_attempts >= RUN_ONCE_LOCK_RETRIES:
                        logger.info("Results worker one-shot could not acquire postgres advisory lock after %s attempts", standby_attempts)
                        return
                time.sleep(STANDBY_SLEEP_SECONDS)
                continue
            if not db.info.get("registry_bootstrapped"):
                bootstrap_registry(db)
                db.commit()
                db.info["registry_bootstrapped"] = True
            global _fifa_identity_reconciled
            if not _fifa_identity_reconciled and writes_enabled():
                try:
                    from collector.fifa_identity_reconcile import reconcile_current_fifa_identity

                    identity_stats = reconcile_current_fifa_identity(db)
                    db.commit()
                    _fifa_identity_reconciled = True
                    logger.info("FIFA identity reconcile %s", identity_stats)
                except Exception:
                    logger.exception("FIFA identity reconcile failed")
                    db.rollback()
            try:
                from collector.fotmob_crosswalk import run_date_boards_if_due

                def _pulse_boards() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                boards = run_date_boards_if_due(db, owner=owner, heartbeat=_pulse_boards)
                if boards:
                    logger.info(
                        "FotMob date boards %s",
                        {k: boards.get(k) for k in ("attached", "ingested", "upstream_total", "upstream_eligible", "unmatched", "ambiguous")},
                    )
                    _maybe_log_breadth(db, force=True)
            except Exception:
                logger.exception("FotMob date-board backfill failed")

            try:
                from collector.sofascore_crosswalk import run_if_due as run_sofascore_breadth_if_due

                def _pulse_sofa() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                sofa_breadth = run_sofascore_breadth_if_due(
                    db,
                    owner=owner,
                    heartbeat=_pulse_sofa,
                )
                if sofa_breadth:
                    logger.info(
                        "SofaScore multi-sport breadth %s",
                        {
                            "status": sofa_breadth.get("status"),
                            "upstream_total": sofa_breadth.get("upstream_total"),
                            "eligible": sofa_breadth.get("eligible"),
                            "ingested": sofa_breadth.get("ingested"),
                            "sports": sofa_breadth.get("sports"),
                        },
                    )
            except Exception:
                logger.exception("SofaScore multi-sport breadth failed")

            try:
                from collector.sportscore_crosswalk import run_if_due as run_sportscore_breadth_if_due

                def _pulse_sportscore() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                sportscore_breadth = run_sportscore_breadth_if_due(
                    db,
                    owner=owner,
                    heartbeat=_pulse_sportscore,
                )
                if sportscore_breadth:
                    logger.info(
                        "SportScore multi-sport breadth %s",
                        {
                            "status": sportscore_breadth.get("status"),
                            "upstream_total": sportscore_breadth.get("upstream_total"),
                            "eligible": sportscore_breadth.get("eligible"),
                            "ingested": sportscore_breadth.get("ingested"),
                            "skipped_ambiguous": sportscore_breadth.get("skipped_ambiguous"),
                            "sports": sportscore_breadth.get("sports"),
                        },
                    )
                    _maybe_log_breadth(db, force=True)
            except Exception:
                logger.exception("SportScore multi-sport breadth failed")
                db.rollback()

            try:
                from collector.sportscore_crosswalk import run_team_schedule_if_due

                def _pulse_sportscore_schedule() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                sportscore_schedule = run_team_schedule_if_due(
                    db,
                    owner=owner,
                    heartbeat=_pulse_sportscore_schedule,
                )
                if sportscore_schedule:
                    logger.info(
                        "SportScore team schedule backfill %s",
                        {
                            "status": sportscore_schedule.get("status"),
                            "requests": sportscore_schedule.get("requests"),
                            "upstream_total": sportscore_schedule.get("upstream_total"),
                            "eligible": sportscore_schedule.get("eligible"),
                            "ingested": sportscore_schedule.get("ingested"),
                            "sports": sportscore_schedule.get("sports"),
                        },
                    )
                    _maybe_log_breadth(db, force=True)
            except Exception:
                logger.exception("SportScore team schedule backfill failed")
                db.rollback()

            _collect_official_creators(db)
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
                from collector.provider_crosswalk import run_provider_id_attach_if_due

                def _pulse_attach() -> None:
                    heartbeat_scheduler_lock(db, owner=owner)
                    db.commit()

                attached = run_provider_id_attach_if_due(db, owner=owner, heartbeat=_pulse_attach)
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
            _maybe_log_breadth(db)

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
    # Scheduler mode is persistent unless one-shot is explicitly requested.
    # This avoids Railway restart/lease churn from legacy COLLECTOR_ONCE flags.
    once = run_once_requested() or (not scheduler_enabled() and not keepalive_enabled())
    main(once=once)
