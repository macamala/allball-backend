"""Ingest RSS, classify independently, extract facts, write English NinkoSports copy."""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

import feedparser
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article
from editorial import news_image_is_publishable, pick_article_image

from .news_policy import editorial_day_reason, fair_news_queue, freshness_reason, non_article_news_reason, numeric_tokens, original_draft_reason, source_path_sport_hint
from .news_fact_guard import competition_in_source, fact_lock_reason
from .news_learning import (
    learned_rule_violation_reason,
    mark_auto_corrected,
    mark_retry,
    record_incident,
    rule_prompt_instructions,
    writer_allowed,
    writer_identity,
)
from .news_budget import active_ai_budget, ai_budget_scope, configured_budget, ai_budget_exhausted
from sports_registry.sports import SPORTS
from .classify import Classification, classify_article
from .dedupe import existing_by_url, existing_near_duplicate, unprocessed_source_items
from .extract import extract_from_url, parse_feed_datetime, paragraphs_from_html
from .feeds import enabled_feeds, news_source_is_excluded
from .news_feed_http import read_news_feed
from .news_image_http import news_image_is_reachable, news_hero_url, score_news_image_candidate
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
from .textutil import clean_text, looks_like_garbage, strip_truncation_markers, word_count

logger = logging.getLogger(__name__)
_LAST_STORY_FAILURE = ContextVar("news_last_story_failure", default={})

from .news_source_holds import (
    held_source_urls as _held_ai_source_urls,
    hold_source as _hold_ai_source,
    source_on_cooldown as _source_on_ai_cooldown,
)


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
        # Some legitimate sports publishers expose usable article text in RSS
        # while the linked page is JS-only, returns 202, or defeats the plain
        # extractor. At least 25 source words are required; deterministic and
        # second-pass fact gates still protect publication.
        if rss_ok and word_count(rss_clean) >= 25:
            return rss_clean, "rss-fallback"
        return "", "missing-source"
    if rss_ok:
        return rss_clean, "rss"
    return "", "none"


def _correction_retry_allowed(*, prefer_breadth: bool = False, force: bool = False) -> bool:
    """Conservatively preserve one request for translations when that lane is on."""
    budget = active_ai_budget()
    if budget is None:
        # Isolated callers still mirror production breadth policy.
        return not prefer_breadth
    if getattr(budget, "blocked_reason", None):
        return False
    if prefer_breadth and not force:
        # While many sports are below the coverage floor, ordinary rejected
        # drafts yield to a different sport. A direct-quote correction may force
        # one retry because it is a mechanical originality failure, not a fact guess.
        return False
    translation_reserve = 0
    if not prefer_breadth and os.getenv("NEWS_TRANSLATIONS_ENABLED") == "1":
        try:
            translation_reserve = 1 if int(os.getenv("NEWS_TRANSLATIONS_PER_CYCLE", "0")) > 0 else 0
        except ValueError:
            translation_reserve = 1
    # While multiple sports remain underfilled, reserve one complete writer +
    # validator attempt for a different sport instead of spending the whole
    # cycle correcting one rejected draft.
    breadth_reserve = 0
    source_ceiling = max(
        0,
        int(budget.max_requests) - translation_reserve - breadth_reserve,
    )
    # A full correction may consume writer + semantic-validator requests.
    return int(budget.attempts) + 2 <= source_ceiling


