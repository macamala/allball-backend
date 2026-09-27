"""Persist public-ready article eligibility at ingest/backfill time.

Public GET handlers must read these rows, not reclassify or re-score bodies.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from editorial import classify_media_url, evaluate_quality, news_image_is_publishable
from models import Article, ArticleTaxonomyResolution
from sport_match import MAIN_SPORTS, isolation_ok
from bot.taxonomy import COMPETITIONS
from bot.news_learning import article_has_open_incident
from taxonomy_resolver import (
    MIN_SPORT_CONFIDENCE,
    RESOLVER_VERSION,
    persist_resolution,
    resolve_article_competition,
)

logger = logging.getLogger("ninkosports.public_index")


def persist_public_article(db: Session, article: Article, resolution=None, commit: bool = False):
    """Classify once, store taxonomy + quality + public eligibility."""
    resolved = resolution or resolve_article_competition(article)
    persist_resolution(db, article, resolved)
    db.flush()
    article.sport = resolved.sport
    article.league = resolved.public_competition
    if resolved.public_competition:
        meta = COMPETITIONS.get(resolved.public_competition) or {}
        if meta.get("country"):
            article.country = meta.get("country")
    db.add(article)
    media_kind = classify_media_url(article.image_url)
    if media_kind in {"CREST_OR_LOGO", "GRAPHIC"}:
        article.image_url = None
        media_kind = "MISSING"
        db.add(article)
    quality = evaluate_quality(
        title=article.title,
        summary=article.summary,
        body=article.ai_content or article.content or article.summary,
        image_url=article.image_url,
    )
    isolated = True
    if resolved.sport in MAIN_SPORTS:
        isolated = isolation_ok(
            article, resolved.sport, strict=True, resolution=resolved
        )
    public = bool(
        quality.get("ok")
        and resolved.sport
        and resolved.sport_confidence >= MIN_SPORT_CONFIDENCE
        and isolated
        and news_image_is_publishable(article.image_url)
        and not article_has_open_incident(db, article.id)
    )
    row = (
        db.query(ArticleTaxonomyResolution)
        .filter(ArticleTaxonomyResolution.article_id == article.id)
        .first()
    )
    if row is None:
        return resolved
    row.quality_ok = bool(quality.get("ok"))
    row.public_ok = public
    row.hero_media_kind = media_kind
    row.word_count = int(quality.get("word_count") or 0)
    db.add(row)
    if commit:
        db.commit()
    return resolved


def index_missing(db: Session, limit: int = 400) -> int:
    """Backfill articles that lack a current public index row. Never called from GET."""
    missing = (
        db.query(Article)
        .outerjoin(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            (ArticleTaxonomyResolution.id.is_(None))
            | (ArticleTaxonomyResolution.resolver_version != RESOLVER_VERSION)
            | (ArticleTaxonomyResolution.hero_media_kind.is_(None))
            | (Article.image_url.ilike("%/images/ic/%"))
        )
        .order_by(Article.id.desc())
        .limit(limit)
        .all()
    )
    counted = 0
    for article in missing:
        persist_public_article(db, article)
        counted += 1
    if counted:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("public index backfill failed")
            return 0
    return counted


def repair_recent_unresolved(db: Session, limit: int = 24) -> int:
    """Re-evaluate only recent AI articles already held from public News by taxonomy.

    This is bounded, zero-AI and never rewrites article copy. It exists so a
    newly added safe sport marker can rescue recent valid stories without
    enabling historical mass repair.
    """
    rows = (
        db.query(Article)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            Article.ai_generated.is_(True),
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(False),
        )
        .order_by(Article.id.desc())
        .limit(max(1, min(int(limit), 50)))
        .all()
    )
    repaired = 0
    for article in rows:
        before = load_cached_resolution(db, article)
        if before is not None and before.public_ok:
            continue
        resolved = resolve_article_competition(article)
        persist_public_article(db, article, resolved, commit=False)
        cached = (
            db.query(ArticleTaxonomyResolution)
            .filter(ArticleTaxonomyResolution.article_id == article.id)
            .first()
        )
        if cached is not None and cached.public_ok:
            repaired += 1
    if rows:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent unresolved News repair failed")
            return 0
    if repaired:
        logger.info("[public_index] repaired recent unresolved articles=%s", repaired)
    return repaired


def load_cached_resolution(db: Session, article: Article):
    if not getattr(article, "id", None):
        return None
    return (
        db.query(ArticleTaxonomyResolution)
        .filter(
            ArticleTaxonomyResolution.article_id == article.id,
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        )
        .first()
    )


def load_cached_resolutions(db: Session, articles: Sequence[Article]) -> dict:
    ids = [article.id for article in articles if getattr(article, "id", None)]
    if not ids:
        return {}
    rows = (
        db.query(ArticleTaxonomyResolution)
        .filter(
            ArticleTaxonomyResolution.article_id.in_(ids),
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        )
        .all()
    )
    return {row.article_id: row for row in rows}



def recent_public_sport_inventory(db: Session, max_age_hours: int = 72) -> dict[str, int]:
    """Counts the same current, image-valid News inventory readers can browse."""
    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution.resolved_sport,
            func.count(ArticleTaxonomyResolution.id),
        )
        .join(Article, Article.id == ArticleTaxonomyResolution.article_id)
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            ArticleTaxonomyResolution.resolved_sport.isnot(None),
            ArticleTaxonomyResolution.hero_media_kind.in_(("EDITORIAL_PHOTO", "UNKNOWN")),
            Article.image_url.isnot(None),
            Article.image_url != "",
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .group_by(ArticleTaxonomyResolution.resolved_sport)
        .all()
    )
    return {str(sport): int(count or 0) for sport, count in rows if sport}


def repair_recent_duplicate_news(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Hide recent cross-source duplicate News rows without deleting articles.

    Newest public row wins. The stricter ingest-time detector prevents recurrence;
    this bounded repair cleans legacy duplicate cards already in the public index.
    """
    from bot.dedupe import titles_are_near_duplicate

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    rows = (
        db.query(
            ArticleTaxonomyResolution,
            Article.id,
            Article.title,
        )
        .join(
            Article,
            Article.id == ArticleTaxonomyResolution.article_id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )
    from bot.dedupe import _title_tokens

    kept_titles: dict[str, dict[int, str]] = {}
    token_index: dict[str, dict[str, set[int]]] = {}
    hidden = 0
    for tax, article_id, article_title in rows:
        sport = str(tax.resolved_sport or "")
        title = article_title or ""
        if not sport or not title:
            continue
        tokens = _title_tokens(title)
        sport_titles = kept_titles.setdefault(sport, {})
        sport_index = token_index.setdefault(sport, {})

        candidate_ids: set[int] = set()
        token_hits: dict[int, int] = {}
        for token in tokens:
            for candidate_id in sport_index.get(token, ()):
                token_hits[candidate_id] = token_hits.get(candidate_id, 0) + 1
        # Near-duplicate headlines should share multiple meaningful terms. Exact
        # normalization still gets a fallback scan over the small recent set.
        candidate_ids.update(
            candidate_id for candidate_id, hits in token_hits.items() if hits >= 3
        )
        normalized = None
        duplicate = False
        for candidate_id in candidate_ids:
            other = sport_titles.get(candidate_id, "")
            if other and titles_are_near_duplicate(title, other):
                duplicate = True
                break
        if not duplicate:
            from bot.textutil import normalize_title

            normalized = normalize_title(title)
            duplicate = any(
                normalize_title(other) == normalized
                for other in sport_titles.values()
            )
        if duplicate:
            tax.public_ok = False
            db.add(tax)
            hidden += 1
            continue

        sport_titles[int(article_id)] = title
        for token in tokens:
            sport_index.setdefault(token, set()).add(int(article_id))
    if hidden:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent News duplicate repair failed")
            return 0
        logger.info("[public_index] hid recent duplicate News rows=%s", hidden)
    return hidden



def _distinctive_title_sport_support(title: str, sport: str) -> bool:
    """Require a word-bounded alias unique to the proposed sport in the headline."""
    from bot.taxonomy import SPORT_ALIASES

    haystack = " " + (title or "").casefold() + " "
    aliases = [
        str(alias).casefold()
        for alias in SPORT_ALIASES.get(sport, ())
        if str(alias).strip()
    ]
    other_aliases = {
        str(alias).casefold().strip()
        for other_sport, rows in SPORT_ALIASES.items()
        if other_sport != sport
        for alias in rows
        if str(alias).strip()
    }
    for alias in aliases:
        needle = alias.strip()
        if len(needle) < 4 or needle in other_aliases:
            continue
        pattern = re.compile(
            r"(?<!\w)" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?!\w)",
            re.IGNORECASE,
        )
        if pattern.search(haystack):
            return True
    return False

