"""Conservative duplicate detection for NEW articles."""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from models import Article
from .textutil import normalize_title


def existing_by_url(db: Session, source_url: str) -> Optional[Article]:
    if not source_url:
        return None
    return (
        db.query(Article)
        .filter(
            (Article.external_id == source_url) | (Article.source_url == source_url)
        )
        .first()
    )


def existing_near_duplicate(
    db: Session,
    title: str,
    published_at: Optional[datetime],
) -> Optional[Article]:
    key = normalize_title(title)
    if not key or len(key) < 16:
        return None

    window_start = None
    if published_at:
        window_start = published_at - timedelta(hours=48)

    query = db.query(Article)
    if window_start:
        query = query.filter(Article.created_at >= window_start - timedelta(days=2))
    recent = query.order_by(Article.created_at.desc()).limit(400).all()
    for article in recent:
        if normalize_title(article.title or "") == key:
            return article
    return None
