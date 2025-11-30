import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from .fetch_sources import fetch_and_store_all_articles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Koliko često da radi worker (u minutima)
INTERVAL_MINUTES = int(os.getenv("NEWS_FETCH_INTERVAL_MINUTES", "10"))

# Koliko AI članaka sme da prepiše po jednom run-u
MAX_AI_ARTICLES = int(os.getenv("NEWS_MAX_AI_ARTICLES", "50"))


def job():
  """
  Jedan job:
  - povuče vesti (preko NewsAPI za sada)
  - napravi/upiše artikle u bazu
  - uradi AI rewrite u ai_content
  """
  logger.info("Running NinkoSports pipeline (scheduled job)...")
  try:
      created = fetch_and_store_all_articles(
          max_per_league=3,         # max 3 članka po ligi po run-u
          hard_limit=None,          # nema ukupnog limita po run-u
          use_ai=True,              # koristi OpenAI
          max_ai_chars=3000,        # max ulaznih karaktera za AI
          max_ai_articles=MAX_AI_ARTICLES,  # max AI rewritova po run-u
      )
      logger.info(
          "NinkoSports pipeline finished successfully. "
          "AI rewrote %s articles in this run.",
          created,
      )
  except Exception as e:
      logger.exception(f"NinkoSports pipeline failed: {e}")


if __name__ == "__main__":
  logger.info(
      "Starting NinkoSports scheduler "
      f"(every {INTERVAL_MINUTES} minutes)..."
  )

  scheduler = BlockingScheduler()

  scheduler.add_job(
      job,
      "interval",
      minutes=INTERVAL_MINUTES,
      max_instances=1,
      coalesce=True,
  )

  # drži proces živim
  scheduler.start()
