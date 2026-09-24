"""CyberScore identity-only artwork repair for current visible Dota 2 events.

The current tournament pages expose the tournament mark and participant team
logos in HTML. We only apply artwork when both canonical event participants
exist on the same tournament page. No fixtures/results/status/times are read
or changed.
"""

from __future__ import annotations

import html as html_lib
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from sqlalchemy import or_
from sqlalchemy.orm import Session

from collector.cache import note_list_invalidation
from collector.http import fetch_text
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.participant_text import fold_for_identity
from collector.util import dump_json, load_json

RUN_INTERVAL_S = 600
_next_run_at = 0.0

PAGES = (
    "https://cyberscore.live/en/tournaments/tournament-1789482541627/",
    "https://cyberscore.live/en/tournaments/pgl-wallachia-season-9/",
)

_HEADERS = {
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://cyberscore.live/",
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


def _attrs(tag: str) -> Dict[str, str]:
    return {
        name.lower(): html_lib.unescape(value.strip())
        for name, _quote, value in _ATTR_RE.findall(tag or "")
    }


def _page_assets(raw_html: str, base_url: str) -> Dict[str, Any]:
    teams: Dict[str, Dict[str, str]] = {}
    tournament_logo = ""
    tournament_name = ""

    for tag in _IMG_RE.findall(raw_html or ""):
        attrs = _attrs(tag)
        alt = str(attrs.get("alt") or attrs.get("title") or "").strip()
        source = str(
            attrs.get("src")
            or attrs.get("data-src")
            or attrs.get("data-lazy-src")
            or ""
        ).strip()
        if not alt or not source:
            continue
        logo = urljoin(base_url, source)
        lower = alt.casefold()

        if lower.endswith(" - tournament logo"):
            name = alt[: -len(" - tournament logo")].strip()
            if name and not tournament_logo:
                tournament_name = name
                tournament_logo = logo
            continue

        if lower.endswith(" - team logo"):
            name = alt[: -len(" - team logo")].strip()
            key = _key(name)
            if not key:
                continue
            existing = teams.get(key)
            if existing and existing.get("logo") != logo:
                teams[key] = {"name": name, "logo": "", "conflict": "1"}
                continue
            if not existing:
                teams[key] = {"name": name, "logo": logo}

    teams = {
        key: row
        for key, row in teams.items()
        if row.get("logo") and not row.get("conflict")
    }
    return {
        "teams": teams,
        "tournament_logo": tournament_logo,
        "tournament_name": tournament_name,
    }


def run_if_due(db: Session, *, getter=None, heartbeat=None) -> Optional[Dict[str, Any]]:
    global _next_run_at
    now_mono = time.monotonic()
    if now_mono < _next_run_at:
        return None
    _next_run_at = now_mono + RUN_INTERVAL_S

    fetch = getter or (lambda url: fetch_text(url, headers=_HEADERS))
    pages: list[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "status": "ok",
        "requests": 0,
        "http_errors": 0,
        "pages_ok": 0,
        "candidate_rows": 0,
        "matched_rows": 0,
        "rows_updated": 0,
        "participant_logos_filled": 0,
        "competition_logos_filled": 0,
        "by_page": {},
    }

    for url in PAGES:
        result = fetch(url)
        stats["requests"] += 1
        if not getattr(result, "ok", False):
            stats["http_errors"] += 1
            stats["by_page"][url] = {"ok": False, "teams": 0, "tournament_logo": False}
            continue
        raw = getattr(result, "payload", None)
        assets = _page_assets(raw if isinstance(raw, str) else "", url)
        pages.append({"url": url, **assets})
        stats["pages_ok"] += 1
        stats["by_page"][url] = {
            "ok": True,
            "teams": len(assets["teams"]),
            "tournament_logo": bool(assets["tournament_logo"]),
            "tournament_name": assets["tournament_name"],
        }
        if heartbeat:
            heartbeat()

    if not pages:
        stats["status"] = "fetch_error" if stats["http_errors"] else "empty"
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

        matching = [
            page
            for page in pages
            if home_key in page["teams"] and away_key in page["teams"]
        ]
        if len(matching) != 1:
            # Zero is unresolved; >1 is ambiguous across tournament pages.
            continue
        page = matching[0]
        stats["matched_rows"] += 1
        changed = False
        extra_changed = False

        for side_name, mirror_name, key in (
            ("home", "participant_a", home_key),
            ("away", "participant_b", away_key),
        ):
            side = participants.get(side_name)
            if not isinstance(side, dict) or _logo(side):
                continue
            asset = page["teams"].get(key) or {}
            logo = str(asset.get("logo") or "").strip()
            if not logo:
                continue
            merged = dict(side)
            merged["logo"] = logo
            participants[side_name] = merged
            mirror = participants.get(mirror_name)
            if isinstance(mirror, dict) and not _logo(mirror):
                mirror_copy = dict(mirror)
                mirror_copy["logo"] = logo
                participants[mirror_name] = mirror_copy
            stats["participant_logos_filled"] += 1
            changed = True

        comp_logo = str(page.get("tournament_logo") or "").strip()
        if needs_comp and comp_logo:
            extra["competition_logo"] = comp_logo
            sources = extra.get("identity_asset_sources")
            if not isinstance(sources, dict):
                sources = {}
            sources["competition_logo"] = "cyberscore-tournament-page"
            extra["identity_asset_sources"] = sources
            extra_changed = True
            changed = True
            stats["competition_logos_filled"] += 1

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
