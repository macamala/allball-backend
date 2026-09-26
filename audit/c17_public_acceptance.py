"""C17 real public/API/browser acceptance; no mocked responses or DB writes."""
import json,re,time,gzip,urllib.request,unicodedata
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from playwright.sync_api import sync_playwright
OUT=Path('/tmp/c17-public');OUT.mkdir(exist_ok=True)
API='https://allball-backend-production.up.railway.app';SITE='https://ninkosports.com'
REPORT={'at':datetime.now(timezone.utc).isoformat(),'api':[],'browser':[]}
def get(name,url):
    start=time.monotonic();record={'url':url,'at':datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'NinkoSports-owned-site-QA/17'}),timeout=45) as r:
            data=r.read();data=gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data
            record.update(http=r.status,payload=json.loads(data))
    except Exception as e:record['error']=str(e)
    record['seconds']=time.monotonic()-start;(OUT/(name+'.json')).write_text(json.dumps(record,ensure_ascii=False));return record

def checked(name,action):
    row={'name':name,'pass':False}
    try:row.update(action() or {});row['pass']=True
    except Exception as e:row['error']=repr(e)
    REPORT['api'].append(row)

def stamp(value):return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
def text(value):return ''.join(c for c in unicodedata.normalize('NFKD',re.sub(r'\s*\(W\)\s*$','',str(value),flags=re.I)).casefold() if c.isalnum())
before=json.loads(Path('/tmp/c17-before/cohort.json').read_text())
current=get('cohort',before['url']);assert current.get('http')==200,current
EVENTS=current['payload']['events'];BYID={e['id']:e for e in EVENTS}
def retention():
    a={e['id'] for e in before['payload']['events']};assert not a-set(BYID),sorted(a-set(BYID))
    assert all(e.get('football_gender') in ('men','women','unknown') for e in EVENTS)
    return {'before':len(a),'after':len(BYID),'removed':0,'added':len(set(BYID)-a),'categories':dict(Counter(e['football_gender'] for e in EVENTS))}
checked('Canonical ID retention and explicit categories',retention)

def native_categories():
    from collector.football_category import native_gender
    from collector.fotmob_crosswalk import _fotmob_competition_identity
    compared={};mismatches=[]
    for path in Path('/tmp/c17-source').glob('native-*.json'):
        for league in json.loads(path.read_text())['payload']['leagues']:
            gender=native_gender(league)
            if not gender:continue
            for match in league.get('matches',[]):
                candidates=[e for e in EVENTS if abs(stamp(e['start_time'])-stamp(match['status']['utcTime']))<=60 and all(str(e[s].get('id'))==str(match[s].get('id')) or text(e[s]['name'])==text(match[s]['name']) for s in ('home','away'))]
                if len(candidates)!=1:continue
                e=candidates[0];compared[e['id']]=gender
                if e['football_gender']!=gender:mismatches.append([e['id'],gender,e['football_gender']])
                if gender=='women' and e['competition_key'] in ('mexico-liga-mx','fa-cup'):mismatches.append([e['id'],'women in male competition'])
    assert len(compared)>100 and 'women' in compared.values(),len(compared)
    assert not mismatches,mismatches[:10]
    return {'matched_native_events':len(compared),'categories':dict(Counter(compared.values()))}
checked('Independent captured native gender identities',native_categories)

TOP='football-nor-toppserien';MXW='football-mex-liga-mx-femenil-apertura'
HUBS={}
for key in (TOP,MXW,'mexico-liga-mx'):
    HUBS[key]=get('hub-'+key,API+'/sports-data/competitions/'+key+'/hub')
def women_hub():
    d=HUBS[TOP];assert d.get('http')==200;h=d['payload'];expected={e['id'] for e in EVENTS if e['competition_key']==TOP}
    assert expected and expected<={e.get('id') for e in h['events']}
    old=json.loads(Path('/tmp/c17-before/toppserien.json').read_text())['payload'];assert {e.get('id') for e in old['events'] if e.get('id')}<={e.get('id') for e in h['events']}
    e=BYID['ninko-evt-20117688e59bd5e8ef68'];detail=get('women-match',API+'/sports-data/matches/'+e['id']);assert detail.get('http')==200
    public=detail['payload']['event'];assert public['id']==e['id'] and public['football_gender']=='women' and public['competition_key']==TOP
    return {'season':h['season'],'records':len(h['events']),'linked':h['coverage']['linked_match_details'],'cohort_links_retained':len(expected),'detail_id':public['id']}
checked('Women season canonical links and detail category',women_hub)

def mexico_isolation():
    w=HUBS[MXW];m=HUBS['mexico-liga-mx'];assert w.get('http')==m.get('http')==200
    women={e['id'] for e in EVENTS if e['competition_key']==MXW};assert women
    men_ids={e.get('id') for e in m['payload']['events']};assert not women&men_ids
    assert women<={e.get('id') for e in w['payload']['events']}
    return {'women_cohort':len(women),'women_hub_records':len(w['payload']['events']),'male_hub_records':len(m['payload']['events']),'cross_category_ids':0}
