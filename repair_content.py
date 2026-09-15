"""Repair existing public articles that stored publisher chrome.

Never called from public GET. Re-extracts from source_url when salvage fails.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from bot.extract import extract_from_url
from bot.site_chrome import is_site_chrome_text, strip_site_chrome
from editorial import evaluate_quality, public_summary, sanitize_body, sanitize_summary
from models import Article, ArticleTaxonomyResolution
from public_cache import bump_public_cache
from public_index import persist_public_article
from taxonomy_resolver import RESOLVER_VERSION

logger = logging.getLogger("ninkosports.repair_content")


def _raw_text(article: Article) -> str:
    return " ".join(
        part
        for part in (
            article.summary,
            article.content,
            article.ai_content,
        )
        if part
    )


def _usable_prose(text: str, title: Optional[str]) -> str:
    cleaned = sanitize_body(text or "", title=title)
    if not cleaned or is_site_chrome_text(cleaned):
        return ""
    quality = evaluate_quality(title=title, summary=cleaned[:280], body=cleaned)
    if quality.get("ok") or (
        "navigation" not in quality.get("flags", [])
        and quality.get("word_count", 0) >= 40
        and "weak_body" not in quality.get("flags", [])
    ):
        return cleaned
    if quality.get("word_count", 0) >= 40 and not is_site_chrome_text(cleaned):
        return cleaned
    return ""


def _hide(db: Session, article: Article) -> None:
    row = (
        db.query(ArticleTaxonomyResolution)
        .filter(ArticleTaxonomyResolution.article_id == article.id)
        .first()
    )
    if row is None:
        return
    row.public_ok = False
    row.quality_ok = False
    db.add(row)


def _write_clean(db: Session, article: Article, body: str) -> None:
    title = article.title
    article.content = body
    if article.ai_content:
        article.ai_content = body
    summary = public_summary(article.summary, title=title)
    if not summary:
        summary = sanitize_summary(body, title=title)[:280]
    article.summary = summary
    persist_public_article(db, article)


def repair_one(db: Session, article: Article, *, allow_fetch: bool = True) -> str:
    """Returns repaired|hidden|clean."""
    raw = _raw_text(article)
    if not is_site_chrome_text(raw):
        return "clean"
    salvaged = _usable_prose(strip_site_chrome(raw) or raw, article.title)
    replacement = salvaged
    source = (article.source_url or article.external_id or "").strip()
    if not replacement and allow_fetch and source.startswith("http"):
        extracted, _image = extract_from_url(source)
        replacement = _usable_prose(extracted, article.title)
    if replacement:
        _write_clean(db, article, replacement)
        return "repaired"
    _hide(db, article)
    return "hidden"


def repair_contaminated(
    db: Optional[Session] = None,
    *,
    page_size: int = 300,
    max_pages: int = 20,
    allow_fetch: bool = True,
) -> dict:
    from database import SessionLocal

    stats = {"scanned": 0, "detected": 0, "repaired": 0, "hidden": 0}
    own = db is None
    session = db or SessionLocal()
    try:
        offset = 0
        for _ in range(max_pages):
            batch = (
                session.query(Article)
                .join(
                    ArticleTaxonomyResolution,
                    ArticleTaxonomyResolution.article_id == Article.id,
                )
                .filter(
                    ArticleTaxonomyResolution.public_ok == True,  # noqa: E712
                    ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
                )
                .order_by(Article.id.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            if not batch:
                break
            offset += page_size
            for article in batch:
                stats["scanned"] += 1
                result = repair_one(session, article, allow_fetch=allow_fetch)
                if result == "clean":
                    continue
                stats["detected"] += 1
                if result == "repaired":
                    stats["repaired"] += 1
                else:
                    stats["hidden"] += 1
            if len(batch) < page_size:
                break
        session.commit()
        if stats["repaired"] or stats["hidden"]:
            bump_public_cache()
    except Exception:
        session.rollback()
        logger.exception("content repair failed")
    finally:
        if own:
            session.close()
    logger.info(
        "content repair scanned=%s detected=%s repaired=%s hidden=%s",
        stats["scanned"],
        stats["detected"],
        stats["repaired"],
        stats["hidden"],
    )
    return stats
