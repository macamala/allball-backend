"""Bounded ESPN first-party News JSON discovery.

Discovery only. The endpoint provides source headline/description/timestamp/image
and canonical article URL. Nothing here publishes directly; every row still
passes the shared Sydney-day, classification, originality, factuality, image,
dedupe and public-taxonomy gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

_SOURCES = (
    {
        "sport": "motorsport",
        "publisher": "ESPN F1",
        "url": "https://site.api.espn.com/apis/site/v2/sports/racing/f1/news",
    },
    {
        "sport": "american-football",
        "publisher": "ESPN NFL",
        "url": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
    },
    {
        "sport": "basketball",
        "publisher": "ESPN NBA",
        "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news",
    },
    {
        "sport": "ice-hockey",
        "publisher": "ESPN NHL",
        "url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/news",
    },
    {
        "sport": "baseball",
        "publisher": "ESPN MLB",
        "url": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/news",
    },
)
_CACHE = {"at": 0.0, "rows": []}
_CACHE_SECONDS = 8 * 60


def _stamp(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _web_href(row: Dict) -> Optional[str]:
    links = row.get("links")
    if not isinstance(links, dict):
        return None
    web = links.get("web")
    if not isinstance(web, dict):
        return None
    value = str(web.get("href") or "").strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or not parts.hostname.endswith("espn.com"):
        return None
    return value


def _images(row: Dict) -> List[dict]:
    output = []
    seen = set()
    for image in row.get("images") or []:
        if not isinstance(image, dict):
            continue
        url = str(image.get("url") or "").strip()
        if not url or url in seen:
            continue
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        if parts.scheme != "https" or not parts.hostname:
            continue
        seen.add(url)
        try:
            width = int(image.get("width") or 0)
        except (TypeError, ValueError):
            width = 0
        try:
            height = int(image.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        output.append({
            "url": url,
            "source": "espn-json",
            "width": width,
            "height": height,
            "in_article": str(image.get("type") or "").lower() == "header",
        })
    output.sort(
        key=lambda item: (
            1 if item.get("in_article") else 0,
            int(item.get("width") or 0) * int(item.get("height") or 0),
        ),
        reverse=True,
    )
    return output


def _candidate(row: Dict, source: Dict) -> Optional[Dict]:
    if not isinstance(row, dict) or row.get("premium") is True:
        return None
    title = str(row.get("headline") or "").strip()
    facts = str(row.get("description") or "").strip()
    published = _stamp(row.get("published"))
    url = _web_href(row)
    if not title or not facts or published is None or not url:
        return None
    images = _images(row)
    lead = images[0]["url"] if images else None
    return {
        "title": title,
        "summary": facts,
        "url": url,
        "image": lead,
        "image_candidates": images,
        "published_at": published,
        "_extracted": facts,
        "_extracted_image": lead,
        "_classification_text": facts,
        "feed": {
            "kind": "league",
            "sport": source["sport"],
            "league": None,
            "country": "usa",
            "publisher": source["publisher"],
            "representation": "espn-site-news-json",
        },
    }


def fetch_espn_news_entries(per_sport: int = 12) -> List[Dict]:
    if os.getenv("NEWS_ESPN_NEWS_JSON_ENABLED") != "1":
        return []
    now = time.monotonic()
    cached = _CACHE.get("rows")
    if (
        isinstance(cached, list)
        and cached
        and now - float(_CACHE.get("at") or 0) < _CACHE_SECONDS
    ):
        return list(cached)

    limit = max(1, min(int(per_sport), 25))
    output = []
    seen = set()
    with httpx.Client(
        timeout=httpx.Timeout(15, connect=6),
        follow_redirects=False,
        headers={"User-Agent": "NinkoSports-News/1.0", "Accept": "application/json"},
    ) as client:
        for source in _SOURCES:
            try:
                response = client.get(source["url"])
                if response.status_code != 200:
                    logger.warning(
                        "[espn_news] source=%s http_status=%s",
                        source["sport"], response.status_code,
                    )
                    continue
                data = response.json()
            except Exception as exc:
                logger.warning(
                    "[espn_news] source=%s failed=%s",
                    source["sport"], type(exc).__name__,
                )
                continue
            rows = data.get("articles") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                continue
            accepted = 0
            for raw in rows:
                item = _candidate(raw, source)
                if not item or item["url"] in seen:
                    continue
                seen.add(item["url"])
                output.append(item)
                accepted += 1
                if accepted >= limit:
                    break
            logger.info(
                "[espn_news] source=%s rows=%s accepted=%s image_ready=%s",
                source["sport"],
                len(rows),
                accepted,
                sum(
                    1 for item in output[-accepted:]
                    if accepted and item.get("image_candidates")
                ),
            )
    _CACHE["at"] = now
    _CACHE["rows"] = list(output)
    return output
