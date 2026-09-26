"""Ingest RSS, classify independently, extract facts, write English NinkoSports copy."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

from .news_policy import fair_news_queue, freshness_reason, original_draft_reason
from .news_budget import ai_budget_scope, configured_budget, ai_budget_exhausted
from sports_registry.sports import SPORTS
from .classify import classify_article
from .dedupe import existing_by_url, existing_near_duplicate
from .extract import extract_from_url, parse_feed_datetime, paragraphs_from_html
from .feeds import enabled_feeds
from .news_feed_http import read_news_feed
from .media_url import collect_feed_image_candidates, pick_source_image, width_from_url
from .quality import (
    enough_for_brief,
    is_dramatic_shortening,
    is_english_enough,
    quality_check,
)
from .site_chrome import is_site_chrome_text, strip_site_chrome
from .rewrite_ai import (
    ai_available,
    openai_rate_limited,
    parse_ai_output,
    reset_openai_rate_limit,
    validate_story_facts,
    write_ninkosports_story,
)
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


def select_facts(extracted: str, rss_text: str) -> str:
    """Prefer extracted article prose. Never keep publisher chrome as facts."""
    facts, _origin = source_article_facts(extracted, rss_text, source_url="")
    return facts


def source_article_facts(
    extracted: str,
    rss_text: str,
    source_url: str = "",
) -> tuple:
    """
    RSS is discovery metadata when a real article page exists.
    Returns (facts, origin) where origin is source|rss|missing-source|none.
    """
    extracted_clean = strip_site_chrome(extracted or "") or (extracted or "")
    rss_clean = strip_site_chrome(rss_text or "") or (rss_text or "")
    extracted_ok = bool(extracted_clean) and not is_site_chrome_text(extracted_clean)
    rss_ok = bool(rss_clean) and not is_site_chrome_text(rss_clean)
    if extracted_ok:
        return extracted_clean, "source"
    if (source_url or "").strip().startswith("http"):
        return "", "missing-source"
    if rss_ok:
        return rss_clean, "rss"
    return "", "none"


def _ai_story(title: str, facts: str, sport: str, league: str, max_ai_chars: int) -> tuple:
    """Returns (parsed_dict_or_None, reason). reason is ok|empty|too-short."""
    payload = facts[: max(1, max_ai_chars)]
    raw = write_ninkosports_story(title=title, facts=payload, sport=sport, league=league)
    parsed = parse_ai_output(raw or "")
    body = parsed.get("body") or ""
    if not body:
        return None, "empty"
    if is_dramatic_shortening(facts, body):
        raw = write_ninkosports_story(
            title=title,
            facts=payload,
            sport=sport,
            league=league,
            retry_for_length=True,
        )
        parsed = parse_ai_output(raw or "")
        body = parsed.get("body") or ""
        if not body or is_dramatic_shortening(facts, body):
            logger.info(
                "[fetch_sources] reject summary-sized rewrite of substantial source: %s",
                title[:80],
            )
            return None, "too-short"
        parsed["body"] = body
    facts_ok, facts_reason = validate_story_facts(title, payload, parsed)
    if not facts_ok:
        logger.info(
            "[fetch_sources] reject factual validation=%s title=%s",
            facts_reason,
            title[:80],
        )
        return None, facts_reason
    return parsed, "ok"


def _extract_image_url(entry) -> Optional[str]:
    return pick_source_image(collect_feed_image_candidates(entry))


def _extract_image_candidates(entry) -> list:
    candidates = []
    for url, width in collect_feed_image_candidates(entry):
        if not url:
            continue
        candidates.append(
            {
                "url": url,
                "source": "rss",
                "width": width or width_from_url(url),
                "in_article": False,
            }
        )
    return candidates


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
    feed = feedparser.parse(read_news_feed(url))
    entries = list(feed.entries or []) if feed.version else []
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
    for entry in entries[:100]:
        title = strip_truncation_markers(clean_text(entry.get("title") or ""))
        raw_summary = entry.get("summary") or entry.get("description") or ""
        parsed_summary = paragraphs_from_html(raw_summary)
        summary = strip_truncation_markers(
            parsed_summary or clean_text(raw_summary)
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
                "image_candidates": _extract_image_candidates(entry),
                "published_at": parse_feed_datetime(entry),
                "feed": feed_cfg,
            }
        )
    now = datetime.now(timezone.utc)
    fresh = [item for item in items if not freshness_reason(item["published_at"], now)]
    fresh.sort(key=lambda item: item["published_at"], reverse=True)
    return fresh[:max(1, max_articles)]


def _ingest_item(db: Session, item: Dict, use_ai: bool, max_ai_chars: int, ai_budget: int) -> tuple:
    """Returns (created_article_or_None, ai_used_bool)."""
    # Budget absence is never permission to publish copied source prose.
    if not use_ai or ai_budget <= 0 or openai_rate_limited():
        return None, False
    if freshness_reason(item.get("published_at"), datetime.now(timezone.utc)):
        return None, False
    source_url = item["url"]
    if existing_by_url(db, source_url):
        return None, False

    published_at = item.get("published_at")
    if existing_near_duplicate(db, item["title"], published_at):
        logger.info("[fetch_sources] skip near-duplicate title: %s", item["title"][:80])
        return None, False

    rss_text = item.get("summary") or ""
    extracted, extracted_image = extract_from_url(source_url)
    facts, origin = source_article_facts(extracted, rss_text, source_url)
    facts = strip_truncation_markers(facts)
    if origin == "missing-source" or not facts or is_site_chrome_text(facts) or not enough_for_brief(item["title"], facts):
        logger.info(
            "[fetch_sources] skip %s facts: %s",
            origin or "insufficient",
            item["title"][:80],
        )
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
    if use_ai and ai_budget > 0 and not openai_rate_limited():
        parsed, rewrite_reason = _ai_story(
            title=item["title"],
            facts=facts,
            sport=tags.sport or "sports",
            league=tags.league or "",
            max_ai_chars=max_ai_chars,
        )
        if rewrite_reason == "too-short":
            logger.info(
                "[fetch_sources] skip substantial source with summary-only rewrite: %s",
                item["title"][:80],
            )
            return None, False
        body = (parsed or {}).get("body") or ""
        title = (parsed or {}).get("title") or item["title"]
        ok_ai, reason_ai = quality_check(title, body, tags.sport, require_english=True) if body else (False, "empty-rewrite")
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
        logger.info("[fetch_sources] hold: no accepted original draft")
        return None, False
    draft_reason = original_draft_reason(
        {"title": story_title, "summary": story_summary, "body": story_body},
        item["title"], facts,
    )
    if draft_reason:
        logger.info("[fetch_sources] hold original draft: %s", draft_reason)
        return None, False

    from taxonomy_resolver import resolve_article_competition

    class _Probe:
        pass

    probe = _Probe()
    probe.title = story_title
    probe.summary = story_summary
    probe.content = story_body
    probe.ai_content = story_body if used_ai else None
    probe.sport = tags.sport
    probe.league = tags.league
    resolved = resolve_article_competition(probe)
    stamp_sport = resolved.sport
    stamp_league = resolved.public_competition

    from editorial import sanitize_body as _sanitize_body, sanitize_summary as _sanitize_summary, sanitize_title as _sanitize_title

    story_title = _sanitize_title(story_title)
    story_body = _sanitize_body(story_body, title=story_title)
    story_summary = _sanitize_summary(story_summary, title=story_title)

    from editorial import pick_article_image

    image_url = pick_article_image(
        list(item.get("image_candidates") or [])
        + (
            [{"url": extracted_image, "source": "og", "in_article": False}]
            if extracted_image
            else []
        )
    )
    if image_url and len(image_url) > 500:
        image_url = image_url[:500]
    slug = _make_unique_slug(db, _slugify(story_title))
    article = Article(
        external_id=source_url[:500],
        title=story_title,
        slug=slug,
        sport=stamp_sport,
        league=stamp_league,
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
    try:
        from public_index import persist_public_article

        persist_public_article(db, article, resolved, commit=True)
        from public_cache import bump_public_cache

        bump_public_cache()
    except Exception:
        db.rollback()
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


def _fetch_and_store_all_articles(
    max_per_league: int = 3,
    hard_limit: Optional[int] = None,
    use_ai: bool = True,
    max_ai_chars: int = 6000,
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
    reset_openai_rate_limit()
    try:
        per_feed = max(1, max_per_league)
        queued = []
        for feed in enabled_feeds():
            try:
                queued.extend(_fetch_feed_entries(feed, per_feed))
            except Exception as e:
                logger.error("[fetch_sources] feed error %s: %s", feed.get("url"), e)
        def classify_candidate(item):
            feed = item.get("feed") or {}
            return classify_article(item["title"], item.get("summary") or "",
                feed_kind=feed.get("kind", "mixed"), feed_sport=feed.get("sport"),
                feed_league=feed.get("league"), feed_country=feed.get("country"))
        queued, admission = fair_news_queue(queued, classify_candidate,
            sport_order=[row["id"] for row in SPORTS if row["active"] and row["supports_news"]])
        logger.info("[fetch_sources] eligible=%s rejected=%s", len(queued), admission)
        for item in queued:
            if ai_budget <= 0 or openai_rate_limited() or ai_budget_exhausted():
                break
            if hard_limit is not None and created >= hard_limit:
                break
            allow_ai = use_ai and ai_budget > 0 and not openai_rate_limited()
            try:
                article, used_ai = _ingest_item(
                    db,
                    item,
                    use_ai=allow_ai,
                    max_ai_chars=max_ai_chars,
                    ai_budget=ai_budget,
                )
            except Exception as e:
                logger.exception("[fetch_sources] item failed: %s", e)
                db.rollback()
                continue
            if article:
                created += 1
            if used_ai:
                rewritten += 1
                ai_budget = max(0, ai_budget - 1)
        return rewritten
    finally:
        db.close()



def fetch_and_store_all_articles(max_per_league=3, hard_limit=None, use_ai=True,
                                 max_ai_chars=6000, max_ai_articles=None):
    """Original-only ingestion with explicit attempt budget and durable ledger.

    No approved AI allowance means no feed/extraction/DB work. This does not
    activate the worker, change its interval, or authorize historical repairs.
    """
    if not use_ai or not isinstance(max_ai_articles, int) or max_ai_articles <= 0:
        return 0
    budget = configured_budget(max_ai_articles)
    if not ai_available() or not budget.can_start():
        logger.warning("[fetch_sources] permitted AI route/ledger/allowance missing; ingest not started")
        return 0
    with ai_budget_scope(budget):
        result = _fetch_and_store_all_articles(max_per_league, hard_limit, use_ai,
                                               max_ai_chars, max_ai_articles)
    logger.info("[fetch_sources] AI attempts=%s limit=%s stop=%s", budget.attempts,
                budget.max_requests, budget.blocked_reason)
    return result
