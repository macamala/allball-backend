"""SQLAlchemy query counters for persistence profiling."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine

_counts: Counter = Counter()
_slow: list[Dict[str, Any]] = []
_attached = False


def reset_sql_profile() -> None:
    _counts.clear()
    _slow.clear()


def snapshot() -> Dict[str, Any]:
    return {
        "select": int(_counts["select"]),
        "insert": int(_counts["insert"]),
        "update": int(_counts["update"]),
        "delete": int(_counts["delete"]),
        "other": int(_counts["other"]),
        "statements": int(_counts["statements"]),
        "flushes": int(_counts["flushes"]),
        "commits": int(_counts["commits"]),
        "rollbacks": int(_counts["rollbacks"]),
        "slowest": sorted(_slow, key=lambda row: row["s"], reverse=True)[:8],
    }


def _kind(statement: str) -> str:
    head = (statement or "").lstrip().split(" ", 1)[0].upper()
    if head in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return head.lower()
    return "other"


def attach_sql_profile(engine: Engine) -> None:
    global _attached
    if _attached:
        return
    _attached = True

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        context._ninko_sql_t0 = __import__("time").perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        _counts["statements"] += 1
        kind = _kind(statement)
        _counts[kind] += 1
        started = getattr(context, "_ninko_sql_t0", None)
        if started is None:
            return
        elapsed = __import__("time").perf_counter() - started
        if elapsed >= 0.25:
            _slow.append({"s": round(elapsed, 4), "kind": kind, "sql": " ".join((statement or "").split())[:180]})

    @event.listens_for(engine, "commit")
    def _commit(conn):  # noqa: ANN001
        _counts["commits"] += 1

    @event.listens_for(engine, "rollback")
    def _rollback(conn):  # noqa: ANN001
        _counts["rollbacks"] += 1

    from sqlalchemy.orm import Session

    @event.listens_for(Session, "after_flush")
    def _flush(session, flush_context):  # noqa: ANN001
        _counts["flushes"] += 1
