"""Reject low-quality candidates before OpenAI or publication."""

import re
from typing import Optional, Tuple

from .site_chrome import is_site_chrome_text
from .textutil import TRUNCATION_RE, clean_text, looks_like_garbage, normalize_title, word_count


MIN_FACT_CHARS = 80
MIN_BRIEF_CHARS = 40
MIN_SOURCE_WORDS = 180
MIN_BRIEF_WORDS = 60
SUMMARY_MAX_WORDS = 140


def is_substantial_source(text: Optional[str]) -> bool:
    return word_count(text) >= MIN_SOURCE_WORDS


def is_summary_sized(text: Optional[str]) -> bool:
    return word_count(text) < SUMMARY_MAX_WORDS


def is_dramatic_shortening(source: Optional[str], output: Optional[str]) -> bool:
    """True when a full source article collapsed into an RSS-sized stub."""
    return is_substantial_source(source) and is_summary_sized(output)


def needs_full_source_repair(stored: Optional[str], extracted: Optional[str]) -> bool:
    """Existing public copy looks like a feed stub; source page has a real article."""
    stored_n = word_count(stored)
    extracted_n = word_count(extracted)
    return stored_n < MIN_SOURCE_WORDS and extracted_n >= 250 and extracted_n >= max(stored_n * 2, 250)


def has_truncation(text: str) -> bool:
    return bool(text and TRUNCATION_RE.search(text))


def is_english_enough(text: str) -> bool:
    """Heuristic: published NinkoSports copy should be mostly Latin letters."""
    if not text:
        return False
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 20:
        return False
    latin = sum(ch.isascii() for ch in letters)
    return (latin / len(letters)) >= 0.75


def quality_check(
    title: str,
    body: str,
    sport: Optional[str],
    require_english: bool = False,
) -> Tuple[bool, str]:
    title = clean_text(title)
    body = clean_text(body)

    if not title or len(title) < 8:
        return False, "empty-title"
    if looks_like_garbage(title) or looks_like_garbage(body):
        return False, "garbage"
    if has_truncation(title) or has_truncation(body):
        return False, "truncation-marker"
    if not sport:
        return False, "unknown-sport"
    combined = f"{title} {body}"
    if len(body) < MIN_BRIEF_CHARS and len(combined) < MIN_FACT_CHARS:
        return False, "insufficient-facts"
    if require_english and not is_english_enough(body or title):
        return False, "not-english"
    if re.search(
        r"cookie (policy|settings)|subscribe to our newsletter|appeared first on|skip to main content|skip to navigation",
        body.lower(),
    ):
        return False, "boilerplate"
    if is_site_chrome_text(body) or is_site_chrome_text(title):
        return False, "boilerplate"
    return True, "ok"


def enough_for_brief(title: str, body: str) -> bool:
    title = clean_text(title)
    body = clean_text(body)
    return bool(title) and (len(body) >= MIN_BRIEF_CHARS or len(title) >= 24)


def normalized_duplicate_key(title: str) -> str:
    return normalize_title(title)
