"""Article comments. Readers can list; only signed-in users can write."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_db, load_user_from_request, rate_limit, require_csrf, require_user
from models import Comment, CommentLike, CommentReport, User

router = APIRouter(tags=["comments"])
TAG_RE = re.compile(r"<[^>]+>")
MAX_LEN = 1200
MAX_DEPTH = 2


def sanitize_comment(text: str) -> str:
    cleaned = TAG_RE.sub(" ", text or "")
    cleaned = html.unescape(cleaned)
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _public_comment(row: Comment, user: User, liked: bool, viewer_id: Optional[int]) -> dict:
    hidden = bool(row.hidden or row.deleted_at)
    body = "" if hidden else row.body
    return {
        "id": row.id,
        "article_id": row.article_id,
        "parent_id": row.parent_id,
        "body": body,
        "like_count": int(row.like_count or 0),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "deleted": bool(row.deleted_at),
        "hidden": bool(row.hidden),
        "liked": liked,
        "own": viewer_id == row.user_id if viewer_id else False,
        "author": {
            "display_name": user.display_name if user else "NinkoSports reader",
        },
    }


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_LEN)
    parent_id: Optional[int] = None


class CommentEditIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_LEN)


class ReportIn(BaseModel):
    reason: str = Field(min_length=3, max_length=80)
    detail: Optional[str] = Field(default=None, max_length=400)


@router.get("/articles/{slug}/comments")
def list_comments(slug: str, request: Request, db: Session = Depends(get_db)):
    from models import Article

    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    viewer = load_user_from_request(request, db)
    rows = (
        db.query(Comment)
        .filter(Comment.article_id == article.id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    users = {
        user.id: user
        for user in db.query(User).filter(User.id.in_({row.user_id for row in rows} or {0})).all()
    }
    liked_ids = set()
    if viewer and rows:
        liked_ids = {
            like.comment_id
            for like in db.query(CommentLike)
            .filter(
                CommentLike.user_id == viewer.id,
                CommentLike.comment_id.in_([row.id for row in rows]),
            )
            .all()
        }
    visible = [row for row in rows if not (row.hidden and (not viewer or viewer.id != row.user_id))]
    return {
        "count": sum(1 for row in rows if not row.hidden and not row.deleted_at),
        "comments": [
            _public_comment(row, users.get(row.user_id), row.id in liked_ids, viewer.id if viewer else None)
            for row in visible
        ],
    }


@router.post("/articles/{slug}/comments")
def create_comment(
    slug: str,
    payload: CommentIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    from models import Article

    require_csrf(request)
    rate_limit(request, "comment", 8, 600)
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    body = sanitize_comment(payload.body)
    if len(body) < 2:
        raise HTTPException(status_code=400, detail="Comment is too short.")
    parent = None
    if payload.parent_id:
        parent = db.query(Comment).filter(Comment.id == payload.parent_id, Comment.article_id == article.id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Reply target not found.")
        depth = 1
        walk = parent
        while walk.parent_id:
            depth += 1
            walk = db.query(Comment).filter(Comment.id == walk.parent_id).first()
            if not walk:
                break
        if depth >= MAX_DEPTH:
            raise HTTPException(status_code=400, detail="Replies are limited to one level.")
    recent = (
        db.query(Comment)
        .filter(Comment.user_id == user.id, Comment.article_id == article.id, Comment.body == body)
        .order_by(Comment.created_at.desc())
        .first()
    )
    if recent and recent.created_at and (datetime.utcnow() - recent.created_at).total_seconds() < 120:
        raise HTTPException(status_code=429, detail="Duplicate comment.")
    row = Comment(
        article_id=article.id,
        user_id=user.id,
        parent_id=parent.id if parent else None,
        body=body,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _public_comment(row, user, False, user.id)


@router.patch("/comments/{comment_id}")
def edit_comment(
    comment_id: int,
    payload: CommentEditIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    require_csrf(request)
    row = db.query(Comment).filter(Comment.id == comment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments.")
    row.body = sanitize_comment(payload.body)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _public_comment(row, user, False, user.id)


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    require_csrf(request)
    row = db.query(Comment).filter(Comment.id == comment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    if row.user_id != user.id and user.role not in {"admin", "moderator"}:
        raise HTTPException(status_code=403, detail="You can only delete your own comments.")
    row.deleted_at = datetime.utcnow()
    row.body = ""
    db.add(row)
    db.commit()
    return {"ok": True}


@router.post("/comments/{comment_id}/like")
def like_comment(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    require_csrf(request)
    row = db.query(Comment).filter(Comment.id == comment_id).first()
    if not row or row.deleted_at:
        raise HTTPException(status_code=404, detail="Comment not found")
    existing = (
        db.query(CommentLike)
        .filter(CommentLike.user_id == user.id, CommentLike.comment_id == comment_id)
        .first()
    )
    if existing:
        db.delete(existing)
        row.like_count = max(0, int(row.like_count or 0) - 1)
        liked = False
    else:
        db.add(CommentLike(user_id=user.id, comment_id=comment_id))
        row.like_count = int(row.like_count or 0) + 1
        liked = True
    db.add(row)
    db.commit()
    return {"liked": liked, "like_count": row.like_count}


@router.post("/comments/{comment_id}/report")
def report_comment(
    comment_id: int,
    payload: ReportIn,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    require_csrf(request)
    rate_limit(request, "report", 10, 600)
    row = db.query(Comment).filter(Comment.id == comment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.add(
        CommentReport(
            comment_id=comment_id,
            user_id=user.id,
            reason=sanitize_comment(payload.reason)[:80],
            detail=sanitize_comment(payload.detail or "")[:400] or None,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/moderation/comments/{comment_id}/hide")
def hide_comment(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_user),
):
    require_csrf(request)
    if user.role not in {"admin", "moderator"}:
        raise HTTPException(status_code=403, detail="Moderator access required.")
    row = db.query(Comment).filter(Comment.id == comment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Comment not found")
    row.hidden = True
    db.add(row)
    db.commit()
    return {"ok": True, "hidden": True}
