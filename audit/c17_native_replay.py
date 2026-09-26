"""Read-only replay of captured native category, suffix and scorer evidence."""
import json,sys
from pathlib import Path
from collector.football_category import native_info,native_gender
from collector.fotmob_crosswalk import _fotmob_competition_identity
from collector.fotmob_rich import verified_detail_identity
from collector.football_scorers import scorer_spec,parse_scorers
from collector.fotmob_tables import parse_tables
source,native,scorers,out=map(Path,sys.argv[1:5]);report={'categories':[],'details':[],'scorers':[]}
for f in sorted(source.glob('native-*.json')):
 for league in json.loads(f.read_text())['payload']['leagues']:
  info=native_info(league)
  if not info:continue
  key=_fotmob_competition_identity({'_league':league})[0]
  gender=native_gender(league)
  if info['gender']=='female':assert gender=='women' and key!='mexico-liga-mx'
  report['categories'].append({'parent':info['parent'],'key':key,'gender':gender})
for f in native.glob('*-detail.json'):
 root=json.loads(f.read_text())['payload'];g=root['general'];identity={'start_time':g['matchTimeUTCDate'],**{s:{**g[s+'Team'],'name':g[s+'Team']['name']+' (W)'} for s in ['home','away']}}
 assert verified_detail_identity(root,g['matchId'],identity)
 report['details'].append(g['matchId'])
for f in scorers.glob('*.json'):
 evidence=json.loads(f.read_text());pid=str(evidence['league']['id']);root=json.loads((native/(pid+'.json')).read_text())['payload']
 context={'parent':pid,'season':root['details']['selectedSeason'],'table_rows':parse_tables(root),'_scorer_specs':root['stats']['players']}
 spec=scorer_spec(context);assert spec
 rows=parse_scorers(evidence['payload'],context,spec)
 assert rows and rows[0]['goals']>=0
 report['scorers'].append({'parent':pid,'rows':len(rows),'top':rows[0]})
out.mkdir(exist_ok=True);(out/'native-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Categories',len(report['categories']),'female matches',sum(r['gender']=='women' for r in report['categories']),'detail identities',report['details'],'scorer leagues',[(r['parent'],r['rows']) for r in report['scorers']])
