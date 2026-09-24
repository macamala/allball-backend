"""Liquipedia identity-only artwork repair for visible Dota 2 events.

This reads only two current tournament pages and extracts participant artwork.
It never creates fixtures or changes score/status/start time. Existing artwork
always wins; only blank participant logos are filled.
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
from collector.models import SportsEvent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 600
_next_run_at = 0.0

PAGES = (
    "https://liquipedia.net/dota2/BetBoom_Streamers_Battle/15",
    "https://liquipedia.net/dota2/PGL/Wallachia/9",
)

_HEADERS = {
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://liquipedia.net/dota2/",
}

_IMG_RE = re.compile(r"<img\\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\\s*=\\s*(["'])(.*?)\\2""", re.S)


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
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "by_page": {},
    }
    catalog: Dict[str, Dict[str, str]] = {}

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
        page_stats["assets"] = len(page_catalog)
        page_stats["image_candidates"] = _diagnostic_image_candidates(raw_html, url)
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
        missing = [
            side_name
            for side_name in ("home", "away")
            if isinstance(participants.get(side_name), dict)
            and str((participants.get(side_name) or {}).get("name") or "").strip()
            and not _logo(participants.get(side_name))
        ]
        if not missing:
            continue
        stats["candidate_rows"] += 1
        changed = False

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

        if not changed:
            continue
        row.participants_json = dump_json(participants)
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
