"""Bounded NewsAPI.ai / Event Registry discovery for fresh sports news.

Discovery only. This adapter never publishes and never calls an AI writer.
Every returned candidate still passes the shared NinkoSports freshness,
classification, originality, factuality, image and public-taxonomy gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time
from typing import Dict, List
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://eventregistry.org/api/v1/article/getArticles"
_CACHE = {"at": 0.0, "rows": []}
_CACHE_SECONDS = 30 * 60


def _parse_stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _editorial_date() -> str:
    name = os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney"
    try:
        zone = ZoneInfo(name)
    except Exception:
        zone = timezone.utc
    return datetime.now(timezone.utc).astimezone(zone).date().isoformat()


def _candidate(row: Dict):
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    body = str(row.get("body") or "").strip()
    stamp = _parse_stamp(row.get("dateTimePub") or row.get("dateTime"))
    image = str(row.get("image") or "").strip() or None
    if not title or not url or not body or stamp is None:
        return None
    candidates = []
    if image:
        candidates.append({
            "url": image,
            "source": "newsapi-ai",
            "in_article": False,
        })
    return {
        "title": title,
        "summary": body[:2400],
        "url": url,
        "image": image,
        "image_candidates": candidates,
        "published_at": stamp,
        "_extracted": body,
        "_extracted_image": image,
        "feed": {
            "kind": "mixed",
            "sport": None,
            "publisher": "NewsAPI.ai",
            "representation": "aggregator",
        },
    }


def fetch_newsapi_ai_entries(limit: int = 100) -> List[Dict]:
    """Fetch at most one page every 30 minutes and reuse it between cycles."""
    if os.getenv("NEWS_NEWSAPI_AI_ENABLED") != "1":
        return []
    key = (os.getenv("NEWS_API_KEY") or "").strip()
    if not key:
        logger.warning("[news_aggregator] NEWS_API_KEY missing")
        return []

    now = time.monotonic()
    cached = _CACHE.get("rows")
    if isinstance(cached, list) and cached and now - float(_CACHE.get("at") or 0) < _CACHE_SECONDS:
        return list(cached)

    count = max(1, min(int(limit), 100))
    day = _editorial_date()
    payload = {
        "action": "getArticles",
        "categoryUri": "news/Sports",
        "dateStart": day,
        "dateEnd": day,
        "articlesPage": 1,
        "articlesCount": count,
        "articlesSortBy": "date",
        "articlesSortByAsc": False,
        "articlesArticleBodyLen": -1,
        "includeArticleImage": True,
        "isDuplicateFilter": "skipDuplicates",
        "dataType": ["news"],
        "resultType": "articles",
        "apiKey": key,
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(25, connect=8),
            follow_redirects=False,
        ) as client:
            response = client.post(
                _ENDPOINT,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
            )
        if response.status_code != 200:
            logger.warning("[news_aggregator] NewsAPI.ai HTTP %s", response.status_code)
            return []
        data = response.json()
    except Exception as exc:
        logger.warning("[news_aggregator] NewsAPI.ai request failed=%s", type(exc).__name__)
        return []

    articles = data.get("articles") if isinstance(data, dict) else None
    raw_rows = articles.get("results") if isinstance(articles, dict) else None
    if not isinstance(raw_rows, list):
        logger.warning("[news_aggregator] NewsAPI.ai invalid response shape")
        return []

    rows = []
    seen = set()
    for raw in raw_rows:
        item = _candidate(raw)
        if not item or item["url"] in seen:
            continue
        seen.add(item["url"])
        rows.append(item)
    _CACHE["at"] = now
    _CACHE["rows"] = list(rows)
    logger.info("[news_aggregator] NewsAPI.ai fresh candidates=%s requested=%s day=%s", len(rows), count, day)
    return rows
