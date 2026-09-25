"""Real public team/player navigation must not raise on name fallback."""
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.models import Base, SportsEvent, SportsEventDetail
from collector.entity_profiles import player_profile, team_profile, _matches_player, _matches_side
from collector.util import dump_json

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as session:
        def add(eid,visible,canonical=None):
            session.add(SportsEvent(event_id=eid,fingerprint=eid,sport_id='football',competition_id='league',event_family='team_match',start_time=datetime.utcnow()-timedelta(days=1),status='finished',live=False,display_eligible=visible,canonical_event_id=canonical,score_json=dump_json({'home':0,'away':1}),participants_json=dump_json({'home':{'id':'h','name':'Sligo Rovers'},'away':{'id':'a','name':"St. Patrick's Athletic"}}),extra_json='{}'))
            session.add(SportsEventDetail(event_id=eid,lineups_json=dump_json({'away':{'start':[{'id':825815,'name':'Aidan Keena','number':'9','image':'https://example.test/real-image.png'},{'id':1,'name':'Other Person','number':'1'}]}})))
        add('match',True);add('hidden',False);add('alias',False,'match');session.commit();yield session

@pytest.mark.parametrize('key',['825815','Aidan Keena'])
def test_existing_player_by_id_and_name_with_match_context(db,key):
    result=player_profile(db,player_key=key,name='Aidan Keena',event_id='match')
    assert result['available'] is True and result['player']['id']==825815
    assert result['name']=='Aidan Keena' and [e['id'] for e in result['appearances']]==['match']
    assert result['player']['number']=='9'

@pytest.mark.parametrize('key',['h','Sligo Rovers'])
def test_existing_team_by_id_and_name_without_exception(db,key):
    result=team_profile(db,entity_key=key,name='Sligo Rovers',sport='football',competition='league')
    assert result['available'] is True and result['team']['id']=='h'
    assert [e['id'] for e in result['results']]==['match']
    assert result['form']==['L']

@pytest.mark.parametrize('name',['Missing Person','Aidan Keena Junior'])
def test_unknown_player_does_not_alias_to_someone_else(db,name):
    result=player_profile(db,player_key=name,name=name,event_id='match')
    assert result['available'] is False and result['appearances']==[]

def test_unknown_team_does_not_alias_to_other_team(db):
    result=team_profile(db,entity_key='unknown',name='Sligo Rovers Women',sport='football',competition='league')
    assert result['available'] is False

def test_name_fallback_is_still_literal_not_broad_fuzzy():
    assert _matches_player({'name':'Aidan Keena'},player_key='name',name='Aidan Keena')
    assert not _matches_player({'name':'Aidan Keena'},player_key='name',name='Keena')
    assert _matches_side({'name':'Sligo Rovers'},entity_key='name',name='Sligo Rovers')
    assert not _matches_side({'name':'Sligo Rovers'},entity_key='name',name='Sligo')