def _ai_story(
    title: str,
    facts: str,
    sport: str,
    league: str,
    max_ai_chars: int,
    trusted_context: str = "",
    correction_reason: str = "",
    learned_instructions: str = "",
    correction_feedback: Optional[dict] = None,
) -> tuple:
    """Returns (parsed_dict_or_None, reason). reason is ok|empty|too-short."""
    payload = facts[: max(1, max_ai_chars)]
    # Classification can infer a men's league from a shared club name. Never
    # promote that guess into writer or validator source evidence.
    league = league if competition_in_source(league, title + '\n' + payload) else ''
    _LAST_STORY_FAILURE.set({})

    def reject(reason, draft, feedback=None):
        _LAST_STORY_FAILURE.set({
            "draft": draft, "source_facts": payload[:6000],
            "validator_feedback": feedback or {},
        })
        return None, reason

    raw = write_ninkosports_story(
        title=title,
        facts=payload,
        sport=sport,
        league=league,
        correction_reason=correction_reason,
        learned_instructions=learned_instructions,
        correction_feedback=correction_feedback,
    )
    parsed = parse_ai_output(raw or "")
    body = parsed.get("body") or ""
    if not body:
        return reject("empty", parsed)
    if is_dramatic_shortening(facts, body):
        raw = write_ninkosports_story(
            title=title,
            facts=payload,
            sport=sport,
            league=league,
            retry_for_length=True,
            correction_reason=correction_reason,
            learned_instructions=learned_instructions,
            correction_feedback=correction_feedback,
        )
        parsed = parse_ai_output(raw or "")
        body = parsed.get("body") or ""
        if not body or is_dramatic_shortening(facts, body):
            logger.info(
                "[fetch_sources] reject summary-sized rewrite of substantial source: %s",
                title[:80],
            )
            return reject("too-short", parsed)
        parsed["body"] = body
    deterministic_reason = original_draft_reason(
        {
            "title": parsed.get("title") or title,
            "summary": parsed.get("summary") or body[:280],
            "body": body,
        },
        title,
        payload,
    )
    if deterministic_reason:
        feedback = None
        if deterministic_reason == "unsupported_number":
            output = "\n".join(str(parsed.get(k) or "") for k in ("title", "summary", "body"))
            missing = sorted(numeric_tokens(output) - numeric_tokens(title + "\n" + payload, include_spelled=True))
            feedback = {"unsupported_claims": ["Numeric token absent from source: " + token for token in missing[:6]],
                        "changed_names": []}
            logger.info("[fetch_sources] unsupported_numeric_tokens=%s title=%s", missing[:6], title[:80])
        logger.info(
            "[fetch_sources] reject deterministic=%s before validator title=%s",
            deterministic_reason,
            title[:80],
        )
        return reject(deterministic_reason, parsed, feedback)
    lock_reason = fact_lock_reason(
        parsed,
        title,
        payload,
        expected_sport=sport if sport and sport != "sports" else None,
        expected_league=league or None,
    )
    if lock_reason:
        logger.info(
            "[fetch_sources] reject fact-lock=%s before semantic validator title=%s",
            lock_reason,
            title[:80],
        )
        return reject(lock_reason, parsed)
    facts_ok, facts_reason = validate_story_facts(
        title, payload, parsed, trusted_context=trusted_context
    )
    if not facts_ok:
        logger.info(
            "[fetch_sources] reject factual validation=%s title=%s",
            facts_reason,
            title[:80],
        )
        from .free_ai_router import last_validation_feedback
        feedback = last_validation_feedback()
        logger.info("[fetch_sources] validation_review=%s title=%s", feedback, title[:80])
        return reject(facts_reason, parsed, feedback)
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


def _pick_reachable_article_image(candidates: list, max_checks: int = 6) -> Optional[str]:
    """Choose the best candidate that actually serves image bytes."""
    ranked = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        score = score_news_image_candidate(candidate)
        url = news_hero_url(str(candidate.get("url") or "").strip())
        if score < 0 or not url or not news_image_is_publishable(url):
            continue
        ranked.append((score, url))
    ranked.sort(key=lambda row: row[0], reverse=True)
    seen = set()
    checks = 0
    for _score, url in ranked:
        if url in seen:
            continue
        seen.add(url)
        checks += 1
        if news_image_is_reachable(url):
            return url
        if checks >= max(1, int(max_checks)):
            break
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


def _rss_publication_time(entry, feed_cfg):
    fields = {key: entry.get(key) for key in ('published', 'published_parsed')
              if entry.get(key) is not None}
    raw = fields.get('published')
    if isinstance(raw, str):
        for alias, offset in (feed_cfg.get('rss_timezone_aliases') or {}).items():
            # Only publisher-verified explicit zone names are mapped. Never
            # assign an offset to a timestamp that did not include one.
            raw = re.sub(r'\s' + re.escape(alias) + r'\s*$', ' ' + offset, raw)
        fields['published'] = raw
    return parse_feed_datetime(fields)


