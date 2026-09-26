from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from bot.news_budget import AiRequestBudget, ai_budget_scope, reserve_ai_request, configured_budget

@pytest.mark.parametrize('bad', [-1,21,True,'4',None])
def test_invalid_request_caps(bad):
    with pytest.raises(ValueError): AiRequestBudget(bad)

@pytest.mark.parametrize('bad', [-1,201,True,'4',None])
def test_invalid_daily_caps(bad):
    with pytest.raises(ValueError): AiRequestBudget(2,daily_limit=bad)

def test_no_active_scope_never_spends(): assert reserve_ai_request() is False

def test_no_ledger_never_spends():
    budget=AiRequestBudget(2)
    assert not budget.reserve() and budget.attempts==0

def test_actual_reservations_stop_at_cycle_cap(tmp_path):
    budget=AiRequestBudget(2,tmp_path/'ledger.sqlite')
    with ai_budget_scope(budget): assert [reserve_ai_request() for _ in range(5)]==[True,True,False,False,False]
    assert budget.attempts==2

def test_failed_attempts_are_not_refunded_by_new_budget_instance(tmp_path):
    path=tmp_path/'ledger.sqlite'
    first=AiRequestBudget(2,path,daily_limit=2)
    assert first.reserve() and first.reserve()
    second=AiRequestBudget(2,path,daily_limit=2)
    assert not second.reserve() and second.blocked_reason=='daily_request_limit'

def test_nested_scope_cannot_reset_the_outer_cap(tmp_path):
    outer=AiRequestBudget(1,tmp_path/'ledger.sqlite'); inner=AiRequestBudget(20,tmp_path/'other.sqlite')
    with ai_budget_scope(outer):
        assert reserve_ai_request()
        with ai_budget_scope(inner): assert not reserve_ai_request()
    assert inner.attempts==0 and outer.attempts==1

def test_concurrent_budget_instances_share_atomic_daily_cap(tmp_path):
    path=tmp_path/'ledger.sqlite'
    with ThreadPoolExecutor(max_workers=4) as pool:
        decisions=list(pool.map(lambda _:AiRequestBudget(3,path,daily_limit=3).reserve(),range(12)))
    assert sum(decisions)==3

def test_daily_rollover_uses_utc(tmp_path):
    stamp=datetime(2026,9,26,23,59,tzinfo=timezone.utc)
    path=tmp_path/'ledger.sqlite'
    assert AiRequestBudget(1,path,1,clock=lambda:stamp).reserve()
    assert not AiRequestBudget(1,path,1,clock=lambda:stamp).reserve()
    assert AiRequestBudget(1,path,1,clock=lambda:stamp+timedelta(minutes=2)).reserve()

def test_invalid_config_fails_closed(monkeypatch):
    monkeypatch.setenv('NEWS_AI_MAX_REQUESTS_PER_RUN','banana')
    assert configured_budget(10).max_requests==0

def test_missing_directory_does_not_create_unapproved_storage(tmp_path):
    path=tmp_path/'missing'/'ledger.sqlite'
    assert not AiRequestBudget(1,path).reserve()
    assert not path.parent.exists()


def test_precheck_stops_daily_exhaustion_before_feeds(tmp_path):
    path=str(tmp_path/'cap.db')
    first=AiRequestBudget(2,path,daily_limit=1)
    assert first.can_start() and first.reserve()
    assert not AiRequestBudget(2,path,daily_limit=1).can_start()


def test_precheck_missing_or_invalid_ledger():
    assert not AiRequestBudget(2).can_start()
    assert not AiRequestBudget(2,'relative.db').can_start()
