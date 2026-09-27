"""Cached six-language translations for already-public NinkoSports articles.

Translations are strictly secondary to English News creation. One bounded
zero-price JSON request translates one article into all configured languages,
then deterministic gates reject changed proper names, invented numbers, links,
incomplete bodies, or Serbian Cyrillic. Failures never hide the English article.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

from models import Article, ArticleTaxonomyResolution, ArticleTranslation
from taxonomy_resolver import RESOLVER_VERSION
from .free_ai_router import free_json_completion, selected_free_model_name
from .news_policy import protected_proper_names

logger = logging.getLogger(__name__)

LANGUAGES = ("sr", "es", "de", "fr", "it", "pt")
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,:/–-]\d+)*(?:%|\b)")

_SYSTEM = """You are the NinkoSports literary translation desk.
Translate the supplied English sports article faithfully and completely.

Preserve the NinkoSports voice, not just the information:
- keep the rhythm, warmth, restrained poetry and emotional cadence of the original;
- preserve metaphors when they work naturally in the target language;
- where a literal metaphor sounds awkward, recreate the SAME literary feeling
  without adding a new factual claim;
- do not flatten expressive sports prose into corporate or machine-like language.

FACTUAL RULES:
- Do not summarize, add context, add links, add quotes, or change any fact.
- Preserve every team/person/competition/venue name EXACTLY.
- Preserve every numeric token exactly as digits, including scores, minutes,
  percentages, dates and statistics.
- Serbian must be natural Serbian LATIN script only, never Cyrillic.
- Serbian should sound like a passionate sports columnist from the Balkans,
  not like a literal machine translation.

Return JSON only. The top-level keys must be exactly sr,es,de,fr,it,pt.
Each language value must be an object with exactly title,summary,body strings.
"""


def translations_enabled() -> bool:
    return os.getenv("NEWS_TRANSLATIONS_ENABLED") == "1"


def _numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text or ""))


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or "", flags=re.UNICODE))


def _translation_reject(reason: str, language: Optional[str] = None):
    logger.info("[translations] validation reject=%s language=%s", reason, language or "-")
    return None


def _validate(source: Dict[str, str], payload: object) -> Optional[Dict[str, Dict[str, str]]]:
    if not isinstance(payload, dict) or set(payload) != set(LANGUAGES):
        return _translation_reject("top-level-shape")
    source_combined = "\n".join(source.values())
    source_numbers = _numbers(source_combined)
    protected = protected_proper_names(source_combined)
    source_words = max(1, _word_count(source.get("body") or ""))

    cleaned: Dict[str, Dict[str, str]] = {}
    for language in LANGUAGES:
        row = payload.get(language)
        if not isinstance(row, dict) or set(row) != {"title", "summary", "body"}:
            return _translation_reject("language-shape", language)
        title = row.get("title")
        summary = row.get("summary")
        body = row.get("body")
        if not all(isinstance(value, str) and value.strip() for value in (title, summary, body)):
            return _translation_reject("missing-text", language)
        title, summary, body = title.strip(), summary.strip(), body.strip()
        combined = f"{title}\n{summary}\n{body}"
        if re.search(r"https?://|www\.", combined, re.I):
            return _translation_reject("external-link", language)
        if _numbers(combined) != source_numbers:
            return _translation_reject("numbers-changed", language)
        folded = combined.casefold()
        if any(name.casefold() not in folded for name in protected):
            return _translation_reject("proper-name-changed", language)
        if _word_count(body) < max(25, int(source_words * 0.50)):
            return _translation_reject("body-too-short", language)
        if language == "sr" and CYRILLIC_RE.search(combined):
            return _translation_reject("serbian-cyrillic", language)
        cleaned[language] = {"title": title, "summary": summary, "body": body}
    return cleaned


def translate_article_payload(article: Article) -> Optional[Dict[str, Dict[str, str]]]:
    source = {
        "title": str(article.title or "").strip(),
        "summary": str(article.summary or "").strip(),
        "body": str(article.ai_content or article.content or article.summary or "").strip(),
    }
    if not all(source.values()) or len(source["body"]) > 12000:
        # Never cache a translation of only the first part of an article.
        return None
    prompt = (
        "ENGLISH TITLE:\n" + source["title"][:1000]
        + "\n\nENGLISH SUMMARY:\n" + source["summary"][:1600]
        + "\n\nENGLISH BODY:\n" + source["body"]
    )
    raw = free_json_completion(_SYSTEM, prompt, max_tokens=9000)
    if not raw:
        return None
    import json

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return _validate(source, payload)


def _latest_missing(db: Session, limit: int) -> list[Article]:
    rows = (
        db.query(Article)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok.is_(True),
        )
        .order_by(Article.ai_generated.desc(), Article.published_at.desc(), Article.id.desc())
        .limit(max(10, min(limit * 30, 120)))
        .all()
    )
    output = []
    cutoff = datetime.utcnow() - timedelta(hours=6)
    for article in rows:
        translation_rows = (
            db.query(ArticleTranslation)
            .filter(
                ArticleTranslation.article_id == article.id,
                ArticleTranslation.language_code.in_(LANGUAGES),
            )
            .all()
        )
        ready = {row.language_code for row in translation_rows if row.status == "ready"}
        recently_failed = any(
            row.status == "failed" and row.updated_at is not None and row.updated_at >= cutoff
            for row in translation_rows
        )
        if recently_failed:
            continue
        if ready != set(LANGUAGES):
            output.append(article)
            if len(output) >= limit:
                break
    return output


def _mark_failed(db: Session, article: Article) -> None:
    model = (selected_free_model_name() or "")[:80] or None
    now = datetime.utcnow()
    for language in LANGUAGES:
        row = (
            db.query(ArticleTranslation)
            .filter(
                ArticleTranslation.article_id == article.id,
                ArticleTranslation.language_code == language,
            )
            .first()
        )
        if row is None:
            row = ArticleTranslation(article_id=article.id, language_code=language)
            db.add(row)
        if row.status != "ready":
            row.status = "failed"
            row.provider = "xkiro-free"
            row.model_name = model
            row.updated_at = now


def _store(db: Session, article: Article, translations: Dict[str, Dict[str, str]]) -> int:
    model = (selected_free_model_name() or "")[:80] or None
    now = datetime.utcnow()
    stored = 0
    for language in LANGUAGES:
        data = translations[language]
        row = (
            db.query(ArticleTranslation)
            .filter(
                ArticleTranslation.article_id == article.id,
                ArticleTranslation.language_code == language,
            )
            .first()
        )
        if row is None:
            row = ArticleTranslation(article_id=article.id, language_code=language)
            db.add(row)
        row.translated_title = data["title"]
        row.translated_summary = data["summary"]
        row.translated_body = data["body"]
        row.status = "ready"
        row.provider = "xkiro-free"
        row.model_name = model
        row.updated_at = now
        stored += 1
    return stored


def translate_latest_articles(limit: int = 1) -> int:
    """Translate latest missing public articles. One AI request per article."""
    if not translations_enabled():
        return 0
    limit = max(1, min(int(limit), 3))
    from database import SessionLocal

    db = SessionLocal()
    translated = 0
    try:
        for article in _latest_missing(db, limit):
            payload = translate_article_payload(article)
            if not payload:
                _mark_failed(db, article)
                db.commit()
                logger.info("[translations] held article=%s cooldown_hours=6", article.id)
                continue
            with db.begin_nested():
                translated += _store(db, article, payload)
        if translated:
            db.commit()
        return translated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
