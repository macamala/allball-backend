"""Preserve verified source times in News; no score tables or invented times."""
from datetime import datetime, time, timezone
import logging
import re

from sqlalchemy import text

from models import Article
from .news_policy import freshness_reason, news_source_identity

logger = logging.getLogger(__name__)
_READY = False


def ensure_news_publication_clock(db):
    """Repair the confirmed legacy DATE column under the News owner lock.

    Models already declare DateTime. Existing dates retain their existing
    midnight value; only newly supplied, verified source times gain precision.
    A short lock timeout avoids waiting behind API readers. Failure aborts this
    News cycle and retries on its normal cadence.
    """
    global _READY
    if _READY or db.get_bind().dialect.name != 'postgresql':
        return
    column = db.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='articles' AND column_name='published_at'")).scalar()
    if column == 'date':
        try:
            db.execute(text("SET LOCAL lock_timeout = '1s'"))
            db.execute(text("SET LOCAL statement_timeout = '8s'"))
            db.execute(text('ALTER TABLE articles ALTER COLUMN published_at TYPE timestamp without time zone USING published_at::timestamp without time zone'))
            db.commit()
            logger.warning('[news_clock] restored source time precision: articles.published_at date -> timestamp')
        except Exception as exc:
            db.rollback()
            original = getattr(exc, 'orig', None)
            state = getattr(original, 'pgcode', None) or getattr(original, 'sqlstate', None)
            state = state if isinstance(state, str) and re.fullmatch(r'[A-Z0-9]{5}', state) else 'unknown'
            logger.error('[news_clock] migration refused sqlstate=%s error_type=%s', state, type(exc).__name__)
            raise RuntimeError('news_publication_clock_migration_unavailable') from None
    elif column not in {'timestamp without time zone', 'timestamp with time zone'}:
        db.rollback()
        logger.error('[news_clock] publication column is absent or has an unsupported type')
        raise RuntimeError('news_publication_clock_type_unverified')
    else:
        db.commit()
    _READY = True


def repair_verified_source_times(db, candidates, *, now=None, limit=200):
    """Recover recent midnight-truncated times from the same public source.

    No extra HTTP or AI calls. Discovery must identify actual publication
    evidence; update/creation timestamps cannot repair a publication timestamp.
    This changes only time precision, never public eligibility or story content.
    """
    now = now or datetime.now(timezone.utc)
    verified = {}
    conflicts = set()
    for item in candidates:
        if item.get('_publication_evidence') not in {'rss-published', 'article-published'}:
            continue
        stamp = item.get('published_at')
        key = news_source_identity(item.get('url'))
        if not key or not isinstance(stamp, datetime) or freshness_reason(stamp, now, max_age_hours=72):
            continue
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        if key in verified and verified[key] != stamp:
            conflicts.add(key)
        verified[key] = stamp
    for key in conflicts:
        verified.pop(key, None)
    if not verified:
        return 0
    rows = (db.query(Article).filter(Article.ai_generated.is_(True), Article.source_url.isnot(None))
            .order_by(Article.id.desc()).limit(500).all())
    repaired = 0
    for article in rows:
        if '/live-scores' in str(article.source_url or ''):
            continue
        stamp = verified.get(news_source_identity(article.source_url))
        current = article.published_at
        if (stamp is None or not isinstance(current, datetime) or current.time() != time()
                or current.date() != stamp.date() or stamp.time() == time()):
            continue
        article.published_at = stamp
        db.add(article)
        repaired += 1
        if repaired >= max(1, min(int(limit), 200)):
            break
    if repaired:
        db.commit()
        from public_cache import bump_public_cache
        bump_public_cache()
        logger.info('[news_clock] verified source publication times restored=%s', repaired)
    return repaired
