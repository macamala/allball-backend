"""Read-only all-competition football audit; never infer scores or mutate data."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os
import re
import time
import unicodedata

OUT=Path(os.getenv('FOOTBALL_AUDIT_OUT','/tmp/all-football'));OUT.mkdir(parents=True,exist_ok=True)
BASE='https://allball-backend-production.up.railway.app'
NOW=datetime.now(timezone.utc)
TODAY=NOW.date()

def read(target):
    name,url=target
    begin=time.monotonic()
    try:
        with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-read-only-football-audit/1.0'}),timeout=25) as r:
            record={'url':url,'http_status':r.status,'fetched_at':datetime.now(timezone.utc).isoformat(),'payload':json.loads(r.read(12_000_000))}
    except Exception as e:
        record={'url':url,'error':str(e)[:400]}
    record['seconds']=round(time.monotonic()-begin,3)
    (OUT/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False))
    return name,record

def fold(name):
    if isinstance(name,dict):name=name.get('name') or name.get('default') or ''
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(name or '')).encode('ascii','ignore').decode().lower())

def stamp(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def event_key(home,away,start):
    t=stamp(start)
    return (fold(home),fold(away),t.isoformat(timespec='minutes') if t else '')

def source_rows(payload):
    if isinstance(payload,list):
        for node in payload:yield from source_rows(node)
    elif isinstance(payload,dict):
        if isinstance(payload.get('matches'),list):
            league={k:v for k,v in payload.items() if k!='matches'}
            for row in payload['matches']:
                if isinstance(row,dict):yield row,league
        else:
            for value in payload.values():
                if isinstance(value,(dict,list)):yield from source_rows(value)

_,schema=read(('openapi',BASE+'/openapi.json'))
parameters=(schema.get('payload',{}).get('paths',{}).get('/sports-data/events',{}).get('get',{}).get('parameters',[]))
params_info={p['name']:p.get('schema',{}) for p in parameters}
targets=[]
for offset in range(-7,4):
    day=TODAY+timedelta(days=offset)
    params={'sport':'football','date_from':f'{day}T00:00:00Z','date_to':f'{day}T23:59:59Z'}
    if 'limit' in params_info:params['limit']=min(5000,int(params_info['limit'].get('maximum',5000)))
    targets += [('public-'+str(day),BASE+'/sports-data/events?'+urlencode(params)),
                ('source-'+str(day),'https://www.fotmob.com/api/data/matches?date='+day.strftime('%Y%m%d'))]
for path in ('/sports-data/status','/sports-data/live','/sports-data/competitions'):
    if path in schema.get('payload',{}).get('paths',{}):targets.append((path.rsplit('/',1)[-1],BASE+path+'?sport=football'))
with ThreadPoolExecutor(max_workers=3) as pool:data=dict(pool.map(read,targets))
report={'checked_at':NOW.isoformat(),'date_basis':'UTC inclusive days','event_parameters':params_info,'days':[],'competitions':{},'detail_checks':[]}
all_public=[];all_source=[];problems=[]
for offset in range(-7,4):
    day=str(TODAY+timedelta(days=offset))
    pub=data['public-'+day];src=data['source-'+day]
    p=pub.get('payload',{})
    rows=p.get('events',[]) if isinstance(p,dict) else []
    source=list(source_rows(src.get('payload',{})))
    # Provider boards may span date boundaries. Compare only the requested UTC day.
    source=[(r,l) for r,l in source if str((r.get('status')or{}).get('utcTime')or r.get('time')or'')[:10]==day]
    all_public+=rows;all_source+=source
    pk=defaultdict(list)
    for r in rows:pk[event_key(r.get('home'),r.get('away'),r.get('start_time'))].append(r)
    counts=Counter();league_counts=defaultdict(Counter);issues=[]
    for raw,lg in source:
        st=raw.get('status')or{};key=event_key(raw.get('home'),raw.get('away'),st.get('utcTime')or raw.get('time'))
        candidates=pk.get(key,[])
        lc=league_counts[str(lg.get('parentLeagueId')or lg.get('primaryId')or lg.get('id'))]
        lc['upstream']+=1
        state='finished' if st.get('finished') else 'live' if st.get('started') else 'scheduled'
        score=[(raw.get('home')or{}).get('score'),(raw.get('away')or{}).get('score')]
        counts['upstream_'+state]+=1
        if not candidates:
            counts['unmatched']+=1;lc['unmatched']+=1
            issues.append({'kind':'unmatched_name_kickoff','source_id':raw.get('id'),'league':lg.get('name'),'source_status':state,'home':raw.get('home'),'away':raw.get('away'),'start':st.get('utcTime')})
            continue
        counts['matched']+=1;lc['matched']+=1
        for r in candidates:
            actual=r.get('score')or{}
            bad_state=state in ('finished','live') and r.get('status')!=state
            bad_score=all(x is not None for x in score) and [actual.get('home'),actual.get('away')]!=score
            if bad_state or bad_score:
                counts['mismatch']+=1;lc['mismatch']+=1
                issues.append({'kind':'status_or_score','id':r.get('id'),'source_id':raw.get('id'),'league':lg.get('name'),'competition':r.get('competition_key'),'home':fold(raw.get('home')),'away':fold(raw.get('away')),'start':st.get('utcTime'),'source_status':state,'public_status':r.get('status'),'source_score':score,'public_score':actual,'updated_at':r.get('updated_at')})
    stale=[r for r in rows if r.get('status')=='scheduled' and stamp(r.get('start_time')) and stamp(r['start_time'])<NOW-timedelta(hours=4)]
    for key,value in league_counts.items():
        dest=report['competitions'].setdefault(key,{'counts':Counter(),'names':set()})
        dest['counts'].update(value)
        dest['names'].update(str(l.get('name')) for _,l in source if str(l.get('parentLeagueId')or l.get('primaryId')or l.get('id'))==key)
    report['days'].append({'date':day,'http_status':pub.get('http_status'),'source_http_status':src.get('http_status'),'public_total':len(rows),'source_total':len(source),'public_status':dict(Counter(r.get('status') for r in rows)),'counts':dict(counts),'scheduled_over_4h':len(stale),'duplicate_pairs':sum(len(v)-1 for v in pk.values()),'response_meta':{k:v for k,v in p.items() if k not in ('events','matches')},'issues':issues})
    problems+=issues
# One detail per mismatched public competition, capped to bound production load.
chosen={}
for item in problems:
    if item.get('id') and item['competition'] not in chosen:chosen[item['competition']]=item
with ThreadPoolExecutor(max_workers=3) as pool:
    details=dict(pool.map(read,[('detail-'+i['id'],BASE+'/sports-data/matches/'+i['id']) for i in list(chosen.values())[:25]]))
for key,record in details.items():
    event=(record.get('payload')or{}).get('event')or{}
    report['detail_checks'].append({'id':key[7:],'http_status':record.get('http_status'),'event_id':event.get('id'),'status':event.get('status'),'score':event.get('score'),'competition':event.get('competition_key'),'fields':list(event)})
for value in report['competitions'].values():value['counts']=dict(value['counts']);value['names']=sorted(value['names'])
report['totals']={'public':len(all_public),'upstream':len(all_source),'leagues':len(report['competitions']),'counts':dict(sum((Counter(d['counts']) for d in report['days']),Counter()))}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'totals':report['totals'],'days':[{k:v for k,v in d.items() if k not in ('issues','response_meta')} for d in report['days']],'sample_mismatches':[i for i in problems if i['kind']=='status_or_score'][:30]},ensure_ascii=False,indent=2))
