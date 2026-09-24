"""Liquipedia identity-only artwork repair for visible Dota 2 events.

This reads only two current tournament pages and extracts participant and
competition artwork. It never creates fixtures or changes score/status/start
time. Existing artwork always wins; only blank identity assets are filled.
"""

from __future__ import annotations

import html as html_lib
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.cache import note_list_invalidation
from collector.html_parse import parse_liquipedia_html
from collector.http import fetch_text
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 600
_next_run_at = 0.0

PAGES = (
    "https://liquipedia.net/dota2/BetBoom_Streamers_Battle/15",
    "https://liquipedia.net/dota2/PGL/Wallachia/9",
)

# Exact artwork files exposed by the current tournament infoboxes in Railway.
# The BetBoom season-15 page currently reuses the season-13 series artwork.
# We only trust these files when BOTH canonical participants belong to that
# exact current tournament page.
_PAGE_ARTWORK = {
    PAGES[0]: "BetBoom_Streamers_Battle_13_allmode.png",
    PAGES[1]: "PGL_Wallachia_allmode.png",
}

_HEADERS = {
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://liquipedia.net/dota2/",
}

_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(["'])(.*?)\2""", re.S)


def _key(value: Any) -> str:
    tokens = [
        token
        for token in fold_for_identity(str(value or "")).split()
        if token not in {"team", "dota", "2"}
    ]
    return " ".join(tokens)


def _logo(side: Any) -> str:
    if not isinstance(side, dict):
        return ""
    return str(
        side.get("logo")
        or side.get("image")
        or side.get("crest")
        or side.get("badge")
        or side.get("team_logo")
        or side.get("teamLogo")
        or ""
    ).strip()


def _diagnostic_image_candidates(raw_html: str, base_url: str) -> List[Dict[str, str]]:
    """Return a bounded list of relevant image candidates from Railway-visible HTML.

    Diagnostic only: this never writes an image into an event. It lets production
    logs prove the exact tournament/team artwork exposed by Liquipedia before we
    add any conservative write path.
    """
    found: List[Dict[str, str]] = []
    seen = set()
    needles = ("pgl", "wallachia", "betboom", "streamers", "battle", "ybn")
    for tag in _IMG_RE.findall(raw_html or ""):
        attrs = {
            name.lower(): html_lib.unescape(value.strip())
            for name, _quote, value in _ATTR_RE.findall(tag)
        }
        source = str(
            attrs.get("src")
            or attrs.get("data-src")
            or attrs.get("data-lazy-src")
            or ""
        ).strip()
        if not source:
            continue
        alt = str(attrs.get("alt") or attrs.get("title") or "").strip()
        combined = f"{alt} {source}".casefold()
        keyword_match = any(needle in combined for needle in needles)
        url = urljoin(base_url, source)
        if not keyword_match and "/commons/images/" not in url:
            continue
        key = (alt, url)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "alt": alt[:120],
                "class": str(attrs.get("class") or "")[:160],
                "url": url[:500],
                "keyword_match": "1" if keyword_match else "0",
            }
        )
        if len(found) >= 18:
            break
    return found


def _team_keys_from_html(raw_html: str) -> set[str]:
    keys: set[str] = set()
    for event in parse_liquipedia_html(raw_html or ""):
        for side_name in ("home", "away"):
            side = event.get(side_name) if isinstance(event.get(side_name), dict) else {}
            key = _key(side.get("name"))
            if key:
                keys.add(key)
    return keys


def _primary_competition_logo(raw_html: str, page_url: str) -> str:
    """Return only the exact current infobox artwork expected on this page."""
    fragment = _PAGE_ARTWORK.get(page_url)
    if not fragment:
        return ""

    best_url = ""
    best_score = -1
    for tag in _IMG_RE.findall(raw_html or ""):
        attrs = {
            name.lower(): html_lib.unescape(value.strip())
            for name, _quote, value in _ATTR_RE.findall(tag)
        }
        source = str(
            attrs.get("src")
            or attrs.get("data-src")
            or attrs.get("data-lazy-src")
            or ""
        ).strip()
        if not source or fragment.casefold() not in source.casefold():
            continue
        absolute = urljoin(page_url, source)
        # Prefer the original file; otherwise take the largest rendered thumb.
        score = 10_000 if "/thumb/" not in absolute else 0
        width = re.search(r"/(\d+)px-[^/]+$", absolute)
        if width:
            score = max(score, int(width.group(1)))
        if score > best_score:
            best_url = absolute
            best_score = score
    return best_url


