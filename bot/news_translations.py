"""Cached six-language translations for already-public NinkoSports articles.

Translations are strictly secondary to English News creation. One bounded
zero-price JSON request translates one article into all configured languages,
then deterministic gates reject changed proper names, invented numbers, links,
incomplete bodies, or Serbian Cyrillic. Failures never hide the English article.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import unicodedata
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
TRANSLATION_PROVIDER = "xkiro-free-v12"
# Release marker: v12 protects exact proper names with reversible translation tokens.
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
- Protected multi-word names in the source are represented by LOCKED NAME TOKENS.
- Copy every LOCKED NAME TOKEN exactly wherever it appears. Never translate,
  transliterate, split, alter or drop a token. The server restores the original
  proper name after translation.
- Preserve every numeric VALUE exactly, including scores, minutes, percentages,
  dates and statistics. Locale punctuation may change naturally (for example
  100,023 -> 100.023 or 4.52 -> 4,52), but the numeric value must not change.
- Every value listed under LOCKED NUMERIC VALUES must appear in EVERY language.
  Never omit a listed age, score, count, ranking, date, percentage or statistic.
- Do NOT introduce any numeral that is not listed under LOCKED NUMERIC VALUES.
  If the source says "one" as a word, keep it as a word; never convert it into "1".
- Serbian must be natural Serbian LATIN script only, never Cyrillic.
- Serbian should sound like a passionate sports columnist from the Balkans,
  not like a literal machine translation.

Return JSON only.
Preferred schema: one flat object with exactly these 18 string fields:
sr_title,sr_summary,sr_body,es_title,es_summary,es_body,
de_title,de_summary,de_body,fr_title,fr_summary,fr_body,
it_title,it_summary,it_body,pt_title,pt_summary,pt_body.
Do not return arrays, prose, markdown or omitted fields.
"""


def translations_enabled() -> bool:
    return os.getenv("NEWS_TRANSLATIONS_ENABLED") == "1"


def _canonical_number(token: str) -> str:
    token = (
        (token or "").replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )
    suffix = "%" if token.endswith("%") else ""
    core = token[:-1] if suffix else token

    # Scores, ratios and dates keep their structural separator; normalize only
    # dash glyphs. Decimal/thousands punctuation inside simple numbers may be
    # localized by the target language without changing the numeric value.
    if any(sep in core for sep in (":", "/", "-")):
        return core + suffix

    if "," not in core and "." not in core:
        return core + suffix

    separators = [ch for ch in core if ch in ",."]
    parts = re.split(r"[.,]", core)

    if len(set(separators)) == 1:
        # 100,023 / 100.023 and 1,234,567 / 1.234.567 are equivalent
        # grouping conventions. Otherwise treat a single separator as decimal.
        if len(parts) > 1 and all(len(group) == 3 for group in parts[1:]):
            return "".join(parts) + suffix
        if len(parts) == 2:
            return f"{parts[0]}.{parts[1]}" + suffix

    # Mixed separators: the last separator is decimal only when followed by
    # one or two digits; preceding punctuation is grouping.
    last_pos = max(core.rfind(","), core.rfind("."))
    fractional = core[last_pos + 1 :]
    integer = re.sub(r"[.,]", "", core[:last_pos])
    if 1 <= len(fractional) <= 2:
        return f"{integer}.{fractional}" + suffix
    return re.sub(r"[.,]", "", core) + suffix


def _numbers(text: str) -> set[str]:
    return {_canonical_number(token) for token in NUMBER_RE.findall(text or "")}


def _name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = (
        stripped.replace("’", "'")
        .replace("‘", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    return " ".join(stripped.casefold().split())


def _contains_name(text: str, name: str) -> bool:
    return _name_key(name) in _name_key(text)


def _mask_protected_names(source: Dict[str, str], names: list[str]):
    """Hide exact proper names behind immutable tokens during translation."""
    masked = dict(source)
    unique = []
    seen = set()
    for name in names:
        value = str(name or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)

    locks = []
    for index, name in enumerate(sorted(unique, key=len, reverse=True)[:24]):
        token = f"__NINKONAME_{chr(ord('A') + index)}__"
        changed = False
        for field in ("title", "summary", "body"):
            value = masked.get(field) or ""
            replaced = value.replace(name, token)
            if replaced != value:
                masked[field] = replaced
                changed = True
        if changed:
            locks.append((token, name))
    return masked, locks


def _restore_protected_names(
    payload: Dict[str, Dict[str, str]],
    locks: list[tuple[str, str]],
) -> Dict[str, Dict[str, str]]:
    restored: Dict[str, Dict[str, str]] = {}
    for language, row in payload.items():
        restored_row = {}
        for field in ("title", "summary", "body"):
            value = row.get(field)
            if not isinstance(value, str):
                restored_row[field] = value
                continue
            for token, name in locks:
                value = value.replace(token, name)
            restored_row[field] = value
        restored[language] = restored_row
    return restored


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or "", flags=re.UNICODE))


