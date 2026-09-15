"""Generic publisher-chrome detection and stripping.

Never keys off a publisher brand. Legitimate prose that mentions
BBC, Football, News, Home, etc. must survive.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

# UI chrome — not publisher names.
CHROME_PHRASES = (
    "accessibility help",
    "your account",
    "more menu",
    "close menu",
    "skip to content",
    "skip to main content",
    "skip to navigation",
    "skip to main navigation",
    "to play this video you need to enable javascript",
    "enable javascript in your browser",
    "cookie consent",
    "accept all cookies",
    "manage cookies",
    "cookie settings",
    "sign in to your account",
    "create your account",
    "help & faqs",
    "help and faqs",
    "full sports a-z",
)

CHROME_PHRASE_RE = re.compile(
    "|".join(re.escape(p) for p in CHROME_PHRASES),
    re.IGNORECASE,
)
JS_VIDEO_RE = re.compile(
    r"to play this video you need to enable javascript(?: in your browser)?",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’&+.-]{0,24}")
NAV_TOKEN_RE = re.compile(r"^[A-Z0-9][A-Za-z0-9'’+.-]{0,22}$")
IMAGE_CAPTION_PREFIX_RE = re.compile(r"^image captions?\s*[,:\-–—]?\s*", re.IGNORECASE)
PUBLISHED_AGO_PREFIX_RE = re.compile(
    r"^(?:published|updated)\s+\d+\s+(?:minute|hour|day|week)s?\s+ago\s*",
    re.IGNORECASE,
)
STANDALONE_CMS_RE = re.compile(
    r"^(?:image captions?|top scorers(?:\s+gossip)?|scorers(?:\s+gossip)?|gossip|"
    r"scores?\s*(?:&|and)\s*fixtures|live scores?|match reports?|"
    r"(?:published|updated)\s+\d+\s+(?:minute|hour|day|week)s?\s+ago)$",
    re.IGNORECASE,
)

PROSE_STOP = {
    "the", "a", "an", "and", "of", "to", "in", "for", "with", "on", "at",
    "from", "by", "as", "is", "was", "were", "be", "been", "are", "that",
    "this", "it", "his", "her", "their", "has", "have", "had", "not", "but",
    "or", "he", "she", "said", "will", "would", "could", "after", "before",
    "during", "against", "into", "about", "over", "than", "also", "who",
    "which", "when", "while", "they", "we", "been",
    "says", "said", "scored", "beat", "won", "lost",
}


def _tokens(text: str) -> List[str]:
    return TOKEN_RE.findall(text or "")


def _is_nav_token(token: str) -> bool:
    if not token or token.lower() in PROSE_STOP:
        return False
    if re.search(r"[.?,!:;]", token):
        return False
    if any(ch.islower() for ch in token[1:]):
        # Title Case single words can be nav labels; mixed inner lower is still Title Case.
        if token[0].isupper() and token[1:].islower() and len(token) <= 16:
            return True
        return False
    return bool(NAV_TOKEN_RE.match(token))


def nav_label_run(text: str) -> int:
    longest = current = 0
    for token in _tokens(text):
        if _is_nav_token(token):
            current += 1
            if current > longest:
                longest = current
        else:
            current = 0
    return longest


def chrome_phrase_hits(text: str) -> int:
    if not text:
        return 0
    lower = text.lower()
    return sum(1 for phrase in CHROME_PHRASES if phrase in lower)


def _stop_ratio(text: str) -> float:
    words = [token.lower() for token in _tokens(text)]
    if not words:
        return 1.0
    return sum(1 for word in words if word in PROSE_STOP) / len(words)


def is_site_chrome_text(text: Optional[str]) -> bool:
    """True when text is confidently publisher UI, not sports prose."""
    raw = (text or "").strip()
    if not raw:
        return False
    hits = chrome_phrase_hits(raw)
    run = nav_label_run(raw)
    if hits >= 2:
        return True
    if hits >= 1 and run >= 10:
        return True
    if run >= 18 and _stop_ratio(raw) < 0.08:
        return True
    tokens = _tokens(raw)
    if (
        len(tokens) >= 7
        and run >= 7
        and run >= len(tokens) - 1
        and _stop_ratio(raw) < 0.08
        and "." not in raw
        and not re.search(r"[\d|:?!]", raw)
    ):
        return True
    return False


def _window_is_prose(tokens: Iterable[str]) -> bool:
    items = list(tokens)
    if len(items) < 7:
        return False
    words = [re.sub(r"[^A-Za-z']", "", tok).lower() for tok in items]
    words = [word for word in words if word]
    if len(words) < 7:
        return False
    stops = sum(1 for word in words if word in PROSE_STOP)
    if stops < 3:
        return False
    lower_tokens = sum(1 for tok in items if tok.islower() or (tok[:1].islower()))
    return lower_tokens >= 2


def strip_site_chrome(text: Optional[str]) -> str:
    """Drop leading/interleaved UI chrome. Keep remaining article prose."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if not is_site_chrome_text(raw):
        return raw
    raw = JS_VIDEO_RE.sub(" ", raw)
    raw = CHROME_PHRASE_RE.sub(" ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return ""
    tokens = raw.split()
    start = 0
    while start < len(tokens):
        window = tokens[start : start + 10]
        if _window_is_prose(window):
            break
        start += 1
    else:
        return ""
    rest = " ".join(tokens[start:]).strip()
    if not rest:
        return ""
    if is_site_chrome_text(rest) and nav_label_run(rest) >= 10:
        return ""
    return rest


def is_standalone_cms_fragment(text: Optional[str]) -> bool:
    """True for a whole paragraph that is only CMS chrome, not a real sentence."""
    raw = (text or "").strip().rstrip(".,;:")
    return bool(raw) and bool(STANDALONE_CMS_RE.match(raw))


def is_cms_kicker_prefix(prefix: Optional[str]) -> bool:
    """Title-case nav labels with no sentence punctuation — not mid-sentence words."""
    raw = (prefix or "").strip()
    if not raw or len(raw) > 80 or re.search(r"[.!?]", raw):
        return False
    tokens = TOKEN_RE.findall(raw)
    if not 1 <= len(tokens) <= 6:
        return False
    return all(_is_nav_token(token) or token.lower() in {"and", "&"} for token in tokens)


def strip_leading_cms_chrome(text: Optional[str], title: Optional[str] = None) -> str:
    """Drop leading CMS crumbs and Image caption prefixes. Preserve later prose."""
    raw = (text or "").strip()
    if not raw:
        return ""
    raw = IMAGE_CAPTION_PREFIX_RE.sub("", raw, count=1).strip()
    raw = PUBLISHED_AGO_PREFIX_RE.sub("", raw, count=1).strip()
    title_clean = re.sub(r"\s+", " ", (title or "").strip())
    if title_clean and len(title_clean) >= 8:
        idx = raw.lower().find(title_clean.lower())
        if 0 < idx <= 80:
            prefix = raw[:idx].strip()
            if is_cms_kicker_prefix(prefix) or is_standalone_cms_fragment(prefix):
                raw = raw[idx:].strip()
    return raw
