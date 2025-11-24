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


# Run every 3 hours, never overlapping
scheduler.add_job(
    job,
    "interval",
    minutes=5,
    max_instances=1,
    coalesce=True,
)

logger.info("Starting AllBall scheduler (every 3 hours)...")

if __name__ == "__main__":
    # This call blocks and keeps the process alive
    scheduler.start()

