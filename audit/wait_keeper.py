"""Bounded read-only wait for the normal collector's rolling-deploy handoff."""
from datetime import datetime,time as daytime,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from pathlib import Path
import json,time
now=datetime.now(ZoneInfo('Australia/Sydney'))
start=datetime.combine(now.date(),daytime(),tzinfo=now.tzinfo)
params={'sport':'football','competition':'uefa-nations-league','date_from':start.astimezone(timezone.utc).isoformat(),'date_to':(start+timedelta(days=1,microseconds=-1)).astimezone(timezone.utc).isoformat()}
url='https://allball-backend-production.up.railway.app/sports-data/events?'+urlencode(params)
out=Path('/tmp/football-release-check');out.mkdir(exist_ok=True)
history=[]
for attempt in range(12):
    try:
        with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-release-QA/1.0'}),timeout=15) as response:
            data=json.loads(response.read())
        rows=data.get('events') or data.get('matches') or []
        matches=[r for r in rows if (r.get('home')or{}).get('name')=='Andorra' and (r.get('away')or{}).get('name')=='Malta']
        record={'attempt':attempt+1,'checked_at':datetime.now(timezone.utc).isoformat(),'rows':len(rows),'matches':matches}
        history.append(record)
        if len(matches)==1 and (matches[0].get('score')or{}).get('home')==1 and (matches[0].get('score')or{}).get('away')==2:
            print('Canonical Andorra result visible on public day board',flush=True)
            break
    except Exception as exc:
        history.append({'attempt':attempt+1,'error':str(exc)[:200]})
    if attempt<11:time.sleep(10)
(out/'keeper-preflight.json').write_text(json.dumps(history,ensure_ascii=False))
print(json.dumps({'attempts':len(history),'last':history[-1]},ensure_ascii=False))
