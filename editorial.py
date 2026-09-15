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
ELLIPSIS_MARK_RE = re.compile(r"\[\s*(?:\.{3}|…)\s*\]")
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
SOCIAL_PIC_RE = re.compile(r"\bpic\.twitter\.com/\S+", re.IGNORECASE)
SOCIAL_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:x|twitter|t\.co)\.com/\S+",
    re.IGNORECASE,
)
WATCH_NOW_RE = re.compile(r"\bwatch now on\b.{0,120}", re.IGNORECASE)
HANDLE_STAMP_RE = re.compile(
    r"(?:[A-Za-z0-9 .,'&/-]{0,80})?\(@[\w.]+\)\s+"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4}",
    re.IGNORECASE,
)
LOCATION_CAPTION_RE = re.compile(
    r"^(?P<caption>[A-Z][A-Z .'-]{1,48},\s+[A-Z][A-Z .'-]{1,40}"
    r"\s+[-–—]\s+[A-Z]{3,9}\s+\d{1,2}:.*?"
    r"(?:\(Photo by [^)]+\)|\(Getty Images\)))"
    r"\s*(?P<body>.*)$",
    re.DOTALL,
)
STANDALONE_CREDIT_RE = re.compile(
    r"^(?:photo(?:graph)?(?:\s+by)?\s*:?\s+.+|"
    r"getty images.*|"
    r"\(photo by .+\))$",
    re.IGNORECASE,
)

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

# Website chrome that must never appear as NinkoSports prose.
CHROME_PHRASES = (
    "required fields are marked",
    "notify me of follow-up comments",
    "notify me of new comments",
    "notify me of new posts",
    "leave a reply",
    "leave a comment",
    "your email address will not be published",
    "save my name, email, and website",
    "save my name, email and website",
    "post comment",
    "post a comment",
    "submit comment",
    "log in to comment",
    "login to comment",
    "register to comment",
    "sign in to comment",
    "logged in as",
    "you must be logged in",
    "subscribe to our newsletter",
    "sign up for our newsletter",
    "sign up to our newsletter",
    "newsletter signup",
    "accept cookies",
    "we use cookies",
    "cookie policy",
    "privacy policy",
    "terms of use",
    "terms and conditions",
    "follow us on",
    "share this article",
    "share this post",
    "related posts",
    "you may also like",
    "latest italian football news",
    "latest football news",
    "all rights reserved",
    "copyright ©",
    "powered by wordpress",
    "this website uses cookies",
    "manage consent",
    "view comments",
    "no comments yet",
    "comments are closed",
    "search for:",
    "skip to footer",
    "watch now on",
    "pic.twitter.com",
    "download our app",
    "subscribe now",
    "sign up for breaking news",
)

