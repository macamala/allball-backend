"""Legacy entrypoint delegates to the same original-only, budgeted pipeline.

No separate RSS-summary publisher or raw-source fallback is permitted.
"""
import os
from .fetch_sources import fetch_and_store_all_articles


def run_pipeline():
    try:
        cap = int(os.getenv("NEWS_MAX_AI_ARTICLES", "0"))
    except ValueError:
        return 0
    if not 0 < cap <= 10:
        return 0
    return fetch_and_store_all_articles(max_per_league=3, hard_limit=cap,
                                       use_ai=True, max_ai_articles=cap)
