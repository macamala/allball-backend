from datetime import datetime, timezone
import sys
from types import SimpleNamespace

import pytest

from bot.news_budget import PostgresAiRequestBudget
import news_runtime


class BudgetState:
    def __init__(self):
        self.table = False
        self.attempts = {}


class BudgetCursor:
    def __init__(self, state):
        self.state = state
        self.row = None

    def execute(self, sql, params=None):
        normalized = " ".join(str(sql).split()).lower()
        if "set local" in normalized:
            self.row = None
        elif "to_regclass" in normalized:
            self.row = ("news_ai_requests",) if self.state.table else (None,)
        elif normalized.startswith("select attempts from news_ai_requests"):
            self.row = (
                (self.state.attempts.get(params[0]),)
                if params[0] in self.state.attempts else None
            )
        elif normalized.startswith("create table if not exists news_ai_requests"):
            self.state.table = True
            self.row = None
        elif normalized.startswith("insert into news_ai_requests"):
            day, limit = params
            current = self.state.attempts.get(day, 0)
            if current >= limit:
                self.row = None
            else:
                current += 1
                self.state.attempts[day] = current
                self.row = (current,)
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")

    def fetchone(self):
        return self.row

    def close(self):
        pass


class BudgetConnection:
    def __init__(self, state):
        self.state = state
        self.autocommit = False

    def cursor(self):
        return BudgetCursor(self.state)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_postgres_budget_persists_daily_cap_across_instances():
    state = BudgetState()
    connect = lambda dsn: BudgetConnection(state)
    stamp = datetime(2026, 9, 27, 3, tzinfo=timezone.utc)
    first = PostgresAiRequestBudget(3, "postgresql://fixture/db", 3,
                                    clock=lambda: stamp, connect_fn=connect)
    second = PostgresAiRequestBudget(3, "postgresql://fixture/db", 3,
                                     clock=lambda: stamp, connect_fn=connect)
    assert first.can_start()
    assert first.reserve() and first.reserve()
    assert second.reserve()
    assert not second.reserve()
    assert second.blocked_reason == "daily_request_limit"
    assert not PostgresAiRequestBudget(
        2, "postgresql://fixture/db", 3, clock=lambda: stamp, connect_fn=connect
    ).can_start()


def test_postgres_accounting_config_needs_no_railway_volume_when_news_ai_is_enabled():
    env = {
        "DATABASE_URL": "postgresql://user:secret@db.example/ninko",
        "NEWS_ACCOUNTING_BACKEND": "postgres",
        "NEWS_MAX_AI_ARTICLES": "1",
        "NEWS_TRANSLATIONS_ENABLED": "0",
        "NEWS_TRANSLATIONS_PER_CYCLE": "0",
        "NEWS_HISTORICAL_REPAIR_ENABLED": "0",
        "NEWS_EXPANDED_FEEDS_ENABLED": "0",
        "NEWS_NEWSAPI_AI_ENABLED": "0",
        "NEWS_AI_MAX_REQUESTS_PER_RUN": "2",
        "NEWS_AI_MAX_REQUESTS_PER_DAY": "3",
        "NEWS_AI_PROVIDER_MODE": "xkiro_free",
        "XKIRO_API_KEY": "FIXTURE_ONLY",
    }
    assert news_runtime.configuration_errors(env) == []
    assert news_runtime.storage_errors(env) == []


def test_removed_data_news_flag_cannot_create_a_data_only_configuration():
    env = {
        "DATABASE_URL": "postgresql://user:secret@db.example/ninko",
        "NEWS_ACCOUNTING_BACKEND": "postgres",
        "NEWS_MAX_AI_ARTICLES": "0",
        "NEWS_DATA_NEWS_ENABLED": "1",
        "NEWS_TRANSLATIONS_ENABLED": "0",
        "NEWS_TRANSLATIONS_PER_CYCLE": "0",
        "NEWS_HISTORICAL_REPAIR_ENABLED": "0",
        "NEWS_EXPANDED_FEEDS_ENABLED": "0",
        "NEWS_NEWSAPI_AI_ENABLED": "0",
    }
    assert news_runtime.configuration_errors(env) == ["no_news_lane_enabled"]


class OwnerState:
    locked = False


class OwnerCursor:
    def __init__(self, state):
        self.state = state
        self.row = None

    def execute(self, sql, params=None):
        if "pg_try_advisory_lock" in sql:
            if self.state.locked:
                self.row = (False,)
            else:
                self.state.locked = True
                self.row = (True,)
        elif "pg_advisory_unlock" in sql:
            self.state.locked = False
            self.row = (True,)
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.row

    def close(self):
        pass


class OwnerConnection:
    def __init__(self, state):
        self.state = state
        self.autocommit = False

    def cursor(self):
        return OwnerCursor(self.state)

    def close(self):
        pass


def test_postgres_advisory_owner_blocks_second_cycle_and_releases(monkeypatch):
    state = OwnerState()
    state.locked = False
    fake = SimpleNamespace(connect=lambda *a, **kw: OwnerConnection(state))
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    monkeypatch.setenv("NEWS_ACCOUNTING_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@db.example/ninko")

    with news_runtime.news_owner():
        with pytest.raises(news_runtime.NewsOwnerUnavailable):
            with news_runtime.news_owner():
                pytest.fail("duplicate owner acquired")
    with news_runtime.news_owner():
        assert state.locked
    assert not state.locked
