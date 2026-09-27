"""Conservative duplicate detection for NEW articles."""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re
from typing import Optional

from sqlalchemy.orm import Session

from models import Article
from .textutil import normalize_title
from .news_policy import canonical_news_url


def existing_by_url(db: Session, source_url: str) -> Optional[Article]:
    if not source_url:
        return None
    exact = (
        db.query(Article)
        .filter(
            (Article.external_id == source_url) | (Article.source_url == source_url)
        )
        .first()
    )
    if exact is not None:
        return exact
    target = canonical_news_url(source_url)
    if not target:
        return None
    recent = (
        db.query(Article)
        .filter(Article.source_url.isnot(None))
        .order_by(Article.id.desc())
        .limit(500)
        .all()
    )
    for article in recent:
        if canonical_news_url(article.source_url or article.external_id or "") == target:
            return article
    return None


def _title_tokens(value: str) -> set[str]:
    stop = {
        "the","and","for","with","from","before","into","over","under","will",
        "news","latest","update","report","live","says","set","new","sport",
    }
    aliases = {
        "confirms": "confirm", "confirmed": "confirm", "confirming": "confirm",
        "following": "after",
        "clash": "match", "game": "match", "fixture": "match",
        "beats": "beat", "beaten": "beat",
        "wins": "win", "won": "win",
        "signs": "sign", "signed": "sign",
        "joins": "join", "joined": "join",
    }
    tokens = set()
    for token in re.findall(r"[a-z0-9]{3,}", normalize_title(value or "")):
        if token in stop:
            continue
        tokens.add(aliases.get(token, token))
    return tokens


def title_similarity(left: str, right: str) -> float:
    """Conservative cross-source headline similarity.

    Exact normalized titles are 1.0. Otherwise combine character similarity and
    significant-token overlap. This is deliberately strict to avoid collapsing
    genuinely different stories about the same club/player.
    """
    a = normalize_title(left or "")
    b = normalize_title(right or "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    chars = SequenceMatcher(None, a, b).ratio()
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return chars
    shared = len(ta & tb)
    union = len(ta | tb)
    jaccard = shared / max(1, union)
    containment = shared / max(1, min(len(ta), len(tb)))
    # Strong character agreement or a near-contained significant-token set.
    if chars >= 0.90:
        return chars
    if shared >= 4 and jaccard >= 0.72:
        return max(chars, jaccard)
    if shared >= 5 and containment >= 0.86 and chars >= 0.72:
        return max(chars, containment)
    return max(chars, jaccard * 0.92)


def titles_are_near_duplicate(left: str, right: str) -> bool:
    return title_similarity(left, right) >= 0.86


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
        existing = article.title or ""
        if normalize_title(existing) == key or titles_are_near_duplicate(existing, title):
            return article
    return None
