from datetime import datetime, timezone

import pytest

from bot import news_source_holds as holds


@pytest.mark.parametrize('reason', sorted(holds._EDITORIAL_RETRY_REASONS))
def test_failed_editorial_correction_waits_one_hour_in_memory(monkeypatch, reason):
    monkeypatch.setattr(holds, '_MEMORY', {})
    monkeypatch.setattr(holds, '_postgres_dsn', lambda: None)
    clock = [1000.0]
    monkeypatch.setattr(holds.time, 'monotonic', lambda: clock[0])
    url = 'https://example.test/verified-news'
    assert not holds._retryable_reason(reason)
    holds.hold_source(url, reason)
    for elapsed in (600, 1800, 3599):
        clock[0] = 1000.0 + elapsed
        assert holds.source_on_cooldown(url)
        assert holds.held_source_urls([url]) == {url}
    clock[0] = 4601.0
    assert not holds.source_on_cooldown(url)
    assert holds.held_source_urls([url]) == set()


def test_editorial_pause_persists_with_same_expiry_and_reason(monkeypatch):
    records = []
    class Cursor:
        def execute(self, sql, args=None):
            if sql.startswith('INSERT'): records.append(args)
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def commit(self): pass
        def close(self): pass
    monkeypatch.setattr(holds, '_postgres_dsn', lambda: 'test-only')
    monkeypatch.setattr(holds, '_connect', lambda dsn: Connection())
    monkeypatch.setattr(holds, '_ensure_schema', lambda cursor: None)
    before = datetime.now(timezone.utc)
    holds.hold_source('https://example.test/verified-news', 'direct_quote_requires_review')
    assert len(records) == 1
    _, expiry, reason = records[0]
    assert 3590 < (expiry - before).total_seconds() < 3610
    assert reason == 'direct_quote_requires_review'


def test_transport_and_unavailable_validator_remain_retryable():
    for reason in ('empty', 'validator-unavailable', 'validator-independent-unavailable'):
        assert holds._retryable_reason(reason)
    assert not holds._retryable_reason('missing-or-unreachable-publishable-image')


def test_audited_clock_retry_matches_only_one_url_old_numeric_reason(monkeypatch):
    statements=[]
    class Cursor:
        rowcount=1
        def execute(self,sql,args=None): statements.append((sql,args))
        def fetchall(self):return []
        def close(self):pass
    class Connection:
        def cursor(self):return Cursor()
        def commit(self):pass
        def close(self):pass
    monkeypatch.setattr(holds,'_postgres_dsn',lambda:'test-only')
    monkeypatch.setattr(holds,'_connect',lambda dsn:Connection())
    monkeypatch.setattr(holds,'_ensure_schema',lambda cursor:None)
    other='https://example.test/unrelated'
    assert holds.held_source_urls([other]) == set()
    assert not [s for s,a in statements if s.startswith('UPDATE')]
    statements.clear()
    assert holds.held_source_urls([holds._ZVEZDA_CLOCK_REPAIR_URL,other]) == set()
    updates=[(s,a) for s,a in statements if s.startswith('UPDATE')]
    assert len(updates)==2
    sql,args=updates[0]
    assert "reason='unsupported_number'" in sql and 'updated_at < %s::timestamptz' in sql
    assert args == (holds._fingerprint(holds._ZVEZDA_CLOCK_REPAIR_URL),'2026-09-30T01:02:00Z')
    sql,args=updates[1]
    assert "reason='unsupported_competition:uefa-conference-league'" in sql
    assert args == (holds._fingerprint(holds._ZVEZDA_CLOCK_REPAIR_URL),'2026-09-30T01:13:00Z')
