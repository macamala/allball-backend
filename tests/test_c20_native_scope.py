"""Two production conflict classes, bounded proof, and immutable old links."""
from copy import deepcopy
from datetime import datetime,timedelta
import pytest
from tests.test_football_global_refresh import setup,fresh,RECORDED
from tests.test_football_source_roots import snap
from collector.football_board_refresh import consume_board_match
from collector.adapters_fotmob import match_to_event
from collector.models import SportsEvent,SportsCompetition
from collector.util import dump_json,load_json,isoformat
from collector.list_extra import store_list_extra


def case(db,source,kind):
    raw=fresh(RECORDED[0]);raw['id']=1000014161 if kind=='parent' else 5882299
    if kind=='parent':
        raw['_league']={'id':1000001696,'parentLeagueId':274,'primaryId':274,'name':'Primera A','ccode':'COL','isGroup':False}
        sides=[('Chicó FC',6255),('Deportivo Pasto',4405)]
    else:
        raw['_league']={'id':938777,'parentLeagueId':9907,'primaryId':9907,'name':'Liga F','ccode':'ESP','isGroup':False}
        sides=[('Athletic Club (W)',789880),('Atlético Madrid (W)',671936)]
    if kind=='women-italy':
        raw['id']=5977767
        raw['_league']={'id':942146,'parentLeagueId':10178,'primaryId':10178,'name':'Serie A Femminile','ccode':'ITA','isGroup':False}
        sides=[('Inter (W)',1184314),('Fiorentina (W)',856740)]
    if kind=='women-germany':
        raw['id']=6040018
        raw['_league']={'id':10650,'primaryId':10650,'name':'DFB Pokal Frauen','ccode':'GER','isGroup':False}
        sides=[('Blau-Gelb Marburg (W)',2061640),('RB Leipzig (W)',1513040)]
    for side,(name,tid) in zip(('home','away'),sides):
        raw[side].update(id=tid,name=name,longName=name,score=3 if side=='home' else 0)
    raw['status'].update(utcTime=isoformat(datetime.utcnow()-timedelta(hours=2)),finished=True,started=True,scoreStr='3 - 0',reason={'short':'FT'})
    out=consume_board_match(db,raw,source,{});db.commit();assert not out.get('rejected'),out
    keeper=db.query(SportsEvent).one();rich=load_json(keeper.extra_json)
    old='football-col-primera-a' if kind=='parent' else 'spain-la-liga'
    old={'women-italy':'italy-serie-a','women-germany':'germany-dfb-pokal'}.get(kind,old)
    if not db.get(SportsCompetition,old):
        db.add(SportsCompetition(competition_id=old,sport_id='football',name='Earlier bucket',slug=old,event_model='team_match'))
    legacy=SportsEvent(event_id='legacy',fingerprint='legacy-fp',sport_id='football',competition_id=old,
        event_family='team_match',start_time=keeper.start_time,status='scheduled',live=False,
        participants_json=keeper.participants_json,score_json=dump_json({'home':None,'away':None}),
        display_eligible=True,extra_json=dump_json({**rich,'display_eligible':True,'quarantine_disposition':'AMBIGUOUS'}))
    if kind=='parent':
        rich['source_competition_id']='274';rich['quarantine_disposition']=None
        rich['source_competition_context']={'id':274,'primaryId':274,'name':'Primera A','ccode':'COL','isGroup':False}
        keeper.extra_json=dump_json(rich);store_list_extra(keeper,rich)
    store_list_extra(legacy,load_json(legacy.extra_json));db.add(legacy);db.commit();db.info.clear()
    return raw,keeper,legacy