def _translation_reject(reason: str, language: Optional[str] = None):
    logger.info("[translations] validation reject=%s language=%s", reason, language or "-")
    return None


def _canonical_translation_payload(payload: object):
    """Accept only structurally equivalent complete translation payloads."""
    import json

    if not isinstance(payload, dict):
        return None

    # Some compatible models wrap the requested object once.
    for wrapper in ("translations", "translation", "result", "data"):
        inner = payload.get(wrapper)
        if isinstance(inner, dict):
            payload = inner
            break

    required = ("title", "summary", "body")

    # Preferred flat schema: sr_title, sr_summary, sr_body, ...
    flat = {}
    flat_ok = True
    for language in LANGUAGES:
        row = {}
        for field in required:
            key = f"{language}_{field}"
            value = payload.get(key)
            if not isinstance(value, str):
                flat_ok = False
                break
            row[field] = value
        if not flat_ok:
            break
        flat[language] = row
    if flat_ok and set(flat) == set(LANGUAGES):
        return flat

    # Backward-compatible nested schema. Each language may itself be a JSON
    # string or a one-item list containing the same required object.
    nested = {}
    for language in LANGUAGES:
        row = payload.get(language)
        if isinstance(row, str):
            try:
                row = json.loads(row)
            except (TypeError, ValueError):
                return None
        if isinstance(row, list) and len(row) == 1 and isinstance(row[0], dict):
            row = row[0]
        if not isinstance(row, dict):
            return None

        # Allow only well-known harmless wrappers, never guess from free text.
        if not set(required).issubset(row):
            for wrapper in ("translation", "article", "content", "result"):
                inner = row.get(wrapper)
                if isinstance(inner, dict) and set(required).issubset(inner):
                    row = inner
                    break
        if not set(required).issubset(row):
            return None
        nested[language] = {field: row.get(field) for field in required}
    return nested if set(nested) == set(LANGUAGES) else None


def _json_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold().strip()


def _normalize_language_row(row):
    if isinstance(row, str):
        import json
        try:
            decoded = json.loads(row)
        except (TypeError, ValueError):
            return None
        if decoded is row:
            return None
        return _normalize_language_row(decoded)

    if isinstance(row, (list, tuple)):
        if len(row) != 3 or not all(isinstance(value, str) for value in row):
            return None
        return {"title": row[0], "summary": row[1], "body": row[2]}

    if not isinstance(row, dict):
        return None

    required = {"title", "summary", "body"}
    if required.issubset(set(row)):
        return {key: row.get(key) for key in required}

    aliases = {
        "title": {"title", "naslov", "titulo", "titel", "titre", "titolo"},
        "summary": {
            "summary", "sazetak", "resumen", "zusammenfassung",
            "resume", "sintesi", "resumo",
        },
        "body": {"body", "tekst", "text", "cuerpo", "texte", "testo", "corpo"},
    }
    normalized = {_json_key(key): value for key, value in row.items()}
    mapped = {}
    for target, names in aliases.items():
        value = next((normalized[name] for name in names if name in normalized), None)
        if isinstance(value, str):
            mapped[target] = value
    if set(mapped) == required:
        return mapped

    # Tolerate one harmless wrapper such as {"translation": [...]}; do not
    # recursively combine multiple fields or guess ambiguous shapes.
    if len(row) == 1:
        return _normalize_language_row(next(iter(row.values())))
    return None


