"""Guarded News scheduling; importing this module performs no ingestion or DB work.

Policy: never mass-rewrite historical articles. Explicit maintenance is bounded.
"""
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _start_errors():
    from deploy.news.preflight import runtime_errors
    from news_runtime import storage_errors
    errors = runtime_errors(os.environ)
    return errors or storage_errors(os.environ)



def _run_zero_ai_public_repairs():
    """Keep public News clean even when the writer allowance is exhausted."""
    from database import SessionLocal
    from public_cache import bump_public_cache
    from public_index import (
        recent_public_sport_inventory,
        repair_recent_duplicate_news,
        repair_recent_news_images,
        repair_recent_sport_mislabels,
        repair_recent_unresolved,
    )

    db = SessionLocal()
    try:
        images = repair_recent_news_images(db, limit=80, max_age_hours=72, recover_limit=8)
        mislabels = repair_recent_sport_mislabels(db, limit=600, max_age_hours=168)
        repaired = repair_recent_unresolved(db, limit=24)
        duplicates = repair_recent_duplicate_news(db, limit=600, max_age_hours=168)
        inventory = recent_public_sport_inventory(db, max_age_hours=72)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error('News zero-AI repair failed: %s', type(exc).__name__)
        return {}
    finally:
        db.close()
    if images or mislabels or repaired or duplicates:
        bump_public_cache()
    logger.info(
        'News zero-AI repair: images=%s mislabels=%s unresolved=%s duplicates=%s inventory=%s',
        images,
        mislabels,
        repaired,
        duplicates,
        inventory,
    )
    return inventory


def _run_image_health():
    """Bounded zero-AI hero-image maintenance for the current public feed."""
    from database import SessionLocal
    from public_cache import bump_public_cache
    from public_index import repair_recent_news_images

    db = SessionLocal()
    try:
        changed = repair_recent_news_images(
            db,
            limit=80,
            max_age_hours=72,
            recover_limit=8,
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error('News image-health repair failed: %s', type(exc).__name__)
        return 0
    finally:
        db.close()
    if changed:
        bump_public_cache()
    logger.info('News image-health finished: changed=%s', changed)
    return changed


def image_health_job():
    """Run image maintenance under the same single News write-owner lock."""
    from news_runtime import NewsOwnerUnavailable, news_owner

    errors = _start_errors()
    if errors:
        logger.error('News image-health held: %s', ','.join(errors))
        return 0
    try:
        with news_owner():
            return _run_image_health()
    except NewsOwnerUnavailable as exc:
        # The main 30-minute News cycle already performs the same image repair.
        # If both schedules meet on one boundary, one owner is enough.
        logger.info('News image-health skipped: %s', exc)
        return 0

def _run_cycle():
    """Called under news_owner. Every tick rechecks flags before importing DB code."""
    errors = _start_errors()
    if errors:
        logger.error('News cycle held: %s', ','.join(errors))
        return 0
    from bot.news_budget import ai_budget_exhausted, ai_budget_scope, configured_budget
    maximum = int(os.environ['NEWS_MAX_AI_ARTICLES'])
    budget = configured_budget(maximum)
    from public_cache import bump_public_cache

    historical = os.environ['NEWS_HISTORICAL_REPAIR_ENABLED'] == '1'
    rewritten = indexed = translated_rows = 0

    if maximum <= 0 or not budget.can_start():
        reason = 'article_limit_disabled' if maximum <= 0 else (budget.blocked_reason or 'allowance_or_ledger_unavailable')
        _run_zero_ai_public_repairs()
        logger.info('News AI lane held: %s', reason)
        return 0

    from bot.fetch_sources import fetch_and_store_all_articles
    from bot.rewrite_ai import reset_openai_rate_limit
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
            try:
                from database import SessionLocal
                from public_index import repair_recent_unresolved
                repair_db = SessionLocal()
                try:
                    repaired = repair_recent_unresolved(repair_db, limit=24)
                finally:
                    repair_db.close()
                if repaired:
                    bump_public_cache()
            except Exception as exc:
                logger.error('Recent News taxonomy repair failed: %s', type(exc).__name__)
            # English freshness always wins. Translate only after new-story
            # ingestion, from whatever request allowance remains.
            if (
                os.environ.get('NEWS_TRANSLATIONS_ENABLED') == '1'
                and int(os.environ.get('NEWS_TRANSLATIONS_PER_CYCLE', '0')) > 0
                and not ai_budget_exhausted()
            ):
                try:
                    from bot.news_translations import translate_latest_articles
                    translated_rows = translate_latest_articles(
                        limit=int(os.environ['NEWS_TRANSLATIONS_PER_CYCLE'])
                    )
                except Exception as exc:
                    logger.error('News translation lane failed: %s', type(exc).__name__)
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
        logger.info(
            'News cycle finished: ai_articles=%s translated_rows=%s indexed=%s attempts=%s stop=%s history=%s',
            rewritten, translated_rows, indexed, budget.attempts,
            budget.blocked_reason, historical,
        )
        return rewritten
    except Exception as exc:
        logger.error('News AI cycle failed: %s', type(exc).__name__)
        return 0


def job():
    """Explicit one-cycle entry point with the same startup and ownership gates."""
    from news_runtime import NewsOwnerUnavailable, news_owner
    errors = _start_errors()
    if errors:
        logger.error('News job held: %s', ','.join(errors))
        return 0
    try:
        with news_owner():
            return _run_cycle()
    except NewsOwnerUnavailable as exc:
        logger.error('News job held: %s', exc)
        return 0


def _next_interval_boundary(now, interval_minutes, offset_minutes=0):
    """Return the next UTC wall-clock boundary for an interval and safe offset."""
    step_seconds = max(1, int(interval_minutes)) * 60
    offset_seconds = (max(0, int(offset_minutes)) * 60) % step_seconds
    epoch = int(now.timestamp())
    next_epoch = ((epoch - offset_seconds) // step_seconds + 1) * step_seconds + offset_seconds
    return datetime.fromtimestamp(next_epoch, tz=timezone.utc)


def main():
    """Run only the independent NinkoSports News pipeline."""
    errors = _start_errors()
    if errors:
        logger.error('News startup refused: %s', ','.join(errors))
        return 78

    from apscheduler.schedulers.blocking import BlockingScheduler
    interval = int(os.environ['NEWS_FETCH_INTERVAL_MINUTES'])
    scheduler = BlockingScheduler()
    now = datetime.now(timezone.utc)
    first_run = _next_interval_boundary(now, interval)
    image_interval = 10
    # Offset by five minutes so image maintenance never races the :00/:30 writer lock.\n    first_image_run = _next_interval_boundary(now, image_interval, offset_minutes=5)
    logger.info(
        'Starting NinkoSports News scheduler every %s minutes; first cycle=%s; image-health=%s minutes first=%s (offset=5m)',
        interval,
        first_run.isoformat(),
        image_interval,
        first_image_run.isoformat(),
    )
    try:
        # Do not run a one-shot cycle on every Railway deployment. Repeated
        # deploys previously spent the same durable daily AI allowance before
        # the regular 30-minute schedule had a chance to control cadence.
        scheduler.add_job(
            job,
            'interval',
            minutes=interval,
            start_date=first_run,
            max_instances=1,
            coalesce=True,
            id='news-interval-cycle',
            replace_existing=True,
        )
        scheduler.add_job(
            image_health_job,
            'interval',
            minutes=image_interval,
            start_date=first_image_run,
            max_instances=1,
            coalesce=True,
            id='news-image-health-cycle',
            replace_existing=True,
        )
        scheduler.start()
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
