"""Fetch and extract article text from a canonical source URL."""

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import List, Optional, Tuple

import httpx

from .site_chrome import is_site_chrome_text, strip_site_chrome
from .textutil import clean_text

logger = logging.getLogger(__name__)

USER_AGENT = (
    "NinkoSportsBot/1.0 (+https://ninkosports.com; editorial extraction)"
)

CHROME_TAGS = {
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "menu",
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "button",
    "input",
    "select",
    "textarea",
    "label",
}
CHROME_ROLES = {
    "navigation",
    "banner",
    "contentinfo",
    "complementary",
    "search",
    "menu",
}
CHROME_ATTR_RE = re.compile(
    r"\b(?:site-nav|global-nav|main-nav|footer-nav|skiplink|skip-link|"
    r"cookie|consent|newsletter|subscribe|masthead|sidebar)\b",
    re.IGNORECASE,
)


def _og(html: str, prop: str) -> Optional[str]:
    match = re.search(
        rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']',
        html,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _attr_map(attrs) -> dict:
    return {str(key).lower(): str(value or "") for key, value in attrs}


def _is_chrome_open(tag: str, attrs) -> bool:
    if tag in CHROME_TAGS:
        return True
    attrs = _attr_map(attrs)
    role = attrs.get("role", "").lower()
    if role in CHROME_ROLES:
        return True
    blob = " ".join(
        [
            attrs.get("class", ""),
            attrs.get("id", ""),
            attrs.get("aria-label", ""),
        ]
    )
    return bool(CHROME_ATTR_RE.search(blob))


class _ArticleExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.in_p = 0
        self.in_main = 0
        self.buf: List[str] = []
        self.main_parts: List[str] = []
        self.body_parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.ignore:
            self.ignore += 1
            return
        if _is_chrome_open(tag, attrs):
            self.ignore = 1
            return
        attrs_map = _attr_map(attrs)
        if tag in {"article", "main"} or attrs_map.get("role", "").lower() == "main":
            self.in_main += 1
        if tag in {"p", "h2"}:
            self.in_p += 1
            self.buf = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.ignore:
            self.ignore = max(0, self.ignore - 1)
            return
        if tag in {"p", "h2"} and self.in_p:
            self.in_p -= 1
            text = clean_text("".join(self.buf))
            self.buf = []
            if _keep_paragraph(text):
                target = self.main_parts if self.in_main else self.body_parts
                target.append(text)
        if tag in {"article", "main"} and self.in_main:
            self.in_main -= 1

    def handle_data(self, data):
        if self.ignore or not self.in_p:
            return
        self.buf.append(data)


def _keep_paragraph(text: str) -> bool:
    if len(text) < 40:
        return False
    if is_site_chrome_text(text):
        return False
    lower = text.lower()
    if any(
        junk in lower
        for junk in (
            "cookie",
            "newsletter",
            "subscribe",
            "all rights reserved",
            "privacy policy",
            "skip to main content",
            "skip to navigation",
        )
    ):
        return False
    return True


def paragraphs_from_html(html: str) -> str:
    parser = _ArticleExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        logger.info("[extract] HTML parse failed; falling back to tag scan")
    parts = parser.main_parts or parser.body_parts
    cleaned = []
    seen = set()
    for part in parts:
        text = strip_site_chrome(part) or part
        if not _keep_paragraph(text):
            continue
        key = text[:80]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= 20:
            break
    return "\n\n".join(cleaned)


def parse_feed_datetime(entry) -> Optional[datetime]:
    for attr in ("published", "updated", "created"):
        raw = entry.get(attr) if hasattr(entry, "get") else None
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw)
        except Exception:
            continue
    parsed = entry.get("published_parsed") if hasattr(entry, "get") else None
    if parsed:
        try:
            return datetime(*parsed[:6])
        except Exception:
            return None
    return None


def extract_from_url(url: str, timeout: float = 12.0) -> Tuple[str, Optional[str]]:
    """
    Returns (article_text, image_url_or_none).
    Empty text means extraction failed; caller must not invent facts.
    """
    if not url:
        return "", None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                logger.info("[extract] HTTP %s for %s", resp.status_code, url)
                return "", None
            html = resp.text or ""
    except Exception as e:
        logger.info("[extract] failed %s: %s", url, e)
        return "", None

    image = _og(html, "og:image")
    text = paragraphs_from_html(html)
    text = strip_site_chrome(text) or text
    if is_site_chrome_text(text):
        text = ""
    if len(text) < 80:
        desc = _og(html, "og:description")
        if desc:
            desc = strip_site_chrome(clean_text(desc))
            if desc and not is_site_chrome_text(desc):
                text = desc
    return text, image
