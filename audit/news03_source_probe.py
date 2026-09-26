"""Bounded source metadata audit only: no articles stored, no AI or production calls."""
import hashlib
import json
import socket
import ipaddress
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser
import httpx
import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot.news_source_catalog import SOURCE_CANDIDATES, news_sport_ids, validate_catalog
from bot.extract import parse_feed_datetime

USER_AGENT = "NinkoSportsNewsAudit/1.0 (+https://ninkosports.com)"
MAX_BYTES = 2000000
NOW = datetime.now(timezone.utc)


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('unsafe_url')
    addresses = socket.getaddrinfo(parts.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('nonpublic_address')


def read(url):
    for _ in range(4):
        public_url(url)
        with httpx.Client(timeout=httpx.Timeout(8), follow_redirects=False, headers={'User-Agent':USER_AGENT}) as client:
            with client.stream('GET',url) as response:
                if response.status_code in (301,302,303,307,308):
                    location=response.headers.get('location')
                    if not location: raise ValueError('redirect_without_location')
                    target=urljoin(url,location)
                    old_host=(urlsplit(url).hostname or '').removeprefix('www.')
                    new_host=(urlsplit(target).hostname or '').removeprefix('www.')
                    if old_host != new_host: raise ValueError('cross_host_redirect_needs_review')
                    url=target; continue
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>MAX_BYTES: raise ValueError('oversize')
                return response.status_code,url,response.headers.get('content-type',''),bytes(data)
    raise ValueError('redirect_limit')


class FeedLinks(HTMLParser):
    def __init__(self): super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='link' and a.get('type') in ('application/rss+xml','application/atom+xml') and a.get('href'):
            self.links.append(a['href'])


def probe(candidate):
    sport,publisher,url,kind=candidate
    result={'sport':sport,'publisher':publisher,'url':url,'expected':kind,'state':'UNVERIFIED','reuse_rights':'NOT_VERIFIED','publication_ready':False}
    try:
        parts=urlsplit(url); robot_url=f'{parts.scheme}://{parts.netloc}/robots.txt'
        status,_,_,raw=read(robot_url)
        if status==200:
            robots=RobotFileParser();robots.parse(raw.decode('utf-8','replace').splitlines())
            if not robots.can_fetch(USER_AGENT,url):
                result.update(state='ROBOTS_DISALLOWED');return result
        elif status not in (404,410):
            result.update(state='ROBOTS_UNVERIFIED',robots_status=status);return result
        status,final,content_type,raw=read(url)
        result.update(http_status=status,final_url=final,content_type=content_type,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if status!=200:
            result['state']='ACCESS_BLOCKED' if status in (401,403,429) else 'HTTP_ERROR';return result
        parsed=feedparser.parse(raw)
        rows=[]
        if parsed.version and parsed.entries:
            for entry in parsed.entries[:30]:
                link=entry.get('link');title=entry.get('title');stamp=parse_feed_datetime(entry)
                if not isinstance(link,str) or not link.startswith('https://') or not isinstance(title,str) or not title.strip(): continue
                rows.append({'title':title[:220],'url':link,'published_at':stamp.isoformat() if stamp else None,'timezone_known':bool(stamp and stamp.tzinfo)})
            aware=[datetime.fromisoformat(row['published_at']) for row in rows if row['timezone_known']]
            fresh=[stamp for stamp in aware if 0<=(NOW-stamp).total_seconds()<=72*3600]
            result.update(state='RSS_METADATA_FRESH' if fresh else 'RSS_METADATA_STALE_OR_UNDATED',format=parsed.version,entry_count=len(rows),fresh_72h=len(fresh),sample=rows[:5],latest_aware=max(aware).isoformat() if aware else None)
        else:
            parser=FeedLinks();parser.feed(raw.decode('utf-8','replace'))
            result.update(state='HTML_ONLY_NEEDS_ADAPTER',feed_links=[urljoin(final,x) for x in parser.links[:5]])
    except Exception as error:
        result.update(state='FETCH_ERROR',error=f'{type(error).__name__}:{str(error)[:180]}')
    return result


if __name__=='__main__':
    validate_catalog()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(probe,SOURCE_CANDIDATES))
    report={'observed_at':NOW.isoformat(),'mode':'bounded external source metadata GETs only; no AI, DB, production, or rights assertion','sports_total':len(news_sport_ids()),'sources_total':len(rows),'sources':rows,'per_sport':{sport:[row['state'] for row in rows if row['sport']==sport] for sport in news_sport_ids()}}
    out=Path('evidence');out.mkdir(exist_ok=True)
    (out/'news03-source-probe.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('NEWS03_SOURCE_PROBE '+json.dumps(report,ensure_ascii=False))
