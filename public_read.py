"""Cheap public-read queries. SELECT indexed rows only. No classification."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, load_only

from bot.taxonomy import competition_label, country_label, sport_label
from editorial import (
    attach_inline_media,
    classify_media_url,
    lift_hero_caption,
    maybe_related_insert,
    public_media_items,
    public_summary,
    sanitize_body,
    sanitize_title,
    scrub_public_blocks,
    to_blocks,
)
from models import Article, ArticleTaxonomyResolution
from related import rank_related
from sport_match import MAIN_SPORTS
from taxonomy_resolver import (
    RESOLVER_VERSION,
    TaxonomyResolution,
    cache_row_to_resolution,
)

LIST_FIELDS = (
    Article.id,
    Article.title,
    Article.slug,
    Article.image_url,
    Article.summary,
    Article.created_at,
    Article.published_at,
    Article.is_breaking,
    Article.country,
    Article.division,
    Article.ai_generated,
    Article.view_count,
)

PublicPair = Tuple[Article, ArticleTaxonomyResolution]


def _sort_expr():
    from sqlalchemy import func

    return func.coalesce(Article.published_at, Article.created_at)


def public_query(db: Session, *, cards: bool = True):
    query = (
        db.query(Article, ArticleTaxonomyResolution)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
        )
    )
    if cards:
        query = query.options(load_only(*LIST_FIELDS))
    return query


def apply_scope(
    query,
    *,
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    exclude_competitions: Optional[Sequence[str]] = None,
    require_image: bool = False,
    require_photo: bool = False,
    breaking: bool = False,
    viewed: bool = False,
):
    if sport == "other":
        query = query.filter(
            (ArticleTaxonomyResolution.resolved_sport.is_(None))
            | (ArticleTaxonomyResolution.resolved_sport.notin_(MAIN_SPORTS))
        )
    elif sport:
        query = query.filter(ArticleTaxonomyResolution.resolved_sport == sport)
    if competition:
        query = query.filter(ArticleTaxonomyResolution.resolved_competition == competition)
    if exclude_competitions:
        keys = [item for item in exclude_competitions if item]
        if keys:
            query = query.filter(
                (ArticleTaxonomyResolution.resolved_competition.is_(None))
                | (ArticleTaxonomyResolution.resolved_competition.notin_(keys))
            )
    if require_image:
        query = query.filter(Article.image_url.isnot(None), Article.image_url != "")
    if require_photo:
        query = query.filter(ArticleTaxonomyResolution.hero_media_kind == "EDITORIAL_PHOTO")
    if breaking:
        query = query.filter(Article.is_breaking.is_(True))
    if viewed:
        query = query.filter(Article.view_count > 0)
    return query


def fetch_public(
    db: Session,
    *,
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    exclude_competitions: Optional[Sequence[str]] = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "newest",
    require_image: bool = False,
    require_photo: bool = False,
    breaking: bool = False,
    viewed: bool = False,
    cards: bool = True,
) -> List[PublicPair]:
    query = apply_scope(
        public_query(db, cards=cards),
        sport=sport,
        competition=competition,
        exclude_competitions=exclude_competitions,
        require_image=require_image,
        require_photo=require_photo,
        breaking=breaking,
        viewed=viewed,
    )
    order = _sort_expr().asc() if sort == "oldest" else _sort_expr().desc()
    if viewed:
        query = query.order_by(Article.view_count.desc(), order)
    else:
        query = query.order_by(order)
    return query.offset(offset).limit(limit).all()


def serialize_card(article: Article, tax: ArticleTaxonomyResolution) -> dict:
    sport = tax.resolved_sport
    competition = tax.resolved_competition
    kind = tax.hero_media_kind or "UNKNOWN"
    image = article.image_url if kind != "MISSING" else None
    return {
        "id": article.id,
        "title": sanitize_title(article.title),
        "slug": article.slug,
        "sport": sport,
        "league": competition,
        "country": article.country,
        "division": article.division,
        "image_url": image,
        "summary": public_summary(article.summary, title=article.title),
        "created_at": article.created_at,
        "published_at": article.published_at or article.created_at,
        "ai_generated": bool(getattr(article, "ai_generated", False)),
        "is_breaking": bool(getattr(article, "is_breaking", False)),
        "sport_label": sport_label(sport) if sport else None,
        "league_label": competition_label(competition) if competition else None,
        "country_label": country_label(article.country),
        "quality_ok": bool(tax.quality_ok),
        "sport_match_ok": bool(tax.public_ok),
        "hero_media_kind": kind,
    }


def serialize_cards(pairs: Sequence[PublicPair]) -> List[dict]:
    return [serialize_card(article, tax) for article, tax in pairs]


def stored_resolution(article: Article, tax: Optional[ArticleTaxonomyResolution]):
    if tax is not None:
        return cache_row_to_resolution(tax)
    return TaxonomyResolution(
        sport=getattr(article, "sport", None),
        competition=getattr(article, "league", None),
        sport_confidence=0.5 if getattr(article, "sport", None) else 0.0,
        competition_confidence=0.0,
        evidence=["stored-unindexed"],
    )


def serialize_detail(
    article: Article,
    tax: Optional[ArticleTaxonomyResolution],
    media_rows=None,
    related_insert=None,
) -> dict:
    resolved = stored_resolution(article, tax)
    raw_body = article.ai_content or article.content or article.summary
    title = sanitize_title(article.title)
    summary = public_summary(article.summary, title=article.title)
    body = sanitize_body(raw_body, title=article.title)
    if summary and body:
        prefix = summary[: min(48, len(summary))].lower()
        if prefix and body.lower().startswith(prefix):
            summary = ""
    media = public_media_items(article.image_url, media_rows)
    blocks, media = lift_hero_caption(to_blocks(raw_body, title=article.title), media)
    blocks = attach_inline_media(blocks, media)
    blocks = maybe_related_insert(blocks, related_insert)
    blocks = scrub_public_blocks(blocks)
    hero = next((item for item in media if item.get("is_hero")), media[0] if media else None)
    hero_kind = (
        (tax.hero_media_kind if tax is not None else None)
        or (hero or {}).get("presentation")
        or classify_media_url(article.image_url)
    )
    words = len((body or "").split())
    inline = sum(1 for item in media if not item.get("is_hero"))
    if words < 220:
        presentation = "brief"
    elif words >= 900 or inline:
        presentation = "major"
    else:
        presentation = "standard"
    quality_ok = bool(tax.quality_ok) if tax is not None else True
    sport_match_ok = bool(tax.public_ok) if tax is not None else bool(resolved.sport)
    return {
        "id": article.id,
        "title": title,
        "slug": article.slug,
        "sport": resolved.sport,
        "league": resolved.public_competition,
        "country": article.country,
        "division": article.division,
        "image_url": hero["url"] if hero and hero_kind != "MISSING" else None,
        "summary": summary,
        "created_at": article.created_at,
        "published_at": article.published_at or article.created_at,
        "ai_generated": bool(getattr(article, "ai_generated", False)),
        "is_breaking": bool(getattr(article, "is_breaking", False)),
        "sport_label": sport_label(resolved.sport) if resolved.sport else None,
        "league_label": competition_label(resolved.public_competition)
        if resolved.public_competition
        else None,
        "country_label": country_label(article.country),
        "quality_ok": quality_ok,
        "sport_match_ok": sport_match_ok,
        "hero_media_kind": hero_kind,
        "content": body,
        "blocks": blocks,
        "media": media,
        "reading_time_minutes": max(1, round(max(words, 1) / 220)),
        "presentation_type": presentation,
    }


def neighbor_article(db: Session, article: Article, tax: Optional[ArticleTaxonomyResolution], newer: bool):
    if tax is None or not tax.resolved_sport:
        return None
    stamp = article.published_at or article.created_at
    if stamp is None:
        return None
    stamp_col = _sort_expr()
    query = apply_scope(
        public_query(db, cards=True),
        sport=tax.resolved_sport,
    ).filter(Article.id != article.id)
    if newer:
        query = query.filter(stamp_col > stamp).order_by(stamp_col.asc())
    else:
        query = query.filter(stamp_col < stamp).order_by(stamp_col.desc())
    if tax.resolved_competition:
        match = query.filter(
            ArticleTaxonomyResolution.resolved_competition == tax.resolved_competition
        ).first()
        if match:
            return match[0]
    pair = query.first()
    return pair[0] if pair else None


def related_cards(db: Session, article: Article, tax: Optional[ArticleTaxonomyResolution], limit: int = 6) -> List[dict]:
    if tax is None or not tax.resolved_sport:
        return []
    source = cache_row_to_resolution(tax)
    pairs: List[PublicPair] = []
    pool_size = max(limit * 4, 24)
    if tax.resolved_competition:
        pairs.extend(
            fetch_public(
                db,
                sport=tax.resolved_sport,
                competition=tax.resolved_competition,
                limit=pool_size,
            )
        )
    if len(pairs) < pool_size:
        seen = {article.id, *[row.id for row, _ in pairs]}
        extra = fetch_public(db, sport=tax.resolved_sport, limit=pool_size)
        for row, other in extra:
            if row.id in seen:
                continue
            pairs.append((row, other))
            seen.add(row.id)
            if len(pairs) >= pool_size:
                break
    pool = [row for row, _ in pairs if row.id != article.id]
    resolutions = {row.id: cache_row_to_resolution(other) for row, other in pairs}
    ranked = rank_related(
        article,
        source,
        pool,
        resolutions,
        quality_ok=lambda _row: True,
        isolation_ok=lambda row, sport, strict=True, resolution=None: True,
        limit=limit,
    )
    by_id = {row.id: other for row, other in pairs}
    return [serialize_card(row, by_id[row.id]) for row in ranked if row.id in by_id]
