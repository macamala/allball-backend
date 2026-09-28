"""Explicit actual-request budget. No money cap or account-wide guarantee.

Production may use the existing Postgres database for durable request accounting;
the original SQLite ledger remains as an offline/legacy backend. Reservations are
charged before HTTP and never refunded on timeout/rejection. Both backends fail
closed when accounting cannot be verified.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from threading import Lock

_ACTIVE = ContextVar('news_ai_budget', default=None)


class AiRequestBudget:
    def __init__(self, max_requests, ledger_path=None, daily_limit=40, clock=None):
        if type(max_requests) is not int or not 0 <= max_requests <= 20:
            raise ValueError('max_requests must be 0..20')
        if type(daily_limit) is not int or not 0 <= daily_limit <= 1440:
            raise ValueError('daily_limit must be 0..1440')
        self.max_requests = max_requests
        self.daily_limit = daily_limit
        self.ledger_path = ledger_path
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.attempts = 0
        self.blocked_reason = None
        self._lock = Lock()

    def can_start(self):
        """Cheap conservative precheck before fetching feeds; reserve is authority."""
        self.blocked_reason = None
        if not self.max_requests or not self.daily_limit:
            self.blocked_reason = 'allowance_disabled'
            return False
        if not self.ledger_path:
            self.blocked_reason = 'durable_ledger_required'
            return False
        path = Path(self.ledger_path)
        if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
            self.blocked_reason = 'invalid_ledger_path'
            return False
        if not path.exists():
            return True
        try:
            with sqlite3.connect(str(path), timeout=5) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_ai_requests'").fetchone()
                if not exists:
                    return True
                day = self.clock().astimezone(timezone.utc).date().isoformat()
                row = db.execute('SELECT attempts FROM news_ai_requests WHERE day=?', (day,)).fetchone()
                if row and int(row[0]) >= self.daily_limit:
                    self.blocked_reason = 'daily_request_limit'
                    return False
                return True
        except (sqlite3.Error, OSError, ValueError):
            self.blocked_reason = 'ledger_unavailable'
            return False

    def reserve(self):
        with self._lock:
            if self.attempts >= self.max_requests:
                self.blocked_reason = 'cycle_request_limit'; return False
            if not self.ledger_path:
                self.blocked_reason = 'durable_ledger_required'; return False
            path = Path(self.ledger_path)
            if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
                self.blocked_reason = 'invalid_ledger_path'; return False
            day = self.clock().astimezone(timezone.utc).date().isoformat()
            try:
                with sqlite3.connect(str(path), timeout=5) as db:
                    db.execute('CREATE TABLE IF NOT EXISTS news_ai_requests (day TEXT PRIMARY KEY, attempts INTEGER NOT NULL)')
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute('SELECT attempts FROM news_ai_requests WHERE day=?', (day,)).fetchone()
                    count = row[0] if row else 0
                    if count >= self.daily_limit:
                        self.blocked_reason = 'daily_request_limit'; return False
                    db.execute('INSERT INTO news_ai_requests(day,attempts) VALUES (?,1) ON CONFLICT(day) DO UPDATE SET attempts=attempts+1', (day,))
                    db.commit()
            except (sqlite3.Error, OSError, ValueError):
                self.blocked_reason = 'ledger_unavailable'; return False
            self.attempts += 1
            return True


class PostgresAiRequestBudget:
    def __init__(self, max_requests, dsn, daily_limit=40, clock=None, connect_fn=None):
        if type(max_requests) is not int or not 0 <= max_requests <= 20:
            raise ValueError('max_requests must be 0..20')
        if type(daily_limit) is not int or not 0 <= daily_limit <= 1440:
            raise ValueError('daily_limit must be 0..1440')
        self.max_requests = max_requests
        self.daily_limit = daily_limit
        self.dsn = dsn
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.connect_fn = connect_fn
        self.attempts = 0
        self.blocked_reason = None
        self._lock = Lock()

    def _connect(self):
        if self.connect_fn is not None:
            return self.connect_fn(self.dsn)
        import psycopg2
        return psycopg2.connect(
            self.dsn,
            connect_timeout=5,
            application_name='ninkosports-news-budget',
        )

    def can_start(self):
        self.blocked_reason = None
        if not self.max_requests or not self.daily_limit:
            self.blocked_reason = 'allowance_disabled'
            return False
        if not self.dsn:
            self.blocked_reason = 'durable_ledger_required'
            return False
        connection = cursor = None
        try:
            connection = self._connect()
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute("SELECT to_regclass('public.news_ai_requests')")
            exists = cursor.fetchone()
            if not exists or exists[0] is None:
                return True
            day = self.clock().astimezone(timezone.utc).date().isoformat()
            cursor.execute('SELECT attempts FROM news_ai_requests WHERE day=%s', (day,))
            row = cursor.fetchone()
            if row and int(row[0]) >= self.daily_limit:
                self.blocked_reason = 'daily_request_limit'
                return False
            return True
        except Exception:
            self.blocked_reason = 'ledger_unavailable'
            return False
        finally:
            if cursor is not None:
                try: cursor.close()
                except Exception: pass
            if connection is not None:
                try: connection.close()
                except Exception: pass

    def reserve(self):
        with self._lock:
            if self.attempts >= self.max_requests:
                self.blocked_reason = 'cycle_request_limit'
                return False
            if not self.dsn:
                self.blocked_reason = 'durable_ledger_required'
                return False
            connection = cursor = None
            try:
                connection = self._connect()
                cursor = connection.cursor()
                try:
                    cursor.execute("SET LOCAL lock_timeout = '3s'")
                    cursor.execute("SET LOCAL statement_timeout = '8s'")
                except Exception:
                    connection.rollback()
                    cursor.close()
                    cursor = connection.cursor()
                cursor.execute(
                    'CREATE TABLE IF NOT EXISTS news_ai_requests ('
                    'day DATE PRIMARY KEY, attempts INTEGER NOT NULL CHECK (attempts >= 0))'
                )
                day = self.clock().astimezone(timezone.utc).date().isoformat()
                cursor.execute(
                    'INSERT INTO news_ai_requests(day,attempts) VALUES (%s,1) '
                    'ON CONFLICT(day) DO UPDATE SET attempts=news_ai_requests.attempts+1 '
                    'WHERE news_ai_requests.attempts < %s RETURNING attempts',
                    (day, self.daily_limit),
                )
                row = cursor.fetchone()
                if row is None:
                    connection.rollback()
                    self.blocked_reason = 'daily_request_limit'
                    return False
                connection.commit()
            except Exception:
                if connection is not None:
                    try: connection.rollback()
                    except Exception: pass
                self.blocked_reason = 'ledger_unavailable'
                return False
            finally:
                if cursor is not None:
                    try: cursor.close()
                    except Exception: pass
                if connection is not None:
                    try: connection.close()
                    except Exception: pass
            self.attempts += 1
            return True


def configured_budget(max_articles):
    try:
        from news_runtime import accounting_backend, postgres_dsn, request_limits
        limits = request_limits(os.environ)
        if limits is None:
            return AiRequestBudget(0)
        requests, daily = limits
        backend = accounting_backend(os.environ)
        if backend == 'postgres':
            return PostgresAiRequestBudget(requests, postgres_dsn(os.environ), daily)
        if backend == 'file':
            return AiRequestBudget(requests, os.environ.get('NEWS_AI_LEDGER_PATH'), daily)
        return AiRequestBudget(0)
    except (TypeError, ValueError):
        return AiRequestBudget(0)


@contextmanager
def ai_budget_scope(budget):
    # Nested operations share the outer budget, not a fresh allowance.
    current = _ACTIVE.get()
    token = _ACTIVE.set(current if current is not None else budget)
    try: yield _ACTIVE.get()
    finally: _ACTIVE.reset(token)


def active_ai_budget():
    return _ACTIVE.get()


def reserve_ai_request():
    budget = _ACTIVE.get()
    return bool(budget is not None and budget.reserve())


def ai_budget_exhausted():
    budget = _ACTIVE.get()
    return budget is None or budget.attempts >= budget.max_requests or bool(budget.blocked_reason)
