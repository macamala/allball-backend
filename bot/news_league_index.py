"""Assign existing public football stories to newly available News menus.

Only explicit headline evidence can change a tag. Text, publication time,
quality, image and public/held status are never changed by this maintenance.
"""
from datetime import datetime, timedelta
import logging

from sqlalchemy import func

from models import Article, ArticleTaxonomyResolution
from taxonomy_resolver import RESOLVER_VERSION, resolve_article_competition
from .news_fact_guard import competition_in_source
from .taxonomy import COMPETITIONS

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
        # Existing specific domestic tags are retained. Repair missing/broad
        # tags and the shared Champions League / World Cup naming collisions.
        if tax.resolved_competition not in {None, 'football-international', 'uefa-champions-league', 'fifa-world-cup'}:
            continue
        resolved = resolve_article_competition(article)
        key = resolved.public_competition
        if (resolved.sport != 'football' or not key or key == tax.resolved_competition
                or resolved.competition_confidence < .9
                or not competition_in_source(key, article.title or '')):
            continue
        tax.resolved_competition = key
        tax.competition_confidence = f'{resolved.competition_confidence:.3f}'
        article.league = key
        article.country = COMPETITIONS[key]['country']
        db.add(tax)
        db.add(article)
        changed += 1
    if changed:
        db.commit()
    logger.info('News football league menus: tagged=%s scanned=%s', changed, len(rows))
    return changed
