"""Ingest RSS, classify independently, extract facts, write English NinkoSports copy."""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import feedparser
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

from .classify import classify_article
from .dedupe import existing_by_url, existing_near_duplicate
from .extract import extract_from_url, parse_feed_datetime
from .feeds import enabled_feeds
from .quality import enough_for_brief, is_english_enough, quality_check
from .rewrite_ai import parse_ai_output, write_ninkosports_story
from .taxonomy import COMPETITIONS
from .textutil import clean_text, looks_like_garbage, strip_truncation_markers

logger = logging.getLogger(__name__)

# Public filter catalog (human labels included for the API).
LEAGUE_CONFIG: List[Dict] = [
    {
        "sport": meta["sport"],
        "league": slug,
        "country": meta["country"],
        "label": meta["label"],
        "query": meta["label"],
    }
    for slug, meta in COMPETITIONS.items()
]


def clean_html_text(text: str) -> str:
    return clean_text(text)


def _extract_image_url(entry) -> Optional[str]:
    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        for m in media_content:
            url = m.get("url")
            if url:
                return url
    media_thumb = entry.get("media_thumbnail")
    if media_thumb and isinstance(media_thumb, list):
        for m in media_thumb:
            url = m.get("url")
            if url:
                return url
    links = entry.get("links") or []
    for link in links:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            url = link.get("href")
            if url:
                return url
    summary = entry.get("summary") or entry.get("description") or ""
    import re

    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if match:
        return match.group(1)
    return None


def _slugify(title: str, fallback: str = "") -> str:
    import re

    if not title:
        title = fallback or "article"
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title)
    slug = slug.strip().lower()
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:90] or "article"


def _make_unique_slug(db: Session, base_slug: str, skip_article_id: Optional[int] = None) -> str:
    slug = base_slug
    counter = 1
    while True:
        q = db.query(Article).filter(Article.slug == slug)
        if skip_article_id is not None:
            q = q.filter(Article.id != skip_article_id)
        if q.first() is None:
            return slug
        counter += 1
        slug = f"{base_slug}-{counter}"


def _fetch_feed_entries(feed_cfg: Dict, max_articles: int) -> List[Dict]:
    url = feed_cfg["url"]
    logger.info("[fetch_sources] Fetching RSS kind=%s url=%s", feed_cfg.get("kind"), url)
    feed = feedparser.parse(url)
    entries = list(feed.entries or [])
    if not entries:
        logger.warning(
            "[fetch_sources] empty/unusable RSS for %s bozo=%s — fail closed",
            url,
            getattr(feed, "bozo_exception", None),
        )
        return []
    if getattr(feed, "bozo", False):
        logger.warning(
            "[fetch_sources] RSS warning for %s: %s (using parsed entries)",
            url,
            feed.bozo_exception,
        )

    items = []
    for entry in entries[: max(1, max_articles)]:
        title = strip_truncation_markers(clean_text(entry.get("title") or ""))
        summary = strip_truncation_markers(
            clean_text(entry.get("summary") or entry.get("description") or "")
        )
        link = (entry.get("link") or "").strip()
        if not link or not title or looks_like_garbage(title):
            continue
        items.append(
            {
                "title": title,
                "summary": summary,
                "url": link,
                "image": _extract_image_url(entry),
                "published_at": parse_feed_datetime(entry),
                "feed": feed_cfg,
            }
        )
    return items


