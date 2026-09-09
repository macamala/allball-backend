import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from .fetch_sources import fetch_and_store_all_articles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Na koliko minuta da radi jedan run (default 10 min)
INTERVAL_MINUTES = int(os.getenv("NEWS_FETCH_INTERVAL_MINUTES", "10"))

# Koliko AI članaka sme da obradi po jednom run-u
MAX_AI_ARTICLES = int(os.getenv("NEWS_MAX_AI_ARTICLES", "10"))


def job():
    """
    One ingest cycle for NEW candidates only:
    - fetch enabled RSS feeds
    - classify from article evidence (not feed buckets)
    - extract/clean facts, quality-gate, dedupe
    - write original English NinkoSports copy for new rows
    - never mass-rewrite historical articles
    """
    logger.info("Running NinkoSports pipeline (scheduled job)...")
    try:
        rewritten = fetch_and_store_all_articles(
            max_per_league=3,
            hard_limit=None,
            use_ai=True,
            max_ai_chars=3000,
            max_ai_articles=MAX_AI_ARTICLES,
        )
        logger.info(
            "NinkoSports pipeline finished successfully. "
            "AI rewrote %s articles in this run.",
            rewritten,
        )
    except Exception as e:
        logger.exception(f"NinkoSports pipeline failed: {e}")


if __name__ == "__main__":
    logger.info(
        "Starting NinkoSports scheduler "
        f"(every {INTERVAL_MINUTES} minutes)..."
    )

    # 🔥 Odmah jedan run na startu – ne čekaš 10 minuta
    logger.info("Running initial NinkoSports job immediately on startup...")
    job()

    scheduler = BlockingScheduler()

    scheduler.add_job(
        job,
        "interval",
        minutes=INTERVAL_MINUTES,
        max_instances=1,
        coalesce=True,
    )

    # this keeps the process alive
    scheduler.start()


