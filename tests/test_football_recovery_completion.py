"""Real grouped table fixtures plus current-board/keeper regression tests."""
import json
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta

from collector.adapters import FetchResult
from collector.adapters_fotmob import parse_fotmob_table
from collector.canonical_standings import canonicalize_standing_rows, unwrap_standings
from collector.models import SportsEvent, SportsCompetition, SportsSource, SportsSourceCompetition, SportsSourceHealth
from collector.identity import remember_mapping
from collector.match import match_event
from collector.sources import plan_sources
from collector.util import dump_json,load_json
from database import SessionLocal

FIX=json.loads((Path(__file__).parent/'fixtures/fotmob_nations_tables_20260924.json').read_text())


def test_real_nations_tables_keep_divisions_groups_and_zeroes():
    rows = [row for payload in FIX.values() for row in parse_fotmob_table(payload)]
    canonical = canonicalize_standing_rows(rows,sport='football')
    assert len(canonical)==54
    groups={row['group'] for row in canonical}
    assert len(groups)==14
    assert {row['stage'] for row in canonical} == {f'UEFA Nations League {x}' for x in 'ABCD'}
    serbia = next(row for row in canonical if row['team']=='Serbia')
    assert serbia['group']=='UEFA Nations League A Grp. 2'
    assert {row['team'] for row in canonical if row['group']==serbia['group']}=={'Serbia','Greece','Netherlands','Germany'}
    belgium=next(row for row in canonical if row['team']=='Belgium')
    assert all(belgium[key]==0 for key in ['played','wins','draws','losses','goals_for','goals_against','goal_difference','points'])
    assert all(row['logo'] for row in canonical)


def test_fetch_nations_loads_all_four_and_rejects_partial_divisions():
    from collector.standings_enrich import fetch_competition_standings
    calls=[]
    def get(url):
        lid=url.rsplit('=',1)[-1];calls.append(lid)
        return FetchResult(ok=True,http_status=200,payload=FIX[lid])
    table=fetch_competition_standings('uefa-nations-league',getter=get)
    assert len(unwrap_standings(table))==54
    assert table['season']=='2026/2027'
    assert calls==['9806','9807','9808','9809']
    assert table['schema_revision']==2
    def partial(url):
        return FetchResult(ok=False,http_status=503) if url.endswith('9809') else get(url)
    assert fetch_competition_standings('uefa-nations-league',getter=partial)=={}


def test_existing_source_mapping_updates_canonical_keeper_not_hidden_observation():
    db=SessionLocal()
    try:
        start=datetime.utcnow()-timedelta(hours=5)
        db.add(SportsCompetition(competition_id='uefa-nations-league',sport_id='football',name='Nations',slug='nations',event_model='team_match'))
        db.add(SportsSource(source_id='fm-test',display_name='test',kind='test',enabled=True,adapter_key='fotmob'))
        sides={'home':{'name':'Andorra','id':'10045','logo':'verified-andorra'},'away':{'name':'Malta','id':'8495','logo':'verified-malta'}}
        keeper=SportsEvent(event_id='stable-public',sport_id='football',competition_id='uefa-nations-league',start_time=start,
                           participants_json=dump_json(sides),score_json=dump_json({'home':None,'away':None}),status='scheduled',display_eligible=True,event_family='team_match')
        child=SportsEvent(event_id='old-observation',sport_id='football',competition_id='uefa-nations-league',start_time=start,
                          participants_json=dump_json(sides),score_json=dump_json({'home':1,'away':2}),status='finished',display_eligible=False,
                          canonical_event_id='stable-public',event_family='team_match')
        db.add_all([keeper,child]);db.flush()
        remember_mapping(db,entity_kind='event',ninko_id=child.event_id,source_id='fm-test',source_entity_id='5181874');db.commit()
        incoming={**sides,'sport':'football','competition_key':'uefa-nations-league','source_event_id':'5181874',
                  'start_time':start.isoformat()+'Z','status':'finished','score':{'home':1,'away':2}}
        assert match_event(db,incoming,source_id='fm-test').event_id=='stable-public'
        assert child.display_eligible is False
        child.canonical_event_id=child.event_id;db.flush()
        assert match_event(db,incoming,source_id='fm-test') is None
    finally: db.close()


def test_cached_board_processing_does_not_consume_additional_http_rate_budget(monkeypatch):
    import collector.adapters_fotmob as fm
    from collector.limits import record_hit,_hits
    db=SessionLocal()
    try:
        db.add(SportsCompetition(competition_id='england-premier-league',sport_id='football',name='Premier',slug='premier',event_model='team_match'))
        db.add(SportsSource(source_id='fm-cache',display_name='test',kind='test',enabled=True,adapter_key='fotmob',upstream_family='fotmob',rate_limit_per_minute=1))
        db.add(SportsSourceCompetition(competition_id='england-premier-league',source_id='fm-cache',enabled=True,priority=1,upstream_family='fotmob'))
        db.commit(); record_hit('fm-cache')
        assert not plan_sources(db,'england-premier-league','live_scores')['primary']
        fm._BOARD.clear();fm._BOARD_AT.clear()
        calls=[]
        def get(url):
            calls.append(url);return FetchResult(ok=True,http_status=200,payload={'leagues':[]})
        with fm.shared_board_batch():
            fm._load_boards(get,dates=fm.board_dates(past_days=1,future_days=0),ttl_seconds=fm.LIVE_BOARD_TTL_SECONDS)
            n=len(calls)
            assert plan_sources(db,'england-premier-league','live_scores')['primary']
            assert not plan_sources(db,'england-premier-league','results')['primary']
            assert len(calls)==n and len(_hits['fm-cache'])==1
            db.add(SportsSourceHealth(source_id='fm-cache',rate_limited_until=datetime.utcnow()+timedelta(minutes=3)))
            db.flush()
            assert not plan_sources(db,'england-premier-league','live_scores')['primary']
        assert not plan_sources(db,'england-premier-league','live_scores')['primary']
    finally: db.close()


def test_exact_ireland_alias_dedupes_same_fixture_without_merging_northern_ireland():
    from collector.provider import _dedupe_public_fixture_rows
    from collector.participant_alias import names_equivalent
    assert names_equivalent('Ireland','Republic of Ireland')
    assert not names_equivalent('Ireland','Northern Ireland')
    assert not names_equivalent('Ireland','Ireland U21')
    common={'sport':'football','competition_key':'uefa-nations-league','start_time':'2026-09-24T18:45:00Z','home':{'name':'Kosovo'}}
    stale={**common,'id':'stale','away':{'name':'Republic of Ireland'},'score':{'home':None,'away':None},'status':'scheduled'}
    current={**common,'id':'current','away':{'name':'Ireland'},'score':{'home':1,'away':0},'status':'finished'}
    for rows in ([stale,current],[current,stale]):
        out=_dedupe_public_fixture_rows(rows,{'uefa-nations-league'})
        assert len(out)==1 and out[0]['id']=='current'
