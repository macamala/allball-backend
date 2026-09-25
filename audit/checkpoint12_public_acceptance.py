"""C12 production-only evidence; no mocks, writes, or manual result changes."""
import asyncio, json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright
OUT = Path('/tmp/c12-public'); OUT.mkdir(parents=True, exist_ok=True)
API = 'https://allball-backend-production.up.railway.app'
IDS = ['ninko-evt-bb4071086c3ea042f6e9', 'ninko-evt-8ea488bb6f0bcf5038b7', 'ninko-evt-5c9f97c091957c442eb3', 'ninko-evt-d807549bf94203765dd7', 'ninko-evt-f150e48ad644076a2b20', 'ninko-evt-86345b6cb47a7c4b8524']
def get(eid):
    with urllib.request.urlopen(urllib.request.Request(API+'/sports-data/matches/'+eid, headers={'Accept':'application/json'}), timeout=30) as r:
        payload=json.load(r)
    (OUT/(eid+'.json')).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    e=payload.get('event') or {}
    return {'requested_id':eid, **{k:e.get(k) for k in ('id','home','away','status','score','competition_key','start_time')}}
async def main():
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'details':[], 'browser':[], 'errors':[]}
    with ThreadPoolExecutor(max_workers=3) as pool: result['details']=list(pool.map(get, IDS))
    result['sligo_converged']=result['details'][0]['id']==result['details'][1]['id'] and result['details'][0]['status']=='finished' and (result['details'][0]['score'] or {}).get('away')==1
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        ctx=await browser.new_context(viewport={'width':1440,'height':1000}, timezone_id='Australia/Sydney', locale='en-AU')
        page=await ctx.new_page(); network=[]; by_id={}; tasks=[]
        page.on('pageerror',lambda e:result['errors'].append(str(e)))
        async def response(r):
            if '/sports-data/' not in r.url:return
            network.append({'url':r.url,'status':r.status})
            if r.status==200:
                try:
                    data=await r.json()
                    for e in (data.get('events') or data.get('matches') or []):
                        if isinstance(e,dict) and e.get('id'):by_id[e['id']]=e
                except Exception:pass
        def capture(r): tasks.append(asyncio.create_task(response(r)))
        page.on('response',capture)
        for sport in ('football','tennis','all'):
            await page.goto('https://ninkosports.com/live-scores?date=2026-09-25&sport='+sport,wait_until='domcontentloaded')
            await page.wait_for_selector('.score-row-link',timeout=45000)
            await page.wait_for_timeout(1200)
            await asyncio.gather(*tasks); tasks.clear()
            for width in (1440,390,320):
                await page.set_viewport_size({'width':width,'height':1000});await page.wait_for_timeout(300)
                dom=await page.evaluate('''() => ({overflow:document.documentElement.scrollWidth>innerWidth+1, liveCounter:document.querySelector('.score-live-global')?.textContent||'', mainLive:document.querySelectorAll('.score-centre-main .score-row.is-live').length, mainIds:[...document.querySelectorAll('.score-centre-main .score-row-link')].map(e=>e.getAttribute('href').split('/').pop()), sideIds:[...document.querySelectorAll('.score-centre-aside .score-row-link')].map(e=>e.getAttribute('href').split('/').pop()), topText:document.querySelector('.score-aside-links')?.textContent||'', names:[...document.querySelectorAll('.score-centre-aside .score-name[title]')].map(e=>({text:e.textContent,title:e.title,width:e.getBoundingClientRect().width,whiteSpace:getComputedStyle(e).whiteSpace,ellipsis:getComputedStyle(e).textOverflow,scroll:e.scrollWidth,client:e.clientWidth})), sidebarSets:document.querySelectorAll('.score-centre-aside .score-sets').length})''')
                unknown=[eid for eid in dom['sideIds'] if eid not in by_id]
                wrong=[eid for eid in dom['sideIds'] if sport!='all' and (by_id.get(eid)or{}).get('sport')!=sport]
                passed=not dom['overflow'] and not wrong and not unknown and dom['sidebarSets']==0
                if width==1440:
                    passed=passed and all(x['whiteSpace']=='normal' and x['ellipsis']!='ellipsis' and x['width']>=70 and x['text']==x['title'] for x in dom['names'])
                if sport=='football':passed=passed and 'WTA' not in dom['topText'] and 'GBGB' not in dom['topText']
                if sport=='tennis':passed=passed and 'Nations League' not in dom['topText']
                if dom['liveCounter'].strip():passed=passed and int(re.search(r'\d+',dom['liveCounter']).group())==dom['mainLive']
                else:passed=passed and dom['mainLive']==0
                result['browser'].append({'sport':sport,'width':width,'pass':passed,'unknown':unknown,'wrong_sport':wrong,**dom})
                await page.screenshot(path=str(OUT/f'{sport}-{width}.png'),full_page=False)
        await asyncio.gather(*tasks)
        result['network']=network
        result['source_rows_seen']={eid:{k:e.get(k) for k in ('sport','competition_key','status','home','away')} for eid,e in by_id.items()}
        result['bundle']=await page.evaluate("[...document.scripts].map(s=>s.src).filter(s=>s.includes('/assets/'))")
        await browser.close()
    (OUT/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_rows_seen','network')},ensure_ascii=False,indent=2))
    assert not result['errors'] and all(x['pass'] for x in result['browser'])
    # Open old-link identities are evidence, not silently waived as solved.
if __name__=='__main__':asyncio.run(main())
