import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["NINKO_SKIP_STARTUP_INDEX"] = "1"
os.environ["NINKO_SKIP_INTEGRITY_BACKFILL"] = "1"
os.environ["RESULTS_COLLECTION_ENABLED"] = "true"
os.environ["RESULTS_WRITE_ENABLED"] = "true"
os.environ["RESULTS_SCHEDULER_ENABLED"] = "false"

import pytest


@pytest.fixture(autouse=True)
def reset_collector_state():
    from database import SessionLocal, engine
    from models import Base
    import collector.models  # noqa: F401
    from collector.adapters import ADAPTERS
    from collector.limits import _hits
    from collector.adapters_wta import reset_wta_caches
    from collector.models import (
        SportsCollectorJob,
        SportsCompetition,
        SportsEntity,
        SportsEvent,
        SportsEventDetail,
        SportsIdMap,
        SportsRankingSnapshot,
        SportsRawIngest,
        SportsReadCache,
        SportsSource,
        SportsSourceCompetition,
        SportsSourceHealth,
        SportsStandingSnapshot,
        SportsEventObservation,
        SportsParticipantAlias,
        SportsCompetitionHealth,
        SportsIngestionRun,
        SportsIngestionError,
        SportsSchedulerLease,
        SportsSchedulerSlot,
        SportsLiveWatch,
    )

    Base.metadata.create_all(bind=engine)
    reset_wta_caches()
    yield
    ADAPTERS.clear()
    _hits.clear()
    db = SessionLocal()
    try:
        for model in (
            SportsReadCache,
            SportsCollectorJob,
            SportsRawIngest,
            SportsIdMap,
            SportsSourceHealth,
            SportsStandingSnapshot,
            SportsRankingSnapshot,
            SportsEventObservation,
            SportsParticipantAlias,
            SportsIngestionError,
            SportsIngestionRun,
            SportsSchedulerLease,
            SportsSchedulerSlot,
            SportsLiveWatch,
            SportsCompetitionHealth,
            SportsEventDetail,
            SportsEvent,
            SportsSourceCompetition,
            SportsEntity,
            SportsSource,
            SportsCompetition,
        ):
            db.query(model).delete()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
