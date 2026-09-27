"""Bounded discovery from official sports-news index pages and sitemaps.

This is discovery only, not a licence claim. Every source is an allowlisted
first-party sports/esports site. Index and article reads reuse the robots-aware
public News transport, reject cross-host links, and fail closed on missing
explicit publication timestamps or missing article prose.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

from .extract import (
    article_text_from_html,
    collect_page_image_candidates,
    page_published_at_from_html,
    page_title_from_html,
)
from .news_feed_http import read_news_feed
from .news_policy import freshness_reason
from .textutil import clean_text

logger = logging.getLogger(__name__)

HTML_INDEXES = (
    {
        "id": "ihf-handball",
        "sport": "handball",
        "publisher": "IHF",
        "url": "https://www.ihf.info/media-center/news",
        "host": "www.ihf.info",
        "paths": ("/media-center/news/",),
    },
    {
        "id": "valorant-esports",
        "sport": "valorant",
        "publisher": "VALORANT Esports",
        "url": "https://valorantesports.com/en-US/news",
        "host": "valorantesports.com",
        "paths": ("/news/", "/en-US/news/"),
        "force_locale": "/en-US/news/",
    },
    {
        "id": "lol-esports",
        "sport": "league-of-legends",
        "publisher": "LoL Esports",
        "url": "https://lolesports.com/en-US/lolesports/news",
        "host": "lolesports.com",
        "paths": ("/news/", "/en-US/news/"),
        "force_locale": "/en-US/news/",
    },
    {
        "id": "rocket-league-competitive",
        "sport": "rocket-league",
        "publisher": "Rocket League",
        "url": "https://www.rocketleague.com/news/tag/competitive",
        "host": "www.rocketleague.com",
        "paths": ("/news/",),
        "exclude_paths": ("/news/tag/",),
    },
    {
        # The public page is JS-heavy in some clients. If no ordinary anchors
        # are present this source simply yields zero rows; it never falls back
        # to a third-party scraper.
        "id": "call-of-duty-league",
        "sport": "call-of-duty",
        "publisher": "Call of Duty League",
        "url": "https://callofdutyleague.com/en-us/news",
        "host": "callofdutyleague.com",
        "paths": ("/en-us/news/", "/news/"),
    },
    {
        # Generic Overwatch news also contains game updates, so only esports
        # anchors with explicit competitive markers are admitted.
        "id": "overwatch-esports",
        "sport": "overwatch",
        "publisher": "Overwatch",
        "url": "https://overwatch.blizzard.com/en-us/news/",
        "host": "overwatch.blizzard.com",
        "paths": ("/en-us/news/",),
        "keywords": ("owcs", "esports", "world cup", "competitive"),
    },
)

SITEMAPS = (
    {
        "id": "uefa-futsal",
        "sport": "futsal",
        "publisher": "UEFA",
        "url": "https://www.uefa.com/sitemap/news/latest.xml",
        "host": "www.uefa.com",
        "url_markers": ("uefafutsalchampionsleague",),
        "title_markers": ("futsal",),
    },
)

MAX_INDEX_BYTES = 2_000_000
MAX_LINKS_PER_SOURCE = 8


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_href: Optional[str] = None
        self.current_text: List[str] = []
        self.links: List[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a" or self.current_href is not None:
            return
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        href = values.get("href", "").strip()
        if href:
            self.current_href = href
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self.current_href is None:
            return
        text = clean_text(" ".join(self.current_text))
        self.links.append((self.current_href, text))
        self.current_href = None
        self.current_text = []


def _same_host_url(base: str, href: str, expected_host: str, cfg: Dict) -> Optional[str]:
    try:
        absolute = urljoin(base, href)
        parts = urlsplit(absolute)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname != expected_host:
        return None
    path = parts.path or "/"
    if not any(path.startswith(prefix) for prefix in cfg.get("paths", ())):
        return None
    if any(path.startswith(prefix) for prefix in cfg.get("exclude_paths", ())):
        return None
    force_locale = cfg.get("force_locale")
    if force_locale and path.startswith("/news/"):
        suffix = path[len("/news/") :]
        absolute = f"https://{expected_host}{force_locale}{suffix}"
        parts = urlsplit(absolute)
        path = parts.path
    return absolute.split("#", 1)[0]


def _anchor_candidates(cfg: Dict) -> List[tuple[str, str]]:
    try:
        raw = read_news_feed(cfg["url"])
        if len(raw) > MAX_INDEX_BYTES:
            return []
        html = raw.decode("utf-8", "replace")
    except Exception as exc:
        logger.info("[official_index] index unavailable %s: %s", cfg["id"], type(exc).__name__)
        return []
    parser = _AnchorParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return []

    output: List[tuple[str, str]] = []
    seen = set()
    required = tuple(str(x).lower() for x in cfg.get("keywords", ()))
    for href, title in parser.links:
        url = _same_host_url(cfg["url"], href, cfg["host"], cfg)
        if not url or url in seen:
            continue
        text = clean_text(title)
        if required and not any(marker in text.lower() for marker in required):
            continue
        if not text or text.lower() in {"read more", "news", "latest", "image"}:
            continue
        seen.add(url)
        output.append((url, text))
        if len(output) >= MAX_LINKS_PER_SOURCE:
            break
    return output


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(node, wanted: str) -> str:
    wanted = wanted.lower()
    for child in node.iter():
        if _local_name(str(child.tag)) == wanted and child.text:
            return clean_text(child.text)
    return ""


def _sitemap_candidates(cfg: Dict) -> List[tuple[str, str]]:
    try:
        raw = read_news_feed(cfg["url"])
        if len(raw) > MAX_INDEX_BYTES:
            return []
        root = ET.fromstring(raw)
    except Exception as exc:
        logger.info("[official_index] sitemap unavailable %s: %s", cfg["id"], type(exc).__name__)
        return []

    output: List[tuple[str, str]] = []
    seen = set()
    for node in root.iter():
        if _local_name(str(node.tag)) != "url":
            continue
        loc = _child_text(node, "loc")
        title = _child_text(node, "title")
        try:
            parts = urlsplit(loc)
        except ValueError:
            continue
        if parts.scheme != "https" or parts.hostname != cfg["host"]:
            continue
        blob = f"{loc} {title}".lower()
        url_ok = any(marker in blob for marker in cfg.get("url_markers", ()))
        title_ok = any(marker in blob for marker in cfg.get("title_markers", ()))
        if not (url_ok or title_ok) or loc in seen:
            continue
        seen.add(loc)
        output.append((loc.split("#", 1)[0], title))
        if len(output) >= MAX_LINKS_PER_SOURCE:
            break
    return output


def _hydrate(cfg: Dict, url: str, fallback_title: str) -> Optional[Dict]:
    try:
        raw = read_news_feed(url)
        if len(raw) > MAX_INDEX_BYTES:
            return None
        html = raw.decode("utf-8", "replace")
    except Exception as exc:
        logger.info("[official_index] article unavailable %s: %s", cfg["id"], type(exc).__name__)
        return None

    published_at = page_published_at_from_html(html)
    if published_at is None or freshness_reason(published_at, datetime.now(timezone.utc)):
        return None
    title = page_title_from_html(html) or fallback_title
    body = article_text_from_html(html)
    if not title or not body:
        return None
    image = None
    try:
        from editorial import pick_article_image

        image = pick_article_image(collect_page_image_candidates(html))
    except Exception:
        image = None
    feed = {
        "url": cfg["url"],
        "kind": "league",
        "sport": cfg["sport"],
        "league": None,
        "country": "international",
        "publisher": cfg["publisher"],
        "enabled": True,
        "note": "first-party official index; article page hydrated before admission",
    }
    return {
        "title": clean_text(title),
        "summary": "",
        "url": url,
        "image": image,
        "image_candidates": [],
        "published_at": published_at,
        "feed": feed,
        "_extracted": body,
        "_extracted_image": image,
    }


def fetch_official_index_entries(max_per_source: int = 3) -> List[Dict]:
    """Return fresh hydrated official stories; never writes DB or calls AI."""
    limit = max(1, min(int(max_per_source), 5))
    items: List[Dict] = []
    for cfg in HTML_INDEXES:
        hydrated = 0
        for url, title in _anchor_candidates(cfg):
            item = _hydrate(cfg, url, title)
            if item is None:
                continue
            items.append(item)
            hydrated += 1
            if hydrated >= limit:
                break
    for cfg in SITEMAPS:
        hydrated = 0
        for url, title in _sitemap_candidates(cfg):
            item = _hydrate(cfg, url, title)
            if item is None:
                continue
            items.append(item)
            hydrated += 1
            if hydrated >= limit:
                break
    return items
