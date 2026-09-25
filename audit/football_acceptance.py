"""Read-only football acceptance across every upstream league; no fixed league list.

Exact-name/kickoff unmatched rows remain UNRESOLVED, not claimed missing. Pregame
0-0 is not a played result. Independent HTTP errors are never a healthy empty day.
"""
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE='https://allball-backend-production.up.railway.app'
LIVE={'live','halftime','break','ht','inplay','in_play'}
FINAL={'finished','ft','aet','pen','awarded','ended','final'}

def read(target):
    name,url=target
    try:
        with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-read-only-football-acceptance/1.0'}),timeout=25) as response:
            record={'url':url,'http_status':response.status,'fetched_at':datetime.now(timezone.utc).isoformat(),'payload':json.loads(response.read(15_000_000))}
    except Exception as error:
        record={'url':url,'error':str(error)[:400]}
    return name,record

def folded(value):
    if isinstance(value,dict):value=value.get('name') or value.get('default') or ''
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower())

def instant(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (TypeError,ValueError):return None

def integer(value):
    try:return int(value) if value is not None and value!='' else None
    except (TypeError,ValueError):return None

def key(home,away,start):
    value=instant(start)
    return folded(home),folded(away),value.isoformat(timespec='minutes') if value else ''

def source_rows(node):
    if isinstance(node,list):
        for item in node:yield from source_rows(item)
    elif isinstance(node,dict):
        if isinstance(node.get('matches'),list):
            league={k:v for k,v in node.items() if k!='matches'}
            for row in node['matches']:
                if isinstance(row,dict):yield row,league
        else:
            for item in node.values():
                if isinstance(item,(list,dict)):yield from source_rows(item)

def source_state(raw):
    status=raw.get('status') or {}
    reason=status.get('reason') or {}
    text=folded(str(reason.get('short') or reason.get('long') or ''))
    if 'postp' in text:return 'postponed'
    if 'cancel' in text or 'cancl' in text:return 'cancelled'
    if 'aband' in text or 'abnd' in text:return 'abandoned'
    if 'susp' in text:return 'suspended'
    if 'delay' in text:return 'delayed'
    if status.get('finished'):return 'finished'
    if status.get('started'):return 'live'
    return 'scheduled'

def source_score(raw,state):
    if state not in ('finished','live'):return [None,None]
    value=(raw.get('status') or {}).get('scoreStr') or ''
    match=re.fullmatch(r'\s*(\d+)\s*[-:]\s*(\d+)\s*',str(value))
    if match:return [int(match[1]),int(match[2])]
    return [integer((raw.get(side) or {}).get('score')) for side in ('home','away')]

def analyze(records,checked_at):
    days=[];totals=Counter();competitions=defaultdict(Counter);issues=[];asset_urls=set()
    for name,source in sorted(records.items()):
        if not name.startswith('source-'):continue
        date=name[7:];public=records.get('public-'+date,{})
        if public.get('http_status')!=200 or source.get('http_status')!=200:
            days.append({'date':date,'error':'http_or_parse_failure','public':public.get('http_status'),'source':source.get('http_status')});totals['failed_days']+=1;continue
        public_rows=(public.get('payload') or {}).get('events') or []
        upstream=[(r,l) for r,l in source_rows(source.get('payload')) if str((r.get('status') or {}).get('utcTime') or '')[:10]==date]
        lookup=defaultdict(list)
        for row in public_rows:
            lookup[key(row.get('home'),row.get('away'),row.get('start_time'))].append(row)
            if row.get('competition_logo'):asset_urls.add(row['competition_logo'])
        count=Counter(public=len(public_rows),source=len(upstream));local=[]
        for raw,league in upstream:
            start=(raw.get('status') or {}).get('utcTime');state=source_state(raw);expected=source_score(raw,state)
            found=lookup.get(key(raw.get('home'),raw.get('away'),start),[])
            league_id=str(league.get('parentLeagueId') or league.get('primaryId') or league.get('id'))
            competition=competitions[league_id];competition['source']+=1;count['source_'+state]+=1
            if not found:
                count['unresolved_identity']+=1;competition['unresolved_identity']+=1
                local.append({'kind':'unresolved_identity','date':date,'league_id':league_id,'league':league.get('name'),'source_id':str(raw.get('id')),'home':(raw.get('home') or {}).get('name'),'away':(raw.get('away') or {}).get('name'),'start':start,'source_status':state,'source_score':expected})
                continue
            count['matched']+=1;competition['matched']+=1
            for row in found:
                actual=[integer((row.get('score') or {}).get(side)) for side in ('home','away')]
                public_state=row.get('status')
                same_state=(public_state in FINAL if state=='finished' else public_state in LIVE if state=='live' else public_state==state)
                # Non-played outcomes are counted separately; delayed/scheduled can change between reads.
                bad_state=state in ('finished','live') and not same_state
                bad_score=state in ('finished','live') and all(v is not None for v in expected) and expected!=actual
                if bad_state or bad_score:
                    count['played_mismatch']+=1;competition['played_mismatch']+=1
                    local.append({'kind':'played_mismatch','date':date,'id':row.get('id'),'league_id':league_id,'league':league.get('name'),'source_id':str(raw.get('id')),'home':(raw.get('home') or {}).get('name'),'away':(raw.get('away') or {}).get('name'),'start':start,'source_status':state,'public_status':public_state,'source_score':expected,'public_score':actual})
                elif state in ('finished','live'):
                    count['played_agree']+=1;competition['played_agree']+=1
        count['duplicate_exact_pairs']=sum(len(v)-1 for v in lookup.values())
        count['scheduled_over_4h']=sum(row.get('status')=='scheduled' and bool(instant(row.get('start_time'))) and instant(row['start_time'])<checked_at-timedelta(hours=4) for row in public_rows)
        totals.update(count);issues+=local
        days.append({'date':date,**dict(count),'public_status':dict(Counter(row.get('status') for row in public_rows))})
    return {'checked_at':checked_at.isoformat(),'date_basis':'UTC','pass_played_comparison':not totals['played_mismatch'] and not totals['failed_days'],'scope_note':'Unresolved exact names/kickoff are not proof of missing fixtures; all-sport completeness, lineups and real in-play latency require separate acceptance.','days':days,'totals':dict(totals),'competition_count':len(competitions),'competitions':{k:dict(v) for k,v in competitions.items()},'issues':issues,'competition_asset_urls':sorted(asset_urls)}

parser=argparse.ArgumentParser();parser.add_argument('--offline');parser.add_argument('--out',default='/tmp/football-acceptance');args=parser.parse_args()
out=Path(args.out);out.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc)
if args.offline:
    records={path.stem:json.loads(path.read_text()) for path in Path(args.offline).glob('*.json') if path.stem.startswith(('source-','public-'))}
