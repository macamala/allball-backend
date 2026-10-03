from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from copy import deepcopy
import pytest
from bot.news_football_priority import spread_football_leagues
from bot.news_policy import fair_news_queue

EPL='england-premier-league'
J1='japan-j1-league'

def row(id,league=EPL,tier=1):
    return {'id':id,'league':league,'tier':tier}

def spread(rows,inventory,enabled=False):
    return spread_football_leagues(rows,inventory,section=lambda item:item['league'],
        priority=lambda item:item['tier'],coverage_first=enabled)


def test_empty_other_has_first_opportunity_without_extra_slots_or_displacing_zvezda():
    items=[row('zvezda','serbia-superliga',2),*[row(str(i)) for i in range(9)],row('j1',J1,0),row('j2','japan-j2-league',0)]
    original=deepcopy(items)
    output=spread(items,{EPL:5},True)
    assert output[0]['id']=='zvezda' and output[1]['id']=='j1'
    assert [a['tier'] for a in output[1:5]]==[0,1,1,1]
    assert [a['tier'] for a in output[5:9]]==[0,1,1,1]
    assert sorted(a['id'] for a in output)==sorted(a['id'] for a in items)
    assert items==original

@pytest.mark.parametrize('inventory',[{}, {EPL:0},{EPL:1}])
def test_unfilled_main_league_keeps_first_three_slots(inventory):
    items=[*[row(str(i)) for i in range(4)],row('j1',J1,0)]
    assert [a['tier'] for a in spread(items,inventory,True)[:4]]==[1,1,1,0]

@pytest.mark.parametrize('other',[None,'made-up-league','football-international','football-women','football-youth','football-national-teams'])
def test_unknown_or_broad_topic_never_gets_a_fake_empty_league_slot(other):
    items=[*[row(str(i)) for i in range(4)],row('other',other,0)]
    assert [a['tier'] for a in spread(items,{EPL:5},True)[:4]]==[1,1,1,0]


def test_a_populated_other_league_uses_the_regular_order():
    items=[*[row(str(i)) for i in range(4)],row('j1',J1,0)]
    assert [a['tier'] for a in spread(items,{EPL:5,J1:1},True)[:4]]==[1,1,1,0]


def test_default_order_and_single_lane_behavior_are_unchanged():
    items=[*[row(str(i)) for i in range(4)],row('j1',J1,0)]
    assert [a['tier'] for a in spread(items,{EPL:5})[:4]]==[1,1,1,0]
    assert spread([],{},True)==[]
    assert spread([row('one',J1,0)],{},True)==[row('one',J1,0)]
    assert spread([row('one')],{},True)==[row('one')]

@pytest.mark.parametrize('minute,first',[(0,EPL),(10,J1),(20,EPL),(30,EPL),(40,J1),(50,EPL)])
def test_normal_news_cycle_has_only_one_protected_opportunity_per_three_cycles(minute,first):
    now=datetime(2026,10,3,3,minute,tzinfo=timezone.utc)
    items=[{'url':f'https://publisher.example/{i}','title':'Premier League football club confirms appointment',
        'league':EPL,'published_at':now-timedelta(minutes=30),'summary':''} for i in range(4)]
    items.append({'url':'https://publisher.example/japan','title':'J1 League football club confirms appointment',
        'league':J1,'published_at':now-timedelta(minutes=30),'summary':''})
    original=deepcopy(items)
    queue,rejected=fair_news_queue(items,lambda item:SimpleNamespace(sport='football',league=item['league']),
        now=now,football_inventory={EPL:5},max_age_hours=24)
    assert queue[0]['league']==first and len(queue)==5
    assert not rejected and items==original


def test_stale_or_nonarticle_supply_cannot_create_opportunity():
    now=datetime(2026,10,3,3,10,tzinfo=timezone.utc)
    base={'url':'https://publisher.example/one','title':'Premier League football club confirms appointment','league':EPL,'summary':'','published_at':now-timedelta(minutes=30)}
    items=[base,dict(base,url='https://publisher.example/old',league=J1,title='J1 League club confirms appointment',published_at=now-timedelta(days=2))]
    queue,rejected=fair_news_queue(items,lambda item:SimpleNamespace(sport='football',league=item['league']),now=now,football_inventory={EPL:5},max_age_hours=24)
    assert queue==[base] and rejected['stale_publication']==1
