from unittest.mock import Mock
import pytest
from bot import news_fact_guard as guard
from bot import rewrite_ai as writer

@pytest.mark.parametrize('source,sport,expected', [
    ('Concacaf and Conmebol confirmed the programme.','football',{'CONCACAF','CONMEBOL'}),
    ('Concacaf confirmed the programme.','basketball',set()),
    ('УЕФА и ФИФА потврдили.','football',{'UEFA','FIFA'}),
    ('柏エフォートFCから加入しました。','football',{'FC'}),
    ('Liga nacija football update.','football',set()),
    ('Premier League football update.','football',set()),
    ('Uefa confirmed the competition rules.','football',{'UEFA'}),
])
def test_contract_exposes_only_the_existing_literal_gate(source,sport,expected):
    assert guard.source_attested_acronyms(source,sport)==expected

@pytest.mark.parametrize('source,league,permitted,forbidden',[
    ('Liga nacija football report.','uefa-nations-league','NONE','UEFA'),
    ('Premier League football report.','england-premier-league','NONE','EPL'),
    ('Uefa confirmed a football decision.','uefa-champions-league','UEFA','FIFA'),
    ('柏エフォートFCから加入しました。','japan-j1-league','FC','JFA'),
])
def test_writer_metadata_is_not_permission_to_invent_an_acronym(monkeypatch,source,league,permitted,forbidden):
    call=Mock(return_value=None)
    monkeypatch.setattr(writer,'openai_rate_limited',lambda:False)
    monkeypatch.setattr(writer,'_call_selected_ai',call)
    writer.write_ninkosports_story('Football update',source,sport='football',league=league)
    prompt=call.call_args.args[0]
    contract=next(line for line in prompt.splitlines() if 'ALLOWED SOURCE ACRONYMS:' in line)
    assert permitted in contract and forbidden not in contract
    assert 'editorial routing metadata, not additional source facts' in prompt
    assert 'Never print format labels or all-capital section headings' in prompt
    assert source in prompt
    assert call.call_count==1 and call.call_args.kwargs['quality_retry'] is False

@pytest.mark.parametrize('token',['UEFA','CONTRACT','FIFA','JFA'])
def test_prompt_clarification_does_not_weaken_draft_validation(monkeypatch,token):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    draft={'title':'Football update','summary':'The committee confirmed its programme.','body':f'{token} confirmed the programme.'}
    assert guard.fact_lock_reason(draft,'Football update','A football committee confirmed the programme.',expected_sport='football')=='unsupported_acronym:'+token

@pytest.mark.parametrize('reason',['unsupported_number','copied_source_headline','direct_quote_requires_review'])
def test_all_prior_early_rejection_gates_remain(monkeypatch,reason):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:reason)
    assert guard.fact_lock_reason({'body':'UEFA football update.'},'UEFA football','UEFA confirmed it.',expected_sport='football')==reason