def _fetch_feed_entries(feed_cfg: Dict, max_articles: int) -> List[Dict]:
    url = feed_cfg["url"]
    if news_source_is_excluded(url):
        return []
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
        feed_content = entry.get("content") or []
        content_values = []
        if isinstance(feed_content, list):
            content_values = [
                str(row.get("value") or "")
                for row in feed_content
                if isinstance(row, dict) and row.get("value")
            ]
        elif isinstance(feed_content, dict) and feed_content.get("value"):
            content_values = [str(feed_content.get("value") or "")]
        parsed_candidates = []
        for raw in [raw_summary, *content_values]:
            parsed = paragraphs_from_html(raw)
            cleaned = strip_truncation_markers(parsed or clean_text(raw))
            if cleaned:
                parsed_candidates.append(cleaned)
        summary = max(parsed_candidates, key=len) if parsed_candidates else ""
        link = (entry.get("link") or "").strip()
        if feed_cfg.get("article_https_host"):
            try:
                parts = urlsplit(link)
                if (parts.hostname != feed_cfg["article_https_host"] or parts.username
                        or parts.password or parts.scheme not in {"http", "https"}
                        or parts.port not in {None, 80, 443}):
                    continue
                # This publisher advertises legacy HTTP links in its RSS. Its
                # same-path HTTPS article endpoint has been independently verified.
                link = urlunsplit(("https", parts.hostname, parts.path, parts.query, parts.fragment))
            except ValueError:
                continue
        if not link or not title or looks_like_garbage(title):
            continue
        allowed_paths = feed_cfg.get('allowed_article_paths') or ()
        excluded_paths = feed_cfg.get('excluded_article_paths') or ()
        path = urlsplit(link).path
        if ((allowed_paths and not any(path.startswith(prefix) for prefix in allowed_paths))
                or any(path.startswith(prefix) for prefix in excluded_paths)):
            continue
        if feed_cfg.get("rss_fallback_only") and word_count(summary) < 25:
            logger.info(
                "[fetch_sources] skip thin rss-only metadata: %s",
                title[:80],
            )
            continue
        items.append(
            {
                "title": title,
                "summary": summary,
                "url": link,
                "image": _extract_image_url(entry),
                "image_candidates": _extract_image_candidates(entry),
                "published_at": _rss_publication_time(entry, feed_cfg),
                "_publication_evidence": "rss-published",
                "feed": feed_cfg,
            }
        )
    now = datetime.now(timezone.utc)
    fresh = [item for item in items if not freshness_reason(item["published_at"], now)]
    fresh.sort(key=lambda item: item["published_at"], reverse=True)
    return fresh[:max(1, max_articles)]


def _collect_rss_entries(feeds, max_articles):
    """Read up to six publishers concurrently, one request per host at a time.

    Only public discovery runs in threads. AI budgets and database writes stay
    on the owning cycle thread; output order does not depend on network timing.
    """
    groups = {}
    for index, feed in enumerate(feeds):
        host = (urlsplit(feed['url']).hostname or '').lower().removeprefix('www.')
        groups.setdefault(host, []).append((index, feed))
    if not groups:
        return []

    def collect_host(rows):
        result = []
        for index, feed in rows:
            try:
                result.append((index, _fetch_feed_entries(feed, max_articles)))
            except Exception as exc:
                logger.warning('[fetch_sources] RSS held url=%s error_type=%s',
                               feed.get('url'), type(exc).__name__)
        return result

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(6, len(groups))) as pool:
        collected = [row for group in pool.map(collect_host, groups.values()) for row in group]
    items = [item for _, entries in sorted(collected, key=lambda row: row[0]) for item in entries]
    logger.info('[fetch_sources] RSS discovery feeds=%s hosts=%s candidates=%s elapsed=%.1fs',
                len(feeds), len(groups), len(items), time.monotonic() - started)
    return items


def _reconcile_public_taxonomy(tags, resolved, feed: Dict):
    """Preserve source-proven sport unless rewritten copy supplies a contradiction."""
    from taxonomy_resolver import TaxonomyResolution

    trusted_feed = (
        feed.get("kind") == "league"
        and feed.get("sport")
        and feed.get("sport") == tags.sport
    )
    if resolved.sport and tags.sport and resolved.sport != tags.sport:
        return None, "taxonomy-conflict"

    if not resolved.sport and tags.sport:
        competition = None
        competition_confidence = 0.0
        evidence = [f"source-classifier-sport:{getattr(tags, 'reason', 'evidence')}"]
        if trusted_feed and feed.get("league") and tags.league == feed.get("league"):
            competition = tags.league
            competition_confidence = 0.86
            evidence.append("trusted-dedicated-feed-competition")
        confidence = {
            "high": 0.92,
            "medium": 0.84,
            "low": 0.76,
        }.get(getattr(tags, "confidence", None), 0.76)
        resolved = TaxonomyResolution(
            sport=tags.sport,
            competition=competition,
            sport_confidence=confidence,
            competition_confidence=competition_confidence,
            evidence=evidence,
        )

    if not resolved.sport:
        return None, "taxonomy-unresolved-after-rewrite"
    return resolved, None


