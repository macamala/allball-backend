"""Deterministic NinkoSports result briefs from our own public Live Scores API.

No upstream provider is contacted here. The public scores endpoint has already
applied canonicalization, visibility, dedupe and source-branding policy. This
lane turns only finalized public event fields into short original NinkoSports
briefs. It never invents incidents, quotes, tactics, injuries or statistics.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import re
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy.orm import Session

from models import Article

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://allball-backend-production.up.railway.app"
_ALLOWED_API_HOST = "allball-backend-production.up.railway.app"
_FINISHED = {"finished", "complete", "final", "ft", "ended", "aet", "pen", "awarded"}
_MAX_RESPONSE_BYTES = 8_000_000
_MAX_EVENTS_PER_GROUP = 30


def _api_base() -> Optional[str]:
    value = (os.getenv("NEWS_SPORTS_API_BASE") or _DEFAULT_API_BASE).strip().rstrip("/")
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or parts.hostname != _ALLOWED_API_HOST
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        return None
    return value


def data_news_available() -> bool:
    return os.getenv("NEWS_DATA_NEWS_ENABLED") == "1" and _api_base() is not None


def _public_recent(day: str) -> List[Dict]:
    base = _api_base()
    if not base:
        return []
    url = f"{base}/sports-data/recent?date={quote(day, safe='')}"
    try:
        with httpx.Client(timeout=httpx.Timeout(18, connect=5), follow_redirects=False) as client:
            with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    logger.warning("[data_news] scores API HTTP %s", response.status_code)
                    return []
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > _MAX_RESPONSE_BYTES:
                        logger.warning("[data_news] scores API response limit")
                        return []
        import json

        payload = json.loads(raw)
    except Exception as exc:
        logger.warning("[data_news] scores API unavailable: %s", type(exc).__name__)
        return []
    if not isinstance(payload, dict) or payload.get("connected") is False:
        return []
    rows = payload.get("events")
    if not isinstance(rows, list):
        return []
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "").strip().lower() not in _FINISHED:
            continue
        if not row.get("id") or not row.get("sport"):
            continue
        output.append(row)
    return output


def _side_name(value) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("display_name") or "").strip()
    return str(value or "").strip()


def _participant_pair(event: Dict) -> Tuple[str, str]:
    left = _side_name(event.get("home")) or _side_name(event.get("participant_a"))
    right = _side_name(event.get("away")) or _side_name(event.get("participant_b"))
    return left, right


def _score_pair(event: Dict) -> Tuple[Optional[str], Optional[str]]:
    score = event.get("score")
    if not isinstance(score, dict):
        return None, None
    left, right = score.get("home"), score.get("away")
    if left in (None, "") or right in (None, ""):
        return None, None
    return str(left).strip(), str(right).strip()


def _winner_name(event: Dict) -> str:
    winner = event.get("winner")
    if isinstance(winner, dict):
        return _side_name(winner)
    return str(winner or "").strip()


def _event_result_sentence(event: Dict) -> Optional[str]:
    left, right = _participant_pair(event)
    left_score, right_score = _score_pair(event)
    competition = str(event.get("competition_name") or event.get("competition") or "").strip()
    stage = str(event.get("stage") or event.get("round") or "").strip()

    if left and right and left_score is not None and right_score is not None:
        context = f" in {competition}" if competition else ""
        suffix = f" ({stage})" if stage else ""
        try:
            a, b = float(left_score), float(right_score)
        except ValueError:
            a = b = None
        if a is not None and b is not None:
            if a > b:
                return f"{left} beat {right} {left_score}-{right_score}{context}{suffix}."
            if b > a:
                return f"{right} beat {left} {right_score}-{left_score}{context}{suffix}."
            return f"{left} and {right} finished {left_score}-{right_score}{context}{suffix}."
        return f"{left} and {right} finished with a recorded score of {left_score}-{right_score}{context}{suffix}."

    winner = _winner_name(event)
    label = str(
        event.get("race_name")
        or event.get("tournament_name")
        or event.get("competition_name")
        or event.get("competition")
        or event.get("stage")
        or ""
    ).strip()
    if winner and label:
        return f"{winner} was recorded as the winner of {label}."
    if winner:
        return f"{winner} was recorded as the winner of the completed event."
    return None


def _competition_key(event: Dict) -> str:
    return str(event.get("competition_key") or event.get("competition") or "unclassified").strip()[:160]


def _competition_label(events: Iterable[Dict], fallback: str) -> str:
    for event in events:
        value = str(event.get("competition_name") or event.get("competition") or "").strip()
        if value:
            return value[:180]
    return fallback.replace("-", " ").strip().title() or "Competition"


def _sport_label(sport: str) -> str:
    from sports_registry.sports import get_sport

    row = get_sport(sport)
    return str((row or {}).get("name") or sport.replace("-", " ").title())


def build_result_brief(sport: str, competition_key: str, day: str, events: List[Dict]) -> Optional[Dict]:
    """Pure deterministic formatter. Returns no draft if there is no result fact."""
    seen = set()
    rows = []
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id or event_id in seen:
            continue
        sentence = _event_result_sentence(event)
        if not sentence:
            continue
        seen.add(event_id)
        rows.append((event_id, sentence))
        if len(rows) >= _MAX_EVENTS_PER_GROUP:
            break
    if not rows:
        return None

    competition = _competition_label(events, competition_key)
    sport_name = _sport_label(sport)
    if len(rows) == 1:
        core = rows[0][1].rstrip(".")
        title = core[:240]
    else:
        title = f"{competition} results: {len(rows)} completed {sport_name.lower()} events"

    result_text = " ".join(sentence for _, sentence in rows)
    summary = (
        f"NinkoSports Result Brief: {len(rows)} finalized "
        f"{sport_name.lower()} result{'s' if len(rows) != 1 else ''} from {competition}."
    )
    body = (
        f"NinkoSports recorded {len(rows)} completed {sport_name.lower()} "
        f"event{'s' if len(rows) != 1 else ''} in {competition} for {day}. "
        "This result brief uses only finalized fields already available in the "
        "NinkoSports Live Scores record; scheduled and live events are excluded.\n\n"
        f"{result_text}\n\n"
        "The roundup changes only when the canonical final-result record changes. "
        "No unverified scorers, incidents, quotes, injuries, tactics or statistics are added."
    )
    digest = hashlib.sha256("|".join(event_id for event_id, _ in rows).encode("utf-8")).hexdigest()[:16]
    return {
        "title": title,
        "summary": summary,
        "body": body,
        "event_ids": [event_id for event_id, _ in rows],
        "signature": digest,
        "competition_label": competition,
    }


def _slug_piece(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\s-]", " ", value or "")
    return re.sub(r"[\s-]+", "-", value.strip().lower()).strip("-")[:80] or "results"


def _upsert_group(db: Session, sport: str, competition_key: str, day: str, events: List[Dict]) -> bool:
    draft = build_result_brief(sport, competition_key, day, events)
    if not draft:
        return False
    external_id = f"ninkosports-results:{day}:{sport}:{competition_key}"[:500]
    article = db.query(Article).filter(Article.external_id == external_id).first()
    now = datetime.now(timezone.utc)
    body = draft["body"]
    if article is not None and (article.content or "") == body and (article.title or "") == draft["title"]:
        return False

    if article is None:
        base_slug = f"results-{day}-{_slug_piece(sport)}-{_slug_piece(competition_key)}"
        slug = base_slug[:290]
        counter = 1
        while db.query(Article).filter(Article.slug == slug).first() is not None:
            counter += 1
            slug = f"{base_slug[:280]}-{counter}"
        article = Article(external_id=external_id, slug=slug)
        db.add(article)

    article.title = draft["title"]
    article.sport = sport
    article.league = competition_key
    article.country = None
    article.division = 1
    article.image_url = None
    article.source_url = (
        f"https://ninkosports.com/live-scores?date={quote(day, safe='')}"
        f"&sport={quote(sport, safe='')}"
    )[:500]
    article.summary = draft["summary"]
    article.content = body
    article.ai_content = None
    article.ai_generated = False
    article.is_live = True
    article.is_breaking = False
    article.published_at = now
    db.flush()

    from taxonomy_resolver import TaxonomyResolution
    from public_index import persist_public_article

    resolved = TaxonomyResolution(
        sport=sport,
        competition=competition_key if competition_key != "unclassified" else None,
        sport_confidence=1.0,
        competition_confidence=1.0 if competition_key != "unclassified" else 0.0,
        evidence=["canonical-ninkosports-live-scores"],
    )
    persist_public_article(db, article, resolved, commit=False)
    return True


def ingest_result_briefs(days: int = 2, max_groups: int = 120) -> int:
    """Refresh bounded daily competition roundups. No AI request is consumed."""
    if not data_news_available():
        return 0
    from database import SessionLocal

    now = datetime.now(timezone.utc)
    grouped: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)
    for offset in range(max(1, min(int(days), 3))):
        day = (now - timedelta(days=offset)).date().isoformat()
        for event in _public_recent(day):
            sport = str(event.get("sport") or "").strip()
            if not sport:
                continue
            grouped[(sport, _competition_key(event), day)].append(event)

    ordered = sorted(grouped.items(), key=lambda item: item[0])[: max(1, min(int(max_groups), 300))]
    if not ordered:
        return 0

    db = SessionLocal()
    changed = 0
    try:
        for (sport, competition_key, day), events in ordered:
            try:
                if _upsert_group(db, sport, competition_key, day, events):
                    changed += 1
            except Exception as exc:
                db.rollback()
                logger.warning("[data_news] group held %s/%s: %s", sport, competition_key, type(exc).__name__)
        if changed:
            db.commit()
            try:
                from public_cache import bump_public_cache

                bump_public_cache()
            except Exception:
                logger.warning("[data_news] public cache bump failed")
        return changed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
