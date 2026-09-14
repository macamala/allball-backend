"""Internal taxonomy QA counts. Never exposed on public API payloads."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence

from editorial import classify_media_url, evaluate_quality, has_nav_contamination, suitable_for_lead_hero
from sport_match import MAIN_SPORTS
from taxonomy_resolver import MIN_SPORT_CONFIDENCE, resolve_article_competition

logger = logging.getLogger("ninkosports.taxonomy_audit")


def _resolved_of(article, resolutions: Optional[dict]):
    article_id = getattr(article, "id", None)
    if resolutions and article_id in resolutions:
        return resolutions[article_id]
    return resolve_article_competition(article)


def audit_article_sample(articles: Sequence, resolutions: Optional[dict] = None) -> Dict[str, int]:
    counts = {
        "total_candidates": 0,
        "resolved_football": 0,
        "resolved_basketball": 0,
        "resolved_tennis": 0,
        "resolved_motorsport": 0,
        "unknown": 0,
        "rejected_contamination": 0,
        "rejected_sport_mismatch": 0,
        "rejected_low_confidence": 0,
        "rejected_duplicate": 0,
        "rejected_bad_media_for_hero": 0,
        "sport_disagreements": 0,
        "competition_disagreements": 0,
        "source_chrome_contamination": 0,
        "duplicate_headline_body_starts": 0,
        "bad_unknown_hero_media": 0,
    }
    seen_titles = set()
    for article in articles:
        counts["total_candidates"] += 1
        resolved = _resolved_of(article, resolutions)
        stored_sport = getattr(article, "sport", None)
        stored_league = getattr(article, "league", None)
        quality = evaluate_quality(
            title=getattr(article, "title", None),
            summary=getattr(article, "summary", None),
            body=getattr(article, "ai_content", None) or getattr(article, "content", None),
            image_url=getattr(article, "image_url", None),
        )
        sport = resolved.sport
        if sport in MAIN_SPORTS:
            counts[f"resolved_{sport}"] += 1
        else:
            counts["unknown"] += 1
        if stored_sport and sport and stored_sport != sport:
            counts["sport_disagreements"] += 1
            counts["rejected_sport_mismatch"] += 1
        if stored_league and resolved.public_competition and stored_league != resolved.public_competition:
            counts["competition_disagreements"] += 1
        if resolved.sport and resolved.sport_confidence < MIN_SPORT_CONFIDENCE:
            counts["rejected_low_confidence"] += 1
        flags = set(quality.get("flags") or [])
        if flags & {"navigation", "cdata", "truncation"}:
            counts["rejected_contamination"] += 1
            counts["source_chrome_contamination"] += 1
        raw_body = getattr(article, "content", None) or ""
        if has_nav_contamination(raw_body):
            counts["source_chrome_contamination"] += 1
        title = (getattr(article, "title", "") or "").strip().lower()
        if title and raw_body.strip().lower().startswith(title[: min(48, len(title))]):
            counts["duplicate_headline_body_starts"] += 1
        if title in seen_titles:
            counts["rejected_duplicate"] += 1
        elif title:
            seen_titles.add(title)
        kind = classify_media_url(getattr(article, "image_url", None))
        if kind in {"CREST_OR_LOGO", "GRAPHIC", "MISSING", "UNKNOWN"}:
            counts["bad_unknown_hero_media"] += 1
        if not suitable_for_lead_hero(getattr(article, "image_url", None)):
            counts["rejected_bad_media_for_hero"] += 1
    return counts


def log_homepage_audit(counts: Dict[str, int]) -> None:
    logger.info(
        "homepage taxonomy qa total=%s football=%s basketball=%s tennis=%s motorsport=%s unknown=%s "
        "contamination=%s mismatch=%s low_conf=%s duplicate=%s bad_hero_media=%s",
        counts.get("total_candidates", 0),
        counts.get("resolved_football", 0),
        counts.get("resolved_basketball", 0),
        counts.get("resolved_tennis", 0),
        counts.get("resolved_motorsport", 0),
        counts.get("unknown", 0),
        counts.get("rejected_contamination", 0),
        counts.get("rejected_sport_mismatch", 0),
        counts.get("rejected_low_confidence", 0),
        counts.get("rejected_duplicate", 0),
        counts.get("rejected_bad_media_for_hero", 0),
    )
