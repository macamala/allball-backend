"""Share an existing News cycle allowance across waiting football leagues.

This does not increase a budget, authorise publication, weaken a validator or
request data. It only prevents repeated repair attempts from consuming a cycle
while another underfilled football competition already has a queued source.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path

_CATALOG = json.loads((Path(__file__).parent / 'news_football_leagues.json').read_text())
_TOPICS = {'football-international','football-women','football-youth','football-national-teams'}
_KNOWN = frozenset(row['league'] for row in _CATALOG) - _TOPICS
_YIELD_REPAIRS = ContextVar('news_football_yield_repairs', default=False)


def _count(value):
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0


def underfilled_football_pending(pending, inventory, current=None, *, floor=2):
    """Only existing queued competitions can establish a coverage debt.

    Caller removes the current item from pending first. Unknown menu hints and
    broad news topics do not invent a missing league or receive a quota.
    """
    return sorted(key for key, count in (pending or {}).items()
                  if key in _KNOWN and key != current and _count(count) > 0
                  and _count((inventory or {}).get(key)) < _count(floor))


@contextmanager
def football_breadth_scope(pending, inventory, current=None, *, enabled=False):
    token = _YIELD_REPAIRS.set(bool(enabled and underfilled_football_pending(pending, inventory, current)))
    try:
        yield
    finally:
        _YIELD_REPAIRS.reset(token)


def yield_football_repairs():
    return _YIELD_REPAIRS.get()
