from pathlib import Path
import subprocess
subprocess.run(['git','merge-base','--is-ancestor','8594e96b0dd41fc3649c1e0509230517fa2415b0','HEAD'],check=True)
p=Path('collector/provider.py');s=p.read_text();start=s.index('def _dedupe_public_fixture_rows(');end=s.index('\ndef public_event_detail',start)
part=s[start:end];old='    for row in events:\n';assert old in part
part=part.replace(old,'''    # Equal-kickoff SQL rows have no implicit order. A stable input order keeps
    # the existing score/verified-competition precedence independent of query
    # plan, sport filter, cache miss or arrival order. Never mutate input rows.
    ordered = sorted(events, key=lambda r: (str(r.get("start_time") or ""),
                     str(r.get("sport") or ""), str(r.get("id") or "")))
    for row in ordered:
''',1)
s=s[:start]+part+s[end:]
s=s.replace('query.order_by(SportsEvent.start_time.desc())','query.order_by(SportsEvent.start_time.desc(), SportsEvent.event_id.desc())')
s=s.replace('query.order_by(SportsEvent.start_time.asc())','query.order_by(SportsEvent.start_time.asc(), SportsEvent.event_id.asc())')
p.write_text(s)
p=Path('collector/cache.py');s=p.read_text();assert 'LIST_CACHE_VERSION = "p0v31"' in s;p.write_text(s.replace('LIST_CACHE_VERSION = "p0v31"','LIST_CACHE_VERSION = "p0v32"',1))
Path('tests/test_public_fixture_stability.py').write_text('''"""The same physical fixture must keep the same public representative."""
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
''')
p=Path('audit/football_test_selection.txt');s=p.read_text();assert 'tests/test_public_fixture_stability.py' not in s;p.write_text(s.rstrip()+'\ntests/test_public_fixture_stability.py\n')