def _ingest_item(db: Session, item: Dict, use_ai: bool, max_ai_chars: int, ai_budget: int) -> tuple:
    """Returns (created_article_or_None, ai_used_bool)."""
    source_url = item["url"]
    if existing_by_url(db, source_url):
        return None, False

    published_at = item.get("published_at")
    if existing_near_duplicate(db, item["title"], published_at):
        logger.info("[fetch_sources] skip near-duplicate title: %s", item["title"][:80])
        return None, False

    rss_text = item.get("summary") or ""
    extracted, extracted_image = extract_from_url(source_url)
    facts = extracted if len(extracted) >= len(rss_text) else "\n\n".join(
        p for p in (extracted, rss_text) if p
    )
    facts = strip_truncation_markers(clean_text(facts))
    if not enough_for_brief(item["title"], facts):
        logger.info("[fetch_sources] skip insufficient facts: %s", item["title"][:80])
        return None, False

    feed = item.get("feed") or {}
    tags = classify_article(
        item["title"],
        facts,
        feed_kind=feed.get("kind") or "mixed",
        feed_sport=feed.get("sport"),
        feed_league=feed.get("league"),
        feed_country=feed.get("country"),
    )
    ok, reason = quality_check(item["title"], facts, tags.sport, require_english=False)
    if not ok:
        logger.info("[fetch_sources] skip quality=%s title=%s", reason, item["title"][:80])
        return None, False

    story_title = item["title"]
    story_body = facts
    story_summary = facts[:400]
    used_ai = False
    if use_ai and ai_budget > 0:
        raw = write_ninkosports_story(
            title=item["title"],
            facts=facts[:max_ai_chars],
            sport=tags.sport or "sports",
            league=tags.league or "",
        )
        parsed = parse_ai_output(raw or "")
        body = parsed.get("body") or ""
        title = parsed.get("title") or item["title"]
        ok_ai, reason_ai = quality_check(title, body, tags.sport, require_english=True)
        if ok_ai:
            story_title = title
            story_body = body
            story_summary = parsed.get("summary") or body.split("\n", 1)[0][:280]
            used_ai = True
        else:
            logger.info(
                "[fetch_sources] AI skipped/rejected: %s title=%s",
                reason_ai,
                item["title"][:80],
            )

    if not used_ai:
        if not is_english_enough(facts):
            logger.info(
                "[fetch_sources] skip non-English without usable AI: %s",
                item["title"][:80],
            )
            return None, False
        ok_en, reason_en = quality_check(
            story_title, story_body, tags.sport, require_english=True
        )
        if not ok_en:
            logger.info("[fetch_sources] skip english brief: %s", reason_en)
            return None, False

    image_url = item.get("image") or extracted_image
    if image_url and len(image_url) > 500:
        image_url = image_url[:500]
    slug = _make_unique_slug(db, _slugify(story_title))
    article = Article(
        external_id=source_url[:500],
        title=story_title,
        slug=slug,
        sport=tags.sport,
        league=tags.league,
        country=tags.country,
        division=1,
        image_url=image_url,
        source_url=source_url[:500],
        summary=story_summary,
        content=story_body,
        ai_content=story_body if used_ai else None,
        ai_generated=used_ai,
        is_live=True,
        published_at=published_at,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article, used_ai


def fetch_all_sports_headlines(
    max_per_league: int = 3,
    hard_limit: int = 20,
) -> List[Dict]:
    """Lightweight RSS list for legacy pipeline.py; does not write DB."""
    all_items: List[Dict] = []
    for feed in enabled_feeds():
        if len(all_items) >= hard_limit:
            break
        for item in _fetch_feed_entries(feed, max_per_league):
            tags = classify_article(item["title"], item.get("summary") or "", feed.get("kind", "mixed"))
            all_items.append(
                {
                    "title": item["title"],
                    "description": item.get("summary"),
                    "content": item.get("summary"),
                    "url": item["url"],
                    "urlToImage": item.get("image"),
                    "sport": tags.sport,
                    "league": tags.league,
                    "country": tags.country,
                }
            )
            if len(all_items) >= hard_limit:
                break
    return all_items[:hard_limit]


def fetch_and_store_all_articles(
    max_per_league: int = 3,
    hard_limit: Optional[int] = None,
    use_ai: bool = True,
    max_ai_chars: int = 3000,
    max_ai_articles: Optional[int] = None,
) -> int:
    """
    NEW pipeline only. Does not backfill historical rows.
    Returns number of articles AI-written in this run.
    """
    db = SessionLocal()
    rewritten = 0
    ai_budget = max_ai_articles if max_ai_articles is not None else 0
    created = 0
    try:
        per_feed = max(1, max_per_league)
        for feed in enabled_feeds():
            if hard_limit is not None and created >= hard_limit:
                break
            try:
                items = _fetch_feed_entries(feed, per_feed)
            except Exception as e:
                logger.error("[fetch_sources] feed error %s: %s", feed.get("url"), e)
                continue
            for item in items:
                if hard_limit is not None and created >= hard_limit:
                    break
                try:
                    article, used_ai = _ingest_item(
                        db, item, use_ai=use_ai, max_ai_chars=max_ai_chars, ai_budget=ai_budget
                    )
                except Exception as e:
                    logger.exception("[fetch_sources] item failed: %s", e)
                    db.rollback()
                    continue
                if article and article.created_at and article.created_at.date() == datetime.utcnow().date():
                    created += 1
                elif article:
                    created += 1
                if used_ai:
                    rewritten += 1
                    ai_budget = max(0, ai_budget - 1)
        return rewritten
    finally:
        db.close()
