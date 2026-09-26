from copy import deepcopy
from types import SimpleNamespace
import pytest
from tests.test_c17_categories_scorers import setup, female_raw
from tests.test_c16_competition_hub import db
from collector.models import SportsEvent, SportsCompetition, SportsSourceCompetition
from collector.util import load_json, dump_json
from collector.list_extra import store_list_extra
from collector.football_category import category_for_event

@pytest.mark.parametrize('key', ['usa-usl-championship', 'korea-k-league-1'])
def test_alternate_provider_keeps_checked_canonical_category(key):
    assert category_for_event({'source_family':'sofascore'},key)=='men'
    assert category_for_event({'source_family':'other'},'unknown-competition')=='unknown'
    assert category_for_event({'source_family':'other','source_competition_name':'Women'},key)=='women'

@pytest.mark.parametrize('restriction', [None,'manual_hidden','hidden','wrong-parent'])
def test_female_hub_includes_same_projected_id_without_waiting_for_worker(setup,restriction):
    from collector.football_board_refresh import consume_board_match
    from collector.provider import NinkoCollectedSportsDataProvider
    from collector.competition_hub import hub
    db,source=setup
    consume_board_match(db,female_raw(),source,{})
    db.commit();row=db.query(SportsEvent).one();key=row.competition_id
    db.add(SportsCompetition(competition_id='mexico-liga-mx',sport_id='football',name='Liga MX',slug='mexico-liga-mx',event_model='team_match'))
    meta=load_json(row.extra_json);meta.update(public_competition_key='mexico-liga-mx',canonical_competition_id='mexico-liga-mx')
    if restriction=='manual_hidden':meta['manual_hidden']=True
    if restriction=='hidden':row.display_eligible=False
    if restriction=='wrong-parent':meta.update(source_parent_competition_id='230',source_competition_id='230',source_group_id='230',source_competition_context={})
    row.competition_id='mexico-liga-mx';row.extra_json=dump_json(meta);store_list_extra(row,meta);db.commit()
    before=(row.event_id,row.competition_id,row.extra_json,row.score_json,row.participants_json)
    p=NinkoCollectedSportsDataProvider()
    out=hub(db,p,key,getter=lambda url:SimpleNamespace(ok=False,payload=None))
    assert [e['id'] for e in out['events']]==([] if restriction else [row.event_id])
    assert (row.event_id,row.competition_id,row.extra_json,row.score_json,row.participants_json)==before
    if not restriction:
        assert out['events'][0]['football_gender']=='women'
        assert not hub(db,p,'mexico-liga-mx',getter=lambda url:SimpleNamespace(ok=False,payload=None))['events']

@pytest.mark.parametrize('wrong',[None,'name','id','season','group','unavailable','duplicate'])
def test_scorer_profile_only_uses_same_verified_season_identity(db,monkeypatch,wrong):
    from collector.entity_profiles import player_profile
    from collector import football_scorers,player_enrichment
    calls=[]
    row={'player_id':'7','name':'Player A','photo':'verified.png','team_id':'1','team':'Alpha','goals':5}
    payload={'available':True,'season':'2026','competition_key':'scoped-league','rows':[row]}
    if wrong=='name':row['name']='Someone Else'
    if wrong=='id':row['player_id']='8'
    if wrong=='season':payload['season']='2025'
    if wrong=='unavailable':payload['available']=False
    if wrong=='duplicate':payload['rows'].append(deepcopy(row))
    def scorers(db,key,**kw):
        calls.append((key,kw));return payload
    enriched=[]
    monkeypatch.setattr(football_scorers,'scorers',scorers)
    monkeypatch.setattr(player_enrichment,'enriched_profile',lambda pid,name:enriched.append((pid,name)) or {'position':'Striker'})
    out=player_profile(db,player_key='7',name='Player A',competition_key='scoped-league',season='2026',group='wrong' if wrong=='group' else '')
    assert out['available'] is (wrong is None)
    if wrong is None:
        assert out['player']['id']=='7' and out['player']['image']=='verified.png' and out['player']['position']=='Striker'
        assert out['appearances']==[] and not out['player'].get('goals')
        assert enriched==[('7','Player A')]
    else:assert not enriched


def test_unscoped_numeric_player_cannot_trigger_unverified_fetch(db,monkeypatch):
    from collector.entity_profiles import player_profile
    from collector import football_scorers
    monkeypatch.setattr(football_scorers,'scorers',lambda *a,**kw:pytest.fail('unscoped request must not choose league'))
    assert not player_profile(db,player_key='7',name='Player A')['available']
