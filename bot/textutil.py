"""Clean RSS/HTML text before classification or AI writing."""

import re
from html import unescape
from typing import Optional

TRUNCATION_RE = re.compile(
    r"\[(?:\s*)\+\s*\d+\s*chars?(?:\s*)\]",
    re.IGNORECASE,
)
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL | re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
PUBLISHER_FOOTER_RE = re.compile(
    r"(?:the post\s+.+?\s+)?appeared first on\s+.+$",
    re.IGNORECASE,
)


def strip_truncation_markers(text: str) -> str:
    if not text:
        return ""
    text = TRUNCATION_RE.sub(" ", text)
    text = re.sub(r"\s*[.…]+\s*$", "", text)
    return text.strip()


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""

    text = unescape(text)
    text = CDATA_RE.sub(r"\1", text)
    text = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<img[^>]*>", " ", text, flags=re.IGNORECASE)
    text = HTML_TAG_RE.sub(" ", text)
    text = strip_truncation_markers(text)
    text = PUBLISHER_FOOTER_RE.sub("", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def looks_like_garbage(text: str) -> bool:
    if not text:
        return True
    lower = text.lower()
    if "<html" in lower or "<script" in lower or "function(" in lower:
        return True
    if "<![cdata" in lower:
        return True
    if TRUNCATION_RE.search(text):
        return True
    letters = sum(ch.isalpha() for ch in text)
    return letters < 12


def normalize_title(title: str) -> str:
    cleaned = clean_text(title).lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