else:
    targets=[]
    for offset in range(-7,4):
        date=now.date()+timedelta(days=offset)
        params={'sport':'football','unlimited':'1','date_from':f'{date}T00:00:00Z','date_to':f'{date}T23:59:59Z'}
        targets += [('public-'+str(date),BASE+'/sports-data/events?'+urlencode(params)),('source-'+str(date),'https://www.fotmob.com/api/data/matches?date='+date.strftime('%Y%m%d'))]
    with ThreadPoolExecutor(max_workers=3) as pool:records=dict(pool.map(read,targets))
    for name,record in records.items():(out/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False))
report=analyze(records,now)
# Inspect one real mismatch per source league, with an upper bound on public detail requests.
if not args.offline:
    selected={}
    for issue in report['issues']:
        if issue['kind']=='played_mismatch':selected.setdefault(issue['league_id'],issue)
    ids=[issue['id'] for issue in list(selected.values())[:24]]
    ids+=['ninko-evt-6d8bf3121dc158b647e1','ninko-evt-86345b6cb47a7c4b8524']
    with ThreadPoolExecutor(max_workers=3) as pool:details=dict(pool.map(read,[('detail-'+eid,BASE+'/sports-data/matches/'+eid) for eid in ids]))
    for name,record in details.items():(out/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False))
    report['detail_summary']={name[7:]:{'http':rec.get('http_status'),'id':((rec.get('payload') or {}).get('event') or {}).get('id'),'status':((rec.get('payload') or {}).get('event') or {}).get('status'),'score':((rec.get('payload') or {}).get('event') or {}).get('score')} for name,rec in details.items()}
(out/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('issues','competitions','competition_asset_urls')},ensure_ascii=False,indent=2))
