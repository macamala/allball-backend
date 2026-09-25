"""Reproductions from the captured native match detail structure, not scores to seed."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.canonical_detail import attach_canonical_detail
from collector.detail_enrich import parse_fotmob_details, enrich_event_row, fetch_family_detail, PARSER_REV
from collector.fotmob_rich import pitch_position, verified_detail_identity, refresh_due, REVISION
from collector.models import Base, SportsEvent, SportsEventDetail
from collector.adapters import FetchResult
from collector.util import dump_json, load_json


def source():
    return {'general': {'matchId': '100', 'homeTeam': {'id': 1, 'name': 'Home FC'}, 'awayTeam': {'id': 2, 'name': 'Away FC'}, 'matchTimeUTCDate': '2026-09-19T18:45:00Z'}, 'content': {
        'matchFacts': {'events': {'events': [
            {'type':'Card', 'time':45, 'overloadTime':2, 'card':'Yellow', 'player':{'id':10,'name':'First Player'}, 'isHome':True},
            {'type':'Half', 'time':45, 'halfStrShort':'HT'},
            {'type':'Substitution', 'time':59, 'swap':[{'id':'11','name':'Sub In'},{'id':'10','name':'Sub Out'}], 'isHome':True},
            {'type':'Goal','time':74,'player':{'id':20,'name':'Scorer'},'newScore':[0,1], 'homeScore':0, 'awayScore':0, 'isHome':False},
            {'type':'Card', 'time':90, 'overloadTime':4, 'card':'Red', 'player':{'id':11,'name':'Sub In'}, 'isHome':True}]}},
        'stats': {'Periods': {p: {'stats':[{'stats':[{'title':'Shots','stats':[None,None]},{'title':'Total shots','stats':[0,3]},{'title':'Total shots','stats':[0,3]}]}]} for p in ['All','FirstHalf','SecondHalf']}},
        'lineup': {'homeTeam': {'starters':[{'id':10,'name':'First Player','positionId':11,'countryCode':'IRL','verticalLayout':{'x':.5,'y':.1},'shirtNumber':1}]}, 'awayTeam': {'starters':[{'id':20,'name':'Scorer','positionId':115,'countryCode':'ENG','verticalLayout':{'x':.5,'y':.8},'shirtNumber':9}]}},
        'shotmap': {'shots':[{'id':301,'teamId':2,'playerId':20,'playerName':'Scorer','min':74,'eventType':'Goal','expectedGoals':0.0,'isOnTarget':True}, {'id':302,'teamId':99,'playerId':30,'playerName':'Unknown Team','min':75,'eventType':'Miss','expectedGoals':None,'isOnTarget':False}]},
    }}


def test_real_detail_fields_survive_public_canonicalization():
    raw=source();before=deepcopy(raw);parsed=parse_fotmob_details(raw)
    public=attach_canonical_detail({'id':'one','sport':'football',**parsed})
    assert raw==before
    timeline=public['timeline']; assert len(timeline)==4
    assert timeline[0]['minute']==45 and timeline[0]['stoppage']==2 and timeline[0]['period']=='1'
    assert timeline[1]['player_in']=='Sub In' and timeline[1]['player_out']=='Sub Out'
    assert timeline[1]['player_in_id']=='11' and timeline[1]['player_out_id']=='10'
    assert timeline[2]['score_after']=={'home':0,'away':1}
    assert timeline[2]['player_id']==20 and timeline[2]['period']=='2'
    assert timeline[3]['stoppage']==4
    assert public['statistics']==[{'label':'Total shots','home':0,'away':3}]
    assert len(public['sport_detail']['statistics_periods']['first_half'])==1
    player=public['lineups']['home']['start'][0]
    assert player['pitch_position']=={'x':.5,'y':.1} and player['country_id']=='IRL'
    assert player['position_id']==11 and 'position' not in player
    assert 'confirmed' not in public['lineups']
    shots=public['sport_detail']['shots'];assert len(shots)==2
    assert shots[0]['xg']==0 and shots[0]['side']=='away' and shots[1]['side'] is None
    assert public['sport_detail']['shots_total']==2
    assert 'score' not in parsed and 'status' not in parsed


@pytest.mark.parametrize('value',[None,{}, {'x':float('nan'),'y':.5},{'x':True,'y':.5},{'x':2,'y':.5},{'x':.5,'y':-1}])
def test_invalid_pitch_coordinates_are_not_invented(value):
    assert pitch_position(value) is None


@pytest.mark.parametrize('field',['match','home','away','time'])
def test_fresh_detail_replacement_requires_identity(field):
    raw=source();ident={'home':{'name':'Home FC'},'away':{'name':'Away FC'},'start_time':'2026-09-19T18:45:00Z'}
    assert verified_detail_identity(raw,'100',ident)
    if field=='match':raw['general']['matchId']='999'
    if field in ['home','away']:raw['general'][field+'Team']['name']='Other'
    if field=='time':raw['general']['matchTimeUTCDate']='2026-09-19T19:45:00Z'
    assert not verified_detail_identity(raw,'100',ident)


def test_unknown_detail_identity_is_not_sufficient():
    assert not verified_detail_identity(source(),'100',{})
    assert not verified_detail_identity(source(),'100',None)
    assert not refresh_due({'fotmob_detail_rev':REVISION})
    assert not refresh_due({'fotmob_detail_checked_at':datetime.utcnow().isoformat()})
    assert refresh_due({'fotmob_detail_checked_at':(datetime.utcnow()-timedelta(minutes=16)).isoformat()})


def test_explicit_wrong_source_match_is_rejected():
    raw=source();raw['general']['matchId']='other'
    getter=lambda url:FetchResult(ok=True, payload=raw, http_status=200)
    assert fetch_family_detail('fotmob','100',getter=getter)=={}


@pytest.fixture
def stored():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        row=SportsEvent(event_id='event',fingerprint='fixed',sport_id='football',competition_id='league',event_family='team_match',start_time=datetime(2026,9,19,18,45),status='finished',live=False,display_eligible=True,
                        participants_json=dump_json({'home':{'name':'Home FC'},'away':{'name':'Away FC'}}),score_json=dump_json({'home':0,'away':1}),
                        extra_json=dump_json({'source_event_ids':{'fotmob':'100'},'detail_fetched_at':datetime.utcnow().isoformat(),'parser_rev':PARSER_REV,'detail_empty':False,'detail_families_tried':['fotmob'],'sport_detail':{'shots':2,'unrelated':'keep'}}))
        record=SportsEventDetail(event_id='event',incidents_json=dump_json([{'type':'substitution','minute':59}]),statistics_json=dump_json([{'label':'Old','home':1,'away':1}]),lineups_json=dump_json({'home':{'start':[{'name':'First Player'}]}}))
        db.add_all([row,record]);db.commit();yield db,row,record


def test_existing_cached_details_refresh_without_score_or_identity_change(stored):
    db,row,record=stored;before=(row.event_id,row.fingerprint,row.status,row.live,row.score_json,row.display_eligible,row.canonical_event_id)
    calls=[]
    def getter(url):calls.append(url);return FetchResult(ok=True,payload=source(),http_status=200)
    enrich_event_row(db,row,getter=getter);db.commit()
    assert len(calls)==1
    assert load_json(record.incidents_json)[1]['player_in']=='Sub In'
    assert len(load_json(record.statistics_json))==1
    extra=load_json(row.extra_json);assert isinstance(extra['sport_detail']['shots'],list)
    assert extra['sport_detail']['unrelated']=='keep'
    assert extra['fotmob_detail_rev']==REVISION
    assert before==(row.event_id,row.fingerprint,row.status,row.live,row.score_json,row.display_eligible,row.canonical_event_id)
    enrich_event_row(db,row,getter=getter);db.commit();assert len(calls)==1


def test_failed_refresh_keeps_rich_cache_and_backoff(stored):
    db,row,record=stored;old=(record.incidents_json,record.statistics_json,record.lineups_json)
    calls=[]
    def getter(url):calls.append(url);return FetchResult(ok=False,http_status=503,error='temporary')
    enrich_event_row(db,row,getter=getter);db.commit()
    assert old==(record.incidents_json,record.statistics_json,record.lineups_json)
    assert 'fotmob_detail_rev' not in load_json(row.extra_json)
    # Failed requests retain existing data and do not create a new eager retry.
    enrich_event_row(db,row,getter=getter);db.commit();assert len(calls)==1
