"""Replay captured actual native facts, isolated SQLite only; not production proof."""
import json,sys
from pathlib import Path
from datetime import datetime,timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from collector.models import Base,SportsCompetition,SportsSourceCompetition,SportsEvent
from collector.util import dump_json,parse_datetime
from collector.competition_hub import _fetch_native
from collector.football_history import parse_history
from types import SimpleNamespace
folder=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);report=[]
for lid,key,expected in [('108','england-league-one',552),('126','ireland-premier-division',180)]:
    root=json.loads((folder/f'native-league-{lid}.json').read_text())['payload']
    fixture=next(m for m in root['fixtures']['allMatches'] if abs((parse_datetime(m['status']['utcTime'])-datetime.utcnow()).total_seconds())<6*86400)
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(SportsCompetition(competition_id=key,sport_id='football',name=root['details']['name'],slug=key,event_model='team_match'))
        db.add(SportsSourceCompetition(competition_id=key,source_id='fotmob',upstream_family='fotmob',source_competition_id=lid,enabled=True))
        db.add(SportsEvent(event_id='test-witness',fingerprint='test-witness',sport_id='football',competition_id=key,event_family='team_match',display_eligible=True,status='scheduled',start_time=parse_datetime(fixture['status']['utcTime']),participants_json=dump_json({s:fixture[s] for s in ['home','away']}),extra_json=dump_json({'source_event_ids':{'fotmob':str(fixture['id'])}})))
        db.commit();result=_fetch_native(db,key,'',lambda url:SimpleNamespace(ok=True,payload=None if 'matchDetails' in url else root))
        assert len(result['events'])==expected,(lid,len(result.get('events',[])))
        assert len(result['table_views']['home'])==len(result['table_views']['away'])==(24 if lid=='108' else 10)
        report.append({'scope':key,'fixtures':len(result['events']),'season':result['season'],'home_rows':len(result['table_views']['home']),'away_rows':len(result['table_views']['away']),'witness_source_id':str(fixture['id'])})
        (out/f'replayed-{lid}.json').write_text(json.dumps(result,ensure_ascii=False))
for mid,expected in [('5100971',57),('6232978',1)]:
    root=json.loads((folder/f'native-detail-{mid}.json').read_text())['payload'];history=parse_history(root)
    assert len(history['h2h'])==expected
    report.append({'match':mid,'historical_meetings':len(history['h2h']),'home_form':len(history.get('form',{}).get('home',{}).get('results',[])),'away_form':len(history.get('form',{}).get('away',{}).get('results',[]))})
    (out/f'history-{mid}.json').write_text(json.dumps(history,ensure_ascii=False))
(out/'native-replay.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
