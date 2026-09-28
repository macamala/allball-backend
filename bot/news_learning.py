"""Persistent correction memory and writer-trust controls for NinkoSports News.

Automated observations may block publication, but only staff-confirmed incidents
become durable trust signals or reusable correction rules. This keeps the system
from learning its own hallucinations as truth.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlsplit

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import NewsCorrectionRule, NewsIncident


def source_host(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        return host or None
    except ValueError:
        return None


def writer_identity() -> tuple[str, str]:
    try:
        from . import rewrite_ai
        mode = str(getattr(rewrite_ai, "AI_PROVIDER_MODE", "") or "").strip().lower()
        if mode == "xkiro_free":
            from .free_ai_router import last_writer_identity, selected_free_model_name
            provider, model = last_writer_identity()
            if provider != "unknown" and model != "unknown":
                return provider, model
            return "xkiro", selected_free_model_name() or "unknown-free-model"
        if mode == "openai_legacy":
            return "openai", str(getattr(rewrite_ai, "OPENAI_MODEL", "") or "unknown")
        return mode or "unknown", "unknown"
    except Exception:
        return "unknown", "unknown"


def record_incident(
    db: Session,
    *,
    reason_code: str,
    source_url: Optional[str] = None,
    sport: Optional[str] = None,
    phase: str = "prepublish",
    article_id: Optional[int] = None,
    draft: Optional[dict] = None,
    writer_provider: Optional[str] = None,
    writer_model: Optional[str] = None,
    details: Optional[dict] = None,
    status: str = "open",
    severity: str = "block",
) -> NewsIncident:
    reason = (reason_code or "unknown")[:180]
    query = db.query(NewsIncident).filter(
        NewsIncident.reason_code == reason,
        NewsIncident.status == "open",
    )
    if article_id is not None:
        query = query.filter(NewsIncident.article_id == article_id)
    elif source_url:
        query = query.filter(NewsIncident.source_url == source_url)
    existing = query.order_by(NewsIncident.id.desc()).first()
    if existing:
        return existing

    excerpt = None
    if isinstance(draft, dict):
        excerpt = "\n\n".join(
            str(draft.get(key) or "").strip()
            for key in ("title", "summary", "body")
            if str(draft.get(key) or "").strip()
        )[:4000]
    provider, model = writer_identity()
    row = NewsIncident(
        article_id=article_id,
        source_url=(source_url or "")[:500] or None,
        source_host=source_host(source_url),
        sport=(sport or "")[:50] or None,
        phase=(phase or "prepublish")[:40],
        reason_code=reason,
        severity=(severity or "block")[:20],
        writer_provider=(writer_provider or provider)[:80],
        writer_model=(writer_model or model)[:160],
        draft_excerpt=excerpt,
        details_json=json.dumps(details or {}, ensure_ascii=False, sort_keys=True)[:12000],
        status=status,
        confirmed=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mark_retry(db: Session, incident: NewsIncident, retry_reason: str) -> None:
    incident.retry_reason_code = (retry_reason or "unknown")[:180]
    db.add(incident)
    db.commit()


def mark_auto_corrected(db: Session, incident: NewsIncident, note: str = "") -> None:
    incident.status = "auto_corrected"
    incident.resolved_at = datetime.utcnow()
    incident.resolution_note = (note or "corrective rewrite passed all publication gates")[:3000]
    db.add(incident)
    db.commit()


def confirm_incident(
    db: Session,
    incident: NewsIncident,
    *,
    user_id: Optional[int],
    resolution_note: str = "",
    dismissed: bool = False,
) -> None:
    incident.confirmed = not dismissed
    incident.confirmed_by_user_id = user_id
    incident.status = "dismissed" if dismissed else "resolved"
    incident.resolved_at = datetime.utcnow()
    incident.resolution_note = (resolution_note or "")[:4000] or None
    db.add(incident)
    db.commit()


def article_has_open_incident(db: Session, article_id: Optional[int]) -> bool:
    if not article_id:
        return False
    return (
        db.query(NewsIncident.id)
        .filter(
            NewsIncident.article_id == article_id,
            NewsIncident.status == "open",
            NewsIncident.severity == "block",
        )
        .first()
        is not None
    )


def _rule_query(db: Session, source_url: Optional[str], sport: Optional[str]):
    host = source_host(source_url)
    query = db.query(NewsCorrectionRule).filter(NewsCorrectionRule.active.is_(True))
    if sport:
        query = query.filter(or_(NewsCorrectionRule.sport.is_(None), NewsCorrectionRule.sport == sport))
    else:
        query = query.filter(NewsCorrectionRule.sport.is_(None))
    if host:
        query = query.filter(or_(NewsCorrectionRule.source_host.is_(None), NewsCorrectionRule.source_host == host))
    else:
        query = query.filter(NewsCorrectionRule.source_host.is_(None))
    return query.order_by(NewsCorrectionRule.id.asc())


def rule_prompt_instructions(
    db: Session,
    *,
    source_url: Optional[str],
    sport: Optional[str],
) -> tuple[str, list[int]]:
    """Return compact, staff-confirmed writing instructions for this source/sport."""
    lines = []
    ids = []
    for rule in _rule_query(db, source_url, sport).all():
        bad = (rule.bad_value or "").strip()
        if len(bad) < 2:
            continue
        ids.append(rule.id)
        if rule.rule_type == "exact_replace" and rule.replacement:
            lines.append(f'Never write "{bad}". Use "{rule.replacement}" when that exact concept is required by the source.')
        elif rule.rule_type == "block_phrase":
            lines.append(f'Never use the phrase "{bad}". Omit or paraphrase it without adding facts.')
    return "\n".join(lines[:12]), ids


def learned_rule_violation_reason(
    db: Session,
    draft: dict,
    *,
    source_url: Optional[str],
    sport: Optional[str],
) -> Optional[str]:
    if not isinstance(draft, dict):
        return "missing_original_draft"
    combined = "\n".join(str(draft.get(k) or "") for k in ("title", "summary", "body"))
    for rule in _rule_query(db, source_url, sport).all():
        bad = (rule.bad_value or "").strip()
        if len(bad) < 2:
            continue
        if re.search(re.escape(bad), combined, re.IGNORECASE):
            return f"learned_rule_violation:{rule.id}"
    return None


def add_confirmed_rule(
    db: Session,
    *,
    rule_type: str,
    bad_value: str,
    replacement: Optional[str] = None,
    sport: Optional[str] = None,
    source_url: Optional[str] = None,
    source_scope: bool = False,
    user_id: Optional[int] = None,
    note: str = "",
) -> NewsCorrectionRule:
    if rule_type not in {"exact_replace", "block_phrase"}:
        raise ValueError("unsupported_rule_type")
    bad = (bad_value or "").strip()
    if len(bad) < 2 or len(bad) > 300:
        raise ValueError("invalid_bad_value")
    repl = (replacement or "").strip() or None
    if rule_type == "exact_replace" and not repl:
        raise ValueError("replacement_required")
    host = source_host(source_url) if source_scope else None
    query = db.query(NewsCorrectionRule).filter(
        NewsCorrectionRule.rule_type == rule_type,
        NewsCorrectionRule.bad_value == bad,
        NewsCorrectionRule.sport == (sport or None),
        NewsCorrectionRule.source_host == host,
    )
    if repl is None:
        query = query.filter(NewsCorrectionRule.replacement.is_(None))
    else:
        query = query.filter(NewsCorrectionRule.replacement == repl)
    row = query.first()
    if row:
        row.active = True
        row.confirmed_count = int(row.confirmed_count or 0) + 1
        row.updated_at = datetime.utcnow()
        if note:
            row.note = note[:4000]
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    row = NewsCorrectionRule(
        rule_type=rule_type,
        bad_value=bad,
        replacement=repl,
        sport=(sport or "")[:50] or None,
        source_host=host,
        active=True,
        confirmed_count=1,
        created_by_user_id=user_id,
        note=(note or "")[:4000] or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def writer_allowed(
    db: Session,
    provider: str,
    model: str,
    *,
    max_confirmed_errors: int = 3,
    window_hours: int = 24,
) -> bool:
    """Persistent circuit-breaker based only on confirmed factual incidents."""
    since = datetime.utcnow() - timedelta(hours=max(1, window_hours))
    count = (
        db.query(NewsIncident.id)
        .filter(
            NewsIncident.writer_provider == provider,
            NewsIncident.writer_model == model,
            NewsIncident.confirmed.is_(True),
            NewsIncident.created_at >= since,
            NewsIncident.status != "dismissed",
        )
        .count()
    )
    return count < max_confirmed_errors
