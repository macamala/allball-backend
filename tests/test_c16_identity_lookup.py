"""Full-season lookup is bounded without forgetting legacy/manual restrictions."""
import json
import pytest
from sqlalchemy import event
from collector.football_history import known_native_rows, public_history, parse_history
from collector.models import SportsEventObservation
from collector.util import dump_json
from tests.test_c16_competition_hub import db, add_row, history_root
from datetime import datetime


@pytest.mark.parametrize('meta',[
    {'source_event_ids': {'fotmob':'99'}},
    {'source_event_ids': {'fotmob':99}},
    {'source_event_ids': {'fotmob':'fotmob:99'}},
    {'source_event_ids': {'fotmob':'FOTMOB:99'}},
    {'source_event_ids': [{'fotmob':'99'}]},
    {'source_event_ids': ['fotmob:99']},
    {'source_family':'fotmob','source_event_id':'99'},
    {'source_family':'fotmob','source_event_id':99},
    {'source_family':'fotmob','source_event_id':'fotmob:99'},
])
def test_legacy_hidden_rows_are_still_found_without_observations(db, meta):
    row=add_row(db,eid='hidden',mid='99',key='other-league',display_eligible=False,
                extra_json=json.dumps(meta,indent='\t'))
    before=(row.extra_json,row.display_eligible,row.event_id,row.score_json)
    assert known_native_rows(db,['99'])['99']==[row]
    root=history_root();current=add_row(db,at=datetime.fromisoformat(root['general']['matchTimeUTCDate'].removesuffix('Z')))
    assert public_history(db,current,parse_history(root))==([], {})
    assert (row.extra_json,row.display_eligible,row.event_id,row.score_json)==before


def test_full_season_uses_two_queries_not_one_scan_per_eighty_matches(db):
    row=add_row(db,mid='1700')
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
    engine=db.get_bind();event.listen(engine,'before_cursor_execute',capture)
    try:
        result=known_native_rows(db,[str(n) for n in range(1000,1701)])
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert result=={'1700':[row]}
    assert len(queries)==2,queries
    assert 'replace(' not in queries[1].lower() and ' like ' not in queries[1].lower()


def test_prefilter_is_not_identity_and_does_not_confuse_numeric_prefixes(db):
    add_row(db,eid='other-family',extra_json=dump_json({'source_event_ids':{'sofascore':'99'},'source_event_id':'99','source_family':'sofascore'}))
    add_row(db,eid='bigger',mid='991')
    add_row(db,eid='untyped',extra_json=dump_json({'source_event_ids':['99']}))
    assert known_native_rows(db,['99'])=={}


def test_observation_conflicts_remain_restrictions_even_without_matching_typed_id(db):
    row=add_row(db,eid='historical-alias',mid='other',display_eligible=False)
    db.add(SportsEventObservation(event_id=row.event_id,source_id='fm',source_family='fotmob',source_event_id='99'));db.commit()
    assert known_native_rows(db,['99'])=={'99':[row]}


def test_empty_or_invalid_request_does_not_scan_any_table(db):
    queries=[];engine=db.get_bind()
    def capture(*args):queries.append(args)
    event.listen(engine,'before_cursor_execute',capture)
    try:assert known_native_rows(db,[])==known_native_rows(db,['bad|.*','99" OR 1=1',''])=={}
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert not queries


def test_excessive_lookup_fails_closed_before_queries(db):
    with pytest.raises(ValueError,match='request exceeded'):
        known_native_rows(db,map(str,range(1,2502)))
