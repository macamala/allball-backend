import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from .pipeline import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def job():
    logger.info("Running AllBall pipeline (scheduled job)...")
    try:
        run_pipeline()
        logger.info("AllBall pipeline finished successfully.")
    except Exception as e:
        logger.exception(f"AllBall pipeline failed: {e}")


if __name__ == "__main__":
    logger.info("Starting AllBall scheduler (every 5 minutes for testing)...")

    scheduler = BlockingScheduler()

    # for testing: every 5 minutes
    scheduler.add_job(
        job,
        "interval",
        minutes=5,        # kad završimo test, promeni u hours=3
        max_instances=1,
        coalesce=True,
    )

    # this keeps the process alive
    scheduler.start()
