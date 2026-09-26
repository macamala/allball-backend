from tests.test_c17_categories_scorers import setup, db, female_raw
from collector.util import dump_json, load_json
from collector.models import SportsEvent, SportsCompetition


def test_womens_season_hub_keeps_canonical_link_with_verified_w_marker(db):
    from tests.test_c16_competition_hub import setup as seed, Provider, get_for
    from collector.competition_hub import hub
    key,row,root=seed(db)
    root['details']['gender']='female'
    row.participants_json=dump_json({'home':{'id':'1','name':'Alpha (W)'},'away':{'id':'2','name':'Beta (W)'}})
    db.commit()
    before=(row.event_id,row.participants_json,row.score_json,row.extra_json)
    result=hub(db,Provider(),key,getter=get_for(root))
    assert result['season']=='2026/2027'
    assert [e['key'] for e in result['events']]==['reference:102','known','reference:103']
    assert result['coverage']['linked_match_details']==1
    assert (row.event_id,row.participants_json,row.score_json,row.extra_json)==before


def test_public_category_identical_on_slim_detail_and_live_delta(setup):
    from collector.football_board_refresh import consume_board_match
    from collector.provider import NinkoCollectedSportsDataProvider,_list_public_event,live_public_event
    from collector.list_extra import store_list_extra
    db,source=setup
    consume_board_match(db,female_raw(),source,{})
    db.commit();row=db.query(SportsEvent).one()
    if not db.get(SportsCompetition,'mexico-liga-mx'):
        db.add(SportsCompetition(competition_id='mexico-liga-mx',sport_id='football',name='Liga MX',slug='mexico-liga-mx',event_model='team_match'))
    row.competition_id='mexico-liga-mx'
    meta=load_json(row.extra_json);meta.update(public_competition_key='mexico-liga-mx',canonical_competition_id='mexico-liga-mx')
    row.extra_json=dump_json(meta);store_list_extra(row,meta);db.commit()
    before=(row.event_id,row.competition_id,row.extra_json,row.score_json,row.participants_json)
    p=NinkoCollectedSportsDataProvider()
    slim=p._to_normalized(row,list_mode=True)
    detail=p._to_normalized(row,include_detail=True)
    for payload in (slim,detail,_list_public_event(slim),live_public_event(slim)):
        assert payload['id']==row.event_id
        assert payload['football_gender']=='women'
        assert payload['competition_key']=='football-mex-liga-mx-femenil-apertura'
    assert (row.event_id,row.competition_id,row.extra_json,row.score_json,row.participants_json)==before
