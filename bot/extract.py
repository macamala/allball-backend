"""Fetch and extract article text from a canonical source URL."""

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple

import httpx

from .textutil import clean_text

logger = logging.getLogger(__name__)

USER_AGENT = (
    "NinkoSportsBot/1.0 (+https://ninkosports.com; editorial extraction)"
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


def _paragraphs_from_html(html: str) -> str:
    blocks = re.findall(
        r"<(?:p|article|h1|h2)[^>]*>(.*?)</(?:p|article|h1|h2)>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    parts = []
    seen = set()
    for raw in blocks:
        text = clean_text(raw)
        if len(text) < 40:
            continue
        key = text[:80]
        if key in seen:
            continue
        seen.add(key)
        lower = text.lower()
        if any(
            junk in lower
            for junk in (
                "cookie",
                "newsletter",
                "subscribe",
                "all rights reserved",
                "privacy policy",
            )
        ):
            continue
        parts.append(text)
        if len(parts) >= 12:
            break
    return "\n\n".join(parts)


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
    text = _paragraphs_from_html(html)
    if len(text) < 80:
        desc = _og(html, "og:description")
        if desc:
            text = clean_text(desc)
    return text, image
