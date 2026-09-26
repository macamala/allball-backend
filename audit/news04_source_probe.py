"""Bounded News04 source research. GETs only; no database, AI or publication.

Every candidate is UNVERIFIED until its own observation. Robots/access denials
are recorded and never bypassed. Full publisher prose is not stored in artifacts.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

import feedparser
from bot.news_feed_http import read_news_feed
from bot.extract import parse_feed_datetime, paragraphs_from_html, _json_ld_article_body, _og
from bot.news_policy import freshness_reason
from bot.classify import classify_article

# These are discovery candidates, not assumed feeds or reuse permissions.
CANDIDATES = [
 ('handball', 'Handball Planet', 'https://www.handball-planet.com/feed/'),
 ('futsal', 'Futsal Focus', 'https://www.futsalfocus.net/feed/'),
 ('futsal', 'U.S. Futsal', 'https://futsal.com/feed/'),
 ('water-polo', 'Total Waterpolo', 'https://total-waterpolo.com/feed/'),
 ('field-hockey', 'The Hockey Paper', 'https://www.thehockeypaper.co.uk/feed/'),
 ('australian-rules', 'Zero Hanger', 'https://www.zerohanger.com/feed/'),
 ('table-tennis', 'Table Tennis England', 'https://www.tabletennisengland.co.uk/feed/'),
 ('badminton', 'Badminton England', 'https://www.badmintonengland.co.uk/feed/'),
 ('badminton', 'Badzine', 'https://www.badzine.net/feed/'),
 ('badminton', 'myKhel', 'https://www.mykhel.com/rss/feeds/sports-badminton-fb.xml'),
 ('esports', 'ESL', 'https://esl.com/feed/'),
 ('esports', 'Esports Insider', 'https://esportsinsider.com/feed'),
 ('esports', 'Dot Esports', 'https://dotesports.com/esports/feed'),
 ('ea-sports-fc', 'Dot Esports', 'https://dotesports.com/ea-sports-fc/feed'),
 ('league-of-legends', 'Dot Esports', 'https://dotesports.com/league-of-legends/feed'),
 ('valorant', 'Dot Esports', 'https://dotesports.com/valorant/feed'),
 ('call-of-duty', 'Dot Esports', 'https://dotesports.com/call-of-duty/feed'),
 ('overwatch', 'Dot Esports', 'https://dotesports.com/overwatch/feed'),
 ('rocket-league', 'Dot Esports', 'https://dotesports.com/rocket-league/feed'),
 ('dota-2', 'Dot Esports', 'https://dotesports.com/dota-2/feed'),
 ('lacrosse', 'USA Lacrosse', 'https://www.usalacrosse.com/magazine/rss.xml'),
 ('snooker', 'WPBSA', 'https://wpbsa.com/feed/'),
 ('snooker', 'World Snooker Federation', 'https://www.worldsnookerfederation.org/feed/'),
 ('darts', 'Dartsnews', 'https://dartsnews.com/feed'),
 ('horse-racing', 'Racing NSW', 'https://www.racingnsw.com.au/feed/'),
 ('winter-sports', 'IBU', 'https://www.biathlonworld.com/news'),
 ('winter-sports', 'FIS', 'https://www.fis-ski.com/inside-fis/news'),
 ('field-hockey', 'FIH', 'https://www.fih.hockey/news'),
 ('water-polo', 'World Aquatics', 'https://www.worldaquatics.com/water-polo/news'),
 ('table-tennis', 'ITTF', 'https://www.ittf.com/news/'),
 ('handball', 'IHF', 'https://www.ihf.info/media-center/news'),
 ('league-of-legends', 'Riot Games', 'https://lolesports.com/en-US/news'),
 ('valorant', 'Riot Games', 'https://valorantesports.com/en-US/news'),
 ('overwatch', 'Overwatch Esports', 'https://esports.overwatch.com/en-us/news'),
 ('rocket-league', 'Rocket League', 'https://www.rocketleague.com/en/news/'),
 ('call-of-duty', 'Call of Duty League', 'https://www.callofdutyleague.com/en-us/news'),
 ('ea-sports-fc', 'EA FC Pro', 'https://www.ea.com/games/ea-sports-fc/fc-pro/news'),
]
LOCKS = {urlsplit(row[2]).hostname: threading.Lock() for row in CANDIDATES}
NOW = datetime.now(timezone.utc)

def probe(row):
 sport, publisher, url = row
 out = dict(sport=sport, publisher=publisher, url=url, observed_at=NOW.isoformat(), reuse_rights='NOT_VERIFIED')
 with LOCKS[urlsplit(url).hostname]:
  try:
   raw = read_news_feed(url)
   out.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
   feed = feedparser.parse(raw)
   if not feed.version:
    html = raw.decode('utf-8','replace')
    out.update(state='NOT_RSS', html_title=_og(html,'og:title'),
       declared_feeds=re.findall(r'<link[^>]+type=[\"\']application/(?:rss|atom)\+xml[\"\'][^>]*>',html,re.I)[:4],
       has_jsonld='application/ld+json' in html, has_next='__NEXT_DATA__' in html)
    return out
   entries = []
   for entry in list(feed.entries)[:60]:
    title = re.sub(r'<[^>]*>', '', entry.get('title') or '').strip()
    link = entry.get('link') or ''
    if not title or not link.startswith('https://'):continue
    stamp = parse_feed_datetime(entry)
    summary = paragraphs_from_html(entry.get('summary') or '')
    tag = classify_article(title, summary)
    entries.append(dict(title=title, url=link, published_at=stamp.isoformat() if stamp else None,
       freshness_reason=freshness_reason(stamp,NOW), classified_sport=tag.sport,
       category_tags=[t.get('term') for t in entry.get('tags',[]) if t.get('term')][:10]))
   fresh = [e for e in entries if not e['freshness_reason']]
   out.update(state='RSS_FRESH' if fresh else 'RSS_STALE_OR_UNDATED', format=feed.version,
       entries=len(entries), fresh_entries=len(fresh), classifications=dict(Counter(e['classified_sport'] for e in entries)),
       sample=(fresh or entries)[:2])
   # One bounded article page per endpoint, no text copied to the report.
   candidates = [e for e in fresh if e['classified_sport']==sport] or fresh
   if candidates:
    target=candidates[0]
    try:
     article_raw=read_news_feed(target['url'])
     html=article_raw.decode('utf-8','replace')
     text=_json_ld_article_body(html) or paragraphs_from_html(html)
     parsed_sport=classify_article(target['title'],text).sport
     out['detail']=dict(url=target['url'],feed_title=target['title'], page_title=_og(html,'og:title'),
        source_words=len(text.split()),source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        page_image_present=bool(_og(html,'og:image')),classified_sport=parsed_sport,
        structured_body_present=bool(_json_ld_article_body(html)),
        state='BODY_PRESENT_UNREVIEWED' if text else 'NO_EXTRACTED_BODY')
    except Exception as exc:out['detail']=dict(url=target['url'],state='READ_FAILED',error=str(exc)[:180])
  except Exception as exc:out.update(state='READ_FAILED',error=str(exc)[:180])
 return out

if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(probe,CANDIDATES))
 report={'observed_at':NOW.isoformat(),'mode':'bounded public GET metadata/extraction only; no AI/DB/publication',
    'rows':rows,'states':dict(Counter(r['state'] for r in rows)),
    'limitations':['Not production coverage, factuality or reuse-rights verification.','Body length and metadata do not certify article completeness.','No access denials bypassed; no publisher body is stored in this report.']}
 Path('evidence').mkdir(exist_ok=True)
 Path('evidence/news04-source-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
