"""Read-only production acceptance for checkpoint11 artwork and identity repairs."""
import json, urllib.request, hashlib, concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c11-assets');OUT.mkdir(parents=True,exist_ok=True)
BASE='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
report={'checked_at':datetime.now(timezone.utc).isoformat(),'api':{},'browser':[],'image_requests':{},'remaining':[]}
windows={'2026-09-25':('2026-09-24T14:00:00Z','2026-09-25T13:59:59Z'),'2026-09-26':('2026-09-25T14:00:00Z','2026-09-26T13:59:59Z')}
def fetch(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-QA/1.0'}),timeout=30) as response:
  return json.load(response)
images=set()
for day,(lo,hi) in windows.items():
 data=fetch(BASE+'/sports-data/events?'+urlencode({'date_from':lo,'date_to':hi,'unlimited':1}));(OUT/(day+'.json')).write_text(json.dumps(data,ensure_ascii=False))
 rows=data['events'];assert data['snapshot']['complete']
 template=[];missing=[];fifa=[]
 for event in rows:
  for side in ('home','away'):
   participant=event.get(side) or {}
   if not isinstance(participant,dict):continue
   logo=participant.get('logo') or participant.get('image') or participant.get('crest') or participant.get('badge')
   if logo and ('{format}' in logo or '%7Bformat%7D' in logo):template.append({'id':event['id'],'side':side,'url':logo})
   if logo and logo.startswith('https://api.fifa.com/api/v3/picture/'):
    images.add(logo);fifa.append({'id':event['id'],'side':side,'name':participant.get('name'),'url':logo})
   if participant.get('name') and not logo:missing.append({'id':event['id'],'sport':event.get('sport'),'side':side,'name':participant.get('name'),'country_id':participant.get('country_id')})
 report['api'][day]={'events':len(rows),'football':sum(e.get('sport')=='football' for e in rows),'remaining_templates':template,'fifa_assets':fifa,'blank_participant_logo_slots':len(missing),'blank_competition_logo_slots':sum(not e.get('competition_logo') for e in rows)}
 report['remaining'].extend(missing)
 assert not template,(day,template)
ids=['ninko-evt-f150e48ad644076a2b20','ninko-evt-d807549bf94203765dd7','ninko-evt-5c9f97c091957c442eb3','ninko-evt-bb4071086c3ea042f6e9','ninko-evt-8ea488bb6f0bcf5038b7']
report['open_identity_details']={}
for eid in ids:
 data=fetch(BASE+'/sports-data/matches/'+eid);(OUT/('detail-'+eid+'.json')).write_text(json.dumps(data,ensure_ascii=False));e=data['event']
 report['open_identity_details'][eid]={k:e.get(k) for k in ('id','status','home','away','score','competition','competition_id','competition_key')}
images.update(['https://api.fifa.com/api/v3/picture/flags-sq-2/MYA','https://api.fifa.com/api/v3/picture/flags-sq-2/TLS','https://api.fifa.com/api/v3/picture/teams-sq-2/1894031','https://api.fifa.com/api/v3/picture/teams-sq-2/1885981'])
def image_get(url):
 try:
  with urllib.request.urlopen(url,timeout=20) as r:
   body=r.read();result={'http':r.status,'content_type':r.headers.get('Content-Type'),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
   result['valid_image']=result['content_type'].startswith('image/') and len(body)>100
   (OUT/('image-'+hashlib.sha256(url.encode()).hexdigest()[:12]+'.bin')).write_bytes(body)
 except Exception as error:result={'error':str(error),'valid_image':False}
 return url,result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 report['image_requests']=dict(pool.map(image_get,sorted(images)[:40]))
report['image_requests_truncated']=len(images)>40
with sync_playwright() as p:
 browser=p.chromium.launch()
 context=browser.new_context(timezone_id='Australia/Sydney',viewport={'width':1440,'height':1000})
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 for day in windows:
  page.goto(SITE+'/live-scores?sport=football&date='+day,wait_until='domcontentloaded',timeout=60000)
  page.locator('.score-centre-main .score-row-link').first.wait_for(timeout=45000)
  for width in (1440,390,320):
   page.set_viewport_size({'width':width,'height':1000});page.evaluate('window.scrollTo(0,0)')
   flags=page.locator('.score-centre-main img[data-country-flag]');flags.first.wait_for(timeout=20000)
   first=flags.first;first.scroll_into_view_if_needed();page.wait_for_function('() => [...document.querySelectorAll(".score-centre-main img[data-country-flag]")].some(n=>n.complete&&n.naturalWidth>0)',timeout=20000)
   page.wait_for_timeout(400)
   visible=flags.evaluate_all('(nodes)=>nodes.filter(n=>{const r=n.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0&&r.width>0}).map(n=>({country:n.dataset.countryFlag,src:n.currentSrc,loaded:n.complete&&n.naturalWidth>0}))')
   missing=page.locator('[data-asset-missing="country-flag"]').count()
   overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
   item={'day':day,'width':width,'flags_in_dom':flags.count(),'visible_flags':visible,'failed_flag_markers':missing,'overflow':overflow,'javascript_errors':list(errors)}
   item['pass']=bool(visible) and all(x['loaded'] for x in visible) and not missing and not overflow and not errors
   report['browser'].append(item);page.screenshot(path=str(OUT/(day+'-'+str(width)+'.png')),full_page=False)
 report['bundle']=page.locator('script[src]').evaluate_all('(nodes)=>nodes.map(n=>n.src)')
 context.close();browser.close()
report['pass']=all(x['pass'] for x in report['browser']) and all(x['valid_image'] for x in report['image_requests'].values())
(OUT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','open_identity_details')},ensure_ascii=False,indent=2))
assert report['pass'],'Actual production artwork acceptance failed; inspect recorded image and browser evidence'
