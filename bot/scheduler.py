import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler

from .fetch_sources import fetch_and_store_all_articles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Na koliko minuta da radi jedan run (default 10 min)
INTERVAL_MINUTES = int(os.getenv("NEWS_FETCH_INTERVAL_MINUTES", "10"))

# Koliko AI članaka sme da obradi po jednom run-u
MAX_AI_ARTICLES = int(os.getenv("NEWS_MAX_AI_ARTICLES", "100"))


def job():
    """
    Jedan ciklus:
    - povuče vesti sa RSS-a za sve lige
    - upiše nove Article zapise u bazu
    - uradi AI rewrite u ai_content (nove + deo starih koji nisu prevedeni)
    """
    logger.info("Running NinkoSports pipeline (scheduled job)...")
    try:
        rewritten = fetch_and_store_all_articles(
            max_per_league=5,                 # max 3 članka po ligi po run-u
            hard_limit=None,                  # nema ukupnog total limita po run-u
            use_ai=True,                      # koristi OpenAI
            max_ai_chars=3000,                # max dužina ulaznog teksta
            max_ai_articles=MAX_AI_ARTICLES,  # max AI rewritova po run-u
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