def _source_grounded_resolution(resolved, title: str, facts: str):
    from taxonomy_resolver import TaxonomyResolution
    competition = resolved.public_competition
    if competition in COMPETITIONS and not competition_in_source(competition, title + '\n' + facts):
        return TaxonomyResolution(sport=resolved.sport, competition=None,
            sport_confidence=resolved.sport_confidence, competition_confidence=0.0,
            evidence=list(getattr(resolved, 'evidence', [])) + ['unsupported-inferred-competition-cleared'])
    return resolved


def _ingest_item(
    db: Session,
    item: Dict,
    use_ai: bool,
    max_ai_chars: int,
    ai_budget: int,
    *,
    prefer_breadth: bool = False,
    first_coverage: bool = False,
) -> tuple:
    """Returns (created_article_or_None, ai_used_bool)."""
    if news_source_is_excluded(item.get("url")):
        return None, False
    # Budget absence is never permission to publish copied source prose.
    if not use_ai or ai_budget <= 0 or openai_rate_limited():
        return None, False
    if freshness_reason(
        item.get("published_at"),
        datetime.now(timezone.utc),
        max_age_hours=24,
    ) or editorial_day_reason(
        item.get("published_at"),
        datetime.now(timezone.utc),
        os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney",
    ):
        return None, False
    source_url = item["url"]
    if existing_by_url(db, source_url):
        return None, False

    if _source_on_ai_cooldown(source_url):
        logger.info("[fetch_sources] skip AI cooldown: %s", item["title"][:80])
        return None, False

    published_at = item.get("published_at")
    if existing_near_duplicate(db, item["title"], published_at):
        logger.info("[fetch_sources] skip near-duplicate title: %s", item["title"][:80])
        return None, False

    rss_text = item.get("summary") or ""
    extracted = item.get("_extracted") or ""
    extracted_image = item.get("_extracted_image")
    if not extracted:
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

    image_candidates = list(item.get("image_candidates") or [])
    if extracted_image:
        image_candidates.append(
            {"url": extracted_image, "source": "og", "in_article": False}
        )
    # Article.image_url is VARCHAR(500). Never publish a truncated/broken source
    # image URL; choose only candidates that can be stored intact.
    image_candidates = [
        candidate
        for candidate in image_candidates
        if isinstance(candidate, dict)
        and 0 < len(str(candidate.get("url") or "").strip()) <= 500
    ]
    image_url = _pick_reachable_article_image(image_candidates)
    if not image_url:
        # RSS extraction historically returned only one chosen image. When it
        # is dead/a logo/a thumbnail, try the other real images on this SAME
        # article before holding it. No AI requests are spent on this repair.
        from .extract import extract_image_candidates_from_url
        alternatives = extract_image_candidates_from_url(source_url)
        image_url = _pick_reachable_article_image([
            row for row in alternatives
            if 0 < len(str(row.get("url") or "")) <= 500
        ])
    if not news_image_is_publishable(image_url):
        _hold_ai_source(source_url, "missing-or-unreachable-publishable-image")
        logger.info(
            "[fetch_sources] hold image reason=missing-or-unreachable-publishable-image title=%s",
            item["title"][:80],
        )
        return None, False

    feed = item.get("feed") or {}
    tags = _classify_item(item, facts)
    ok, reason = quality_check(item["title"], facts, tags.sport, require_english=False)
    if not ok:
        logger.info("[fetch_sources] skip quality=%s title=%s", reason, item["title"][:80])
        return None, False

    story_title = item["title"]
    story_body = facts
    story_summary = facts[:400]
    used_ai = False
    rewrite_reason = None
    if use_ai and ai_budget > 0 and not openai_rate_limited():
        trusted_feed = (
            feed.get("kind") == "league"
            and feed.get("sport")
            and feed.get("sport") == tags.sport
        )
        trusted_context = (
            f"VERIFIED DEDICATED FEED SPORT: {tags.sport}."
            if trusted_feed else ""
        )
        learned_instructions, learned_rule_ids = (
            rule_prompt_instructions(db, source_url=source_url, sport=tags.sport)
            if isinstance(db, Session)
            else ("", [])
        )
        _LAST_STORY_FAILURE.set({})
        parsed, rewrite_reason = _ai_story(
            title=item["title"],
            facts=facts,
            sport=tags.sport or "sports",
            league=tags.league or "",
            max_ai_chars=max_ai_chars,
            trusted_context=trusted_context,
            learned_instructions=learned_instructions,
        )
        provider, model = writer_identity()
        if isinstance(db, Session) and not writer_allowed(db, provider, model):
            logger.error(
                "[fetch_sources] writer circuit open provider=%s model=%s",
                provider,
                model,
            )
            return None, False
        if parsed and isinstance(db, Session):
            learned_violation = learned_rule_violation_reason(
                db, parsed, source_url=source_url, sport=tags.sport
            )
            if learned_violation:
                parsed = None
                rewrite_reason = learned_violation

        incident = None
        if rewrite_reason != "ok":
            failure = _LAST_STORY_FAILURE.get()
            feedback = failure.get("validator_feedback") or {}
            if isinstance(db, Session):
                incident = record_incident(
                    db,
                    reason_code=rewrite_reason or "missing-draft",
                    source_url=source_url,
                    sport=tags.sport,
                    phase="prepublish",
                    draft=parsed or failure.get("draft"),
                    writer_provider=provider,
                    writer_model=model,
                    details={"learned_rule_ids": learned_rule_ids,
                             "source_facts": failure.get("source_facts", ""),
                             "validator_feedback": feedback},
                )
            # One bounded self-correction. It still passes the same deterministic
            # and semantic validator gates inside _ai_story.
            if (
                rewrite_reason not in {"empty", "too-short"}
                and not str(rewrite_reason or '').startswith('validator-source-type:')
                and not openai_rate_limited()
                and not ai_budget_exhausted()
                and _correction_retry_allowed(
                    prefer_breadth=prefer_breadth,
                    force=(
                        rewrite_reason in {
                            "direct_quote_requires_review",
                            "headline_too_similar_to_source",
                            "copied_source_headline",
                        }
                        or str(rewrite_reason or "").startswith("draft_sport_mismatch:")
                        or (
                            (tags.sport in {"football", "basketball"} or first_coverage)
                            and rewrite_reason in {"validator-unsupported-claim", "validator-changed-name", "unsupported_number"}
                            and any(feedback.values())
                            and active_ai_budget() is not None
                            and active_ai_budget().max_requests - active_ai_budget().attempts >= 4
                        )
                    ),
                )
            ):
                retry_parsed, retry_reason = _ai_story(
                    title=item["title"],
                    facts=facts,
                    sport=tags.sport or "sports",
                    league=tags.league or "",
                    max_ai_chars=max_ai_chars,
                    trusted_context=trusted_context,
                    correction_reason=rewrite_reason or "validation-failed",
                    learned_instructions=learned_instructions,
                    correction_feedback=feedback,
                )
                if retry_parsed and isinstance(db, Session):
                    retry_violation = learned_rule_violation_reason(
                        db, retry_parsed, source_url=source_url, sport=tags.sport
                    )
                    if retry_violation:
                        retry_parsed = None
                        retry_reason = retry_violation
                if retry_reason == "ok" and retry_parsed:
                    parsed = retry_parsed
                    rewrite_reason = "ok"
                    if incident is not None:
                        mark_auto_corrected(
                            db,
                            incident,
                            note="corrective rewrite passed deterministic and semantic fact gates",
                        )
                else:
                    rewrite_reason = retry_reason or "retry-failed"
                    if incident is not None:
                        mark_retry(db, incident, rewrite_reason)

        if rewrite_reason == "too-short":
            _hold_ai_source(source_url, "too-short")
            logger.info(
                "[fetch_sources] skip substantial source with summary-only rewrite: %s",
                item["title"][:80],
            )
            return None, False

        body = (parsed or {}).get("body") or ""
        title = (parsed or {}).get("title") or item["title"]
        ok_ai, reason_ai = quality_check(
            title, body, tags.sport, require_english=True
        ) if body else (False, "empty-rewrite")
        if ok_ai and rewrite_reason == "ok":
            story_title = title
            story_body = body
            story_summary = parsed.get("summary") or body.split("\n", 1)[0][:280]
            used_ai = True
        else:
            if isinstance(db, Session) and rewrite_reason == "ok":
                record_incident(
                    db,
                    reason_code=f"quality:{reason_ai}",
                    source_url=source_url,
                    sport=tags.sport,
                    phase="prepublish-quality",
                    draft=parsed,
                    writer_provider=provider,
                    writer_model=model,
                )
            logger.info(
                "[fetch_sources] AI skipped/rejected: %s title=%s",
                rewrite_reason or reason_ai,
                item["title"][:80],
            )

    if not used_ai:
        hold_reason = rewrite_reason or "no-accepted-original-draft"
        if hold_reason not in {"validator-unavailable", "validator-independent-unavailable", "empty"}:
            _hold_ai_source(source_url, hold_reason)
        else:
            logger.info("[fetch_sources] transient AI failure not cooldowned: %s", hold_reason)
        logger.info("[fetch_sources] hold: no accepted original draft")
        return None, False
    draft_reason = original_draft_reason(
        {"title": story_title, "summary": story_summary, "body": story_body},
        item["title"], facts,
    )
    if draft_reason:
        _hold_ai_source(source_url, draft_reason)
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
    rewritten_sport = resolved.sport
    resolved, taxonomy_reason = _reconcile_public_taxonomy(tags, resolved, feed)
    if taxonomy_reason:
        _hold_ai_source(source_url, taxonomy_reason)
        logger.info(
            "[fetch_sources] hold taxonomy reason=%s classified=%s rewritten=%s title=%s",
            taxonomy_reason,
            tags.sport or "unknown",
            rewritten_sport or "unknown",
            item["title"][:80],
        )
        return None, False
    resolved = _source_grounded_resolution(resolved, item['title'], facts)
    stamp_sport = resolved.sport
    stamp_league = resolved.public_competition

    from editorial import sanitize_body as _sanitize_body, sanitize_summary as _sanitize_summary, sanitize_title as _sanitize_title

    story_title = _sanitize_title(story_title)
    story_body = _sanitize_body(story_body, title=story_title)
    story_summary = _sanitize_summary(story_summary, title=story_title)

    if editorial_day_reason(published_at, datetime.now(timezone.utc),
            os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney"):
        logger.info('[fetch_sources] hold: source editorial day changed before publication')
        return None, False
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
        published_at=published_at.astimezone(timezone.utc).replace(tzinfo=None),
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    try:
        from public_index import persist_public_article

        persist_public_article(db, article, resolved, commit=True)
        from public_read import public_query

        if public_query(db).filter(Article.id == article.id).first() is None:
            from editorial import evaluate_quality
            quality = evaluate_quality(title=article.title, summary=article.summary,
                body=article.ai_content or article.content, image_url=article.image_url)
            logger.info("[fetch_sources] hold public admission id=%s sport=%s confidence=%s quality_flags=%s",
                article.id, resolved.sport, resolved.sport_confidence, quality.get("flags"))
            return None, False
        from public_cache import bump_public_cache

        bump_public_cache()
    except Exception:
        db.rollback()
        logger.exception("[fetch_sources] hold: public admission could not be verified")
        return None, False
    logger.info(
        "[fetch_sources] published id=%s sport=%s slug=%s title=%s source_published_at=%s stored_published_at=%s",
        article.id,
        stamp_sport or "unknown",
        article.slug,
        (article.title or "")[:120],
        published_at,
        article.published_at,
    )
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


def _classify_item(item, evidence):
    feed = item.get("feed") or {}
    tags = classify_article(
        item["title"],
        evidence or "",
        feed_kind=feed.get("kind", "mixed"),
        feed_sport=feed.get("sport"),
        feed_league=feed.get("league"),
        feed_country=feed.get("country"),
    )
    if getattr(tags, "reason", "") == "unsupported-news-sport":
        return tags
    hinted = source_path_sport_hint(item.get("url"))
    if not hinted or tags.sport == hinted:
        return tags
    from .news_policy import explicit_headline_sport
    explicit = explicit_headline_sport(item.get('title'))
    if explicit and explicit != hinted:
        return Classification(explicit, tags.league if tags.sport == explicit else None,
            feed.get('country'), 'high', 'explicit-headline-sport')
    return Classification(
        sport=hinted,
        league=None,
        country=feed.get("country"),
        confidence="medium",
        reason="trusted-source-path",
    )


def _classify_candidate(item):
    evidence = item.get("_classification_text") or item.get("summary") or ""
    return _classify_item(item, evidence)


def _enrich_unknown_candidates(items, limit=12):
    """Bounded source-body enrichment for useful mixed-feed headlines with no sport.

    Reject non-article products first, then spend the small extraction allowance
    on candidates whose feed already supplies a sport hint. This avoids wasting
    discovery work on podcasts/scorecards while leaving final classification
    dependent on article evidence.
    """
    pending = []
    for candidate in items:
        if non_article_news_reason(candidate):
            continue
        try:
            candidate_tags = _classify_candidate(candidate)
        except Exception:
            continue
        if candidate_tags.sport is not None or not candidate.get("url"):
            continue
        feed = candidate.get("feed") or {}
        pending.append(candidate)

    pending.sort(
        key=lambda candidate: (
            1 if (candidate.get("feed") or {}).get("sport") else 0,
            1 if candidate.get("image_candidates") or candidate.get("image") else 0,
            candidate.get("published_at") or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    enriched = 0
    for candidate in pending[: max(0, int(limit))]:
        try:
            extracted, extracted_image = extract_from_url(candidate["url"])
        except Exception:
            continue
        if not extracted:
            continue
        candidate["_extracted"] = extracted
        candidate["_extracted_image"] = extracted_image
        candidate["_classification_text"] = extracted
        enriched += 1
    return enriched


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
        from .news_publication_clock import ensure_news_publication_clock, repair_verified_source_times
        ensure_news_publication_clock(db)
        per_feed = max(1, max_per_league)
        # Scan deeper in each downloaded feed, without serially waiting on
        # unrelated publishers. AI and publication limits are unchanged.
        queued = _collect_rss_entries(enabled_feeds(), max(per_feed, 20))
        if os.getenv("NEWS_EXPANDED_FEEDS_ENABLED") == "1":
            try:
                from .news_official_indexes import fetch_official_index_entries

                queued.extend(fetch_official_index_entries(per_feed))
            except Exception as e:
                logger.error("[fetch_sources] official index error: %s", type(e).__name__)
        if os.getenv("NEWS_ESPN_NEWS_JSON_ENABLED") == "1":
            try:
                from .news_espn_api import fetch_espn_news_entries

                queued.extend(fetch_espn_news_entries(12))
            except Exception as e:
                logger.error("[fetch_sources] ESPN News JSON discovery error: %s", type(e).__name__)
        if os.getenv("NEWS_NEWSAPI_ORG_ENABLED") == "1":
            try:
                from .news_newsapi_org import fetch_newsapi_org_entries

                queued.extend(fetch_newsapi_org_entries(100))
            except Exception as e:
                logger.error("[fetch_sources] NewsAPI.org discovery error: %s", type(e).__name__)
        if os.getenv("NEWS_NEWSAPI_AI_ENABLED") == "1":
            try:
                from .news_aggregator import fetch_newsapi_ai_entries

                queued.extend(fetch_newsapi_ai_entries(100))
            except Exception as e:
                logger.error("[fetch_sources] NewsAPI.ai discovery error: %s", type(e).__name__)
        repair_verified_source_times(db, queued)
        before_known = len(queued)
        queued = unprocessed_source_items(db, queued)
        logger.info("[fetch_sources] prequeue known-source-filtered=%s remaining=%s",
                    before_known - len(queued), len(queued))

        # Mixed feeds often have a headline with no sport word even though the
        # actual article body is unambiguous. Enrich only a small bounded set
        # before fair-queue admission. This spends no AI requests, and the same
        # extracted body is reused later by _ingest_item.
        enriched_unknown = _enrich_unknown_candidates(queued, limit=12)
        if enriched_unknown:
            logger.info(
                "[fetch_sources] enriched unknown-sport candidates=%s",
                enriched_unknown,
            )

        held_urls = _held_ai_source_urls(
            [candidate.get("url") for candidate in queued if candidate.get("url")]
        )
        if held_urls:
            before = len(queued)
            queued = [
                candidate
                for candidate in queued
                if candidate.get("url") not in held_urls
            ]
            logger.info(
                "[fetch_sources] prequeue cooldown-filtered=%s remaining=%s",
                before - len(queued),
                len(queued),
            )

        unknown_samples = []
        for candidate in queued:
            if len(unknown_samples) >= 10:
                break
            if non_article_news_reason(candidate):
                continue
            try:
                candidate_tags = _classify_candidate(candidate)
            except Exception:
                continue
            if candidate_tags.sport is None:
                meta = candidate.get("feed") or {}
                unknown_samples.append({
                    "title": str(candidate.get("title") or "")[:120],
                    "feed_sport": meta.get("sport"),
                    "feed_kind": meta.get("kind"),
                    "publisher": meta.get("publisher"),
                    "url": str(candidate.get("url") or "")[:180],
                })
        if unknown_samples:
            logger.info("[fetch_sources] unknown_sport_samples=%s", unknown_samples)

        from public_index import (
            recent_public_sport_inventory,
            repair_recent_duplicate_news,
            repair_recent_gossip_news,
            repair_recent_news_images,
            repair_recent_sport_mislabels,
            repair_recent_unresolved,
        )

        # Self-heal taxonomy first, re-evaluate valid held rows, and run dedupe
        # last so no re-index can resurrect a duplicate. Zero AI is spent here.
        repair_started = time.monotonic()
        images = repair_recent_news_images(db, limit=80, max_age_hours=72, recover_limit=8)
        after_images = time.monotonic()
        mislabels = repair_recent_sport_mislabels(db, limit=600, max_age_hours=168)
        after_mislabels = time.monotonic()
        repaired = repair_recent_unresolved(db, limit=24)
        after_unresolved = time.monotonic()
        gossip = repair_recent_gossip_news(db, limit=600, max_age_hours=168)
        after_gossip = time.monotonic()
        duplicates = repair_recent_duplicate_news(db, limit=600, max_age_hours=168)
        after_dedupe = time.monotonic()
        sport_inventory = recent_public_sport_inventory(db, max_age_hours=24,
            editorial_timezone=os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney")
        logger.info(
            "[fetch_sources] repair phases images=%s %.3fs mislabels=%s %.3fs "
            "unresolved=%s %.3fs gossip=%s %.3fs duplicates=%s %.3fs inventory=%.3fs",
            images,
            after_images - repair_started,
            mislabels,
            after_mislabels - after_images,
            repaired,
            after_unresolved - after_mislabels,
            gossip,
            after_gossip - after_unresolved,
            duplicates,
            after_dedupe - after_gossip,
            time.monotonic() - after_dedupe,
        )
        queued, admission = fair_news_queue(
            queued,
            _classify_candidate,
            max_age_hours=24,
            same_day_timezone=os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney",
            sport_order=[
                row["id"]
                for row in SPORTS
                if row["active"] and row["supports_news"]
            ],
            sport_inventory=sport_inventory,
            coverage_floor=6,
            prioritize_major_sports=True,
        )
        candidate_sports = {}
        for candidate in queued:
            try:
                sport = _classify_candidate(candidate).sport
            except Exception:
                sport = None
            if sport:
                candidate_sports[sport] = candidate_sports.get(sport, 0) + 1
        cycle_budget = active_ai_budget()

        def update_coverage_debt():
            debt = sum(1 for sport in candidate_sports
                if sport_inventory.get(sport, 0) < {"football": 12, "basketball": 8}.get(sport, 6))
            if cycle_budget is not None:
                cycle_budget.english_coverage_debt = debt
            return debt

        update_coverage_debt()
        logger.info(
            "[fetch_sources] eligible=%s rejected=%s current_sport_inventory=%s candidate_sports=%s",
            len(queued),
            admission,
            sport_inventory,
            candidate_sports,
        )
        logger.info("[fetch_sources] editorial_queue_front=%s", [
            {"sport": _classify_candidate(item).sport, "title": item["title"][:90]}
            for item in queued[:8]
        ])
        active_news_sports = [
            row["id"]
            for row in SPORTS
            if row["active"] and row["supports_news"]
        ]
        coverage_debt = sum(
            1 for sport in active_news_sports
            if int(sport_inventory.get(sport, 0) or 0) < 6
        )
        prefer_breadth = coverage_debt > 1
        for item in queued:
            if ai_budget <= 0 or openai_rate_limited() or ai_budget_exhausted():
                break
            active_budget = active_ai_budget()
            if (active_budget is not None
                    and (active_budget.max_requests - active_budget.attempts) < 2):
                logger.info("[fetch_sources] holding final request: an original needs a writer and validator")
                break
            if (
                not prefer_breadth
                and os.getenv("NEWS_TRANSLATIONS_ENABLED") == "1"
                and int(os.getenv("NEWS_TRANSLATIONS_PER_CYCLE", "0") or "0") > 0
                and active_budget is not None
                and (active_budget.max_requests - active_budget.attempts) < 3
            ):
                logger.info("[fetch_sources] preserving final AI request for translation")
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
                    prefer_breadth=prefer_breadth,
                    first_coverage=sport_inventory.get(_classify_candidate(item).sport, 0) == 0,
                )
            except Exception as e:
                logger.exception("[fetch_sources] item failed: %s", e)
                db.rollback()
                continue
            if article:
                created += 1
                sport_inventory[article.sport] = sport_inventory.get(article.sport, 0) + 1
            if used_ai:
                rewritten += 1
                ai_budget = max(0, ai_budget - 1)
        logger.info("[fetch_sources] remaining English coverage debt=%s candidate_sports=%s",
            update_coverage_debt(), len(candidate_sports))
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
    budget = active_ai_budget() or configured_budget(max_ai_articles)
    if not ai_available() or not budget.can_start():
        logger.warning("[fetch_sources] permitted AI route/ledger/allowance missing; ingest not started")
        return 0
    with ai_budget_scope(budget):
        result = _fetch_and_store_all_articles(max_per_league, hard_limit, use_ai,
                                               max_ai_chars, max_ai_articles)
    logger.info("[fetch_sources] AI attempts=%s limit=%s stop=%s", budget.attempts,
                budget.max_requests, budget.blocked_reason)
    return result
