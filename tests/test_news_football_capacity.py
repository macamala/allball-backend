from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from bot.news_football_capacity import underfilled_football_pending, football_breadth_scope, yield_football_repairs

EPL='england-premier-league'
OTHER='sweden-allsvenskan'


def test_only_a_real_waiting_other_competition_establishes_debt():
    pending={EPL:3,OTHER:1,'football-women':12,'football-international':40,'invented-league':100,'italy-serie-b':0}
    assert underfilled_football_pending(pending,{},EPL)==[OTHER]
    assert underfilled_football_pending(pending,{OTHER:2},EPL)==[]
    assert underfilled_football_pending({EPL:3},{},EPL)==[]
    assert underfilled_football_pending({}, {})==[]


def test_completed_or_exhausted_leagues_stop_reserving_repair_attempts():
    pending=Counter({EPL:2,OTHER:1})
    inventory={EPL:0,OTHER:1}
    with football_breadth_scope(pending,inventory,EPL,enabled=True):
        assert yield_football_repairs()
    inventory[OTHER]+=1
    with football_breadth_scope(pending,inventory,EPL,enabled=True):
        assert not yield_football_repairs()
    pending[OTHER]-=1
    with football_breadth_scope(pending,{},EPL,enabled=True):
        assert not yield_football_repairs()


def test_nonfootball_cycle_and_unknown_topics_do_not_change_existing_behavior():
    with football_breadth_scope({OTHER:5},{},EPL):
        assert not yield_football_repairs()
    with football_breadth_scope({'football-international':5,'football-women':4},{},EPL,enabled=True):
        assert not yield_football_repairs()


def test_context_is_restored_after_failure_and_nested_scope():
    assert not yield_football_repairs()
    with pytest.raises(RuntimeError):
        with football_breadth_scope({OTHER:1},{},EPL,enabled=True):
            assert yield_football_repairs()
            with football_breadth_scope({}, {}, enabled=False):
                assert not yield_football_repairs()
            assert yield_football_repairs()
            raise RuntimeError('simulated source failure')
    assert not yield_football_repairs()


def test_forced_repair_yields_to_another_empty_league_without_altering_request_limits(monkeypatch):
    from bot import fetch_sources as fetch
    budget=SimpleNamespace(max_requests=16,attempts=3,blocked_reason=None)
    monkeypatch.setattr(fetch,'active_ai_budget',lambda:budget)
    monkeypatch.delenv('NEWS_TRANSLATIONS_ENABLED',raising=False)
    assert fetch._correction_retry_allowed(force=True)
    with football_breadth_scope({OTHER:1},{},EPL,enabled=True):
        assert not fetch._correction_retry_allowed(force=True)
        assert not fetch._correction_retry_allowed(prefer_breadth=True)
    assert fetch._correction_retry_allowed(force=True)
    assert budget.max_requests==16 and budget.attempts==3


@pytest.mark.parametrize('other_waiting,expected_attempts',[(True,1),(False,2)])
def test_repeated_free_length_repair_waits_for_other_leagues_but_short_copy_stays_rejected(monkeypatch,other_waiting,expected_attempts):
    from bot import fetch_sources as fetch
    from bot import free_ai_router
    writer=Mock(return_value='Short football draft')
    monkeypatch.setattr(fetch,'write_ninkosports_story',writer)
    monkeypatch.setattr(fetch,'parse_ai_output',lambda raw:{'title':'Football news','summary':'Brief summary','body':'Too brief a draft.'})
    monkeypatch.setattr(fetch,'is_dramatic_shortening',lambda *args:True)
    monkeypatch.setattr(fetch,'competition_in_source',lambda *args:False)
    monkeypatch.setattr(free_ai_router,'last_writer_identity',lambda:('gemini','test'))
    validator=Mock(side_effect=AssertionError('Rejected short copy cannot reach publication validation'))
    monkeypatch.setattr(fetch,'validate_story_facts',validator)
    with football_breadth_scope({OTHER:1},{},EPL,enabled=other_waiting):
        result=fetch._ai_story_attempt('Confirmed football news','A substantial source. '*200,'football',EPL,6000)
    assert result==(None,'too-short')
    assert writer.call_count==expected_attempts
    validator.assert_not_called()


def test_writer_instructions_distinguish_body_from_title_and_summary(monkeypatch):
    from bot import rewrite_ai as writer
    calls=[]
    monkeypatch.setattr(writer,'openai_rate_limited',lambda:False)
    monkeypatch.setattr(writer,'_call_selected_ai',lambda prompt,**kwargs:calls.append(prompt) or None)
    writer.write_ninkosports_story('Football update','The coach confirmed the training schedule. '*40,sport='football')
    assert len(calls)==1
    assert 'EXCLUDING the headline and summary' in calls[0]
    assert 'Do not add facts or padding' in calls[0]
    assert 'VERIFIED SOURCE FACTS' in calls[0]


def test_main_pipeline_wraps_ingestion_without_adding_another_writer_or_data_fetch():
    import ast,inspect
    from bot import fetch_sources as fetch
    tree=ast.parse(inspect.getsource(fetch._fetch_and_store_all_articles))
    wrapped=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.With):continue
        for item in node.items:
            expression=item.context_expr
            if isinstance(expression,ast.Call) and isinstance(expression.func,ast.Name) and expression.func.id=='football_breadth_scope':
                wrapped.extend(child for child in ast.walk(node) if isinstance(child,ast.Call) and isinstance(child.func,ast.Name) and child.func.id=='_ingest_item')
    assert len(wrapped)==1
