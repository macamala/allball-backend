"""Assign existing public football stories to newly available News menus.

Headline/lead competition evidence or verified club membership can change a tag. Text, publication time,
quality, image and public/held status are never changed by this maintenance.
"""
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import func

from models import Article, ArticleTaxonomyResolution
from taxonomy_resolver import RESOLVER_VERSION
from .news_football_sections import assign_public_football_section

logger = logging.getLogger(__name__)


def recent_public_football_inventory(db, max_age_hours=24, *, now=None):
    """Count current reader-visible league cards for News scheduling only."""
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError('inventory clock must be timezone-aware')
    end = clock.astimezone(timezone.utc).replace(tzinfo=None)
    stamp = func.coalesce(Article.published_at, Article.created_at)
    rows = (db.query(ArticleTaxonomyResolution.resolved_competition, func.count(Article.id))
        .join(ArticleTaxonomyResolution, ArticleTaxonomyResolution.article_id == Article.id)
        .filter(Article.ai_generated.is_(True), ArticleTaxonomyResolution.public_ok.is_(True),
                ArticleTaxonomyResolution.resolved_sport == 'football',
                ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
                ArticleTaxonomyResolution.hero_media_kind.in_(('EDITORIAL_PHOTO', 'UNKNOWN')),
                Article.image_url.isnot(None), Article.image_url != '',
                ArticleTaxonomyResolution.resolved_competition.isnot(None),
                stamp >= end - timedelta(hours=max(1, int(max_age_hours))), stamp <= end)
        .group_by(ArticleTaxonomyResolution.resolved_competition).all())
    return {str(key): int(count) for key, count in rows}


def repair_football_league_menus(db, limit=300):
    rows = (db.query(Article, ArticleTaxonomyResolution)
        .join(ArticleTaxonomyResolution, ArticleTaxonomyResolution.article_id == Article.id)
        .filter(Article.ai_generated.is_(True),
                ArticleTaxonomyResolution.public_ok.is_(True),
                ArticleTaxonomyResolution.resolved_sport == 'football',
                ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
                func.coalesce(Article.published_at, Article.created_at) >= datetime.utcnow() - timedelta(days=7))
        .order_by(Article.id.desc()).limit(max(1, min(int(limit), 600))).all())
    changed = 0
    for article, tax in rows:
        if not assign_public_football_section(article, tax):
            continue
        db.add(tax)
        db.add(article)
        changed += 1
    if changed:
        db.commit()
    logger.info('News football league menus: tagged=%s scanned=%s', changed, len(rows))
    return changed
