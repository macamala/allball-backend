"""Offline integration checks. Fixture quotas are NOT production approvals.

A shared test file survives separate Python processes; this does not establish
that an unconfigured Railway service has persistent storage or a single owner.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from bot.news_budget import AiRequestBudget
from deploy.news.preflight import NEWS_SERVICE_ID, runtime_errors

RESERVE_SCRIPT = r'''
import json,sys
from datetime import datetime,timezone
from bot.news_budget import AiRequestBudget
budget=AiRequestBudget(int(sys.argv[2]),sys.argv[1],daily_limit=int(sys.argv[3]),
    clock=lambda:datetime(2026,9,26,12,tzinfo=timezone.utc))
decisions=[budget.reserve() for _ in range(int(sys.argv[4]))]
print(json.dumps({'decisions':decisions,'attempts':budget.attempts,'reason':budget.blocked_reason}),flush=True)
raise SystemExit(int(sys.argv[5]))
'''


def process_args(path, per_run, per_day, attempts, exit_code=0):
    return [sys.executable, '-c', RESERVE_SCRIPT, str(path), str(per_run),
            str(per_day), str(attempts), str(exit_code)]


def test_reservations_survive_process_exit_including_failed_work(tmp_path):
    path = tmp_path / 'persisted-test-ledger.sqlite'
    first = subprocess.run(process_args(path, 2, 3, 2, 23), text=True,
                           capture_output=True, timeout=20)
    assert first.returncode == 23
    assert json.loads(first.stdout)['decisions'] == [True, True]
    second = subprocess.run(process_args(path, 2, 3, 2), text=True,
                            capture_output=True, timeout=20, check=True)
    result = json.loads(second.stdout)
    assert result == {'decisions': [True, False], 'attempts': 1,
                      'reason': 'daily_request_limit'}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT day,attempts FROM news_ai_requests').fetchall() == [('2026-09-26', 3)]


def test_separate_processes_cannot_exceed_same_ledger_daily_cap(tmp_path):
    path = tmp_path / 'shared-test-ledger.sqlite'
    children = [subprocess.Popen(process_args(path, 2, 3, 2), text=True,
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(6)]
    outputs = []
    try:
        for child in children:
            out, err = child.communicate(timeout=25)
            assert child.returncode == 0, err
            outputs.append(json.loads(out))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill(); child.wait(timeout=5)
    assert sum(item['attempts'] for item in outputs) == 3
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT SUM(attempts) FROM news_ai_requests').fetchone()[0] == 3


def test_corrupt_ledger_is_not_silently_reset(tmp_path):
    path = tmp_path / 'broken.sqlite'
    original = b'not a sqlite ledger; must be held for operator review'
    path.write_bytes(original)
    budget = AiRequestBudget(2, str(path), daily_limit=3)
    assert not budget.can_start()
    assert not budget.reserve() and budget.attempts == 0
    assert budget.blocked_reason == 'ledger_unavailable'
    assert path.read_bytes() == original


@pytest.mark.parametrize('flag', [None, '0', 'false', 'off', 'invalid'])
def test_disabled_historical_scans_never_open_database(monkeypatch, flag):
    import database
    import repair_content
    if flag is None:
        monkeypatch.delenv('NEWS_HISTORICAL_REPAIR_ENABLED', raising=False)
    else:
        monkeypatch.setenv('NEWS_HISTORICAL_REPAIR_ENABLED', flag)
    monkeypatch.setattr(database, 'SessionLocal', lambda: pytest.fail('historical DB opened'))
    for function in (repair_content.repair_summary_only, repair_content.repair_contaminated):
        result = function()
        assert result['disabled'] and result['scanned'] == 0


def test_news03_flags_do_not_bypass_existing_news02_start_guard(tmp_path):
    env = {'NEWS_WORKER_ENABLED': '1', 'RAILWAY_SERVICE_ID': NEWS_SERVICE_ID,
           'WORKER_DISABLED': '0', 'RESULTS_COLLECTION_ENABLED': '0',
           'RESULTS_SCHEDULER_ENABLED': '0', 'RESULTS_WRITE_ENABLED': '0',
           'DATABASE_URL': 'postgresql://fixture.invalid/test',
           'NEWS_FETCH_INTERVAL_MINUTES': '10', 'NEWS_MAX_AI_ARTICLES': '2',
           'NEWS_AI_LEDGER_PATH': str(tmp_path / 'fixture.sqlite'),
           'NEWS_AI_MAX_REQUESTS_PER_RUN': '2', 'NEWS_AI_MAX_REQUESTS_PER_DAY': '3',
           'NEWS_EXPANDED_FEEDS_ENABLED': '0', 'NEWS_HISTORICAL_REPAIR_ENABLED': '0'}
    assert 'legacy_repair_cost_and_write_review_required' in runtime_errors(env)
    env['RAILWAY_SERVICE_ID'] = 'wrong-service'
    assert 'wrong_or_missing_news_service_identity' in runtime_errors(env)


@pytest.mark.parametrize('per_run,per_day', [(0, 3), (2, 0)])
def test_zero_approved_allowance_does_not_start_ingestion(monkeypatch, tmp_path, per_run, per_day):
    from bot import fetch_sources, rewrite_ai
    monkeypatch.setattr(rewrite_ai, 'OPENAI_API_KEY', 'fixture-not-a-real-key')
    monkeypatch.setenv('NEWS_AI_LEDGER_PATH', str(tmp_path / 'budget.sqlite'))
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_RUN', str(per_run))
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_DAY', str(per_day))
    monkeypatch.setattr(fetch_sources, '_fetch_and_store_all_articles',
                        lambda *a, **kw: pytest.fail('ingestion began'))
    assert fetch_sources.fetch_and_store_all_articles(max_ai_articles=2) == 0
    assert not (tmp_path / 'budget.sqlite').exists()
