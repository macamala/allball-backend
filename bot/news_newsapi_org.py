"""Bounded NewsAPI.org discovery using the existing Railway NEWS_API_KEY.

Discovery only. Three broad sports queries are cached for almost one hour so the
adapter stays within conservative request budgets. Returned rows never publish
directly; the shared NinkoSports Sydney-day, source-fact, image, taxonomy,
originality, dedupe and semantic gates remain authoritative.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time, timezone
import logging
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://newsapi.org/v2/everything"
_CACHE = {"at": 0.0, "rows": []}
_CACHE_SECONDS = 55 * 60
_QUERIES = (
    (
        "major",
        'football OR soccer OR basketball OR tennis OR cricket OR rugby OR '
        '"ice hockey" OR baseball OR golf OR boxing OR MMA OR cycling OR '
        'athletics OR motorsport',
    ),
    (
        "niche",
        'volleyball OR handball OR futsal OR "water polo" OR "field hockey" OR '
        'netball OR lacrosse OR "table tennis" OR badminton OR snooker OR darts OR '
        '"horse racing" OR greyhound OR "harness racing" OR swimming OR skiing',
    ),
    (
        "esports",
        'esports OR "EA Sports FC" OR "Counter-Strike" OR "League of Legends" OR '
        'Dota OR Valorant OR "Call of Duty" OR Overwatch OR "Rocket League"',
    ),
)


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


def _window(now: Optional[datetime] = None) -> tuple[str, str]:
    current = now or datetime.now(timezone.utc)
    tz_name = os.getenv("NEWS_EDITORIAL_TIMEZONE") or "Australia/Sydney"
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = timezone.utc
    local = current.astimezone(zone)
    local_start = datetime.combine(local.date(), dt_time.min, tzinfo=zone)
    start_utc = local_start.astimezone(timezone.utc)
    return (
        start_utc.isoformat().replace("+00:00", "Z"),
        current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def _candidate(row: Dict) -> Optional[Dict]:
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    summary = str(row.get("description") or "").strip()
    stamp = _stamp(row.get("publishedAt"))
    image = str(row.get("urlToImage") or "").strip() or None
    if not title or title == "[Removed]" or not url or stamp is None:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    candidates = []
    if image:
        try:
            image_parts = urlsplit(image)
        except ValueError:
            image_parts = None
        if image_parts and image_parts.scheme in {"http", "https"} and image_parts.hostname:
            candidates.append({
                "url": image,
                "source": "newsapi-org",
                "in_article": False,
            })
        else:
            image = None
    source = row.get("source") or {}
    publisher = str(source.get("name") or "NewsAPI.org").strip() if isinstance(source, dict) else "NewsAPI.org"
    return {
        "title": title,
        "summary": summary,
        "url": url,
        "image": image,
        "image_candidates": candidates,
        "published_at": stamp,
        "feed": {
            "kind": "mixed",
            "sport": None,
            "publisher": publisher[:100] or "NewsAPI.org",
            "representation": "newsapi-org-discovery",
        },
    }


def fetch_newsapi_org_entries(per_group: int = 100) -> List[Dict]:
    if os.getenv("NEWS_NEWSAPI_ORG_ENABLED") != "1":
        return []
    key = (os.getenv("NEWS_API_KEY") or "").strip()
    if not key:
        logger.warning("[newsapi_org] NEWS_API_KEY missing")
        return []
    now_mono = time.monotonic()
    cached = _CACHE.get("rows")
    if (
        isinstance(cached, list)
        and now_mono - float(_CACHE.get("at") or 0) < _CACHE_SECONDS
    ):
        return list(cached)

    page_size = max(1, min(int(per_group), 100))
    start, end = _window()
    output = []
    seen = set()
    with httpx.Client(
        timeout=httpx.Timeout(20, connect=7),
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "NinkoSports-News/1.0"},
    ) as client:
        for label, query in _QUERIES:
            try:
                response = client.get(
                    _ENDPOINT,
                    params={
                        "q": query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": page_size,
                        "from": start,
                        "to": end,
                        "apiKey": key,
                    },
                )
                if response.status_code != 200:
                    code = None
                    try:
                        payload = response.json()
                        code = payload.get("code") if isinstance(payload, dict) else None
                    except Exception:
                        pass
                    logger.warning(
                        "[newsapi_org] group=%s http_status=%s code=%s",
                        label, response.status_code, str(code or "unknown")[:60],
                    )
                    continue
                data = response.json()
            except Exception as exc:
                logger.warning(
                    "[newsapi_org] group=%s failed=%s", label, type(exc).__name__
                )
                continue
            rows = data.get("articles") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                continue
            accepted = 0
            for raw in rows:
                item = _candidate(raw)
                if not item or item["url"] in seen:
                    continue
                seen.add(item["url"])
                output.append(item)
                accepted += 1
            logger.info(
                "[newsapi_org] group=%s rows=%s accepted=%s image_ready=%s window_start=%s",
                label,
                len(rows),
                accepted,
                sum(
                    1 for item in output[-accepted:]
                    if accepted and item.get("image_candidates")
                ),
                start,
            )
    _CACHE["at"] = now_mono
    _CACHE["rows"] = list(output)
    return output
