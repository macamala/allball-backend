from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from bot.news_football_capacity import football_breadth_scope,reserve_paid_for_waiting_football
from bot import news_openai as lane,news_budget

EPL='england-premier-league';OTHER='sweden-allsvenskan'

@pytest.fixture
def setup_lane(monkeypatch):
    cfg={'phase':'production','cycle_limit':2}
    budget=SimpleNamespace(max_requests=16,attempts=6,openai_attempts=1,blocked_reason=None)
    monkeypatch.setattr(lane,'settings',lambda:cfg)
    monkeypatch.setattr(lane,'available',lambda:True)
    monkeypatch.setattr(news_budget,'active_ai_budget',lambda:budget)
    monkeypatch.setattr(news_budget,'ai_budget_exhausted',lambda:False)
    return cfg,budget


def test_one_slot_is_retained_for_an_actual_waiting_underfilled_league(setup_lane):
    cfg,budget=setup_lane
    with lane.source_context({'url':'https://source.example/report'}) as context:
        context.update(verified=True,priority=1)
        assert lane.prefer_paid()
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=True):
            assert reserve_paid_for_waiting_football()
            assert not lane.prefer_paid()
            with lane.force_paid():
                assert not lane.prefer_paid(quality_retry=True)
                assert lane.complete('system','prompt') is None
                assert lane.status()=='reserved_for_waiting_football'
        assert lane.prefer_paid()
    assert (budget.max_requests,budget.attempts,budget.openai_attempts,cfg['cycle_limit'])==(16,6,1,2)


def test_first_existing_paid_opportunity_and_zvezda_priority_are_retained(setup_lane):
    cfg,budget=setup_lane
    with lane.source_context({'url':'https://source.example/report'}) as context:
        context.update(verified=True,priority=1)
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=True):
            budget.openai_attempts=0
            assert lane.prefer_paid()
            budget.openai_attempts=1;context['priority']=2
            assert lane.prefer_paid()

@pytest.mark.parametrize('current,inventory,pending',[
    (OTHER,{EPL:5,OTHER:0},{EPL:1}),
    (EPL,{EPL:0},{OTHER:1}),
    (EPL,{EPL:5},{OTHER:0}),
    (EPL,{EPL:5,OTHER:2},{OTHER:1}),
    (EPL,{EPL:5},{'invented-league':1}),
    (EPL,{EPL:5},{'football-international':1}),
])
def test_underfilled_current_leagues_or_no_real_debt_do_not_wait(setup_lane,current,inventory,pending):
    with lane.source_context({'url':'https://source.example/report'}) as context:
        context.update(verified=True,priority=1)
        with football_breadth_scope(pending,inventory,current,enabled=True):
            assert lane.prefer_paid()


def test_nonfootball_and_review_modes_keep_prior_behavior(setup_lane):
    cfg,budget=setup_lane
    with lane.source_context({'url':'https://source.example/report'}) as context:
        context.update(verified=True,priority=1)
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=False):assert lane.prefer_paid()
        cfg['phase']='dry_run'
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=True):assert lane.prefer_paid()


def test_nested_context_and_exceptions_cannot_leak_reservation():
    assert not reserve_paid_for_waiting_football()
    with pytest.raises(RuntimeError):
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=True):
            assert reserve_paid_for_waiting_football()
            with football_breadth_scope({}, {}, enabled=False):assert not reserve_paid_for_waiting_football()
            assert reserve_paid_for_waiting_football()
            raise RuntimeError('simulated source exception')
    assert not reserve_paid_for_waiting_football()


def test_existing_request_exhaustion_remains_authoritative(setup_lane):
    cfg,budget=setup_lane;budget.openai_attempts=2
    with lane.source_context({'url':'https://source.example/report'}) as context:
        context.update(verified=True,priority=1)
        with football_breadth_scope({OTHER:1},{EPL:5},EPL,enabled=True):
            assert lane.complete('system','prompt') is None
            assert lane.status()=='cycle_allowance_exhausted'
    assert budget.openai_attempts==2
