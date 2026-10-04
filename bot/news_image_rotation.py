"""Bounded in-process keyset cursor for the existing News photo-health job.

This cursor is work selection only: losing it on a restart cannot publish,
remove, rewrite or redateline an article. Existing newest-first ingestion
checks stay unchanged. Database sessions remain with the single News owner.
"""
from __future__ import annotations

_CURSORS: dict[str, int | None] = {}


def next_image_health_rows(query, *, limit: int, football_only: bool, window: int):
    from models import Article, ArticleTaxonomyResolution
    maximum = max(1, min(int(limit), 160))
    # There are just two worker modes; never retain per-request or secret keys.
    scope = 'football' if football_only else 'all'
    if football_only:
        query = query.filter(ArticleTaxonomyResolution.resolved_sport == 'football')
    cursor = _CURSORS.get(scope)
    base = query.order_by(None)
    selected = base.filter(Article.id < cursor) if cursor is not None else base
    rows = selected.order_by(Article.id.desc()).limit(maximum).all()
    if not rows and cursor is not None:
        # Expired/held/deleted rows do not strand the sweep at its old boundary.
        rows = base.order_by(Article.id.desc()).limit(maximum).all()
    next_cursor = int(rows[-1][0].id) if len(rows) == maximum else None
    return rows, scope, next_cursor


def finish_image_health_rows(scope: str, cursor: int | None):
    """Advance only after the caller completed its existing checks/commit."""
    if scope not in {'all', 'football'}:
        raise ValueError('Unknown News image-health scope')
    _CURSORS[scope] = cursor
