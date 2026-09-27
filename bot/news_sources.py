"""One discovery catalog for all NinkoSports News sources.

RSS and official HTML differ only in discovery representation. Every discovered
story enters the same downstream queue and publication guards.
"""
from __future__ import annotations

from .feeds import enabled_feeds


OFFICIAL_HTML_SOURCES = [
    {
        "url": "https://www.ea.com/games/ea-sports-fc/fc-pro/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "ea-sports-fc",
        "publisher": "EA FC Pro",
        "article_prefixes": ("/games/ea-sports-fc/fc-pro/news/",),
        "enabled": True,
    },
    {
        "url": "https://lolesports.com/en-US/lolesports/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "league-of-legends",
        "publisher": "LoL Esports",
        "article_prefixes": ("/en-US/news/", "/en-US/lolesports/news/"),
        "enabled": True,
    },
    {
        "url": "https://valorantesports.com/en-US/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "valorant",
        "publisher": "VALORANT Esports",
        "article_prefixes": ("/en-US/news/",),
        "enabled": True,
    },
    {
        "url": "https://callofdutyleague.com/en-us/news",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "call-of-duty",
        "publisher": "Call of Duty League",
        "article_prefixes": ("/en-us/news/",),
        "enabled": True,
    },
    {
        "url": "https://esports.overwatch.com/en-us",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "overwatch",
        "publisher": "Overwatch Esports",
        "article_prefixes": ("/en-us/news/",),
        "enabled": True,
    },
    {
        "url": "https://www.rocketleague.com/news/tag/competitive",
        "representation": "official_html",
        "kind": "mixed",
        "sport": "rocket-league",
        "publisher": "Rocket League",
        "article_prefixes": ("/news/",),
        "enabled": True,
    },
]


def enabled_sources():
    rows = []
    for feed in enabled_feeds():
        row = dict(feed)
        row["representation"] = "rss"
        rows.append(row)
    rows.extend(dict(row) for row in OFFICIAL_HTML_SOURCES if row.get("enabled"))
    # Canonical URL dedupe while preserving the last explicitly configured row.
    return list({row["url"]: row for row in rows}.values())