checked('Liga MX and Femenil separate competition hubs',mexico_isolation)
SCORERS={}
for key,lid,required in [('ireland-premier-division','126',True),('england-league-one','108',True),(TOP,'331',True),('mexico-liga-mx','230',False),(MXW,'9906',False)]:
    def check_scorer(key=key,lid=lid,required=required):
        p=get('scorers-'+key,API+'/sports-data/competitions/'+key+'/scorers');assert p.get('http')==200;p=p['payload'];SCORERS[key]=p
        if not p.get('available'):
            assert not required,(key,p)
            return {'available':False,'reason':p.get('reason'),'not_claimed_complete':True}
        n=get('native-league-'+lid,'https://www.fotmob.com/api/data/leagues?id='+lid);assert n.get('http')==200;n=n['payload'];assert p['season']==n['details']['selectedSeason']
        specs=[s for s in n['stats']['players'] if ((s.get('participant') or {}).get('stat') or {}).get('name')=='goals'];assert specs
        source=get('native-goals-'+lid,specs[0]['fetchAllUrl']);assert source.get('http')==200
        goals=[r for l in source['payload']['TopLists'] if l.get('StatName')=='goals' for r in l['StatList']];native={str(r.get('ParticiantId') or r.get('ParticipantId')):r for r in goals}
        for row in p['rows']:
            r=native[row['player_id']];assert row['name']==r['ParticipantName'] and row['team_id']==str(r['TeamId']) and row['goals']==int(float(r['StatValue'])) and row['penalties']==int(float(r['SubStatValue']))
        assert p['rows'] and p['football_gender']==('women' if lid in ('331','9906') else 'men')
        return {'available':True,'rows':len(p['rows']),'season':p['season'],'gender':p['football_gender'],'top':p['rows'][0],'source_rows':len(goals)}
    checked('Verified season scorers '+key,check_scorer)

def negatives():
    for name,suffix in [('archive','?season=1900'),('wronggroup','?group=unverified')]:
        d=get('scorers-'+name,API+'/sports-data/competitions/ireland-premier-division/scorers'+suffix);assert d.get('http')==200 and not d['payload']['rows'] and not d['payload']['available']
    return {'unknown_scope_never_substitutes_current_scorers':True}
checked('Scorer season and group negative cases',negatives)

with sync_playwright() as pw:
    browser=pw.chromium.launch()
    for width in (1440,390,320):
        context=browser.new_context(viewport={'width':width,'height':1000},timezone_id='Australia/Sydney',locale='en-AU');page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)));row={'width':width,'pass':False}
        try:
            page.goto(SITE+'/live-scores?sport=football&date=2026-09-26',wait_until='domcontentloaded');page.locator('.football-category-filter').wait_for(timeout=45000);page.locator('.score-row-link[href]').first.wait_for(timeout=45000)
            results={}
            for category,label in [('women','Women'),('men','Men'),('all','All football')]:
                page.locator('.football-category-filter').get_by_role('button',name=re.compile('^'+label+r'\b')).click()
                page.wait_for_function('(label)=>[...document.querySelectorAll(".football-category-filter button")].some(b=>b.textContent.startsWith(label)&&b.getAttribute("aria-pressed")==="true")',label)
                links=page.locator('.score-row-link[href]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href").split("/").pop())')
                assert links
                assert all(i in BYID for i in links)
                if category!='all':assert all(BYID[i]['football_gender']==category for i in links)
                results[category]=len(links)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(OUT/f'board-{category}-{width}.png'),full_page=True)
                if category=='women':
                    page.reload(wait_until='domcontentloaded');page.locator('.score-row-link[href]').first.wait_for(timeout=45000);assert 'category=women' in page.url
            assert results['all']>=results['women']+results['men']
            for key in ('ireland-premier-division',TOP):
                data=SCORERS[key];assert data.get('available')
                page.goto(SITE+'/scores/competition/'+key+'/standings?sport=football&tab=scorers',wait_until='domcontentloaded');page.locator('.scorer-row').first.wait_for(timeout=45000)
                assert page.locator('.scorer-row').count()==min(25,len(data['rows']))
                assert page.locator('.scorer-identity > a').first.inner_text()==data['rows'][0]['name']
                assert int(page.locator('.scorer-goals strong').first.inner_text())==data['rows'][0]['goals']
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(OUT/f'scorers-{key}-{width}.png'),full_page=True)
                if len(data['rows'])>25:page.get_by_role('button',name='Show more scorers',exact=True).click();assert page.locator('.scorer-row').count()==min(50,len(data['rows']))
                tid=data['rows'][0]['team_id'];page.get_by_label('Scorer team',exact=True).select_option(tid)
                expected=[r for r in data['rows'] if r['team_id']==tid];assert page.locator('.scorer-row').count()==min(25,len(expected))
                target=page.locator('.scorer-identity > a').first;player_name=target.inner_text();target.click();page.locator('.entity-hero h1').wait_for(timeout=45000);assert page.locator('.entity-hero h1').inner_text()==player_name
                page.go_back(wait_until='domcontentloaded');page.locator('.scorer-row').first.wait_for(timeout=45000)
            assert not errors,errors;row.update(pass_=True,counts=results,scorer_journeys=2,js_errors=errors);row['pass']=True
        except Exception as e:row['error']=repr(e);row['js_errors']=errors;page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
        REPORT['browser'].append(row);context.close()
    browser.close()
(OUT/'acceptance.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2));print(json.dumps(REPORT,ensure_ascii=False,indent=2))
assert all(x['pass'] for x in REPORT['api']+REPORT['browser']), 'C17 public acceptance has failed checks; inspect evidence'