CHROME_LABEL_RE = re.compile(
    r"^(?:name|email|website|comment|message|subject)\s*\*?\s*:?\s*$",
    re.IGNORECASE,
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


def strip_inline_chrome(text: str) -> str:
    raw = text or ""
    for phrase in CHROME_PHRASES:
        raw = re.sub(re.escape(phrase), " ", raw, flags=re.IGNORECASE)
    raw = CHROME_LABEL_RE.sub(" ", raw)
    raw = SOCIAL_PIC_RE.sub(" ", raw)
    raw = SOCIAL_URL_RE.sub(" ", raw)
    raw = WATCH_NOW_RE.sub(" ", raw)
    raw = HANDLE_STAMP_RE.sub(" ", raw)
    return _collapse_spaces(raw)


def is_chrome_paragraph(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    lower = raw.lower()
    if CHROME_LABEL_RE.match(raw):
        return True
    if any(phrase in lower for phrase in CHROME_PHRASES):
        remainder = strip_inline_chrome(raw)
        if _word_count(remainder) < 12:
            return True
        return False
    if MENU_ESPN_RE.search(raw) or SKIP_NAV_RE.search(raw) or COOKIE_RE.search(raw):
        return True
    if FOOTER_RE.search(raw):
        return True
    if VIDEO_CHROME_RE.search(raw):
        return True
    if SOCIAL_PIC_RE.search(raw) or SOCIAL_URL_RE.search(raw):
        remainder = SOCIAL_PIC_RE.sub(" ", raw)
        remainder = SOCIAL_URL_RE.sub(" ", remainder)
        remainder = WATCH_NOW_RE.sub(" ", remainder)
        remainder = HANDLE_STAMP_RE.sub(" ", remainder)
        if _word_count(remainder) < 12:
            return True
    if WATCH_NOW_RE.search(raw) and _word_count(WATCH_NOW_RE.sub(" ", raw)) < 12:
        return True
    if HANDLE_STAMP_RE.fullmatch(raw.strip()):
        return True
    if lower in {"name *", "email *", "website", "comment", "comments", "menu"}:
        return True
    return False


def chrome_is_interleaved(raw_body: str) -> bool:
    """True when nav/chrome sits in the opening of the article, not only as a trailer."""
    raw = raw_body or ""
    head = raw[:400]
    if MENU_ESPN_RE.search(head) or SKIP_NAV_RE.search(head):
        return True
    if "-->" in head and "menu" in head.lower():
        return True
    words = 0
    for para in restore_paragraphs(strip_contamination(raw)):
        if is_chrome_paragraph(para):
            return words < 40
        words += _word_count(para)
    return False


def cut_trailing_chrome(paragraphs: Sequence[str]) -> List[str]:
    """Drop website chrome that follows a real article. Keep legitimate paragraphs."""
    items = [part.strip() for part in paragraphs if part and part.strip()]
    if not items:
        return []
    cut_at = len(items)
    real_words = 0
    consecutive = 0
    for idx, para in enumerate(items):
        chrome = is_chrome_paragraph(para)
        if chrome:
            if real_words >= 40:
                consecutive += 1
                if consecutive == 1:
                    cut_at = min(cut_at, idx)
                if consecutive >= 1:
                    break
            else:
                consecutive = 0
        else:
            consecutive = 0
            real_words += _word_count(para)
            cut_at = len(items)
    kept = items[:cut_at]
    return [para for para in kept if not is_chrome_paragraph(para)]


def strip_contamination(text: str) -> str:
    if not text:
        return ""
    text = strip_cdata(text)
    text = HTML_TAG_RE.sub(" ", text)
    text = TRUNCATION_RE.sub(" ", text)
    text = ELLIPSIS_MARK_RE.sub(" ", text)
    text = MENU_ESPN_RE.sub(" ", text)
    text = SKIP_NAV_RE.sub(" ", text)
    text = COOKIE_RE.sub(" ", text)
    text = VIDEO_CHROME_RE.sub(" ", text)
    text = FOOTER_RE.sub("", text)
    text = ARROW_MENU_RE.sub(" ", text)
    text = SOCIAL_PIC_RE.sub(" ", text)
    text = SOCIAL_URL_RE.sub(" ", text)
    text = WATCH_NOW_RE.sub(" ", text)
    text = HANDLE_STAMP_RE.sub(" ", text)
    return _collapse_spaces(text)


def _strip_leading_kicker(text: str) -> str:
    current = (text or "").strip()
    for _ in range(2):
        updated = LEADING_KICKER_RE.sub("", current, count=1).strip()
        if updated == current:
            break
        current = updated
    return current


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
    current = _strip_leading_kicker(text.strip())
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
    if chunks and LEADING_CATEGORY_RE.match(chunks[0]):
        chunks = chunks[1:]
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


def split_photo_caption(text: str) -> Tuple[Optional[str], str]:
    """Separate Getty/location credits from the following editorial paragraph."""
    raw = (text or "").strip()
    if not raw:
        return None, ""
    if STANDALONE_CREDIT_RE.match(raw) and _word_count(raw) < 28:
        return raw, ""
    match = LOCATION_CAPTION_RE.match(raw)
    if not match:
        return None, raw
    caption = _collapse_spaces(match.group("caption"))
    body = _collapse_spaces(match.group("body") or "")
    if _word_count(caption) < 6:
        return None, raw
    return caption, body


def to_blocks(text: str, title: Optional[str] = None) -> List[Dict]:
    cleaned = strip_contamination(text or "")
    cleaned = _strip_leading_title(cleaned, title)
    paragraphs = cut_trailing_chrome(restore_paragraphs(cleaned))
    blocks: List[Dict] = []
    caption_emitted = False
    seen_norm = set()
    title_norm = _collapse_spaces(sanitize_title(title)).lower()
    for para in paragraphs:
        para = _strip_leading_title(para, title)
        if is_chrome_paragraph(para):
            continue
        key = _collapse_spaces(para).lower()
        if title_norm and key == title_norm:
            continue
        if key in seen_norm:
            continue
        seen_norm.add(key)
        para = strip_inline_chrome(para)
        if not para or is_chrome_paragraph(para):
            continue
        caption, remainder = split_photo_caption(para)
        if caption and not caption_emitted:
            blocks.append({"type": "caption", "text": caption})
            caption_emitted = True
            para = remainder
            if not para:
                continue
        if _is_list_block(para):
            items = [re.sub(r"^([-*•]|\d+[.)])\s+", "", line).strip() for line in para.split("\n")]
            blocks.append({"type": "list", "items": [item for item in items if item]})
        elif _is_quote(para):
            blocks.append({"type": "quote", "text": para.strip("\"“”«» ").strip()})
        else:
            blocks.append({"type": "paragraph", "text": para})
    return blocks


def is_photo_credit_text(text: Optional[str]) -> bool:
    raw = _collapse_spaces(text or "")
    if not raw:
        return False
    if STANDALONE_CREDIT_RE.match(raw) and _word_count(raw) < 28:
        return True
    if LOCATION_CAPTION_RE.match(raw):
        return True
    lower = raw.lower()
    if "(photo by " in lower or "getty images" in lower:
        return True
    return False


def scrub_public_media(media: Sequence[Dict]) -> List[Dict]:
    """Drop Getty/location credits from public media captions. Keep URLs."""
    out = []
    for item in media or []:
        row = dict(item)
        caption = (row.get("caption") or "").strip()
        if row.get("is_hero") or is_photo_credit_text(caption):
            row["caption"] = ""
        out.append(row)
    return out


def lift_hero_caption(blocks: List[Dict], media: Sequence[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Remove leading photo-credit blocks from prose. Do not publish them as captions."""
    rest = list(blocks or [])
    if rest and rest[0].get("type") == "caption":
        rest = rest[1:]
    return rest, scrub_public_media(media)


def scrub_public_blocks(blocks: Sequence[Dict]) -> List[Dict]:
    """Never let photo credits leak into public prose or caption blocks."""
    out = []
    for block in blocks or []:
        btype = block.get("type")
        if btype == "caption":
            continue
        if btype == "paragraph" and is_photo_credit_text(block.get("text")):
            continue
        out.append(block)
    return out


def sanitize_body(text: Optional[str], title: Optional[str] = None) -> str:
    blocks = to_blocks(text or "", title=title)
    parts = []
    for block in blocks:
        if block["type"] == "caption":
            continue
        if block["type"] == "paragraph" and is_photo_credit_text(block.get("text")):
            continue
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


MEDIA_CREST_RE = re.compile(
    r"(?:^|[/?._~-])(?:logo|crest|badge|escudo|wordmark|coat[-_]?of[-_]?arms|"
    r"club[-_]?mark|team[-_]?logo)(?:[/?._~-]|$)",
    re.IGNORECASE,
)
MEDIA_GRAPHIC_RE = re.compile(
    r"(?:infographic|og[-_]?default|placeholder|sprite|watermark|site[-_]?icon)",
    re.IGNORECASE,
)
LEADING_CATEGORY_RE = re.compile(
    r"^(?:football|soccer|basketball|tennis|motorsport|nba|nfl|mlb|nhl|"
    r"formula\s*1|formula one)\s*$",
    re.IGNORECASE,
)
LEADING_KICKER_RE = re.compile(
    r"^(?:domestic leagues|international(?: news)?|transfer(?:s| news)?|"
    r"breaking(?: news)?|latest(?: news)?|top stories|featured|"
    r"opinion|analysis|rumou?rs|in brief|must read|live blog)\s+",
    re.IGNORECASE,
)
PHOTO_NAME_MARKERS = (
    "photo",
    "getty",
    "match",
    "player",
    "action",
    "crowd",
    "arena",
    "court",
    "pitch",
    "celeb",
    "press",
    "wire",
)
STEM_DIM_RE = re.compile(
    r"^(?P<stem>[a-z0-9]+(?:[-_][a-z0-9]+){0,2})-\d{2,4}x\d{2,4}$",
    re.IGNORECASE,
)


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


def classify_media_url(url: Optional[str]) -> str:
    value = (url or "").strip()
    if not value or not image_is_usable(value):
        return "MISSING"
    lower = value.lower()
    path = lower.split("?", 1)[0]
    if path.endswith(".svg") or ".svg/" in path:
        return "CREST_OR_LOGO"
    if MEDIA_CREST_RE.search(path) or MEDIA_CREST_RE.search(lower):
        return "CREST_OR_LOGO"
    if MEDIA_GRAPHIC_RE.search(lower):
        return "GRAPHIC"
    filename = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    dim_match = STEM_DIM_RE.match(filename)
    if dim_match:
        stem = dim_match.group("stem").replace("_", " ").replace("-", " ")
        if not any(marker in stem for marker in PHOTO_NAME_MARKERS):
            return "CREST_OR_LOGO"
    if re.search(r"\.(?:jpe?g|png|webp|gif)(?:$|\?)", path):
        return "EDITORIAL_PHOTO"
    return "UNKNOWN"


def suitable_for_lead_hero(url: Optional[str]) -> bool:
    return classify_media_url(url) == "EDITORIAL_PHOTO"


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
    flags: List[str] = []
    if title_is_malformed(raw_title):
        flags.append("malformed_title")
    cleaned_title = sanitize_title(raw_title)
    cleaned_summary = sanitize_summary(raw_summary, title=raw_title)
    cleaned_body = sanitize_body(raw_body, title=raw_title)
    combined_clean = " ".join([cleaned_title, cleaned_summary, cleaned_body])
    if has_cdata(combined_clean):
        flags.append("cdata")
    if has_nav_contamination(combined_clean) or chrome_is_interleaved(raw_body):
        flags.append("navigation")
    if has_truncation(combined_clean):
        flags.append("truncation")
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
        kind = classify_media_url(url)
        items.append(
            {
                "id": getattr(row, "id", None),
                "media_type": getattr(row, "media_type", None) or "image",
                "url": url,
                "caption": sanitize_summary(getattr(row, "caption", None)),
                "sort_order": int(getattr(row, "sort_order", 0) or 0),
                "is_hero": bool(getattr(row, "is_hero", False)),
                "presentation": kind,
                "media_kind": kind,
            }
        )
    items.sort(key=lambda item: (not item["is_hero"], item["sort_order"], item["id"] or 0))
    if not items and image_is_usable(image_url):
        kind = classify_media_url(image_url)
        items.append(
            {
                "id": None,
                "media_type": "image",
                "url": image_url,
                "caption": "",
                "sort_order": 0,
                "is_hero": True,
                "presentation": kind,
                "media_kind": kind,
            }
        )
    seen_urls = set()
    unique: List[Dict] = []
    for item in items:
        key = (item.get("url") or "").split("?", 1)[0]
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(item)
    return unique


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
