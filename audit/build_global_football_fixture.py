"""Deterministically preserve 213 real same-node football league identities."""
from pathlib import Path
import hashlib
import json
import sys
base=Path(sys.argv[1]);chosen={}
def walk(node):
    if isinstance(node,list):
        for value in node:yield from walk(value)
    elif isinstance(node,dict):
        if isinstance(node.get('matches'),list):
            lg={key:node.get(key) for key in ('id','primaryId','parentLeagueId','parentLeagueName','name','ccode','isGroup','groupName')}
            for match in node['matches']:
                if isinstance(match,dict) and isinstance(match.get('home'),dict) and isinstance(match.get('away'),dict):
                    yield {key:match.get(key) for key in ('id','home','away','status')},lg
        else:
            for value in node.values():
                if isinstance(value,(dict,list)):yield from walk(value)
for path in sorted(base.glob('source-*.json')):
    record=json.loads(path.read_text());payload=record.get('payload',{})
    for raw,league in walk(payload):
        key=str(league.get('parentLeagueId') or league.get('primaryId') or league.get('id'))
        raw['_league']=league
        if key not in chosen or (raw.get('status',{}).get('finished') and not chosen[key].get('status',{}).get('finished')):
            chosen[key]=raw
assert len(chosen)==213,len(chosen)
payload={'source':'Read-only FotMob date boards 18–28 September 2026, captured 25 September','note':'Recorded identities and results; test code may vary time/status only in isolated fixtures.','matches':list(chosen.values())}
raw=json.dumps(payload,ensure_ascii=False,indent=2).encode()
assert hashlib.sha256(raw).hexdigest()=='06413dac2eb338989cbe47921fa5ea9a74d4b4f4d7385319e2e81e48234d6132'
Path('tests/fixtures/fotmob_all_competitions_20260925.json').write_bytes(raw)
print('Restored all 213 recorded league identities; immutable fixture hash verified.')
