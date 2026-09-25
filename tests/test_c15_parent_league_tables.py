"""Seasonal football source IDs require a current-season fixture witness."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from collector.football_table_identity import scoped_table
from collector.standings_enrich import _fetch_fotmob_dynamic_standings
from collector.util import dump_json, load_json
from tests.test_c15_live_tables import db, add_case


def single_case(db):
    cid, row, native, root = add_case(db)
    # Same pattern as the observed League One 938219 -> 108 response.
    root['details']['name'] = 'Test League'
    root['table'] = [{'data': {'leagueId': 900, 'leagueName': 'Test League',
                              'table': {'all': root['table'][0]['data']['tables'][0]['table']['all']}}}]
    root['fixtures'] = {'allMatches': [{'id': '101', 'home': {'id':'1'}, 'away':{'id':'2'},
        'status': {'utcTime': row.start_time.isoformat()}}]}
    return cid, row, native, root


def test_exact_seasonal_match_authorizes_single_stable_parent_table(db):
    cid, row, native, root = single_case(db)
    before=(row.extra_json,row.participants_json,row.score_json,row.fingerprint,row.competition_id,row.display_eligible)
    calls=[]
    def get(url):
        calls.append(url)
        return SimpleNamespace(ok=True,payload=native if 'matchDetails' in url else root)
    fetched=_fetch_fotmob_dynamic_standings(db,cid,getter=get)
    assert [r['team'] for r in fetched['rows']] == ['Alpha','Beta']
    assert fetched['season']=='2026' and fetched['source_leaf_id']=='9001'
    assert len(calls)==2
    assert (row.extra_json,row.participants_json,row.score_json,row.fingerprint,row.competition_id,row.display_eligible)==before


def test_stored_native_parent_still_requires_fixture_in_the_returned_season(db):
    cid,row,native,root=single_case(db)
    meta=load_json(row.extra_json);meta.update(source_group_id='9001',source_parent_competition_id='900');row.extra_json=dump_json(meta);db.commit()
    calls=[]
    def get(url):calls.append(url);return SimpleNamespace(ok=True,payload=root)
    assert len(_fetch_fotmob_dynamic_standings(db,cid,getter=get)['rows'])==2
    assert len(calls)==1
    root['fixtures']['allMatches']=[]
    assert _fetch_fotmob_dynamic_standings(db,cid,getter=get)=={}


@pytest.mark.parametrize('wrong',['no-season','missing-fixture','wrong-match','duplicate-match','reversed-teams','wrong-team','wrong-time','unknown-time','missing-member','wrong-parent','multiple-tables','composite','nested-groups','invalid-table','no-context-witness'])
def test_parent_fallback_never_borrows_an_unproven_group_or_old_season(db,wrong):
    cid,row,native,root=single_case(db)
    context={'parent_id':'900','leaf_id':'9001','teams':['1','2'],'match_id':'101','start_time':row.start_time.isoformat()}
    fixture=root['fixtures']['allMatches'][0]
    if wrong=='no-season':root['details'].pop('selectedSeason')
    if wrong=='missing-fixture':root['fixtures']['allMatches']=[]
    if wrong=='wrong-match':fixture['id']='999'
    if wrong=='duplicate-match':root['fixtures']['allMatches'].append(deepcopy(fixture))
    if wrong=='reversed-teams':fixture['home'],fixture['away']=fixture['away'],fixture['home']
    if wrong=='wrong-team':fixture['away']['id']='9'
    if wrong=='wrong-time':fixture['status']['utcTime']=(row.start_time-timedelta(days=365)).isoformat()
    if wrong=='unknown-time':fixture['status']['utcTime']=None
    if wrong=='missing-member':root['table'][0]['data']['table']['all'].pop()
    if wrong=='wrong-parent':root['details']['id']=999
    if wrong=='multiple-tables':root['table'].append(deepcopy(root['table'][0]))
    if wrong=='composite':root['table'][0]['data']['composite']=True
    if wrong=='nested-groups':root['table'][0]['data']['tables']=[{'leagueId':999}]
    if wrong=='invalid-table':root['table'][0]['data']['table']={'all':None}
    if wrong=='no-context-witness':context.pop('match_id')
    assert scoped_table(root,context) is None
