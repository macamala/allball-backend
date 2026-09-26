from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from collector.football_category import native_gender, category_for_event, womens_marker_pair, public_category_projection
from collector.fotmob_crosswalk import _fotmob_competition_identity
from collector.competition_identity import label_matches_competition, source_native_public_competition_id
from collector.fotmob_rich import verified_detail_identity
from collector.football_scorers import scorer_spec, parse_scorers, scorers
from collector.util import dump_json, load_json, isoformat
from collector.models import SportsEvent, SportsCompetition
from tests.test_football_global_refresh import setup, fresh
from tests.test_c15_live_tables import db, add_case

@pytest.mark.parametrize('label,cid',[("Women's FA Cup",'fa-cup'),('Liga MX Femenil Apertura','mexico-liga-mx'),('Copa Libertadores Femenina','copa-libertadores'),('UEFA Women Nations League','uefa-nations-league')])
def test_female_label_cannot_use_male_substring_mapping(label,cid):
    assert not label_matches_competition(label,cid)

@pytest.mark.parametrize('label,cid', [('FA Cup','fa-cup'),('Liga MX','mexico-liga-mx'),('NWSL','usa-nwsl'),("Women's Super League",'womens-super-league')])
def test_expected_canonical_labels_remain_valid(label,cid):
    assert label_matches_competition(label,cid)

@pytest.mark.parametrize('parent,name,country,key,gender',[(9906,'Liga MX Femenil Apertura','MEX','football-mex-liga-mx-femenil-apertura','women'),(230,'Liga MX Apertura','MEX','mexico-liga-mx','men'),(331,'Toppserien','NOR','football-nor-toppserien','women'),(9294,'WSL 2','ENG','football-eng-wsl-2','women'),(126,'Premier Division','IRL','ireland-premier-division','men')])
def test_native_competition_and_gender_are_scoped_by_parent_id(parent,name,country,key,gender):
    ctx={'id':parent,'parentLeagueId':parent,'name':name,'ccode':country}
    assert _fotmob_competition_identity({'_league':ctx})[0]==key
    assert native_gender(ctx)==gender

def test_unknown_is_not_silently_male_and_other_source_ids_are_not_fotmob():
    assert category_for_event({'source_family':'other','source_competition_id':'331'})=='unknown'
    assert category_for_event({'source_family':'fotmob','source_competition_id':'999999999'})=='unknown'
    assert native_gender({'id':331,'parentLeagueId':230}) is None

def test_mixed_frozen_bucket_projects_same_event_into_its_proved_womens_scope():
    extra={'source_family':'fotmob','source_parent_competition_id':'9906','source_competition_id':'942125','source_competition_name':'Liga MX Femenil Apertura'}
    before=deepcopy(extra)
    assert public_category_projection(extra)=='football-mex-liga-mx-femenil-apertura'
    assert extra==before and category_for_event(extra,'mexico-liga-mx')=='women'
    assert source_native_public_competition_id(stored_competition_id='football-mex-liga-mx-femenil-apertura',source_competition_name='Liga MX Femenil Apertura',sport_id='football',source_family='fotmob')=='football-mex-liga-mx-femenil-apertura'

def female_raw():
    return fresh({'id':5977364,'_league':{'id':942125,'primaryId':9906,'parentLeagueId':9906,'name':'Liga MX Femenil Apertura','ccode':'MEX'},'home':{'id':980700,'name':'Cruz Azul (W)'},'away':{'id':980702,'name':'Chivas (W)'},'status':{'utcTime':isoformat(datetime.utcnow()-timedelta(hours=1)),'started':True,'finished':True,'scoreStr':'1 - 2'}})

def test_existing_wrong_bucket_is_repaired_without_erasing_match_or_alias(setup):
    from collector.football_board_refresh import consume_board_match
    from collector.list_extra import store_list_extra
    db,source=setup;raw=female_raw()
    out=consume_board_match(db,raw,source,{});db.commit();assert not out.get('rejected'),out
    row=db.query(SportsEvent).one();eid=row.event_id;correct=row.competition_id
    if not db.get(SportsCompetition,'mexico-liga-mx'):
        db.add(SportsCompetition(competition_id='mexico-liga-mx',sport_id='football',name='Liga MX',slug='mexico-liga-mx',event_model='team_match'))
    meta=load_json(row.extra_json);meta.update(public_competition_key='mexico-liga-mx',canonical_competition_id='mexico-liga-mx')
    row.competition_id='mexico-liga-mx';row.extra_json=dump_json(meta);store_list_extra(row,meta)
    child=SportsEvent(event_id='old-alias',fingerprint='old-alias',sport_id='football',competition_id='mexico-liga-mx',event_family='team_match',canonical_event_id=eid,display_eligible=False,extra_json=dump_json({'collapse_role':'observation_only'}))
    db.add(child);db.commit();old_score=row.score_json
    for _ in range(2):
        out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[row]});db.commit()
        assert not out.get('rejected'),out
        assert row.event_id==eid and row.competition_id==correct and row.score_json==old_score
        assert child.canonical_event_id==eid and child.display_eligible is False
        assert db.query(SportsEvent).count()==2

@pytest.mark.parametrize('restriction',[{'manual_hidden':True},{'do_not_restore':True},{'collapse_role':'observation_only'}])
def test_category_repair_never_promotes_restricted_matches(setup,restriction):
    from collector.football_board_refresh import consume_board_match
    db,source=setup;raw=female_raw();consume_board_match(db,raw,source,{});db.commit();row=db.query(SportsEvent).one()
    row.extra_json=dump_json({**load_json(row.extra_json),**restriction});row.display_eligible=False;db.commit()
    old=(row.extra_json,row.competition_id,row.fingerprint,row.score_json)
    out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[row]});db.commit()
    assert out.get('rejected') and (row.extra_json,row.competition_id,row.fingerprint,row.score_json)==old

