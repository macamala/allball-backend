"""Guarded News scheduling; importing this module performs no ingestion or DB work.

Policy: never mass-rewrite historical articles. Explicit maintenance is bounded.
"""
import logging
import os

logger = logging.getLogger(__name__)


def _start_errors():
    from deploy.news.preflight import runtime_errors
    from news_runtime import storage_errors
    errors = runtime_errors(os.environ)
    return errors or storage_errors(os.environ)


def _run_cycle():
    """Called under news_owner. Every tick rechecks flags before importing DB code."""
    errors = _start_errors()
    if errors:
        logger.error('News cycle held: %s', ','.join(errors))
        return 0
    from bot.news_budget import ai_budget_scope, configured_budget
    maximum = int(os.environ['NEWS_MAX_AI_ARTICLES'])
    budget = configured_budget(maximum)
    if maximum <= 0 or not budget.can_start():
        logger.info('News cycle held: allowance_or_ledger_unavailable')
        return 0
    from bot.fetch_sources import fetch_and_store_all_articles
    from bot.rewrite_ai import reset_openai_rate_limit
    from public_cache import bump_public_cache

    historical = os.environ['NEWS_HISTORICAL_REPAIR_ENABLED'] == '1'
    rewritten = indexed = 0
    try:
        # Historical retries and new articles share this one actual-request cap.
        with ai_budget_scope(budget):
            reset_openai_rate_limit()
            if historical:
                from repair_content import repair_summary_only
                repair_summary_only(max_pages=1, max_rewrite=maximum)
            rewritten = fetch_and_store_all_articles(
                max_per_league=3, hard_limit=None, use_ai=True,
                max_ai_chars=6000, max_ai_articles=maximum,
            )
            if historical:
                from database import SessionLocal
                from public_index import index_missing
                from repair_content import repair_contaminated
                db = SessionLocal()
                try:
                    # One bounded batch, never an unbounded old-index loop.
                    indexed = index_missing(db, limit=400)
                finally:
                    db.close()
                repair_contaminated(max_pages=1)
        if rewritten or historical:
            bump_public_cache()
        logger.info('News cycle finished: articles=%s indexed=%s attempts=%s stop=%s history=%s',
                    rewritten, indexed, budget.attempts, budget.blocked_reason, historical)
        return rewritten
    except Exception as exc:
        # Exception strings can contain a credential-bearing DB/source URL.
        logger.error('News cycle failed: %s', type(exc).__name__)
        return 0


def job():
    """Explicit one-cycle entry point with the same startup and ownership gates."""
    from news_runtime import NewsOwnerUnavailable, news_owner
    errors = _start_errors()
    if errors:
        logger.error('News job held: %s', ','.join(errors))
        return 0
    try:
        with news_owner(os.environ['NEWS_AI_LEDGER_PATH']):
            return _run_cycle()
    except NewsOwnerUnavailable as exc:
        logger.error('News job held: %s', exc)
        return 0


def main():
    """Direct python -m invocation cannot bypass the preflight environment gate."""
    from news_runtime import NewsOwnerUnavailable, news_owner
    errors = _start_errors()
    if errors:
        logger.error('News startup refused: %s', ','.join(errors))
        return 78
    try:
        with news_owner(os.environ['NEWS_AI_LEDGER_PATH']):
            from apscheduler.schedulers.blocking import BlockingScheduler
            interval = int(os.environ['NEWS_FETCH_INTERVAL_MINUTES'])
            scheduler = BlockingScheduler()
            logger.info('Starting guarded News scheduler every %s minutes', interval)
            try:
                _run_cycle()
                scheduler.add_job(_run_cycle, 'interval', minutes=interval,
                                  max_instances=1, coalesce=True)
                scheduler.start()
            finally:
                # Keep ownership until in-flight scheduler jobs have stopped.
                if scheduler.running:
                    scheduler.shutdown(wait=True)
    except NewsOwnerUnavailable as exc:
        logger.error('News startup refused: %s', exc)
        return 78
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
