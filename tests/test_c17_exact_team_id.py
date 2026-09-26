import pytest
from datetime import timedelta
from tests.test_c17_team_categories import db,add
from collector.entity_profiles import team_profile

@pytest.mark.parametrize('category,league',[('women','football-nor-toppserien'),('men','ireland-premier-division')])
@pytest.mark.parametrize('exact_newer',[True,False])
def test_exact_verified_club_id_survives_same_category_provider_merge(db,category,league,exact_newer):
 exact=add(db,'exact',league,'6042','Example FC')
 alias=add(db,'alias',league,'138034','Example FC')
 exact.start_time=alias.start_time+timedelta(hours=1 if exact_newer else -1)
 db.commit()
 before=[(r.event_id,r.participants_json,r.score_json) for r in (exact,alias)]
 result=team_profile(db,entity_key='6042',name='Example FC',sport='football')
 assert result['available'] and result['football_gender']==category
 assert result['entity_key']==str(result['team']['id'])=='6042'
 assert {e['id'] for e in result['results']}=={'exact','alias'}
 assert before==[(r.event_id,r.participants_json,r.score_json) for r in (exact,alias)]