def repair_recent_sport_mislabels(
    db: Session,
    *,
    limit: int = 600,
    max_age_hours: int = 168,
) -> int:
    """Hide recent public rows whose own copy clearly proves a different sport.

    Feed/source hints are intentionally excluded. A row is changed only when an
    independent text classification returns a concrete sport that conflicts
    with the cached public sport. Ambiguous/unclassified rows are left alone.
    """
    from bot.classify import classify_article

    cutoff = datetime.utcnow() - timedelta(hours=max(1, int(max_age_hours)))
    # First pass is title-only. The final mismatch rule already requires a
    # distinctive alias for the independently detected sport in the headline,
    # so loading hundreds of large article bodies before checking that condition
    # is unnecessary and can stall the News worker on a remote database.
    rows = (
        db.query(
            ArticleTaxonomyResolution,
            Article.id,
            Article.title,
        )
        .join(
            Article,
            Article.id == ArticleTaxonomyResolution.article_id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
            ArticleTaxonomyResolution.resolved_sport.isnot(None),
            func.coalesce(Article.published_at, Article.created_at) >= cutoff,
        )
        .order_by(
            func.coalesce(Article.published_at, Article.created_at).desc(),
            Article.id.desc(),
        )
        .limit(max(1, min(int(limit), 1200)))
        .all()
    )

    from bot.taxonomy import SPORT_ALIASES

    alias_owners: dict[str, set[str]] = {}
    for candidate_sport, aliases in SPORT_ALIASES.items():
        for alias in aliases or ():
            value = str(alias or "").casefold().strip()
            if len(value) >= 4:
                alias_owners.setdefault(value, set()).add(candidate_sport)
    distinctive_aliases = [
        (alias, next(iter(owners)))
        for alias, owners in alias_owners.items()
        if len(owners) == 1
    ]

    candidates: dict[int, tuple[ArticleTaxonomyResolution, str, set[str]]] = {}
    for tax, article_id, title in rows:
        cached = str(tax.resolved_sport or "")
        raw_title = title or ""
        if not cached or not raw_title:
            continue
        possible: set[str] = set()
        for alias, candidate_sport in distinctive_aliases:
            if candidate_sport == cached:
                continue
            pattern = re.compile(
                r"(?<!\w)" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?!\w)",
                re.IGNORECASE,
            )
            if pattern.search(raw_title):
                possible.add(candidate_sport)
        if possible:
            candidates[int(article_id)] = (tax, raw_title, possible)

    if not candidates:
        return 0

    bodies = {
        int(article_id): (ai_content or content or summary or "")
        for article_id, ai_content, content, summary in (
            db.query(
                Article.id,
                Article.ai_content,
                Article.content,
                Article.summary,
            )
            .filter(Article.id.in_(list(candidates)))
            .all()
        )
    }

    hidden = 0
    for article_id, (tax, title, possible) in candidates.items():
        independent = classify_article(
            title,
            bodies.get(article_id, ""),
            feed_kind="mixed",
            feed_sport=None,
            feed_league=None,
            feed_country=None,
        )
        if (
            independent.sport
            and independent.sport in possible
            and tax.resolved_sport
            and independent.sport != tax.resolved_sport
            and _distinctive_title_sport_support(title, independent.sport)
        ):
            logger.warning(
                "[public_index] hide sport mismatch article=%s cached=%s independent=%s title=%s",
                article_id,
                tax.resolved_sport,
                independent.sport,
                title[:100],
            )
            tax.public_ok = False
            db.add(tax)
            hidden += 1
    if hidden:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("recent News sport-mislabel repair failed")
            return 0
        logger.info("[public_index] hid recent sport-mislabel rows=%s", hidden)
    return hidden
