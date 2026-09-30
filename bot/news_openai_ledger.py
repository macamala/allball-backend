"""News-only, durable and serialized OpenAI reservations and usage accounting.

Reserve the worst-case price BEFORE network I/O. Ambiguous requests retain their
reservation permanently; restarts never make them free or eligible for replay.
No live-score tables, settings or models are imported or changed here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock

from sqlalchemy import (Column, Date, DateTime, Integer, MetaData, Numeric, String,
                        Table, Text, func, insert, select, update)

MONEY = Numeric(18, 9)
ZERO = Decimal('0')
metadata = MetaData()
gate = Table('news_openai_gate', metadata,
    Column('id', Integer, primary_key=True), Column('stop_reason', String(80)))
usage = Table('news_openai_usage', metadata,
    Column('request_key', String(64), primary_key=True),
    Column('source_key', String(64), nullable=False, index=True),
    Column('article_id', Integer, nullable=True, index=True),
    Column('model', String(100), nullable=False),
    Column('purpose', String(16), nullable=False),
    Column('language', String(12)), Column('phase', String(16), nullable=False),
    Column('created_at', DateTime, nullable=False),
    Column('day', Date, nullable=False, index=True),
    Column('month', Date, nullable=False, index=True),
    Column('reserved_usd', MONEY, nullable=False),
    Column('charged_usd', MONEY, nullable=False),
    Column('input_tokens', Integer), Column('cached_input_tokens', Integer),
    Column('cache_write_tokens', Integer), Column('output_tokens', Integer),
    Column('status', String(32), nullable=False), Column('response_text', Text),
    Column('quality_result', String(160)), Column('api_request_id', String(128)))


def utc_now():
    return datetime.now(timezone.utc)


class OpenAILedger:
    def __init__(self, engine, *, clock=utc_now):
        self.engine, self.clock = engine, clock
        self._ready = False
        self._schema_lock = Lock()

    def _ensure(self):
        if self._ready:
            return
        with self._schema_lock:
            if self._ready:
                return
            with self.engine.begin() as conn:
                if self.engine.dialect.name == 'postgresql':
                    from sqlalchemy import text
                    conn.execute(text('SELECT pg_advisory_xact_lock(730091530)'))
                metadata.create_all(conn)
                # An isolated singleton mutex, never an existing application row.
                if self.engine.dialect.name == 'postgresql':
                    from sqlalchemy.dialects.postgresql import insert as upsert
                else:
                    from sqlalchemy.dialects.sqlite import insert as upsert
                conn.execute(upsert(gate).values(id=1).on_conflict_do_nothing())
            self._ready = True

    @contextmanager
    def transaction(self):
        self._ensure()
        with self.engine.connect() as conn:
            try:
                if self.engine.dialect.name == 'sqlite':
                    conn.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    conn.begin()
                    conn.exec_driver_sql("SET LOCAL lock_timeout='3s'")
                    conn.exec_driver_sql("SET LOCAL statement_timeout='8s'")
                conn.execute(select(gate.c.id).where(gate.c.id == 1).with_for_update()).first()
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def reserve(self, *, request_key, source_key, article_id, model, purpose,
                language, phase, reserve_usd, daily, monthly, total, dry_limit=12):
        now = self.clock().astimezone(timezone.utc)
        day, month = now.date(), now.date().replace(day=1)
        with self.transaction() as conn:
            stop = conn.execute(select(gate.c.stop_reason).where(gate.c.id == 1)).scalar()
            if stop:
                return 'safety_stop:' + stop, None
            existing = conn.execute(select(usage).where(usage.c.request_key == request_key)).mappings().first()
            if existing and existing['status'] != 'cancelled':
                if existing['response_text'] and existing['status'] == 'success':
                    return 'cached', dict(existing)
                return 'already_attempted', dict(existing)
            sums = {}
            for period, condition in (('daily', usage.c.day == day),
                    ('monthly', usage.c.month == month), ('total', True)):
                sums[period] = Decimal(str(conn.execute(select(
                    func.coalesce(func.sum(usage.c.charged_usd), 0)
                ).where(condition)).scalar()))
            for period, cap in (('daily', daily), ('monthly', monthly), ('total', total)):
                if sums[period] + reserve_usd > cap:
                    return 'budget_exhausted:' + period, None
            if phase == 'dry_run':
                if purpose != 'write':
                    return 'dry_run_writes_only', None
                count = conn.execute(select(func.count()).select_from(usage).where(
                    usage.c.phase == 'dry_run', usage.c.purpose == 'write',
                    usage.c.status != 'cancelled')).scalar()
                if count >= dry_limit:
                    return 'dry_run_review_required', None
            row = dict(request_key=request_key, source_key=source_key,
                article_id=article_id, model=model, purpose=purpose, language=language,
                phase=phase, created_at=now.replace(tzinfo=None), day=day, month=month,
                reserved_usd=reserve_usd, charged_usd=reserve_usd, status='reserved')
            if existing:
                conn.execute(update(usage).where(usage.c.request_key == request_key).values(**row))
            else:
                conn.execute(insert(usage).values(**row))
            return 'reserved', row

    def finish(self, request_key, *, status, response_text=None, token_usage=None,
               cost=None, api_request_id=None):
        with self.transaction() as conn:
            row = conn.execute(select(usage).where(usage.c.request_key == request_key)).mappings().one()
            # Finalization is idempotent. No second response can lower a charge.
            if row['status'] != 'reserved':
                return
            values = dict(status=status, response_text=response_text,
                          api_request_id=(api_request_id or '')[:128] or None)
            if cost is not None:
                cost = Decimal(str(cost))
                if cost < 0:
                    raise ValueError('negative_usage_cost')
                values['charged_usd'] = cost
                if cost > row['reserved_usd']:
                    conn.execute(update(gate).where(gate.c.id == 1).values(stop_reason='cost_bound_exceeded'))
            if token_usage:
                values.update(token_usage)
            conn.execute(update(usage).where(usage.c.request_key == request_key).values(**values))

    def record_quality(self, request_key, reason):
        with self.transaction() as conn:
            conn.execute(update(usage).where(usage.c.request_key == request_key)
                         .values(quality_result=str(reason)[:160]))

    def bind_article(self, source_key, article_id):
        with self.transaction() as conn:
            conn.execute(update(usage).where(usage.c.source_key == source_key,
                         usage.c.article_id.is_(None)).values(article_id=article_id))

    def report(self):
        with self.transaction() as conn:
            rows = conn.execute(select(usage).order_by(usage.c.created_at)).mappings().all()
        # No source prose, request body, response body, key or connection string.
        return [{k: (str(v) if isinstance(v, Decimal) else v.isoformat()
                     if isinstance(v, (datetime, type(utc_now().date()))) else v)
                 for k,v in row.items() if k != 'response_text'} for row in rows]


_default = None


def ledger():
    global _default
    if _default is None:
        from news_runtime import accounting_backend, postgres_dsn
        import os
        if accounting_backend(os.environ) != 'postgres' or not postgres_dsn(os.environ):
            raise RuntimeError('durable_openai_ledger_required')
        from sqlalchemy import create_engine
        _default = OpenAILedger(create_engine(postgres_dsn(os.environ),
            pool_size=2, max_overflow=0, pool_pre_ping=True, pool_timeout=5,
            connect_args={'connect_timeout': 5, 'application_name': 'news-openai-budget'}))
    return _default
