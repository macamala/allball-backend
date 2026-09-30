"""Bounded discovery from official sports-news index pages and sitemaps.

This is discovery only, not a licence claim. Sources are allowlisted first-party
sports/esports sites or an official competition partner explicitly connected by
the sport's own site. Index and article reads reuse the robots-aware public News
transport, reject cross-host links, and fail closed on missing explicit
publication timestamps or missing article prose.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import logging
import json
import os
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from .extract import (
    article_text_from_html,
    collect_page_image_candidates,
    page_published_at_from_html,
    page_title_from_html,
    _ScopedNewsBody,
)
from .news_feed_http import read_news_feed
from .news_policy import news_freshness_reason, non_article_news_reason
from .news_components import public_components
from .textutil import clean_text

logger = logging.getLogger(__name__)

HTML_INDEXES = (
    {
        'id': 'bundesliga-german-news', 'sport': 'football', 'publisher': 'Bundesliga',
        'url': 'https://www.bundesliga.com/de/bundesliga/news', 'host': 'www.bundesliga.com',
        'paths': ('/de/bundesliga/news/',), 'article_path_re': r'/news/[^/]+-\d+$',
    },
    {
        'id': 'bundesliga-english-news', 'sport': 'football', 'publisher': 'Bundesliga',
        'url': 'https://www.bundesliga.com/en/bundesliga/news', 'host': 'www.bundesliga.com',
        'paths': ('/en/bundesliga/news/',), 'article_path_re': r'/news/[^/]+-\d+$',
    },
    {
        'id': 'bundesliga-2-news', 'sport': 'football', 'publisher': 'Bundesliga',
        'url': 'https://www.bundesliga.com/en/2bundesliga/news', 'host': 'www.bundesliga.com',
        'paths': ('/en/2bundesliga/news/',), 'article_path_re': r'/news/[^/]+-\d+$',
    },
    {
        'id': 'ge-brazil-football-news', 'sport': 'football', 'publisher': 'ge',
        'url': 'https://ge.globo.com/futebol/', 'host': 'ge.globo.com',
        'paths': ('/futebol/',), 'article_path_re': r'/noticia/\d{4}/\d{2}/\d{2}/[^/]+\.ghtml$',
        'verified_official': False,
    },
    {
        'id': 'rugbypass-rugby-news', 'sport': 'rugby', 'publisher': 'RugbyPass',
        'url': 'https://www.rugbypass.com/', 'host': 'www.rugbypass.com',
        'paths': ('/news/',), 'verified_official': False,
        'index_body_class': 'latest', 'anchor_class': 'link-box',
        # RSS dates are naive. Hydrate the article's explicit UTC publication
        # metadata instead; /plus/ subscription articles are not admitted.
    },
    {
        "id": "mozzart-serbian-football-news", "sport": "football", "publisher": "Mozzart Sport",
        "url": "https://www.mozzartsport.com/fudbal/1", "host": "www.mozzartsport.com",
        "paths": ("/fudbal/vesti/",), "article_path_re": r"^/fudbal/vesti/[^/]+/\d+$",
        "exclude_paths": ("/fudbal/vesti/predlozzi-i-tipovanja-", "/fudbal/vesti/ludi-tiket-", "/fudbal/vesti/najava-dana-"),
        "verified_official": False,
    },
    {
        "id": "mozzart-serbian-basketball-news", "sport": "basketball", "publisher": "Mozzart Sport",
        "url": "https://www.mozzartsport.com/kosarka/2", "host": "www.mozzartsport.com",
        "paths": ("/kosarka/vesti/",), "article_path_re": r"^/kosarka/vesti/[^/]+/\d+$",
        "verified_official": False,
    },
    {
        "id": "liverpool-football-news", "sport": "football", "publisher": "Liverpool FC",
        "url": "https://www.liverpoolfc.com/news", "host": "www.liverpoolfc.com",
        "paths": ("/news/",), "exclude_paths": ("/news/road-rome-",),
    },
    {
        "id": "chelsea-football-news", "sport": "football", "publisher": "Chelsea FC",
        "url": "https://www.chelseafc.com/en/news/latest-news", "host": "www.chelseafc.com",
        "paths": ("/en/news/article/",), "exclude_paths": ("/en/news/article/chelsea-diary-",),
        "index_component": "NewsListModule",
    },
    {
        "id": "cricket-australia-news", "sport": "cricket", "publisher": "Cricket Australia",
        "url": "https://www.cricket.com.au/news", "host": "www.cricket.com.au",
        "paths": ("/news/",), "article_path_re": r"^/news/\d+/[^/]+",
        "anchor_class": "o-media-pod__link",
    },
    {
        "id": "wta-tennis-news", "sport": "tennis", "publisher": "WTA",
        "url": "https://www.wtatennis.com/news", "host": "www.wtatennis.com",
        "paths": ("/news/",), "article_path_re": r"^/news/\d+/[^/]+",
    },
    {
        "id": "olympics-global-sports-news",
        "enabled": False,
        "sport": None,
        "kind": "mixed",
        "publisher": "Olympics.com",
        "url": "https://www.olympics.com/en/news/",
        "host": "www.olympics.com",
        "paths": ("/en/news/",),
    },
    {
        "id": "nrl-rugby-league-news",
        "sport": "rugby-league",
        "publisher": "NRL",
        "url": "https://www.nrl.com/news/",
        "host": "www.nrl.com",
        "paths": ("/news/",),
    },
    {
        "id": "chinese-olympic-sports-news",
        "sport": None,
        "kind": "mixed",
        "publisher": "Chinese Olympic Committee",
        "url": "https://en.olympic.cn/news/Sports_News/",
        "host": "en.olympic.cn",
        "paths": ("/news/Sports_News/",),
        "visible_date": True,
        "visible_date_timezone": "Asia/Shanghai",
    },
    {
        "id": "nba-basketball-news",
        "exclude_paths": ("/news/category/",),
        "exclude_articles": ("key-dates", "writers-archive", "nba-guide", "2025-26-nba-player-pronunciation-guide", "2025-26-nba-trade-tracker"),
        "sport": "basketball",
        "publisher": "NBA",
        "url": "https://www.nba.com/news/category/top-stories",
        "host": "www.nba.com",
        "paths": ("/news/",),
    },
    {
        "id": "nfl-american-football-news",
        "sport": "american-football",
        "publisher": "NFL",
        "url": "https://www.nfl.com/news/",
        "host": "www.nfl.com",
        "paths": ("/news/",),
    },
    {
        "id": "nhl-ice-hockey-news",
        "sport": "ice-hockey",
        "publisher": "NHL",
        "url": "https://www.nhl.com/news",
        "host": "www.nhl.com",
        "paths": ("/news/",),
    },
    {
        "id": "mlb-baseball-news",
        "sport": "baseball",
        "publisher": "MLB",
        "url": "https://www.mlb.com/news",
        "host": "www.mlb.com",
        "paths": ("/news/",),
    },
    {
        "id": "pdc-darts-news",
        "sport": "darts",
        "publisher": "PDC",
        "url": "https://www.pdc.tv/news",
        "host": "www.pdc.tv",
        "paths": ("/news/",),
    },
    {
        "id": "ufc-mma-news",
        "sport": "mma",
        "publisher": "UFC",
        "url": "https://www.ufc.com/news",
        "host": "www.ufc.com",
        "paths": ("/news/",),
    },
    {
        "id": "ihf-handball",
        "enabled": False,  # Exact publication times now come from official /news/rss.xml.
        "sport": "handball",
        "publisher": "IHF",
        "url": "https://www.ihf.info/media-center/news",
        "host": "www.ihf.info",
        "paths": ("/media-center/news/",),
        "visible_date": True,
    },
    {
        "id": "volleyball-world-news",
        "sport": "volleyball",
        "publisher": "Volleyball World",
        "url": "https://en.volleyballworld.com/news/",
        "host": "en.volleyballworld.com",
        "paths": ("/news/",),
    },
    {
        "id": "ea-sports-fc-news",
        "sport": "ea-sports-fc",
        "publisher": "EA SPORTS FC",
        "url": "https://www.ea.com/games/ea-sports-fc/news",
        "host": "www.ea.com",
        "paths": (
            "/games/ea-sports-fc/news/",
            "/games/ea-sports-fc/fc-27/news/",
            "/games/ea-sports-fc/fc-26/news/",
        ),
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
        "enabled": False,
        "sport": "rocket-league",
        "publisher": "Rocket League",
        "url": "https://www.rocketleague.com/news/tag/competitive",
        "host": "www.rocketleague.com",
        "paths": ("/news/",),
        "exclude_paths": ("/news/tag/",),
    },
    {
        # Rocket League's own news host currently fails our robots-aware
        # transport closed. BLAST.tv is linked from the official RLCS experience;
        # keep this partner fallback narrowly title-filtered so unrelated BLAST
        # esports articles can never inherit Rocket League taxonomy.
        "id": "rocket-league-blast-partner",
        "sport": "rocket-league",
        "publisher": "BLAST.tv",
        "url": "https://blast.tv/rl/news",
        "host": "blast.tv",
        "paths": ("/rl/news/",),
        "keywords": (
            "rocket league",
            "rlcs",
            "world championship",
            "fort worth",
            "paris major",
        ),
        "max_age_hours": 168,
    },
    {
        "id": "ittf-table-tennis-news",
        "enabled": False,
        "sport": "table-tennis",
        "publisher": "ITTF",
        "url": "https://www.ittf.com/news/",
        "host": "www.ittf.com",
        "paths": ("/2026/",),
    },
    {
        "id": "world-aquatics-water-polo",
        "sport": "water-polo",
        "publisher": "World Aquatics",
        "url": "https://www.worldaquatics.com/news",
        "host": "www.worldaquatics.com",
        "paths": ("/news/",),
        "keywords": ("water polo", "waterpolo", "wp4"),
        "hydrate_keywords_only": True,
    },
    {
        "id": "world-aquatics-swimming",
        "sport": "swimming",
        "publisher": "World Aquatics",
        "url": "https://www.worldaquatics.com/news",
        "host": "www.worldaquatics.com",
        "paths": ("/news/",),
        "keywords": ("swimming", "swimmer", "freestyle", "backstroke", "breaststroke"),
        "hydrate_keywords_only": True,
    },
    {
        "id": "fih-field-hockey-news",
        "enabled": False,
        "sport": "field-hockey",
        "publisher": "FIH",
        "url": "https://www.fih.hockey/news",
        "host": "www.fih.hockey",
        "paths": ("/news/",),
        "keywords": ("hockey", "fih"),
        "hydrate_keywords_only": True,
    },
    {
        "id": "hockey-australia-news",
        "sport": "field-hockey",
        "publisher": "Hockey Australia",
        "url": "https://www.hockey.org.au/news",
        "host": "www.hockey.org.au",
        "paths": ("/news/",),
        "keywords": (
            "hockeyroos",
            "kookaburras",
            "hockey",
            "fih",
            "world cup",
            "pro league",
        ),
        "hydrate_keywords_only": True,
        "max_age_hours": 168,
    },
    {
        "id": "wst-snooker-news",
        "sport": "snooker",
        "publisher": "World Snooker Tour",
        "url": "https://www.wst.tv/news/",
        "host": "www.wst.tv",
        "paths": ("/news/",),
    },
    {
        "id": "world-athletics-news",
        "article_path_re": r"^/news/[^/]+/[^/]+",
        "sport": "athletics",
        "publisher": "World Athletics",
        "url": "https://worldathletics.org/news",
        "host": "worldathletics.org",
        "paths": ("/news/",),
    },
    {
        "id": "fifa-futsal-news",
        "enabled": False,
        "sport": "futsal",
        "publisher": "FIFA",
        "url": "https://inside.fifa.com/organisation/news",
        "host": "inside.fifa.com",
        "paths": ("/organisation/news/",),
        "keywords": ("futsal",),
    },
    {
        "id": "blast-counter-strike-news",
        "sport": "counter-strike",
        "publisher": "BLAST.tv",
        "url": "https://blast.tv/cs",
        "host": "blast.tv",
        "paths": ("/cs/news/",),
    },
    {
        "id": "world-netball-news",
        # WordPress news cards have empty stretched-link anchors; the site's
        # navigation also lives at root paths and must not spend this budget.
        "anchor_class": "stretched-link",
        "sport": "netball",
        "publisher": "World Netball",
        "url": "https://netball.sport/news/",
        "host": "netball.sport",
        "paths": ("/",),
        "exclude_paths": (
            "/news/", "/inside-world-netball/", "/events/", "/about/",
            "/members/", "/contact/", "/privacy/", "/category/", "/tag/",
        ),
        "keywords": ("netball", "nwc2027", "silver ferns", "diamonds"),
        "max_age_hours": 120,
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
        "id": "uefa-football-competitions", "sport": "football", "publisher": "UEFA",
        "url": "https://www.uefa.com/sitemap/news/latest.xml", "host": "www.uefa.com",
        "url_markers": ("/uefachampionsleague/news/", "/uefaeuropaleague/news/",
                        "/uefaconferenceleague/news/", "/uefanationsleague/news/",
                        "/european-qualifiers/news/", "/uefaeuro/news/", "/under21/news/",
                        "/under19/news/", "/under17/news/", "/womenschampionsleague/news/",
                        "/womenseuropeanqualifiers/news/", "/womensnationsleague/news/",
                        "/womenseuro/news/", "/womensunder19/news/", "/womensunder17/news/"),
    },
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
EMBEDDED_URL_RE = re.compile(
    r'''(?:"(?:url|href|canonicalUrl|canonical_url)"\s*:\s*|href\s*=\s*)["']([^"'<>\\]+)["']''',
    re.IGNORECASE,
)
ABSOLUTE_URL_RE = re.compile(r'''https://[^"'<>\\\s]+''', re.IGNORECASE)


class _AnchorParser(HTMLParser):
    def __init__(self, anchor_class=None):
        super().__init__(convert_charrefs=True)
        self.anchor_class = anchor_class
        self.current_href: Optional[str] = None
        self.current_text: List[str] = []
        self.links: List[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a" or self.current_href is not None:
            return
        values = {str(key).lower(): str(value or "") for key, value in attrs}
        if self.anchor_class and self.anchor_class not in values.get("class", "").split():
            return
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
    if path.rstrip("/") == urlsplit(base).path.rstrip("/"):
        return None
    if path.rstrip("/").split("/")[-1] in cfg.get("exclude_articles", ()):
        return None
    if re.search(r"/(?:category|topic|series|pages|tag)/|\.(?:json|xml|js|css)$", path, re.I):
        return None
    if cfg.get("article_path_re") and not re.search(cfg["article_path_re"], path):
        return None
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
    if cfg.get("index_component") == "NewsListModule":
        # Only the public Article records from this page's listing; no app
        # promotion, video/gallery cards, login-only or premium records.
        props = public_components(html, ("NewsListModule",)).get("NewsListModule", {})
        content = props.get("initialContent") or {}
        rows = content.get("items") if isinstance(content, dict) else None
        output, seen = [], set()
        for row in rows if isinstance(rows, list) else []:
            if (not isinstance(row, dict) or row.get("type") != "Article"
                    or row.get("requiresLogin") is not False
                    or row.get("isPremiumContent") is not False):
                continue
            url = _same_host_url(cfg["url"], str(row.get("url") or ""), cfg["host"], cfg)
            if not url or url in seen:
                continue
            seen.add(url)
            output.append((url, clean_text(str(row.get("title") or ""))))
            if len(output) >= MAX_LINKS_PER_SOURCE:
                break
        return output
    if cfg.get('index_body_class'):
        scoped = _ScopedNewsBody(cfg['index_body_class'])
        scoped.feed(html)
        if not scoped.finished:
            return []
        html = ''.join(scoped.parts)
    parser = _AnchorParser(cfg.get("anchor_class"))
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return []

    output: List[tuple[str, str]] = []
    seen = set()
    required = tuple(str(x).lower() for x in cfg.get("keywords", ()))
    discovered = list(parser.links)
    # Do not let a URL rejected from a real anchor (for example generic patch
    # notes under an esports news path) re-enter as an empty-title JSON URL.
    anchor_urls = {
        url
        for href, _title in parser.links
        if (url := _same_host_url(cfg["url"], href, cfg["host"], cfg))
    }
    # A source scoped to verified article-card markup must not re-admit
    # navigation from the unscoped embedded-URL fallback.
    embedded_html = "" if cfg.get("anchor_class") else html
    for match in EMBEDDED_URL_RE.findall(embedded_html):
        href = match.replace("\\/","/")
        url = _same_host_url(cfg["url"], href, cfg["host"], cfg)
        if url and url in anchor_urls:
            continue
        discovered.append((href, ""))
    for match in ABSOLUTE_URL_RE.findall(embedded_html):
        href = match.replace("\\/","/")
        url = _same_host_url(cfg["url"], href, cfg["host"], cfg)
        if url and url in anchor_urls:
            continue
        discovered.append((href, ""))
    for href, title in discovered:
        url = _same_host_url(cfg["url"], href, cfg["host"], cfg)
        if not url or url in seen:
            continue
        text = clean_text(title)
        if (
            required
            and not cfg.get("hydrate_keywords_only")
            and text
            and not any(marker in text.lower() for marker in required)
        ):
            continue
        if text and text.lower() in {"read more", "news", "latest", "image"}:
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


def _sitemap_candidates(cfg: Dict, *, publication_times=None) -> List[tuple[str, str]]:
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
        if non_article_news_reason({"title": title, "url": loc}):
            continue
        seen.add(loc)
        canonical = loc.split("#", 1)[0]
        if publication_times is not None:
            from .extract import _parse_explicit_datetime
            # news:publication_date belongs to this same allowlisted URL.
            # Never substitute sitemap lastmod, fetch time or a naive date.
            stamp = _parse_explicit_datetime(_child_text(node, "publication_date"))
            if stamp is not None:
                publication_times[canonical] = stamp
        output.append((canonical, title))
        if len(output) >= MAX_LINKS_PER_SOURCE:
            break
    return output


_VISIBLE_ENGLISH_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
    r"(20\d{2})(?!\d)",
    re.IGNORECASE,
)
_VISIBLE_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


_VISIBLE_ISO_MINUTE_RE = re.compile(
    r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?:\s+|T)(\d{2}):(\d{2})(?!\d)"
)


def _visible_published_date(
    html: str,
    source_timezone: Optional[str] = None,
) -> Optional[datetime]:
    """Parse only explicit human-visible source dates; never invent 'now'."""
    visible = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", html or "", flags=re.I | re.S)
    text = clean_text(re.sub(r"<[^>]+>", " ", visible))
    iso = _VISIBLE_ISO_MINUTE_RE.search(text)
    if iso and source_timezone:
        try:
            zone = ZoneInfo(source_timezone)
        except Exception:
            return None
        try:
            return datetime(
                int(iso.group(1)),
                int(iso.group(2)),
                int(iso.group(3)),
                int(iso.group(4)),
                int(iso.group(5)),
                tzinfo=zone,
            ).astimezone(timezone.utc)
        except ValueError:
            return None
    # A date without a time/offset does not establish a publication instant.
    # Keep it unverified instead of inventing midnight UTC.
    return None


def _hydrate(cfg: Dict, url: str, fallback_title: str, *, diagnostics=None, sitemap_published_at=None) -> Optional[Dict]:
    def reject(reason):
        if diagnostics is not None:
            diagnostics[reason] += 1
        logger.info("[official_index] rejected source=%s reason=%s url=%s", cfg["id"], reason, url)
        return None

    try:
        raw = read_news_feed(url)
        if len(raw) > MAX_INDEX_BYTES:
            return reject("response_too_large")
        html = raw.decode("utf-8", "replace")
    except Exception as exc:
        logger.info("[official_index] article unavailable %s: %s", cfg["id"], type(exc).__name__)
        return reject("transport_" + type(exc).__name__)

    # NRL galleries share /news/ paths and article metadata. Their captions
    # plus site footer must never become the factual basis for a news story.
    if cfg["id"] == "nrl-rugby-league-news" and re.search(
        r'\bid\s*=\s*["\']vue-gallery-list["\']', html, re.I
    ):
        return reject("non_article_photo_gallery")
    published_at = page_published_at_from_html(html)
    if cfg["id"] == "chelsea-football-news":
        components = public_components(html, ("ArticleHeader", "ArticleLoginOverlay"))
        if components.get("ArticleLoginOverlay", {}).get("requiresLogin") is not False:
            return reject("restricted_article")
        # This is the current article header, not a recommended card or update
        # timestamp. The publisher supplies an explicit UTC offset.
        header = components.get("ArticleHeader", {}).get("articleHeaderDetails") or {}
        from .extract import _parse_explicit_datetime
        published_at = _parse_explicit_datetime(header.get("date")) if isinstance(header, dict) else None
    if published_at is None and cfg["id"] == "world-athletics-news":
        # This CMS exposes the article's publication field in its own page
        # state. Never use a related card's time or the page build/update time.
        match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
        if match:
            try:
                article = json.loads(match.group(1))["props"]["pageProps"]["article"]
                if article.get("urlSlug") == urlsplit(url).path.rstrip("/").split("/")[-1]:
                    from .extract import _parse_explicit_datetime
                    published_at = _parse_explicit_datetime(article.get("liveFrom"))
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
    if published_at is None and cfg.get("visible_date"):
        published_at = _visible_published_date(
            html,
            cfg.get("visible_date_timezone"),
        )
    if published_at is None and isinstance(sitemap_published_at, datetime) and sitemap_published_at.tzinfo is not None:
        published_at = sitemap_published_at
    if published_at is None:
        return reject("publication_time_unverified")
    now = datetime.now(timezone.utc)
    reason = news_freshness_reason(published_at, now)
    if reason:
        return reject(reason)
    title = page_title_from_html(html) or fallback_title
    body = article_text_from_html(html)
    if not title or not body:
        return reject("missing_title" if not title else "missing_article_body")
    if cfg['id'] == 'chelsea-football-news':
        category = header.get('category') if isinstance(header, dict) else None
        section = category.get('title') if isinstance(category, dict) else None
        if section == "Women's Team":
            # Verified metadata from THIS article, not a related card. Keep
            # the team category in the bounded facts seen by both AI roles.
            body = "Source article category: Women's Team.\n\n" + body
    reason = non_article_news_reason({"title": title, "url": url})
    if reason:
        return reject(reason)
    required = tuple(str(x).lower() for x in cfg.get("keywords", ()))
    if required:
        evidence = f"{title} {body[:1600]}".lower()
        if not any(marker in evidence for marker in required):
            return reject("sport_evidence_mismatch")
    image = None
    image_candidates = []
    try:
        from .news_image_http import pick_news_article_image

        for candidate in collect_page_image_candidates(html):
            if not isinstance(candidate, dict):
                continue
            raw_url = str(candidate.get("url") or "").strip()
            if not raw_url:
                continue
            resolved_url = urljoin(url, raw_url)
            parts = urlsplit(resolved_url)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                continue
            row = dict(candidate)
            row["url"] = resolved_url
            image_candidates.append(row)
        image = pick_news_article_image(image_candidates)
    except Exception:
        image = None
        image_candidates = []
    if not image_candidates:
        return reject("missing_image_candidates")
    feed = {
        "url": cfg["url"],
        "kind": cfg.get("kind", "league"),
        "sport": cfg.get("sport"),
        "league": None,
        "country": "international",
        "publisher": cfg["publisher"],
        "verified_official": cfg.get("verified_official", True),
        "enabled": True,
        "note": "bounded publisher index; article page hydrated before admission",
    }
    return {
        "title": clean_text(title),
        "summary": "",
        "url": url,
        "image": image,
        "image_candidates": image_candidates,
        "published_at": published_at,
        "_publication_evidence": "article-published",
        "feed": feed,
        "_extracted": body,
        "_classification_text": body,
        "_extracted_image": image,
    }


def _hydrate_source(cfg: Dict, limit: int, *, sitemap: bool = False) -> List[Dict]:
    """Hydrate one allowlisted source serially; safe unit for bounded host parallelism."""
    publication_times = {}
    candidates = _sitemap_candidates(cfg, publication_times=publication_times) if sitemap else _anchor_candidates(cfg)
    rows: List[Dict] = []
    reasons = Counter()
    for url, title in candidates:
        item = _hydrate(cfg, url, title, diagnostics=reasons, sitemap_published_at=publication_times.get(url))
        if item is None:
            continue
        rows.append(item)
        if len(rows) >= limit:
            break
    logger.info(
        "[official_index] source=%s sport=%s discovered=%s hydrated=%s reasons=%s",
        cfg["id"], cfg.get("sport") or "mixed", len(candidates), len(rows), dict(reasons),
    )
    return rows


def fetch_official_index_entries(max_per_source: int = 3) -> List[Dict]:
    """Return fresh hydrated official stories; never writes DB or calls AI."""
    limit = max(1, min(int(max_per_source), 5))
    items: List[Dict] = []
    football_only = os.getenv('NEWS_FOOTBALL_ONLY') == '1'

    active_html = [cfg for cfg in HTML_INDEXES if cfg.get("enabled", True) is not False]
    if football_only:
        active_html = [cfg for cfg in active_html if not cfg.get('sport') or cfg.get('sport') == 'football']
    if active_html:
        workers = min(4, len(active_html))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="news-official") as pool:
            for rows in pool.map(lambda cfg: _hydrate_source(cfg, limit), active_html):
                items.extend(rows)

    active_sitemaps = [cfg for cfg in SITEMAPS if cfg.get("enabled", True) is not False]
    if football_only:
        active_sitemaps = [cfg for cfg in active_sitemaps if not cfg.get('sport') or cfg.get('sport') == 'football']
    if active_sitemaps:
        workers = min(2, len(active_sitemaps))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="news-sitemap") as pool:
            for rows in pool.map(
                lambda cfg: _hydrate_source(cfg, limit, sitemap=True),
                active_sitemaps,
            ):
                items.extend(rows)

    logger.info("[official_index] total_hydrated=%s", len(items))
    return items
