"""Regression cases from article-bound native J.LEAGUE source text."""
import pytest
from bot.news_policy import numeric_tokens, original_draft_reason
from bot import news_fact_guard as guard

@pytest.mark.parametrize('text,expected',[
 ('全治12週間', {'12'}), ('鈴木は9月29日に負傷', {'9','29'}),
 ('第3、第4腰椎', {'3','4'}), ('2026/27シーズン', {'2026/27'}),
 ('２０２６／２７シーズン', {'2026/27'}), ('全治１２週間', {'12'}),
 ('2027年に昇格', {'2027'}), ('小学5年生', {'5'}),
 ('打率0.300を記録', {'0.300'}), ('勝率50%を記録', {'50%'}),
 ('勝率５０％を記録', {'50%'}), ('通算1,000試合', {'1,000'}),
 ('2-0で勝った', {'2-0'}), ('2–0で勝った', {'2–0'}),
 ('12:30に開始', {'12:30'}),
])
def test_literal_numbers_next_to_cjk_are_not_lost_or_split(text,expected):
    assert numeric_tokens(text)==expected
    assert expected <= numeric_tokens(text,include_spelled=True)

@pytest.mark.parametrize('text', ['J1リーグ','東京U23チーム','クラブFC123所属','甲A12','abc2026/27def','①年','第十二回'])
def test_identifiers_and_non_decimal_symbols_do_not_invent_numeric_evidence(text):
    # Historical ASCII behavior is kept; CJK handling must not introduce one.
    assert '2026/27' not in numeric_tokens(text)
    if text != 'abc2026/27def':
        assert not numeric_tokens(text)

@pytest.mark.parametrize('text', ['2026/27シーズン','２０２６／２７シーズン'])
def test_season_is_atomic_never_an_independent_2026_or_27_fact(text):
    assert not ({'2026','27'} & numeric_tokens(text,include_spelled=True))

def test_existing_western_numbers_money_and_spelled_equivalents_are_retained():
    assert numeric_tokens('Score 2-0, kick-off 18:45, £185m and 60%.')=={'2-0','18:45','185','60%'}
    assert {'12','60','60%'} <= numeric_tokens('Twelve players, with 60% participation.',include_spelled=True)

@pytest.mark.parametrize('source,output',[('2026/27シーズン','2027/28'),('全治12週間','13'),('第3、第4腰椎','5'),('打率0.300','300')])
def test_new_values_do_not_gain_admission(source,output):
    reason=original_draft_reason({'title':'An update on the football squad','summary':'The club confirmed the situation.','body':'The confirmed number is '+output+'.'},'Football club announcement',source)
    assert reason=='unsupported_number'

@pytest.mark.parametrize('source,token', [('柏エフォートFC','FC'),('ＵＥＦＡは','UEFA'),('FIFAによる発表','FIFA'),('ACLの試合','ACL')])
def test_exact_source_acronym_next_to_cjk_is_not_an_added_entity(monkeypatch,source,token):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    assert guard.fact_lock_reason({'title':'Football organisation update','body':token+' was mentioned.'},'Organisation report',source,expected_sport='football') is None

@pytest.mark.parametrize('source', ['柏レイソル', '柏エフォートFCX', 'prefixFCsuffix', '柏エフォートFＣX'])
def test_source_boundary_does_not_allow_invented_fc(monkeypatch,source):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:None)
    assert guard.fact_lock_reason({'title':'Football organisation update','body':'FC was mentioned.'},'Organisation report',source,expected_sport='football')=='unsupported_acronym:FC'

def test_competition_and_independent_semantic_checks_are_not_overridden(monkeypatch):
    monkeypatch.setattr(guard,'original_draft_reason',lambda *args:'copied_source_headline')
    assert guard.fact_lock_reason({'title':'FC announcement','body':'FC'},'Club update','柏エフォートFC',expected_sport='football')=='copied_source_headline'
