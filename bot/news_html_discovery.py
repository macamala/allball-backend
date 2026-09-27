"""Bounded first-party HTML discovery for News sources without usable RSS.

Discovery extracts only metadata needed to locate a fresh article. Full article
facts are fetched later by the shared ingestion path and must pass the same
classification, factuality, originality and publication gates as RSS items.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .extract import _meta_name, _og
from .news_feed_http import read_news_feed
from .news_policy import canonical_news_url, freshness_reason
from .textutil import clean_text, looks_like_garbage

ARTICLE_TYPES = {"NewsArticle", "Article", "BlogPosting", "ReportageNewsArticle"}
LD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
TIME_RE = re.compile(r'<time[^>]+datetime=["\']([^"\']+)', re.I)
META_PUBLISHED_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|datePublished|date)["\'][^>]+content=["\']([^"\']+)',
    re.I,
)
ABS_URL_RE = re.compile(r'https://[^"\'<>\s]+', re.I)


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.href = None
        self.buf = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        data = dict(attrs)
        self.href = data.get("href")
        self.buf = []

    def handle_data(self, data):
        if self.href is not None:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self.href is None:
            return
        text = clean_text(" ".join(self.buf))
        self.links.append((self.href, text))
        self.href = None
        self.buf = []


def _iter_ld(value):
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_ld(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_ld(item)


def _parse_time(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed:
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except Exception:
        return None


def _article_metadata(html, fallback_url):
    best = {}
    for raw in LD_RE.findall(html or ""):
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        for item in _iter_ld(payload):
            kind = item.get("@type")
            kinds = set(kind if isinstance(kind, list) else [kind])
            if not (kinds & ARTICLE_TYPES):
                continue
            headline = clean_text(item.get("headline") or item.get("name") or "")
            stamp = _parse_time(item.get("datePublished") or item.get("dateCreated") or "")
            url = item.get("url")
            if isinstance(item.get("mainEntityOfPage"), dict):
                url = url or item["mainEntityOfPage"].get("@id")
            best = {
                "title": headline,
                "published_at": stamp,
                "url": canonical_news_url(url or fallback_url) or fallback_url,
            }
            if headline and stamp:
                return best

    title = clean_text(_og(html, "og:title") or _meta_name(html, "twitter:title") or "")
    raw_stamp = None
    m = META_PUBLISHED_RE.search(html or "") or TIME_RE.search(html or "")
    if m:
        raw_stamp = m.group(1)
    return {
        "title": title,
        "published_at": _parse_time(raw_stamp),
        "url": fallback_url,
    }


def _allowed_article(url, cfg):
    canonical = canonical_news_url(url)
    if not canonical:
        return None
    landing = canonical_news_url(cfg["url"])
    if canonical == landing:
        return None
    parts = urlsplit(canonical)
    root = urlsplit(cfg["url"])
    if (parts.hostname or "").lower().removeprefix("www.") != (root.hostname or "").lower().removeprefix("www."):
        return None
    prefixes = tuple(cfg.get("article_prefixes") or ())
    if prefixes and not any(parts.path.startswith(prefix) for prefix in prefixes):
        return None
    return canonical


def _candidate_links(html, cfg):
    parser = _LinkParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    raw = (html or "").replace("\\/", "/")
    rows = list(parser.links)
    rows += [(url, "") for url in ABS_URL_RE.findall(raw)]
    out = []
    seen = set()
    for href, text in rows:
        url = _allowed_article(urljoin(cfg["url"], href), cfg)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append((url, clean_text(text)))
        if len(out) >= 80:
            break
    return out


def discover_official_html(cfg, max_articles=3):
    """Return fresh metadata items in the same shape as RSS discovery."""
    raw = read_news_feed(cfg["url"])
    html = raw.decode("utf-8", "replace")
    now = datetime.now(timezone.utc)
    items = []
    probes = 0
    max_probes = max(8, max_articles * 5)
    for url, anchor_title in _candidate_links(html, cfg):
        if probes >= max_probes:
            break
        probes += 1
        try:
            article_raw = read_news_feed(url)
        except Exception:
            continue
        meta = _article_metadata(article_raw.decode("utf-8", "replace"), url)
        title = clean_text(meta.get("title") or anchor_title)
        stamp = meta.get("published_at")
        if not title or looks_like_garbage(title) or freshness_reason(stamp, now):
            continue
        items.append(
            {
                "title": title,
                "summary": "",
                "url": meta.get("url") or url,
                # Do not inherit publisher images from HTML discovery. Media rights
                # are a separate review surface.
                "image": None,
                "image_candidates": [],
                "published_at": stamp,
                "feed": cfg,
            }
        )
    items.sort(key=lambda item: item["published_at"], reverse=True)
    deduped = []
    seen = set()
    for item in items:
        key = canonical_news_url(item["url"])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[: max(1, max_articles)]