def _validate(source: Dict[str, str], payload: object) -> Optional[Dict[str, Dict[str, str]]]:
    payload = _canonical_translation_payload(payload)
    if payload is None:
        return _translation_reject("top-level-shape")
    source_combined = "\n".join(source.values())
    source_numbers = _numbers(source_combined)
    # Preserve central proper names from the source headline/summary exactly.
    # Do not classify every capitalized word in a translated sentence as a new name.
    source_head = f'{source.get("title") or ""}\n{source.get("summary") or ""}'
    protected = [
        name for name in protected_proper_names(source_head)
        if len(name.split()) >= 2
    ]
    acronyms = set(re.findall(r"\b[A-Z][A-Z0-9.-]{1,7}\b", source_combined))
    source_words = max(1, _word_count(source.get("body") or ""))

    cleaned: Dict[str, Dict[str, str]] = {}
    for language in LANGUAGES:
        raw_row = payload.get(language)
        row = _normalize_language_row(raw_row)
        if row is None:
            logger.info(
                "[translations] language shape language=%s type=%s keys=%s",
                language,
                type(raw_row).__name__,
                sorted(raw_row.keys()) if isinstance(raw_row, dict) else [],
            )
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
        translated_numbers = _numbers(combined)
        if translated_numbers != source_numbers:
            logger.info(
                "[translations] number mismatch language=%s missing=%s extra=%s",
                language,
                sorted(source_numbers - translated_numbers),
                sorted(translated_numbers - source_numbers),
            )
            return _translation_reject("numbers-changed", language)
        missing_names = [name for name in protected if not _contains_name(combined, name)]
        if missing_names:
            logger.info(
                "[translations] missing protected names language=%s names=%s",
                language,
                missing_names[:8],
            )
            return _translation_reject("proper-name-changed", language)
        if any(acronym not in combined for acronym in acronyms):
            return _translation_reject("acronym-changed", language)
        if _word_count(body) < max(25, int(source_words * 0.50)):
            return _translation_reject("body-too-short", language)
        if language == "sr" and CYRILLIC_RE.search(combined):
            return _translation_reject("serbian-cyrillic", language)
        cleaned[language] = {"title": title, "summary": summary, "body": body}
    return cleaned


def _decode_json_payload(raw: str):
    import json

    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().lstrip("\ufeff")
    if text.startswith("```"):
        text = re.sub(r"^\s*```(?:json)?\s*", "", text, count=1, flags=re.I)
        text = re.sub(r"\s*```\s*$", "", text, count=1)
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass

    # Some OpenAI-compatible models occasionally wrap a valid JSON object in
    # harmless prose despite response_format. Extract one complete object only;
    # never attempt to repair or guess truncated JSON.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except (TypeError, ValueError):
            return None
    return None


def translate_article_payload(article: Article) -> Optional[Dict[str, Dict[str, str]]]:
    source = {
        "title": str(article.title or "").strip(),
        "summary": str(article.summary or "").strip(),
        "body": str(article.ai_content or article.content or article.summary or "").strip(),
    }
    if not all(source.values()) or len(source["body"]) > 12000:
        # Never cache a translation of only the first part of an article.
        return None
    locked_names = [
        name for name in protected_proper_names(
            f'{source["title"]}\n{source["summary"]}'
        )
        if len(name.split()) >= 2
    ]
    masked_source, name_locks = _mask_protected_names(source, locked_names)
    locked_block = "\n".join(f"- {token}" for token, _name in name_locks) or "- none"
    locked_numbers = sorted(
        _numbers("\n".join(source.values())),
        key=lambda value: (len(value), value),
    )
    number_block = "\n".join(f"- {value}" for value in locked_numbers) or "- none"
    prompt = (
        "LOCKED NAME TOKENS — copy every token VERBATIM wherever it appears. "
        "Do not translate, transliterate, split, alter or drop these tokens; "
        "the server restores the exact proper names after translation:\n"
        + locked_block
        + "\n\nLOCKED NUMERIC VALUES — these are the ONLY numerals allowed in the translation. "
          "Every value below must appear in EVERY language; do not omit any value and "
          "do not create any additional numeral. Locale punctuation may change only "
          "when the numeric value stays identical:\n"
        + number_block
        + "\n\nENGLISH TITLE:\n" + masked_source["title"][:1000]
        + "\n\nENGLISH SUMMARY:\n" + masked_source["summary"][:1600]
        + "\n\nENGLISH BODY:\n" + masked_source["body"]
    )
    raw = free_json_completion(_SYSTEM, prompt, max_tokens=9000)
    if not raw:
        logger.info("[translations] response unavailable article=%s", article.id)
        return None
    payload = _decode_json_payload(raw)
    if payload is None:
        logger.info("[translations] invalid JSON response article=%s", article.id)
        return None
    normalized = _canonical_translation_payload(payload)
    if normalized is None:
        logger.info(
            "[translations] unsupported response shape article=%s top_keys=%s",
            article.id,
            sorted(payload.keys())[:24] if isinstance(payload, dict) else [],
        )
        return None
    restored = _restore_protected_names(normalized, name_locks)
    return _validate(source, restored)


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
        .order_by(Article.ai_generated.desc(), Article.id.desc())
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
            row.status == "failed"
            and row.provider == TRANSLATION_PROVIDER
            and row.updated_at is not None
            and row.updated_at >= cutoff
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
            row.provider = TRANSLATION_PROVIDER
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
        row.provider = TRANSLATION_PROVIDER
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
