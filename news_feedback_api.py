"""Staff-only News incident, correction and confirmed-learning endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_db, require_csrf, require_user
from bot.news_learning import add_confirmed_rule, confirm_incident, record_incident
from bot.taxonomy import COMPETITIONS, canonical_competition_key
from editorial import sanitize_body, sanitize_summary, sanitize_title
from models import Article, NewsCorrectionRule, NewsIncident, User
from sports_registry.sports import canonical_sport_slug, get_sport

router = APIRouter(prefix="/admin/news", tags=["news-admin"])


def require_staff(user: User = Depends(require_user)) -> User:
    if (user.role or "").lower() not in {"admin", "moderator"}:
        raise HTTPException(status_code=403, detail="Staff access required.")
    return user


class IncidentIn(BaseModel):
    reason_code: str = Field(min_length=2, max_length=180)
    note: Optional[str] = Field(default=None, max_length=4000)


class IncidentActionIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=4000)


class RuleIn(BaseModel):
    rule_type: str = Field(max_length=40)
    bad_value: str = Field(min_length=2, max_length=300)
    replacement: Optional[str] = Field(default=None, max_length=300)
    sport: Optional[str] = Field(default=None, max_length=50)
    source_url: Optional[str] = Field(default=None, max_length=500)
    scope: str = Field(default="global", max_length=20)
    note: Optional[str] = Field(default=None, max_length=4000)


class CorrectionIn(BaseModel):
    incident_id: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=500)
    summary: Optional[str] = Field(default=None, max_length=4000)
    body: Optional[str] = Field(default=None, max_length=50000)
    sport: Optional[str] = Field(default=None, max_length=50)
    league: Optional[str] = Field(default=None, max_length=120)
    learn_rule_type: Optional[str] = Field(default=None, max_length=40)
    learn_bad_value: Optional[str] = Field(default=None, max_length=300)
    learn_replacement: Optional[str] = Field(default=None, max_length=300)
    learn_scope: str = Field(default="source", max_length=20)
    note: Optional[str] = Field(default=None, max_length=4000)


def _incident_payload(row: NewsIncident) -> dict:
    return {
        "id": row.id,
        "article_id": row.article_id,
        "source_url": row.source_url,
        "source_host": row.source_host,
        "sport": row.sport,
        "phase": row.phase,
        "reason_code": row.reason_code,
        "retry_reason_code": row.retry_reason_code,
        "severity": row.severity,
        "writer_provider": row.writer_provider,
        "writer_model": row.writer_model,
        "status": row.status,
        "confirmed": bool(row.confirmed),
        "created_at": row.created_at,
        "resolved_at": row.resolved_at,
        "resolution_note": row.resolution_note,
        "draft_excerpt": row.draft_excerpt,
    }


def _reindex(db: Session, article: Article) -> None:
    from public_cache import bump_public_cache
    from public_index import persist_public_article
    from taxonomy_resolver import resolve_article_competition

    persist_public_article(db, article, resolve_article_competition(article), commit=True)
    bump_public_cache()


@router.get("/incidents")
def list_incidents(
    status: str = "open",
    limit: int = 100,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    limit = max(1, min(int(limit), 200))
    query = db.query(NewsIncident)
    if status != "all":
        query = query.filter(NewsIncident.status == status)
    rows = query.order_by(NewsIncident.created_at.desc(), NewsIncident.id.desc()).limit(limit).all()
    return {"count": len(rows), "incidents": [_incident_payload(row) for row in rows]}


@router.get("/rules")
def list_rules(
    active_only: bool = True,
    limit: int = 200,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff),
):
    query = db.query(NewsCorrectionRule)
    if active_only:
        query = query.filter(NewsCorrectionRule.active.is_(True))
    rows = query.order_by(NewsCorrectionRule.id.desc()).limit(max(1, min(limit, 500))).all()
    return {
        "rules": [
            {
                "id": row.id,
                "rule_type": row.rule_type,
                "bad_value": row.bad_value,
                "replacement": row.replacement,
                "sport": row.sport,
                "source_host": row.source_host,
                "active": bool(row.active),
                "confirmed_count": int(row.confirmed_count or 0),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "note": row.note,
            }
            for row in rows
        ]
    }


@router.post("/articles/{article_id}/flag")
def flag_article(
    article_id: int,
    payload: IncidentIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff),
):
    require_csrf(request)
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    row = record_incident(
        db,
        reason_code=payload.reason_code,
        source_url=article.source_url,
        sport=article.sport,
        phase="postpublish-staff",
        article_id=article.id,
        draft={"title": article.title, "summary": article.summary, "body": article.ai_content or article.content},
        details={"flagged_by_user_id": staff.id, "note": payload.note or ""},
    )
    _reindex(db, article)
    return _incident_payload(row)


@router.post("/incidents/{incident_id}/confirm")
def confirm_news_incident(
    incident_id: int,
    payload: IncidentActionIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff),
):
    require_csrf(request)
    row = db.query(NewsIncident).filter(NewsIncident.id == incident_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found.")
    confirm_incident(
        db,
        row,
        user_id=staff.id,
        resolution_note=payload.note or "confirmed by staff",
        dismissed=False,
    )
    return _incident_payload(row)


@router.post("/rules")
def create_rule(
    payload: RuleIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff),
):
    require_csrf(request)
    scope = (payload.scope or "global").lower()
    if scope not in {"source", "sport", "global"}:
        raise HTTPException(status_code=400, detail="Invalid learning scope.")
    sport = None
    if scope in {"source", "sport"}:
        sport = canonical_sport_slug(payload.sport or "")
        if not sport or not get_sport(sport):
            raise HTTPException(status_code=400, detail="Valid sport required for this scope.")
    try:
        row = add_confirmed_rule(
            db,
            rule_type=payload.rule_type,
            bad_value=payload.bad_value,
            replacement=payload.replacement,
            sport=sport,
            source_url=payload.source_url,
            source_scope=scope == "source",
            user_id=staff.id,
            note=payload.note or "staff-confirmed News rule",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rule_id": row.id}


@router.post("/incidents/{incident_id}/dismiss")
def dismiss_incident(
    incident_id: int,
    payload: IncidentActionIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff),
):
    require_csrf(request)
    row = db.query(NewsIncident).filter(NewsIncident.id == incident_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found.")
    confirm_incident(
        db,
        row,
        user_id=staff.id,
        resolution_note=payload.note or "dismissed by staff",
        dismissed=True,
    )
    if row.article_id:
        article = db.query(Article).filter(Article.id == row.article_id).first()
        if article:
            _reindex(db, article)
    return _incident_payload(row)


@router.post("/articles/{article_id}/correct")
def correct_article(
    article_id: int,
    payload: CorrectionIn,
    request: Request,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff),
):
    require_csrf(request)
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")

    if payload.title is not None:
        value = sanitize_title(payload.title)[:500]
        if not value:
            raise HTTPException(status_code=400, detail="Corrected title is empty.")
        article.title = value
    if payload.summary is not None:
        article.summary = sanitize_summary(payload.summary, title=article.title)
    if payload.body is not None:
        body = sanitize_body(payload.body, title=article.title)
        if len(body.split()) < 25:
            raise HTTPException(status_code=400, detail="Corrected article body is too short.")
        article.content = body
        if article.ai_generated:
            article.ai_content = body
    if payload.sport is not None:
        sport = canonical_sport_slug(payload.sport)
        if not sport or not get_sport(sport):
            raise HTTPException(status_code=400, detail="Unknown sport.")
        article.sport = sport
    if payload.league is not None:
        league = canonical_competition_key(payload.league)
        if payload.league and (not league or league not in COMPETITIONS):
            raise HTTPException(status_code=400, detail="Unknown competition.")
        if league and article.sport and COMPETITIONS[league]["sport"] != article.sport:
            raise HTTPException(status_code=400, detail="Competition does not belong to corrected sport.")
        article.league = league

    db.add(article)
    db.commit()
    db.refresh(article)

    incident = None
    if payload.incident_id is not None:
        incident = db.query(NewsIncident).filter(NewsIncident.id == payload.incident_id).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found.")
        if incident.article_id not in {None, article.id}:
            raise HTTPException(status_code=400, detail="Incident belongs to another article.")
        confirm_incident(
            db,
            incident,
            user_id=staff.id,
            resolution_note=payload.note or "corrected by staff",
            dismissed=False,
        )

    rule = None
    if payload.learn_rule_type:
        scope = (payload.learn_scope or "source").lower()
        if scope not in {"source", "sport", "global"}:
            raise HTTPException(status_code=400, detail="Invalid learning scope.")
        try:
            rule = add_confirmed_rule(
                db,
                rule_type=payload.learn_rule_type,
                bad_value=payload.learn_bad_value or "",
                replacement=payload.learn_replacement,
                sport=article.sport if scope in {"source", "sport"} else None,
                source_url=article.source_url,
                source_scope=scope == "source",
                user_id=staff.id,
                note=payload.note or f"learned from article {article.id}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    _reindex(db, article)
    return {
        "ok": True,
        "article_id": article.id,
        "incident": _incident_payload(incident) if incident else None,
        "learned_rule_id": rule.id if rule else None,
    }
