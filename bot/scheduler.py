from apscheduler.schedulers.blocking import BlockingScheduler
from bot.pipeline import run_pipeline
import logging

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


# ⏱ Pokreće job na svaka 3 sata, max 1 istovremeno
scheduler.add_job(
    job,
    "interval",
    hours=3,
    max_instances=1,
    coalesce=True,  # ako zakasni, spoji u jedan
)

logger.info("Starting AllBall scheduler (every 3 hours)...")

if __name__ == "__main__":
    scheduler.start()
