"""Repair existing public articles that stored publisher chrome.

Never called from public GET. Historical scanning is explicit opt-in; no raw source fallback.
"""

from __future__ import annotations

import logging
import os

from bot.news_policy import original_draft_reason
from bot.news_budget import ai_budget_exhausted
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
    # Keep the legacy allow_fetch argument for callers, but never fetch/paste
    # publisher prose. Unsalvageable existing copy is held rather than replaced.
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
    if os.getenv("NEWS_HISTORICAL_REPAIR_ENABLED") != "1":
        stats["disabled"] = True
        return stats
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


def _stored_body(article: Article) -> str:
    return article.ai_content or article.content or article.summary or ""


def repair_summary_one(db: Session, article: Article) -> str:
    """Rewrite a summary-only public article from its source page. Returns rewritten|skipped|clean."""
    from bot.fetch_sources import _ai_story
    from bot.quality import (
        is_dramatic_shortening,
        is_english_enough,
        is_substantial_source,
        needs_full_source_repair,
        quality_check,
        word_count,
    )
    from bot.rewrite_ai import openai_rate_limited
    from editorial import sanitize_body, sanitize_summary, sanitize_title

    if ai_budget_exhausted():
        return "skipped"
    stored = _stored_body(article)
    source = (article.source_url or article.external_id or "").strip()
    if not source.startswith("http"):
        return "skipped"
    extracted, _image = extract_from_url(source)
    extracted = strip_site_chrome(extracted or "") or (extracted or "")
    if is_site_chrome_text(extracted):
        extracted = ""
    extracted_n = word_count(extracted)
    stored_n = word_count(stored)
    if not needs_full_source_repair(stored, extracted):
        if extracted_n >= 80:
            logger.info(
                "summary-repair skip slug=%s stored_words=%s extracted_words=%s",
                article.slug,
                stored_n,
                extracted_n,
            )
        return "clean"

    def _store(body: str, *, used_ai: bool, title: str) -> bool:
        title = sanitize_title(title)
        body = sanitize_body(body, title=title)
        if not body or is_dramatic_shortening(extracted, body):
            return False
        if not is_english_enough(body):
            return False
        article.title = title
        article.content = body
        article.ai_content = body if used_ai else None
        article.ai_generated = used_ai
        article.summary = sanitize_summary(body, title=title)[:280]
        persist_public_article(db, article)
        logger.info(
            "summary-repair stored slug=%s used_ai=%s stored_words=%s extracted_words=%s output_words=%s",
            article.slug,
            used_ai,
            stored_n,
            extracted_n,
            word_count(body),
        )
        return True

    if openai_rate_limited():
        logger.info("summary-repair ai-limited slug=%s", article.slug)
        return "skipped"
    parsed, reason = _ai_story(
        title=article.title or "",
        facts=extracted,
        sport=article.sport or "sports",
        league=article.league or "",
        max_ai_chars=6000,
    )
    body = (parsed or {}).get("body") or ""
    title = (parsed or {}).get("title") or article.title
    if reason == "ok" and body:
        ok, _why = quality_check(title, body, article.sport, require_english=True)
        draft = {"title": title, "summary": (parsed or {}).get("summary") or body[:280], "body": body}
        if ok and not original_draft_reason(draft, article.title or "", extracted) and _store(body, used_ai=True, title=title):
            return "rewritten"
    return "skipped"


def repair_summary_only(
    db: Optional[Session] = None,
    *,
    page_size: int = 80,
    max_pages: int = 8,
    max_rewrite: int = 8,
) -> dict:
    """Background pass for summary-sized public articles. Never called from GET."""
    from database import SessionLocal

    stats = {"scanned": 0, "candidates": 0, "rewritten": 0, "skipped": 0}
    if os.getenv("NEWS_HISTORICAL_REPAIR_ENABLED") != "1":
        stats["disabled"] = True
        return stats
    own = db is None
    session = db or SessionLocal()
    try:
        offset = 0
        for _ in range(max_pages):
            if stats["rewritten"] >= max_rewrite:
                break
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
                if stats["rewritten"] >= max_rewrite:
                    break
                stats["scanned"] += 1
                stored = _stored_body(article)
                from bot.quality import MIN_SOURCE_WORDS, word_count

                if word_count(stored) >= MIN_SOURCE_WORDS:
                    continue
                source = (article.source_url or article.external_id or "").strip()
                if not source.startswith("http"):
                    continue
                stats["candidates"] += 1
                result = repair_summary_one(session, article)
                if result == "rewritten":
                    stats["rewritten"] += 1
                elif result == "skipped":
                    stats["skipped"] += 1
            if len(batch) < page_size:
                break
        session.commit()
        if stats["rewritten"]:
            bump_public_cache()
    except Exception:
        session.rollback()
        logger.exception("summary-only repair failed")
    finally:
        if own:
            session.close()
    logger.info(
        "summary repair scanned=%s candidates=%s rewritten=%s skipped=%s",
        stats["scanned"],
        stats["candidates"],
        stats["rewritten"],
        stats["skipped"],
    )
    return stats
