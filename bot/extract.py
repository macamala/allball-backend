"""Fetch and extract article text from a canonical source URL."""

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import httpx

from .quality import is_substantial_source
from .site_chrome import is_site_chrome_text, strip_site_chrome
from .textutil import clean_text, word_count

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
    "(compatible; NinkoSportsBot/1.0; +https://ninkosports.com)"
)
EXTRACT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
ARTICLE_TAGS = {"p", "h2", "h3", "blockquote"}
MAX_PARAGRAPHS = 40

class _JsonLdParser(HTMLParser):
    """Decode HTML attributes, while preserving the JSON script text verbatim."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.collecting = False
        self.parts = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            mime = str(dict(attrs).get("type") or "").strip().lower()
            self.collecting = mime == "application/ld+json"
            self.parts = []

    def handle_data(self, data):
        if self.collecting:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.collecting:
            self.blocks.append("".join(self.parts))
            self.collecting = False
            self.parts = []


def _json_ld_blocks(html: str) -> List[str]:
    parser = _JsonLdParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return []
    return parser.blocks

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
    "template",
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
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = {}

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "meta":
            row = dict(attrs)
            key = row.get("property") or row.get("name")
            if key and row.get("content"):
                self.values[str(key).lower()] = row["content"].strip()


def _metadata(html: str, key: str) -> Optional[str]:
    parser = _MetaParser()
    for tag in re.findall(r"<meta\b[^>]*>", html or "", re.I):
        parser.feed(tag)
    return parser.values.get(key.lower())
CHROME_ATTR_RE = re.compile(
    r"\b(?:site-nav|global-nav|main-nav|footer-nav|skiplink|skip-link|"
    r"cookie|consent|newsletter|subscribe|masthead|sidebar|"
    r"article-widget--player|news-aside-list|news-container-item|latest-videos-block|bn-chat-premium|"
    r"recommended-news|related-news|category-news|miya-galerija-video|mobile-app|google-follow|footer-top|acknowledgement-of-country)\b",
    re.IGNORECASE,
)


def _og(html: str, prop: str) -> Optional[str]:
    return _metadata(html, prop)


def _meta_name(html: str, name: str) -> Optional[str]:
    return _metadata(html, name)


def _parse_explicit_datetime(raw: Optional[str]) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    parsed = None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError, IndexError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed is None or parsed.tzinfo is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def page_title_from_html(html: str) -> str:
    title = _og(html or "", "og:title") or _meta_name(html or "", "twitter:title")
    if title:
        return clean_text(title)
    for raw in _json_ld_blocks(html):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items = data["@graph"]
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("headline") or item.get("name")
            if isinstance(value, str) and value.strip():
                return clean_text(value)
    match = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    return clean_text(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


def page_published_at_from_html(html: str) -> Optional[datetime]:
    candidates = [
        _og(html or "", "article:published_time"),
        _meta_name(html or "", "article:published_time"),
        _meta_name(html or "", "date"),
        _meta_name(html or "", "pubdate"),
    ]
    for raw in _json_ld_blocks(html):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items = data["@graph"]
        for item in items:
            if isinstance(item, dict):
                value = item.get("datePublished")
                if isinstance(value, str):
                    candidates.append(value)
    for match in re.finditer(r"<time[^>]+datetime=[\"']([^\"']+)", html or "", re.I):
        candidates.append(match.group(1))
    for value in candidates:
        parsed = _parse_explicit_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _json_ld_images(html: str) -> List[dict]:
    out: List[dict] = []
    for raw in _json_ld_blocks(html):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items = data["@graph"]
        for item in items:
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            rows = image if isinstance(image, list) else [image]
            for row in rows:
                url = ""
                width = 0
                height = 0
                if isinstance(row, str):
                    url = row
                elif isinstance(row, dict):
                    url = row.get("url") or row.get("@id") or ""
                    try:
                        width = int(row.get("width") or 0)
                    except (TypeError, ValueError):
                        width = 0
                    try:
                        height = int(row.get("height") or 0)
                    except (TypeError, ValueError):
                        height = 0
                if url:
                    out.append(
                        {
                            "url": url,
                            "source": "jsonld",
                            "width": width,
                            "height": height,
                            "in_article": True,
                        }
                    )
    return out


class _LeadImageExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore = 0
        self.in_main = 0
        self.images: List[dict] = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.ignore:
            if tag not in VOID_TAGS:
                self.ignore += 1
            return
        if _is_chrome_open(tag, attrs):
            self.ignore = 0 if tag in VOID_TAGS else 1
            return
        attrs_map = _attr_map(attrs)
        if tag in {"article", "main"} or attrs_map.get("role", "").lower() == "main":
            self.in_main += 1
        if tag != "img":
            return
        src = attrs_map.get("src") or attrs_map.get("data-src") or ""
        if not src:
            return
        width = 0
        height = 0
        try:
            width = int(attrs_map.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
        try:
            height = int(attrs_map.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        self.images.append(
            {
                "url": src,
                "source": "body",
                "width": width,
                "height": height,
                "alt": attrs_map.get("alt") or "",
                "in_article": bool(self.in_main),
            }
        )

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.ignore:
            self.ignore = max(0, self.ignore - 1)
            return
        if tag in {"article", "main"} and self.in_main:
            self.in_main -= 1


def collect_page_image_candidates(html: str) -> List[dict]:
    candidates: List[dict] = []
    og = _og(html, "og:image")
    if og:
        candidates.append({"url": og, "source": "og", "in_article": False})
    twitter = _meta_name(html, "twitter:image") or _meta_name(html, "twitter:image:src")
    if twitter:
        candidates.append({"url": twitter, "source": "twitter", "in_article": False})
    candidates.extend(_json_ld_images(html))
    parser = _LeadImageExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        parser.images = []
    candidates.extend(parser.images[:8])
    return candidates


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

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.ignore:
            if tag not in VOID_TAGS:
                self.ignore += 1
            return
        if _is_chrome_open(tag, attrs):
            self.ignore = 0 if tag in VOID_TAGS else 1
            return
        attrs_map = _attr_map(attrs)
        if tag in {"article", "main"} or attrs_map.get("role", "").lower() == "main":
            self.in_main += 1
        if tag in ARTICLE_TAGS:
            # HTML permits omitted </p> before the next paragraph.
            self._flush_paragraph()
            self.in_p = 1
            self.buf = []

    def _flush_paragraph(self):
        if not self.in_p:
            return
        text = clean_text("".join(self.buf))
        self.buf = []
        self.in_p = 0
        if _keep_paragraph(text):
            target = self.main_parts if self.in_main else self.body_parts
            target.append(text)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.ignore:
            self.ignore = max(0, self.ignore - 1)
            return
        if tag in ARTICLE_TAGS and self.in_p:
            self._flush_paragraph()
        if tag in {"article", "main"} and self.in_main:
            self._flush_paragraph()
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
        if len(cleaned) >= MAX_PARAGRAPHS:
            break
    return "\n\n".join(cleaned)


def parse_feed_datetime(entry) -> Optional[datetime]:
    """Keep publication ahead of modification, including Atom/ISO feed dates.

    Explicit offsets and feedparser *_parsed tuples are normalized to UTC.
    Naive source values remain naive; missing/invalid dates never become now.
    The existing datetime storage contract is unchanged; no old row is rewritten.
    """
    getter = getattr(entry, "get", None)
    if not callable(getter):
        return None
    for attr in ("published", "updated", "created"):
        raw = getter(attr)
        value = None
        if isinstance(raw, str) and raw.strip():
            raw = raw.strip()
            try:
                value = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError, IndexError):
                try:
                    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except (TypeError, ValueError, OverflowError):
                    pass
        if value is not None:
            return value.astimezone(timezone.utc) if value.tzinfo is not None else value
        # Check this field's parsed form BEFORE trying a later field. A valid
        # published_parsed must never lose to an updated or created timestamp.
        parsed = getter(f"{attr}_parsed")
        if isinstance(parsed, (tuple, list)) and len(parsed) >= 6:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _json_ld_article_body(html: str) -> str:
    """Same article prose from JSON-LD; never a different story or RSS blurb."""
    for raw in _json_ld_blocks(html):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items = data["@graph"]
        for item in items:
            if not isinstance(item, dict):
                continue
            body = item.get("articleBody")
            if not body or not isinstance(body, str):
                continue
            text = strip_site_chrome(clean_text(body)) or clean_text(body)
            if text and not is_site_chrome_text(text) and word_count(text) >= 80:
                return text
    return ""


class _ScopedNewsBody(HTMLParser):
    """Capture a known CMS article body, excluding later recommendation grids."""
    def __init__(self, body_class="single-news-content"):
        super().__init__(convert_charrefs=False)
        self.body_class = body_class
        self.root_tag = None
        self.depth = 0
        self.finished = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.finished:
            return
        if not self.depth:
            if self.body_class in dict(attrs).get('class', '').split():
                self.root_tag = tag
                self.depth = 1
            return
        self.parts.append(self.get_starttag_text())
        if tag == self.root_tag:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.depth and tag not in VOID_TAGS:
            if tag == self.root_tag:
                self.depth -= 1
            if self.depth:
                self.parts.append(f'</{tag}>')
            else:
                self.finished = True

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data(f'&{name};')

    def handle_charref(self, name):
        self.handle_data(f'&#{name};')


def article_text_from_html(html: str) -> str:
    body_class = 'single-news-content' if 'single-news-content' in (html or '') else None
    # Mozzart's article container is distinct from headline grids and betting
    # widgets. Only apply its class under its own canonical publisher metadata.
    canonical = _og(html or '', 'og:url') or _meta_name(html or '', 'url') or ''
    try:
        publisher_host = urlsplit(canonical).hostname
    except ValueError:
        publisher_host = None
    if publisher_host == 'www.mozzartsport.com':
        body_class = 'news-content'
    if body_class:
        scoped = _ScopedNewsBody(body_class)
        try:
            scoped.feed(html)
            scoped.close()
        except Exception:
            return ''
        if not scoped.finished:
            return ''
        html = ''.join(scoped.parts)
    text = paragraphs_from_html(html or "")
    text = strip_site_chrome(text) or text
    if is_site_chrome_text(text):
        text = ""
    if not is_substantial_source(text):
        ld_body = _json_ld_article_body(html or "")
        if word_count(ld_body) > word_count(text):
            text = ld_body
    return text


def extract_image_candidates_from_url(url: str, timeout: float = 12.0) -> List[dict]:
    """Fetch one canonical article page and return its real image candidates.

    Used by the bounded image-health repair path. It does no AI work and does
    not choose a winner; callers can probe several ranked candidates when a
    publisher's primary og:image has expired.
    """
    if not url:
        return []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=EXTRACT_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                logger.info("[extract-images] HTTP %s for %s", resp.status_code, url)
                return []
            html = resp.text or ""
            base_url = str(getattr(resp, "url", None) or url)
    except Exception as e:
        logger.info("[extract-images] failed %s: %s", url, e)
        return []

    output = []
    seen = set()
    for candidate in collect_page_image_candidates(html):
        if not isinstance(candidate, dict):
            continue
        raw = str(candidate.get("url") or "").strip()
        if not raw:
            continue
        resolved = urljoin(base_url, raw)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        row = dict(candidate)
        row["url"] = resolved
        output.append(row)
    return output


def extract_from_url(url: str, timeout: float = 18.0) -> Tuple[str, Optional[str]]:
    """
    Returns (article_text, image_url_or_none).
    Empty text means extraction failed; caller must not invent facts.
    Never substitutes og:description / RSS metadata for the article body.
    """
    if not url:
        return "", None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=EXTRACT_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                logger.info("[extract] HTTP %s for %s", resp.status_code, url)
                return "", None
            html = resp.text or ""
    except Exception as e:
        logger.info("[extract] failed %s: %s", url, e)
        return "", None

    image = None
    try:
        from editorial import pick_article_image

        image = pick_article_image(collect_page_image_candidates(html))
    except Exception:
        image = _og(html, "og:image")
    text = article_text_from_html(html)
    logger.info(
        "[extract] %s words=%s",
        url[:120],
        word_count(text),
    )
    return text, image
