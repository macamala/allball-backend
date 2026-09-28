from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bot import news_publication_clock as clock


@pytest.mark.parametrize('column,migrates', [('date', True), ('timestamp without time zone', False)])
def test_clock_migration_is_exactly_scoped_and_idempotent(monkeypatch, column, migrates):
    monkeypatch.setattr(clock, '_READY', False)
    db = Mock()
    db.get_bind.return_value.dialect.name = 'postgresql'
    db.execute.return_value.scalar.return_value = column
    clock.ensure_news_publication_clock(db)
    commands = [str(call.args[0]) for call in db.execute.call_args_list]
    alters = [sql for sql in commands if sql.startswith('ALTER TABLE')]
    assert len(alters) == int(migrates)
    if migrates:
        assert alters == ['ALTER TABLE articles ALTER COLUMN published_at TYPE timestamp without time zone USING published_at::timestamp without time zone']
        assert "SET LOCAL lock_timeout = '1s'" in commands
        assert "SET LOCAL statement_timeout = '8s'" in commands
    clock.ensure_news_publication_clock(db)
    assert db.execute.call_count == len(commands)


def test_clock_lock_failure_rolls_back_and_never_allows_lossy_writes(monkeypatch):
    monkeypatch.setattr(clock, '_READY', False)
    db = Mock()
    db.get_bind.return_value.dialect.name = 'postgresql'
    def execute(sql):
        if str(sql).startswith('ALTER TABLE'):
            raise RuntimeError('sensitive connection detail')
        return SimpleNamespace(scalar=lambda: 'date')
    db.execute.side_effect = execute
    with pytest.raises(RuntimeError, match='^news_publication_clock_migration_unavailable$'):
        clock.ensure_news_publication_clock(db)
    assert not clock._READY
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_restore_only_same_source_same_date_with_explicit_publication_evidence():
    from database import SessionLocal
    from models import Article
    from public_index import recent_public_sport_inventory
    db = SessionLocal()
    now = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)
    midnight = datetime(2026, 9, 27)
    rows = []
    for i in range(5):
        row = Article(title='Original News', slug=f'clock-{i}', ai_generated=True,
            source_url=f'https://example.test/story-{i}', published_at=midnight)
        db.add(row); rows.append(row)
    rows[4].source_url = 'https://ninkosports.com/live-scores/match'
    db.commit()
    candidates = [dict(url=row.source_url, published_at=datetime(2026,9,27,22,tzinfo=timezone.utc),
                       _publication_evidence='rss-published') for row in rows]
    candidates[1]['_publication_evidence'] = 'updated'
    candidates[2]['published_at'] = datetime(2026,9,28,8,tzinfo=timezone.utc)
    candidates[3]['published_at'] = datetime(2026,9,27,22)  # timezone unknown
    try:
        assert clock.repair_verified_source_times(db, candidates, now=now) == 1
        assert rows[0].published_at == datetime(2026,9,27,22)
        assert all(row.published_at == midnight for row in rows[1:])
        assert clock.repair_verified_source_times(db, candidates, now=now) == 0
    finally:
        db.close()
