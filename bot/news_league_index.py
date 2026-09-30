"""Assign existing public football stories to newly available News menus.

Headline/lead competition evidence or verified club membership can change a tag. Text, publication time,
quality, image and public/held status are never changed by this maintenance.
"""
from datetime import datetime, timedelta
import logging

from sqlalchemy import func

from models import Article, ArticleTaxonomyResolution
from taxonomy_resolver import RESOLVER_VERSION
from .news_football_sections import assign_public_football_section

logger = logging.getLogger(__name__)


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
