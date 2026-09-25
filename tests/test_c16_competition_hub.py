"""Competition-owned records never mutate live identities or invent history."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.models import Base, SportsCompetition, SportsSourceCompetition, SportsEvent, SportsSource
from collector.util import dump_json, load_json, isoformat, parse_datetime
from collector.football_history import parse_history, public_history
from collector.competition_hub import hub, comparison, _fetch_native, _CACHE, _INFLIGHT

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    _CACHE.clear();_INFLIGHT.clear()
    with Session(engine) as session:yield session
    engine.dispose();_CACHE.clear();_INFLIGHT.clear()

def sides():return {'home':{'id':'1','name':'Alpha'},'away':{'id':'2','name':'Beta'}}

def add_row(db, eid='known',mid='101',key='test-league',at=None,**kwargs):
    row=SportsEvent(event_id=eid,fingerprint=eid,sport_id='football',competition_id=key,event_family='team_match',
        start_time=at or datetime.utcnow()+timedelta(days=1),status='scheduled',display_eligible=True,
        participants_json=dump_json(sides()),extra_json=dump_json({'source_event_ids':{'fotmob':mid}}))
    for k,v in kwargs.items():setattr(row,k,v)
    db.add(row);db.commit();return row

def setup(db):
    key='test-league';db.add(SportsCompetition(competition_id=key,sport_id='football',name='Test League',slug=key,event_model='team_match'))
    db.add(SportsSourceCompetition(competition_id=key,source_id='fm',upstream_family='fotmob',source_competition_id='10',enabled=True,priority=1));db.commit()
    row=add_row(db)
    def fixture(mid,at,status=None):return {'id':mid,**sides(),'round':'2','status':{'utcTime':isoformat(at),**(status or {})}}
    t=[{'id':i,'name':name,'idx':i,'pts':3-i,'played':1,'wins':2-i,'draws':0,'losses':i-1,'scoresStr':'2-1'} for i,name in [(1,'Alpha'),(2,'Beta')]]
    root={'details':{'id':10,'name':'Test League','selectedSeason':'2026/2027'},'table':[{'data':{'leagueId':10,'leagueName':'Test League','table':{'all':t,'home':deepcopy(t),'away':deepcopy(t)}}}],
      'fixtures':{'allMatches':[fixture('101',row.start_time),fixture('102',datetime.utcnow()-timedelta(days=3),{'finished':True,'started':True,'scoreStr':'2 - 1'}),fixture('103',datetime.utcnow()+timedelta(days=6))]}}
    return key,row,root

class Provider:
    def __init__(self):self.detail_calls=[]
    def _to_normalized(self,row,**_):
        return {'id':row.event_id,'sport':'football','competition_key':row.competition_id,'competition':'Test League',
            'status':row.status,'start_time':isoformat(row.start_time),'score':load_json(row.score_json,{}),**load_json(row.participants_json),
            'group':(load_json(row.extra_json,{}) or {}).get('group')}
    def get_event(self,eid):
        self.detail_calls.append(eid);return {'id':eid,'competition_key':'test-league','h2h':[],'form':{}}

def get_for(root,detail=None,calls=None):
    def get(url):
        if calls is not None:calls.append(url)
        return SimpleNamespace(ok=True,payload=(detail if 'matchDetails' in url else root))
    return get


def test_static_mapping_uses_known_season_fixture_and_keeps_canonical_id(db):
    key,row,root=setup(db);before=(row.extra_json,row.score_json,row.status,row.fingerprint);p=Provider();calls=[]
    result=hub(db,p,key,getter=get_for(root,calls=calls))
    assert len(result['events'])==3
    assert [e['key'] for e in result['events']]==['reference:102','known','reference:103']
    assert result['events'][1]['id']=='known' and result['events'][1]['round']=='2'
    assert result['season']=='2026/2027' and len(result['table_views']['home'])==2
    assert result['coverage']['linked_match_details']==1 and result['coverage']['native_season_schedule']
    assert (row.extra_json,row.score_json,row.status,row.fingerprint)==before and db.query(SportsEvent).count()==1
    assert p.detail_calls==[]  # Opening TABLE cannot open an arbitrary match.

@pytest.mark.parametrize('wrong',['root-id','season','missing-match','wrong-pair','wrong-time','duplicate-witness','manual-witness','slim-witness','wrong-parent','disabled-source'])
def test_full_season_requires_exact_public_current_witness(db,wrong):
    key,row,root=setup(db)
    if wrong=='root-id':root['details']['id']=11
    if wrong=='season':root['details'].pop('selectedSeason')
    if wrong=='missing-match':root['fixtures']['allMatches'].pop(0)
    if wrong=='wrong-pair':root['fixtures']['allMatches'][0]['home']['name']='Wrong FC'
    if wrong=='wrong-time':root['fixtures']['allMatches'][0]['status']['utcTime']=isoformat(row.start_time+timedelta(days=30))
    if wrong=='duplicate-witness':root['fixtures']['allMatches'].append(deepcopy(root['fixtures']['allMatches'][0]))
    if wrong=='manual-witness':row.extra_json=dump_json({'manual_hidden':True,'source_event_ids':{'fotmob':'101'}})
    if wrong=='slim-witness':row.list_extra_json=dump_json({'display_eligible':False})
    if wrong=='wrong-parent':row.extra_json=dump_json({'source_parent_competition_id':'11','source_event_ids':{'fotmob':'101'}})
    if wrong=='disabled-source':db.add(SportsSource(source_id='fm',display_name='FM',kind='json',adapter_key='fotmob',upstream_family='fotmob',enabled=False))
    db.commit();out=hub(db,Provider(),key,getter=get_for(root))
    assert not any(e['id'] is None for e in out['events'])

@pytest.mark.parametrize('restriction',['hidden','manual','different-league','conflicting-final','slim-hidden'])
def test_source_supplement_does_not_revive_preobservation_restricted_records(db,restriction):
    key,row,root=setup(db);target=add_row(db,eid='restricted',mid='102',at=datetime.utcnow()-timedelta(days=3),key='other-league' if restriction=='different-league' else key)
    if restriction=='hidden':target.display_eligible=False
    if restriction=='manual':target.extra_json=dump_json({'manual_hidden':True,'source_event_ids':{'fotmob':'102'}})
    if restriction=='slim-hidden':target.list_extra_json=dump_json({'display_eligible':False})
    if restriction=='conflicting-final':target.status='finished';target.score_json=dump_json({'home':9,'away':9})
    db.commit();out=hub(db,Provider(),key,getter=get_for(root))
    assert not any(e['key']=='reference:102' for e in out['events'])
    if restriction=='conflicting-final':assert next(e for e in out['events'] if e['id']=='restricted')['score']=={'home':9,'away':9}


def test_explicit_archive_cannot_substitute_current_matches(db):
    key,row,root=setup(db);old=add_row(db,eid='old',mid='9',season='2025',at=datetime.utcnow()-timedelta(days=365))
    out=hub(db,Provider(),key,season='2025',getter=get_for(root))
    assert [e['id'] for e in out['events']]==['old'] and not out['table_views']
    current=hub(db,Provider(),key,getter=get_for(root));assert 'old' not in [e['id'] for e in current['events']]


def test_parent_group_rows_never_borrow_a_different_group(db):
    key,row,root=setup(db)
    row.extra_json=dump_json({'source_event_ids':{'fotmob':'101'},'group':'Group A'});db.commit()
    out=hub(db,Provider(),key,group='Group B',getter=get_for(root))
    assert out['events']==[]


def test_no_synthetic_home_away_tables(db):
    key,row,root=setup(db);root['table'][0]['data']['table'].pop('home')
    out=_fetch_native(db,key,'',get_for(root));assert out['table_views']['home']==[] and len(out['table_views']['away'])==2


def test_cache_singleflight_read_and_source_disable_still_apply(db):
    key,row,root=setup(db);calls=[]
    first=hub(db,Provider(),key,getter=get_for(root,calls=calls));count=len(calls)
    assert first['events'];first['events'].clear()
    assert len(hub(db,Provider(),key,getter=get_for(root,calls=calls))['events'])==3 and len(calls)==count
    db.query(SportsSourceCompetition).first().enabled=False;db.commit()
    assert len(hub(db,Provider(),key,getter=get_for(root,calls=calls))['events'])==1 and len(calls)==count


def test_comparison_is_explicit_and_limited_to_the_selected_competition(db):
    key,row,root=setup(db);provider=Provider()
    assert comparison(db,provider,key,'evil',getter=get_for(root))['reason']=='match_not_in_scope'
    assert provider.detail_calls==[]
    assert comparison(db,provider,key,'known',getter=get_for(root))['available']
    assert provider.detail_calls==['known']


def history_root():
    now=datetime.utcnow();g={'matchId':'101','leagueId':10,'homeTeam':sides()['home'],'awayTeam':sides()['away'],'matchTimeUTCDate':isoformat(now+timedelta(days=1))}
    old={'matchUrl':'/matches/alpha-vs-beta/test#99',**sides(),'league':{'name':'Test League'},'status':{'utcTime':isoformat(now-timedelta(days=7)),'finished':True,'scoreStr':'2 - 1'}}
    form={'linkToMatch':'/matches/alpha-vs-beta/test#99',**sides(),'date':{'utcTime':old['status']['utcTime']},'score':'2 - 1','resultString':'W'}
    reverse=deepcopy(form);reverse['resultString']='L'
    return {'general':g,'content':{'h2h':{'matches':[old]},'matchFacts':{'teamForm':[[form],[reverse]]}}}


def test_history_real_shapes_and_orientation_not_top_level_finished(db):
    root=history_root();root['content']['h2h']['matches'][0]['finished']=False
    before=deepcopy(root);out=parse_history(root)
    assert len(out['h2h'])==1 and out['h2h'][0]['score']=={'home':2,'away':1}
    assert out['form']['home']['summary']=='W' and out['form']['away']['summary']=='L' and root==before
    row=add_row(db,at=datetime.fromisoformat(root['general']['matchTimeUTCDate'].removesuffix('Z')))
    h2h,form=public_history(db,row,out)
    assert h2h[0]['id'] is None and '_source_match_id' not in h2h[0]
    assert form['home']['results'][0]['id'] is None

@pytest.mark.parametrize('bad',['name','id','current','future','unfinished','cancelled','awarded','score','conflicting-duplicate'])
def test_history_ignores_unproven_results(bad):
    root=history_root();old=root['content']['h2h']['matches'][0]
    if bad=='name':old['away']['name']='Namesake'
    if bad=='id':old['away']['id']='other'
    if bad=='current':old['matchUrl']='/matches/a-b/test#101'
    if bad=='future':old['status']['utcTime']=isoformat(datetime.utcnow()+timedelta(days=3))
    if bad=='unfinished':old['status']['finished']=False
    if bad in ('cancelled','awarded'):old['status'][bad]=True
    if bad=='score':old['status']['scoreStr']='-'
    if bad=='conflicting-duplicate':
        copy=deepcopy(old);copy['status']['scoreStr']='9 - 9';root['content']['h2h']['matches'].append(copy)
    assert parse_history(root)['h2h']==[]

@pytest.mark.parametrize('restriction',['hidden','manual','foreign-competition','bad-result','good-link'])
def test_history_respects_known_cross_competition_identity_without_observation(db,restriction):
    root=history_root();history=parse_history(root);row=add_row(db,at=datetime.fromisoformat(root['general']['matchTimeUTCDate'].removesuffix('Z')))
    old=add_row(db,eid='old',mid='99',key='foreign',at=datetime.fromisoformat(history['h2h'][0]['start_time'].removesuffix('Z')),status='finished',score_json=dump_json({'home':2,'away':1}))
    if restriction in ('hidden','foreign-competition'):old.display_eligible=False
    if restriction=='manual':old.extra_json=dump_json({'manual_hidden':True,'source_event_ids':{'fotmob':'99'}})
    if restriction=='bad-result':old.score_json=dump_json({'home':8,'away':8})
    db.commit();h2h,form=public_history(db,row,history)
    if restriction=='good-link':assert h2h[0]['id']=='old'
    else:assert h2h==[] and form=={}


def test_reference_comparison_proves_exact_match_and_never_creates_canonical_rows(db):
    key,row,root=setup(db);history=history_root();history['general']['matchId']='103';history['general']['matchTimeUTCDate']=root['fixtures']['allMatches'][2]['status']['utcTime']
    out=comparison(db,Provider(),key,'reference:103',getter=get_for(root,history))
    assert out['available'] and out['event']['id'] is None and len(out['h2h'])==1
    assert db.query(SportsEvent).count()==1
    history['general']['homeTeam']['id']='999'
    out=comparison(db,Provider(),key,'reference:103',getter=get_for(root,history))
    assert out['h2h']==[] and out['reason']=='history_not_verified'


def test_history_storage_private_and_result_unchanged(db):
    from collector.detail_enrich import enrich_event_row
    from collector.provider import public_event
    root=history_root();row=add_row(db,at=datetime.fromisoformat(root['general']['matchTimeUTCDate'].removesuffix('Z')))
    before=(row.event_id,row.status,row.score_json,row.fingerprint,row.extra_json)
    enrich_event_row(db,row,getter=get_for(root,root));db.commit()
    assert load_json(row.extra_json)['_football_history']['h2h'][0]['score']['home']==2
    assert '_football_history' not in public_event(load_json(row.extra_json))
    assert (row.event_id,row.status,row.score_json,row.fingerprint)==before[:4]


def test_partial_composite_parent_does_not_erase_existing_group_schedule(db):
    key, row, root = setup(db)
    row.extra_json = dump_json({'source_event_ids': {'fotmob': '101'}, 'group': 'Group A'})
    db.commit()
    table = root['table'][0]['data']['table']
    root['table'] = [{'data': {'leagueId': 10, 'composite': True, 'tables': [
        {'leagueId': 1010, 'leagueName': 'Test League Group A', 'table': table}]}}]
    for match in root['fixtures']['allMatches']:
        match['group'] = 'A'  # Bare letters cannot authorize a composite group.
    out = hub(db, Provider(), key, group='Group A', getter=get_for(root))
    assert [e['id'] for e in out['events']] == ['known']
    assert not out['coverage']['native_season_schedule']
    assert out['season'] is None
    assert not out['table_views']
    archived = hub(db, Provider(), key, group='Group A', season='2025', getter=get_for(root))
    assert archived['events'] == []


@pytest.mark.parametrize('hidden', [False, True])
def test_native_storage_key_uses_verified_public_competition_resolver(db, hidden):
    key, row, root = setup(db)
    at = parse_datetime(root['fixtures']['allMatches'][1]['status']['utcTime'])
    native = add_row(db, eid='native-stored-key', mid='102', key='different-native-key', at=at,
                    display_eligible=not hidden, status='finished', score_json=dump_json({'home':2,'away':1}))
    before=(native.event_id,native.competition_id,native.display_eligible,native.score_json)
    class ResolvedProvider(Provider):
        def _to_normalized(self, event, **kwargs):
            result=super()._to_normalized(event, **kwargs)
            if event.event_id=='native-stored-key':result['competition_key']=key
            return result
    out=hub(db,ResolvedProvider(),key,getter=get_for(root))
    matches=[e for e in out['events'] if e.get('id')=='native-stored-key']
    assert bool(matches) is (not hidden)
    assert not any(e['key']=='reference:102' for e in out['events'])
    if matches:assert matches[0]['score']=={'home':2,'away':1}
    assert (native.event_id,native.competition_id,native.display_eligible,native.score_json)==before
