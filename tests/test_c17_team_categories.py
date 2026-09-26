from datetime import datetime,timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from collector.models import Base,SportsEvent,SportsCompetition
from collector.util import dump_json
from collector.entity_profiles import team_profile

@pytest.fixture
def db():
 engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine);session=sessionmaker(bind=engine)()
 yield session
 session.close();engine.dispose()

def add(db,eid,cid,tid,name,extra=None):
 row=SportsEvent(event_id=eid,fingerprint=eid,sport_id='football',competition_id=cid,event_family='team_match',start_time=datetime.utcnow()-timedelta(days=1),status='finished',live=False,display_eligible=True,score_json=dump_json({'home':1,'away':0}),participants_json=dump_json({'home':{'id':tid,'name':name},'away':{'id':'999','name':'Opponent'}}),extra_json=dump_json(extra or {}))
 db.add(row);db.commit();return row

@pytest.mark.parametrize('gender,tid,own,other',[
 ('women','4500','football-nor-toppserien','ireland-premier-division'),
 ('men','8404','ireland-premier-division','football-nor-toppserien')])
def test_same_name_opposite_category_never_enters_club_results(db,gender,tid,own,other):
 a=add(db,'correct',own,tid,'Aalesund')
 b=add(db,'wrong',other,'different-id','Aalesund')
 add(db,'same-category-other-provider',own,'other-provider-id','Aalesund')
 before=[(r.event_id,r.competition_id,r.score_json) for r in db.query(SportsEvent).all()]
 result=team_profile(db,entity_key=tid,name='Aalesund',sport='football')
 assert result['available'] and result['football_gender']==gender
 assert {e['id'] for e in result['results']}=={'correct','same-category-other-provider'}
 assert result['competition_keys']==[own] and all(e['football_gender']==gender for e in result['results'])
 assert before==[(r.event_id,r.competition_id,r.score_json) for r in db.query(SportsEvent).all()]

def test_verified_womens_marker_and_exact_id_anchor(db):
 add(db,'female','football-nor-toppserien','4500','Aalesund (W)')
 add(db,'male','ireland-premier-division','8404','Aalesund')
 r=team_profile(db,entity_key='4500',name='Aalesund',sport='football')
 assert r['name']=='Aalesund (W)' and [e['id'] for e in r['results']]==['female']

def test_unclassified_namesake_is_not_used_as_womens_history(db):
 add(db,'female','football-nor-toppserien','4500','Aalesund')
 add(db,'unknown','unknown-league','other','Aalesund')
 add(db,'exact-unknown','unknown-league','4500','Aalesund')
 r=team_profile(db,entity_key='4500',name='Aalesund',sport='football')
 assert {e['id'] for e in r['results']}=={'female','exact-unknown'}

def test_conflicting_unqualified_ids_are_unavailable_not_combined(db):
 add(db,'female','football-nor-toppserien','4500','Aalesund')
 add(db,'male','ireland-premier-division','4500','Aalesund')
 assert team_profile(db,entity_key='4500',name='Aalesund',sport='football')['available'] is False

def test_womens_team_preserves_legacy_public_competition_scope(db):
 key='football-mex-liga-mx-femenil-apertura'
 db.add(SportsCompetition(competition_id=key,sport_id='football',name='Liga MX Femenil Apertura',slug=key,event_model='team_match'));db.commit()
 add(db,'legacy','mexico-liga-mx','980700','Cruz Azul (W)',{'source_family':'fotmob','source_competition_id':'942125','source_parent_competition_id':'9906','source_competition_name':'Liga MX Femenil Apertura'})
 r=team_profile(db,entity_key='980700',name='Cruz Azul (W)',sport='football',competition=key)
 assert r['available'] and r['competition_keys']==[key] and r['results'][0]['competition_key']==key
 assert db.get(SportsEvent,'legacy').competition_id=='mexico-liga-mx'


def test_unknown_exact_identity_does_not_borrow_known_womens_namesake(db):
 add(db,'unknown-men','norway-eliteserien','8404','Aalesund')
 add(db,'known-women','football-nor-toppserien','4500','Aalesund')
 r=team_profile(db,entity_key='8404',name='Aalesund',sport='football')
 assert r['available'] and r['football_gender']=='unknown'
 assert [e['id'] for e in r['results']]==['unknown-men']
