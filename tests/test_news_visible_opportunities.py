from collections import Counter
from copy import deepcopy
import inspect
import random
import pytest
from bot.news_football_priority import spread_football_leagues
from bot.news_policy import non_article_news_reason, fair_news_queue
MAJOR=['england-premier-league','spain-la-liga','italy-serie-a','germany-bundesliga','france-ligue-1']
OTHER=['usa-mls','sweden-allsvenskan','brazil-serie-b']
def arrange(rows,inventory,**kwargs):
    return spread_football_leagues(rows,inventory,section=lambda r:r['league'],priority=lambda r:r['tier'],**kwargs)
def story(league,n,tier=1):
    return {'league':league,'id':f'{league}-{n}','tier':tier,'title':f'Confirmed story {n}','url':f'https://news.example/{league}/{n}'}
def test_finite_writer_window_reaches_other_major_leagues_before_repeating_one():
    rows=[story(key,n) for key in MAJOR for n in range(5)]
    inventory={key:i*50 for i,key in enumerate(MAJOR)}
    before=arrange(rows,inventory)
    assert len({r['league'] for r in before[:5]})==1
    after=arrange(rows,inventory,distinct_first=True)
    assert {r['league'] for r in after[:5]}==set(MAJOR)
    assert Counter(r['id'] for r in after)==Counter(r['id'] for r in rows)
def test_zvezda_and_existing_major_other_weighted_slots_remain_intact():
    rows=[story('serbia-superliga',0,2)]+[story(key,n) for key in MAJOR for n in range(4)]+[story(key,n,0) for key in OTHER for n in range(4)]
    before=deepcopy(rows);result=arrange(rows,{},distinct_first=True)
    assert result[0]['league']=='serbia-superliga' and result[0]['tier']==2
    assert [r['tier'] for r in result[1:9]]==[1,1,1,0,1,1,1,0]
    assert rows==before
def test_unknown_subject_never_creates_a_first_slot_debt_ahead_of_known_leagues():
    rows=[story(None,0),story(MAJOR[0],0),story(MAJOR[1],0)]
    out=arrange(rows,{MAJOR[0]:99,MAJOR[1]:120},distinct_first=True)
    assert out[-1]['league'] is None and len(out)==3
def test_single_source_supply_is_not_removed_and_no_articles_are_invented():
    rows=[story(MAJOR[0],i) for i in range(5)]
    assert arrange(rows,{},distinct_first=True)==rows
    assert arrange([],{},distinct_first=True)==[]
@pytest.mark.parametrize('seed',range(12))
def test_schedule_is_stable_lossless_and_preserves_in_league_order(seed):
    rng=random.Random(seed);rows=[story(rng.choice(MAJOR+OTHER),i,rng.choice([0,1])) for i in range(80)]
    original=deepcopy(rows);out=arrange(rows,{key:rng.randint(0,200) for key in MAJOR+OTHER},distinct_first=True)
    assert Counter(r['id'] for r in out)==Counter(r['id'] for r in rows)
    for key in MAJOR+OTHER:
        for tier in [0,1]:
            assert [r['id'] for r in out if r['league']==key and r['tier']==tier]==[r['id'] for r in rows if r['league']==key and r['tier']==tier]
    assert rows==original
@pytest.mark.parametrize('title',['Albacete - Eibar en directo | Última hora de LALIGA Hypermotion en vivo hoy','Partido en directo: ultima hora en vivo'])
def test_explicit_live_ticker_is_rejected_before_writer(title):
    assert non_article_news_reason({'title':title})=='non_article_rolling_tracker'
@pytest.mark.parametrize('title',['El entrenador habló en directo sobre la lesión del delantero','Albacete confirma su nuevo entrenador','La liga confirma cambios de horario de última hora'])
def test_actual_reporting_remains_eligible(title):
    assert non_article_news_reason({'title':title}) is None
def test_new_cycle_order_is_only_enabled_with_the_existing_club_coverage_path():
    assert 'distinct_first=football_club_coverage is not None' in inspect.getsource(fair_news_queue)
