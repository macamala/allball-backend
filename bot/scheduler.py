import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from .pipeline import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BlockingScheduler()


def job():
    logger.info("Running AllBall pipeline (scheduled job)...")
    try:
        run_pipeline()
        logger.info("AllBall pipeline finished successfully.")
    except Exception as e:
        logger.exception(f"AllBall pipeline failed: {e}")


# Run every 3 hours (for now set to 5 minutes for testing)
scheduler.add_job(
    job,
    "interval",
    minutes=5,
    max_instances=1,
    coalesce=True,
)

logger.info("Starting AllBall scheduler (every 3 hours)...")


if __name__ == "__main__":
    # TEMP: RUN IMMEDIATELY ON START (delete after testing!)
    logger.info("Running AllBall pipeline immediately for testing...")
    try:
        run_pipeline()
        logger.info("Initial run completed successfully.")
    except Exception as e:
        logger.exception(f"Initial run failed: {e}")

    # This call blocks and keeps the process alive
    scheduler.start()
