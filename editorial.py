"""Presentation-only editorial sanitizer and quality gate.

Never writes to the database. Used when serializing public article payloads
and when choosing premium homepage/sport slots.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TRUNCATION_RE = re.compile(
    r"\[(?:\s*)\+\s*\d+\s*chars?(?:\s*)\]",
    re.IGNORECASE,
)
CDATA_OPEN_RE = re.compile(r"<!\[CDATA\[", re.IGNORECASE)
CDATA_CLOSE_RE = re.compile(r"\]\]>", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)
VIDEO_CHROME_RE = re.compile(
    r"\bplay\s+[A-Z][\w .'-]{0,40}:\s+.{8,140}?\(\d{1,2}:\d{2}\)",
    re.IGNORECASE,
)
MENU_ESPN_RE = re.compile(r"(?:-->\s*)?menu\s+espn\b", re.IGNORECASE)
SKIP_NAV_RE = re.compile(
    r"skip to (?:main content|content|navigation|main navigation)",
    re.IGNORECASE,
)
COOKIE_RE = re.compile(r"\bcookie (?:policy|consent|settings|notice)\b", re.IGNORECASE)
FOOTER_RE = re.compile(
    r"(?:the post\s+.+?\s+)?appeared first on\s+.+$",
    re.IGNORECASE,
)
ARROW_MENU_RE = re.compile(r"-->\s*", re.IGNORECASE)

ENGLISH_STOPWORDS = {
    "the", "a", "an", "and", "of", "to", "in", "for", "with", "on", "at",
    "from", "by", "as", "is", "was", "were", "be", "been", "are", "that",
    "this", "it", "his", "her", "their", "has", "have", "had", "not", "but",
    "or", "they", "he", "she", "we", "after", "before", "during", "against",
    "into", "about", "over", "than", "also", "who", "which", "when", "while",
    "said", "would", "could", "should", "will", "one", "two", "first", "last",
    "match", "game", "team", "season", "goal", "win", "lost", "home",
}

NAV_MARKERS = (
    "menu espn",
    "skip to content",
    "skip to navigation",
    "cookie consent",
)

# Distinctive letters that almost never appear in English sports copy
# except occasional surnames. Thresholds keep player names from tripping this.
SLAVIC_LETTER_RE = re.compile(r"[řěůťďňščžąćęłńśźżŘĚŮŤĎŇŠČŽĄĆĘŁŃŚŹŻ]")

HEADING_MARKERS = (
    "heading",
    "subheading",
    "subhead",
)


def _collapse_spaces(text: str) -> str:
    text = (text or "").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_cdata(text: str) -> str:
    if not text:
        return ""
    text = CDATA_OPEN_RE.sub("", text)
    text = CDATA_CLOSE_RE.sub("", text)
    return text


def strip_contamination(text: str) -> str:
    if not text:
        return ""
    text = strip_cdata(text)
    text = HTML_TAG_RE.sub(" ", text)
    text = TRUNCATION_RE.sub(" ", text)
    text = MENU_ESPN_RE.sub(" ", text)
    text = SKIP_NAV_RE.sub(" ", text)
    text = COOKIE_RE.sub(" ", text)
    text = VIDEO_CHROME_RE.sub(" ", text)
    text = FOOTER_RE.sub("", text)
    text = ARROW_MENU_RE.sub(" ", text)
    return _collapse_spaces(text)


def _strip_leading_title(text: str, title: Optional[str]) -> str:
    if not text or not title:
        return text
    title_clean = strip_contamination(title).strip()
    if len(title_clean) < 8:
        return text
    pattern = re.compile(
        r"^(?:" + re.escape(title_clean) + r")(?:\s*[.!?–—-])?\s+",
        re.IGNORECASE,
    )
    current = text.strip()
    for _ in range(3):
        updated = pattern.sub("", current, count=1).strip()
        if updated == current:
            break
        current = updated
    return current


def sanitize_title(title: Optional[str]) -> str:
    cleaned = strip_contamination(title or "")
    cleaned = re.sub(r"^[\s\-–—:]+", "", cleaned)
    return cleaned.strip()


def sanitize_summary(summary: Optional[str], title: Optional[str] = None) -> str:
    cleaned = strip_contamination(summary or "")
    cleaned = _strip_leading_title(cleaned, title)
    title_clean = sanitize_title(title)
    if title_clean and cleaned.lower() == title_clean.lower():
        return ""
    return cleaned


def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'])", text.strip())
    return [part.strip() for part in parts if part.strip()]


def restore_paragraphs(text: str) -> List[str]:
    """Restore paragraphs using newlines and sentence groups. Never by character count."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    chunks = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
    if len(chunks) == 1:
        lined = [part.strip() for part in re.split(r"\n+", chunks[0]) if part.strip()]
        if len(lined) > 1:
            chunks = lined
    paragraphs: List[str] = []
    for chunk in chunks:
        if len(chunk) < 420:
            paragraphs.append(chunk)
            continue
        sentences = split_sentences(chunk)
        if len(sentences) <= 1:
            paragraphs.append(chunk)
            continue
        buf: List[str] = []
        for sentence in sentences:
            buf.append(sentence)
            joined = " ".join(buf)
            if len(buf) >= 3 or len(joined) >= 280:
                paragraphs.append(joined)
                buf = []
        if buf:
            paragraphs.append(" ".join(buf))
    return paragraphs


