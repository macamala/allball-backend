"""The same physical fixture must keep the same public representative."""
import copy
from itertools import permutations
import pytest
from collector.provider import _dedupe_public_fixture_rows

def event(eid, **updates):
    value={"id":eid,"sport":"football","start_time":"2026-09-25T23:10:00Z","competition_key":"colombia-primera-a","country_id":"co","home":{"name":"Chicó FC","id":"6255"},"away":{"name":"Deportivo Pasto","id":"4405"},"score":{"home":None,"away":None},"status":"scheduled"}
    value.update(updates);return value

@pytest.mark.parametrize("reverse",[False,True])
def test_same_scope_same_stable_representative(reverse):
    rows=[event("ninko-evt-48ee659f22a82cb68ef9"),event("ninko-evt-a65e5b0f697618a40473")]
    if reverse:rows.reverse()
    original=copy.deepcopy(rows)
    assert [r['id'] for r in _dedupe_public_fixture_rows(rows,{'colombia-primera-a'})]==['ninko-evt-48ee659f22a82cb68ef9']
    assert rows==original

@pytest.mark.parametrize("case",['known-score','preferred-league','country'])
def test_existing_precedence_is_preserved_for_every_permutation(case):
    left,right=event('a'),event('z')
    preferred={'colombia-primera-a'}
    if case=='known-score':right.update(status='finished',score={'home':1,'away':0})
    elif case=='preferred-league':left['competition_key']='football-col-primera-a'
    else:left.update(competition_key='football-unknown',country_id=None);right['competition_key']='football-other';preferred=set()
    for rows in permutations([left,right]):
        assert [r['id'] for r in _dedupe_public_fixture_rows(list(rows),preferred)]==['z']

def test_other_sports_and_different_fixtures_are_retained():
    rows=[event('b'),event('a'),event('hockey',sport='ice-hockey'),event('different-time',start_time='2026-09-26T23:10:00Z'),event('different-team',away={'name':'Other Club'})]
    expected={'a','hockey','different-time','different-team'}
    for ordered in permutations(rows):
        assert {r['id'] for r in _dedupe_public_fixture_rows(list(ordered),{'colombia-primera-a'})}==expected