def _catalog_from_html(html: str) -> Dict[str, Dict[str, str]]:
    catalog: Dict[str, Dict[str, str]] = {}
    for event in parse_liquipedia_html(html or ""):
        for side_name in ("home", "away"):
            side = event.get(side_name) if isinstance(event.get(side_name), dict) else {}
            name = str(side.get("name") or "").strip()
            logo = _logo(side)
            key = _key(name)
            if not key or not logo:
                continue
            existing = catalog.get(key)
            if existing and existing.get("logo") != logo:
                # Conflicting identity is unsafe; drop the key entirely.
                catalog[key] = {"name": name, "logo": "", "conflict": "1"}
                continue
            if not existing:
                catalog[key] = {"name": name, "logo": logo}
    return {key: row for key, row in catalog.items() if row.get("logo") and not row.get("conflict")}


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now_mono = time.monotonic()
    if now_mono < _next_run_at:
        return None
    _next_run_at = now_mono + RUN_INTERVAL_S

    fetch = getter or (lambda url: fetch_text(url, headers=_HEADERS))
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "http_errors": 0,
        "pages_ok": 0,
        "catalog": 0,
        "candidate_rows": 0,
        "matched_rows": 0,
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "competition_logos_filled": 0,
        "by_page": {},
    }
    catalog: Dict[str, Dict[str, str]] = {}
    page_assets: List[Dict[str, Any]] = []

    for url in PAGES:
        result = fetch(url)
        stats["requests"] += 1
        page_stats = {"ok": bool(getattr(result, "ok", False)), "assets": 0}
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            stats["by_page"][url] = page_stats
            continue
        html = getattr(result, "payload", None)
        raw_html = html if isinstance(html, str) else ""
        page_catalog = _catalog_from_html(raw_html)
        page_team_keys = _team_keys_from_html(raw_html)
        competition_logo = _primary_competition_logo(raw_html, url)
        page_stats["assets"] = len(page_catalog)
        page_stats["teams"] = len(page_team_keys)
        page_stats["competition_logo"] = competition_logo
        page_stats["image_candidates"] = _diagnostic_image_candidates(raw_html, url)
        page_assets.append(
            {
                "url": url,
                "team_keys": page_team_keys,
                "team_assets": page_catalog,
                "competition_logo": competition_logo,
            }
        )
        stats["pages_ok"] += 1
        stats["by_page"][url] = page_stats
        for key, asset in page_catalog.items():
            existing = catalog.get(key)
            if existing and existing.get("logo") != asset.get("logo"):
                catalog[key] = {"name": asset.get("name", ""), "logo": "", "conflict": "1"}
            elif not existing:
                catalog[key] = asset
        if heartbeat:
            heartbeat()

    catalog = {key: row for key, row in catalog.items() if row.get("logo") and not row.get("conflict")}
    stats["catalog"] = len(catalog)
    if not catalog:
        stats["status"] = "empty" if not stats["http_errors"] else "fetch_error"
        return stats

    low = datetime.utcnow() - timedelta(days=3)
    high = datetime.utcnow() + timedelta(days=3)
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "dota-2",
            or_(SportsEvent.display_eligible.is_(True), SportsEvent.display_eligible.is_(None)),
            SportsEvent.start_time >= low,
            SportsEvent.start_time <= high,
        )
        .all()
    )

    for row in rows:
        participants = load_json(row.participants_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        home = participants.get("home") if isinstance(participants.get("home"), dict) else {}
        away = participants.get("away") if isinstance(participants.get("away"), dict) else {}
        home_key = _key(home.get("name"))
        away_key = _key(away.get("name"))
        if not home_key or not away_key:
            continue

        needs_side = (not _logo(home)) or (not _logo(away))
        needs_comp = not str(extra.get("competition_logo") or "").strip()
        if not (needs_side or needs_comp):
            continue

        stats["candidate_rows"] += 1
        matching_pages = [
            page
            for page in page_assets
            if home_key in page["team_keys"] and away_key in page["team_keys"]
        ]
        if len(matching_pages) == 1:
            stats["matched_rows"] += 1

        changed = False
        extra_changed = False
        for side_name, mirror_name in (("home", "participant_a"), ("away", "participant_b")):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _logo(side):
                continue
            asset = catalog.get(_key(side.get("name")))
            if not asset or not asset.get("logo"):
                continue
            merged = dict(side)
            merged["logo"] = asset["logo"]
            participants[side_name] = merged
            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and not _logo(mirror):
                mirror_copy = dict(mirror)
                mirror_copy["logo"] = asset["logo"]
                participants[mirror_name] = mirror_copy
            stats["participant_logos_filled"] += 1
            changed = True

        if needs_comp and len(matching_pages) == 1:
            comp_logo = str(matching_pages[0].get("competition_logo") or "").strip()
            if comp_logo:
                extra["competition_logo"] = comp_logo
                sources = extra.get("identity_asset_sources")
                if not isinstance(sources, dict):
                    sources = {}
                sources["competition_logo"] = "liquipedia-current-tournament-page"
                extra["identity_asset_sources"] = sources
                stats["competition_logos_filled"] += 1
                extra_changed = True
                changed = True

        if not changed:
            continue
        row.participants_json = dump_json(participants)
        if extra_changed:
            row.extra_json = dump_json(extra)
            store_list_extra(row, extra)
        note_list_invalidation(
            db,
            sport=row.sport_id,
            competition=row.competition_id,
            start_time=row.start_time,
        )
        stats["rows_updated"] += 1

    if stats["rows_updated"]:
        db.commit()
    return stats