@pytest.mark.parametrize('kind',['parent','women','women-italy','women-germany'])
def test_exact_native_conflicts_link_without_losing_results_or_old_ids(setup,kind,monkeypatch):
    db,source=setup;raw,keeper,legacy=case(db,source,kind)
    before={r.event_id:r.fingerprint for r in (keeper,legacy)}
    for _ in range(2):
        out=consume_board_match(db,fresh(raw),source,{str(raw['id']):[keeper,legacy]});db.commit()
        assert not out.get('rejected'),out
        assert db.query(SportsEvent).count()==2
        assert {r.event_id:r.fingerprint for r in (keeper,legacy)}==before
        assert keeper.status=='finished' and load_json(keeper.score_json)['home']==3
        assert legacy.canonical_event_id==keeper.event_id and not legacy.display_eligible
        assert keeper.display_eligible
    from collector.provider import NinkoCollectedSportsDataProvider
    from database import SessionLocal
    monkeypatch.setattr('collector.detail_enrich.enrich_event_row',lambda *_:None)
    monkeypatch.setattr('collector.provider._history_context',lambda *_:([],{}))
    result=NinkoCollectedSportsDataProvider(session_factory=SessionLocal).get_event(legacy.event_id)
    assert result['id']==keeper.event_id and result['score']['home']==3
    assert result['football_gender']==('men' if kind=='parent' else 'women')


@pytest.mark.parametrize('kind,unsafe',[
 ('parent','group'),('parent','group-label'),('parent','no-explicit-ungrouped'),
 ('parent','inherited-owner'),('parent','wrong-team-id'),('parent','different-parent'),
 ('parent','slim-group'),('parent','wrong-context'),
 ('women','inherited-owner'),('women','wrong-team-id'),('women','bool-team-id'),
 ('women','different-country'),('women','different-leaf'),('women','manual'),
 ('women','slim-policy'),('women','contradictory-final'),('women','independent-tree'),
 ('women','unknown-quarantine'),('women','unknown-flag'),('women','unknown-canonical'),
 ('women','missing-source-country'),('women','contradictory-source-country')])
def test_native_scope_bridge_never_relaxes_unproven_identity_or_policy(setup,kind,unsafe):
    db,source=setup;raw,keeper,legacy=case(db,source,kind)
    row=keeper if kind=='parent' else legacy;meta=load_json(row.extra_json)
    if unsafe=='group':raw['_league']['isGroup']=True
    if unsafe=='group-label':raw['_league']['groupName']='Group A'
    if unsafe=='no-explicit-ungrouped':raw['_league'].pop('isGroup',None)
    if unsafe=='inherited-owner':meta['source_family']='thesportsdb'
    if unsafe in ('wrong-team-id','bool-team-id'):
        parts=load_json(row.participants_json);parts['home']['id']=True if unsafe=='bool-team-id' else '999999';row.participants_json=dump_json(parts)
    if unsafe=='different-parent':raw['_league']['parentLeagueId']=999
    if unsafe=='missing-source-country':raw['_league'].pop('ccode',None)
    if unsafe=='contradictory-source-country':raw['_league']['ccode']='GER'
    if unsafe=='wrong-context':meta['source_competition_context']['id']='other-league'
    if unsafe=='different-country':legacy.competition_id='england-premier-league'
    if unsafe=='unknown-canonical':legacy.competition_id='unregistered-competition'
    if unsafe=='different-leaf':meta['source_competition_id']='938778'
    if unsafe=='manual':meta['manual_hidden']=True
    if unsafe=='independent-tree':meta['collapsed_from']=['existing-child']
    if unsafe=='unknown-quarantine':meta['quarantine_disposition']='REAL_CONTRADICTION'
    if unsafe=='unknown-flag':meta['quality_flags']=['unverified-participants']
    if unsafe=='contradictory-final':legacy.status='finished';legacy.score_json=dump_json({'home':1,'away':9})
    row.extra_json=dump_json(meta);store_list_extra(row,meta)
    if unsafe=='slim-policy':row.list_extra_json=dump_json({'do_not_restore':True})
    if unsafe=='slim-group':row.list_extra_json=dump_json({'source_group_id':'other'})
    db.commit();before=snap(db)
    out=consume_board_match(db,raw,source,{str(raw['id']):[keeper,legacy]});db.commit()
    assert out.get('rejected'),out
    assert snap(db)==before