def identity_case():
    at=isoformat(datetime.utcnow());identity={'start_time':at,'home':{'id':'169297','name':'FK Haugesund (W)'},'away':{'id':'4486','name':'LSK Kvinner (W)'}}
    root={'general':{'matchId':'1','matchTimeUTCDate':at,'leagueId':916229,'parentLeagueId':331,'homeTeam':{'id':169297,'name':'FK Haugesund'},'awayTeam':{'id':4486,'name':'LSK Kvinner'}}}
    return root,identity

def test_womens_annotation_accepts_same_native_ids_and_no_other_name_change():
    root,identity=identity_case();assert verified_detail_identity(root,'1',identity)

@pytest.mark.parametrize('wrong',['id','name','reverse','age','reserve','time','match','male-league'])
def test_womens_annotation_exception_cannot_merge_different_teams(wrong):
    root,identity=identity_case();g=root['general']
    if wrong=='id':g['homeTeam']['id']=999
    if wrong=='name':g['homeTeam']['name']='Completely Different'
    if wrong=='reverse':g['homeTeam'],g['awayTeam']=g['awayTeam'],g['homeTeam']
    if wrong=='age':g['homeTeam']['name']+=' U21'
    if wrong=='reserve':g['homeTeam']['name']+=' II'
    if wrong=='time':g['matchTimeUTCDate']=isoformat(datetime.utcnow()-timedelta(days=1))
    if wrong=='match':g['matchId']='2'
    if wrong=='male-league':g.update(leagueId=230,parentLeagueId=230)
    assert not verified_detail_identity(root,'1',identity)

def test_table_context_uses_exact_female_identity_without_mutating_match(db):
    from collector.standings_enrich import _fetch_fotmob_dynamic_standings
    from collector.models import SportsSourceCompetition
    cid,row,native,root=add_case(db)
    row.participants_json=dump_json({'home':{'id':'1','name':'Alpha (W)'},'away':{'id':'2','name':'Beta (W)'}})
    mapping=db.query(SportsSourceCompetition).one();mapping.source_competition_id='916229'
    native['general'].update(leagueId=916229,parentLeagueId=331)
    root['details'].update(id=331,gender='female');root['table']=[{'data':{'leagueId':331,'leagueName':'Toppserien','table':{'all':root['table'][0]['data']['tables'][0]['table']['all']}}}]
    root['fixtures']={'allMatches':[{'id':'101','home':{'id':'1'},'away':{'id':'2'},'status':{'utcTime':row.start_time.isoformat()}}]};db.commit();before=(row.extra_json,row.participants_json,row.score_json)
    result=_fetch_fotmob_dynamic_standings(db,cid,getter=lambda url:SimpleNamespace(ok=True,payload=native if 'matchDetails' in url else root))
    assert len(result.get('rows',[]))==2
    assert (row.extra_json,row.participants_json,row.score_json)==before

def scorer_case():
    spec={'participant':{'id':7,'stat':{'name':'goals','value':5}},'fetchAllUrl':'https://data.fotmob.com/stats/331/season/123/goals.json'}
    native={'parent':'331','season':'2026','table_rows':[{'team_id':'1'}],'_scorer_specs':[spec]}
    root={'TopLists':[{'StatName':'goals','StatList':[{'ParticiantId':7,'ParticipantName':'Player A','TeamId':1,'TeamName':'Alpha','StatValue':5,'SubStatValue':1,'Rank':1,'MatchesPlayed':3}]}]}
    return native,spec,root

def test_scorer_parser_keeps_goals_penalties_team_and_profile_identity():
    native,spec,root=scorer_case();rows=parse_scorers(root,native,spec)
    assert len(rows)==1 and rows[0]['goals']==5 and rows[0]['penalties']==1 and rows[0]['player_id']=='7'
    assert scorer_spec(native)==spec

@pytest.mark.parametrize('wrong',['external','wrong-league','traversal','missing-top','team','duplicate','negative','fraction','wrong-stat'])
def test_scorers_never_borrow_another_league_or_invent_values(wrong):
    native,spec,root=scorer_case();r=root['TopLists'][0]['StatList'][0]
    if wrong in ('external','wrong-league','traversal'):
        spec['fetchAllUrl']={'external':'https://evil.test/stats/331/season/123/goals.json','wrong-league':'https://data.fotmob.com/stats/230/season/123/goals.json','traversal':'https://data.fotmob.com/stats/331/season/123/../goals.json'}[wrong]
        assert scorer_spec(native) is None;return
    if wrong=='missing-top':spec['participant']['id']=8
    if wrong=='team':r['TeamId']=9
    if wrong=='duplicate':root['TopLists'][0]['StatList'].append(deepcopy(r))
    if wrong=='negative':r['StatValue']=-1
    if wrong=='fraction':r['StatValue']=1.5
    if wrong=='wrong-stat':root['TopLists'][0]['StatName']='assists'
    assert parse_scorers(root,native,spec)==[]

def test_scorer_group_without_evidence_cannot_use_whole_league(db):
    calls=[];result=scorers(db,'test',group='Group A',getter=lambda url:calls.append(url))
    assert result['rows']==[] and calls==[]