def _is_quote(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    quotes = {"\"", "“", "”", "«", "»"}
    return stripped[0] in quotes and stripped[-1] in quotes


def _is_list_block(text: str) -> bool:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 2:
        return False
    return all(re.match(r"^([-*•]|\d+[.)])\s+", line) for line in lines)


def _is_heading(text: str, marker: Optional[str] = None) -> bool:
    if marker in HEADING_MARKERS:
        return True
    return False


def to_blocks(text: str, title: Optional[str] = None) -> List[Dict]:
    cleaned = strip_contamination(text or "")
    cleaned = _strip_leading_title(cleaned, title)
    blocks: List[Dict] = []
    for para in restore_paragraphs(cleaned):
        if _is_list_block(para):
            items = [re.sub(r"^([-*•]|\d+[.)])\s+", "", line).strip() for line in para.split("\n")]
            blocks.append({"type": "list", "items": [item for item in items if item]})
        elif _is_quote(para):
            blocks.append({"type": "quote", "text": para.strip("\"“”«» ").strip()})
        else:
            blocks.append({"type": "paragraph", "text": para})
    return blocks


def sanitize_body(text: Optional[str], title: Optional[str] = None) -> str:
    blocks = to_blocks(text or "", title=title)
    parts = []
    for block in blocks:
        if block["type"] == "list":
            parts.append("\n".join(f"- {item}" for item in block["items"]))
        else:
            parts.append(block.get("text") or "")
    return "\n\n".join(part for part in parts if part).strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÿ']+", text or ""))


def looks_non_english(text: str) -> bool:
    raw = text or ""
    if len(SLAVIC_LETTER_RE.findall(raw)) >= 3:
        return True
    words = re.findall(r"[A-Za-zÀ-ÿ']+", raw.lower())
    if len(words) < 50:
        return False
    hits = sum(1 for word in words if word in ENGLISH_STOPWORDS)
    return (hits / len(words)) < 0.10


def title_is_malformed(title: Optional[str]) -> bool:
    raw = title or ""
    if "<![CDATA" in raw.upper() or "]]>" in raw:
        return True
    if HTML_TAG_RE.search(raw):
        return True
    cleaned = sanitize_title(raw)
    if len(cleaned) < 8:
        return True
    letters = sum(ch.isalpha() for ch in cleaned)
    return letters < 6


def has_nav_contamination(text: Optional[str]) -> bool:
    lower = (text or "").lower()
    if MENU_ESPN_RE.search(text or ""):
        return True
    return any(marker in lower for marker in NAV_MARKERS)


def has_truncation(text: Optional[str]) -> bool:
    return bool(TRUNCATION_RE.search(text or ""))


def has_cdata(text: Optional[str]) -> bool:
    raw = text or ""
    return bool(CDATA_OPEN_RE.search(raw) or CDATA_CLOSE_RE.search(raw) or "<![cdata" in raw.lower())


def image_is_usable(url: Optional[str]) -> bool:
    value = (url or "").strip()
    if not value:
        return False
    lower = value.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return False
    if "1x1" in lower or "pixel.gif" in lower or lower.endswith(".svg?blank"):
        return False
    return True


def evaluate_quality(
    *,
    title: Optional[str],
    summary: Optional[str] = None,
    body: Optional[str] = None,
    image_url: Optional[str] = None,
) -> Dict:
    raw_title = title or ""
    raw_summary = summary or ""
    raw_body = body or ""
    combined = " ".join([raw_title, raw_summary, raw_body])
    flags: List[str] = []
    if title_is_malformed(raw_title):
        flags.append("malformed_title")
    if has_cdata(combined):
        flags.append("cdata")
    if has_nav_contamination(combined):
        flags.append("navigation")
    if has_truncation(combined):
        flags.append("truncation")
    cleaned_body = sanitize_body(raw_body, title=raw_title)
    cleaned_title = sanitize_title(raw_title)
    if _word_count(cleaned_body) < 40:
        flags.append("weak_body")
    if looks_non_english(cleaned_body) or looks_non_english(cleaned_title):
        flags.append("non_english")
    if len(SLAVIC_LETTER_RE.findall(raw_title)) >= 2:
        if "non_english" not in flags:
            flags.append("non_english")
    if not image_is_usable(image_url):
        flags.append("unusable_image")
    premium_flags = {
        "malformed_title",
        "cdata",
        "navigation",
        "truncation",
        "weak_body",
        "non_english",
    }
    return {
        "ok": not any(flag in premium_flags for flag in flags),
        "flags": flags,
        "word_count": _word_count(cleaned_body),
    }


def public_media_items(
    image_url: Optional[str],
    media_rows: Optional[Sequence] = None,
) -> List[Dict]:
    items: List[Dict] = []
    for row in media_rows or []:
        url = getattr(row, "url", None)
        if not image_is_usable(url):
            continue
        items.append(
            {
                "id": getattr(row, "id", None),
                "media_type": getattr(row, "media_type", None) or "image",
                "url": url,
                "caption": sanitize_summary(getattr(row, "caption", None)),
                "sort_order": int(getattr(row, "sort_order", 0) or 0),
                "is_hero": bool(getattr(row, "is_hero", False)),
            }
        )
    items.sort(key=lambda item: (not item["is_hero"], item["sort_order"], item["id"] or 0))
    if not items and image_is_usable(image_url):
        items.append(
            {
                "id": None,
                "media_type": "image",
                "url": image_url,
                "caption": "",
                "sort_order": 0,
                "is_hero": True,
            }
        )
    return items


def attach_inline_media(blocks: List[Dict], media: Sequence[Dict]) -> List[Dict]:
    """Place non-hero media between paragraphs. Never repeats the hero image."""
    inline = [item for item in media if not item.get("is_hero")]
    if not inline:
        return list(blocks)
    paragraph_indexes = [idx for idx, block in enumerate(blocks) if block.get("type") == "paragraph"]
    if not paragraph_indexes:
        result = list(blocks)
        for item in inline:
            result.append({"type": "media", **item})
        return result
    result = list(blocks)
    offset = 0
    usable = paragraph_indexes[:-1] or paragraph_indexes
    for i, item in enumerate(inline):
        target = usable[min(i, len(usable) - 1)] + 1 + offset
        result.insert(target, {"type": "media", **item})
        offset += 1
    return result


def maybe_related_insert(blocks: List[Dict], related: Optional[Dict], min_paragraphs: int = 5) -> List[Dict]:
    paragraphs = [block for block in blocks if block.get("type") == "paragraph"]
    if not related or len(paragraphs) < min_paragraphs:
        return blocks
    insert_after = 2
    count = 0
    result = []
    inserted = False
    for block in blocks:
        result.append(block)
        if block.get("type") == "paragraph":
            count += 1
            if not inserted and count == insert_after:
                result.append({"type": "related", "article": related})
                inserted = True
    return result
