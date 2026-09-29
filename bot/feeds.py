"""RSS sources. Mixed feeds are allowed only with independent classification."""

import os
from urllib.parse import urlsplit

from typing import Dict, List, Optional, TypedDict


class Feed(TypedDict, total=False):
    url: str
    kind: str  # league | mixed | disabled
    sport: Optional[str]
    league: Optional[str]
    country: Optional[str]
    enabled: bool
    note: str
    rss_fallback_only: bool


FEEDS: List[Feed] = [
    {'url': 'https://aleagues.com.au/feed/', 'kind': 'league', 'sport': 'football', 'publisher': 'A-Leagues', 'verified_official': True, 'enabled': True, 'allowed_article_paths': ('/news/',), 'note': 'Publisher-advertised RSS with exact UTC dates; public article entry-content and same-article photos. Men, women and national teams; no automatic domestic league stamp. Transfer trackers and ticket promotions held.'},
    {'url': 'https://www.marca.com/rss/googlenews/futbol.xml', 'kind': 'league', 'sport': 'football', 'publisher': 'Marca', 'enabled': True, 'allowed_article_paths': ('/futbol/',), 'note': 'Publisher-advertised football RSS; exact offset timestamps, scoped public article prose and same-article photos verified. Opinion and live products held; no blanket league stamp.'},
    {'url': 'https://www.sportschau.de/fussball/index~rss2.xml', 'kind': 'league', 'sport': 'football', 'publisher': 'Sportschau', 'enabled': True, 'allowed_article_paths': ('/fussball/',), 'note': 'Publisher-advertised dedicated football RSS broadens German and international discovery beyond the mixed-feed limit. Only reporting, never audio episodes or highlight videos.'},
    {'url': 'https://www.volleynews.it/feed/', 'kind': 'league', 'sport': 'volleyball', 'publisher': 'VolleyNews', 'enabled': True, 'verified_official': False, 'note': 'Volleyball reporting with exact RSS/page publication offsets, scoped Elementor article prose and same-article photographs; no league or country stamp.'},
    {'url': 'https://www.wielerflits.nl/feed/', 'kind': 'league', 'sport': 'cycling', 'publisher': 'WielerFlits', 'enabled': True, 'note': 'Exact UTC RSS and matching article publication metadata; scoped Dutch cycling reports with same-article photos. No league stamp; all originality and factual gates remain required.'},
    {'url': 'https://www.golfmonthly.com/feeds.xml', 'kind': 'league', 'sport': 'golf', 'publisher': 'Golf Monthly', 'enabled': True, 'allowed_article_paths': ('/news/',), 'excluded_article_paths': ('/news/live/',), 'note': 'Publisher-advertised RSS with exact UTC dates and scoped public article prose. Excludes equipment, coaching, betting and live products; same-article photo gates remain mandatory.'},
    {'url': 'https://www.eurohoops.net/en/feed/', 'kind': 'league', 'sport': 'basketball', 'publisher': 'Eurohoops', 'enabled': True, 'note': 'Publisher-advertised English RSS: exact UTC publication dates, full prose and same-article 950x500 photographs verified. Broad NBA/EuroLeague/national-team coverage without league stamp; betting products held.'},
    {'url': 'https://lnfoficial.com.br/noticias/feed/', 'kind': 'league', 'sport': 'futsal', 'publisher': 'Liga Nacional de Futsal', 'verified_official': True, 'enabled': True, 'note': 'Official replacement linked by ligafutsal.com.br: exact UTC RSS timestamps, scoped article prose and same-article match photos verified. Expo invitations remain held; no invented publication times or league stamp.'},
    {'url': 'https://swimswam.com/feed/', 'kind': 'league', 'sport': 'swimming', 'publisher': 'SwimSwam', 'enabled': True, 'note': 'Exact UTC RSS and public article dates, scoped WordPress prose and same-article photographs verified. NCAA alone is not basketball evidence; diving and sponsored products remain held.'},
    {'url': 'https://total-waterpolo.com/feed/', 'kind': 'league', 'sport': 'water-polo', 'publisher': 'Total Waterpolo', 'enabled': True, 'note': 'Exact UTC RSS, full original reporting and article photos verified; international and club water polo without a league stamp. Shared Champions League names never imply soccer.'},
    {'url': 'https://www.wpbsa.com/feed/', 'kind': 'league', 'sport': 'snooker', 'publisher': 'WPBSA', 'verified_official': True, 'enabled': True, 'note': 'Governing body RSS: exact UTC timestamps, full match reports and same-article photography verified. Billiards, promotional ceremonies and viewing guides are held separately.'},
    {'url': 'https://en.yna.co.kr/RSS/sports.xml', 'kind': 'mixed', 'publisher': 'Yonhap', 'enabled': True, 'note': 'Verified +0900 RSS and exact article metadata; mixed Asian Games/global sports. Restrict extraction to story-news, excluding unrelated recommendation photos.'},
    {'url': 'https://pbsi.id/feed/', 'kind': 'league', 'sport': 'badminton', 'publisher': 'PBSI', 'verified_official': True, 'enabled': True, 'note': 'Indonesian badminton federation: verified exact UTC RSS, full player statements and same-article match photography; no league stamp.'},
    {'url': 'https://timesofindia.indiatimes.com/rssfeeds/4719148.cms', 'kind': 'mixed', 'enabled': True, 'note': 'Asian Games and global sport; verified timezone-aware RSS, free article prose and same-article JSON-LD photo. No sport/league stamp; liveblogs, medal tables and schedules held.'},
    {'url': 'https://www.ihf.info/news/rss.xml', 'kind': 'league', 'sport': 'handball', 'enabled': True, 'verified_official': True, 'article_https_host': 'www.ihf.info', 'note': 'Official RSS provides exact UTC publication times missing from article pages. Verified same-host HTTPS articles; no league stamp.'},
    {'url': 'https://www.theguardian.com/football/rss', 'kind': 'league', 'sport': 'football', 'enabled': True, 'note': 'Global club and national-team football; never stamp a domestic league.'},
    {'url': 'https://www.theguardian.com/au/sport/rss', 'kind': 'mixed', 'enabled': True, 'note': 'Multi-sport reporting; independently classify; opinion/blog/live products held.'},
    {'url': 'https://www.sportschau.de/index~rss2.xml', 'kind': 'mixed', 'enabled': True, 'note': 'German international and domestic sports reporting; verified article prose, timestamps and image candidates.'},
    {'url': 'https://feeds.as.com/mrss-s/pages/as/site/as.com/section/futbol/portada', 'kind': 'league', 'sport': 'football', 'enabled': True, 'note': 'Global Spanish-language football; no country or league stamp.'},
    {'url': 'https://www.motorsport.com/rss/all/news/', 'kind': 'league', 'sport': 'motorsport', 'enabled': True, 'note': 'F1 and other racing championships; prose and publication timestamps verified; no single-series stamp.'},
    {'url': 'https://feeds.bbci.co.uk/sport/football/premier-league/rss.xml', 'kind': 'league', 'sport': 'football', 'league': 'england-premier-league', 'country': 'england', 'enabled': True},
    {'url': 'https://feeds.bbci.co.uk/sport/football/championship/rss.xml', 'kind': 'league', 'sport': 'football', 'league': 'england-championship', 'country': 'england', 'enabled': True},
    {'url': 'https://as.com/rss/futbol/primera.xml', 'kind': 'league', 'sport': 'football', 'league': 'spain-la-liga', 'country': 'spain', 'enabled': True},
    {'url': 'https://as.com/rss/futbol/segunda.xml', 'kind': 'league', 'sport': 'football', 'league': 'spain-la-liga-2', 'country': 'spain', 'enabled': True},
    {'url': 'https://football-italia.net/feed/', 'kind': 'league', 'sport': 'football', 'enabled': True, 'note': 'Includes national teams and UEFA competitions; publisher country does not establish Serie A.'},
    {'url': 'https://www.espn.com/espn/rss/nba/news', 'kind': 'league', 'sport': 'basketball', 'league': 'nba', 'country': 'usa', 'enabled': True, 'rss_fallback_only': True},
    {'url': 'https://www.espn.com/espn/rss/ncb/news', 'kind': 'league', 'sport': 'basketball', 'league': 'ncaa-basketball', 'country': 'usa', 'enabled': True, 'rss_fallback_only': True},
    {'url': 'https://feeds.bbci.co.uk/sport/football/scottish-premiership/rss.xml', 'kind': 'league', 'sport': 'football', 'league': 'scotland-premiership', 'country': 'scotland', 'enabled': True},
    {'url': 'https://www.skysports.com/rss/29328', 'kind': 'league', 'sport': 'football', 'league': 'scotland-premiership', 'country': 'scotland', 'enabled': True, 'rss_timezone_aliases': {'BST': '+0100'}},
    {'url': 'https://www.hln.be/sport/voetbal/rss.xml', 'kind': 'league', 'sport': 'football', 'enabled': True, 'note': 'Belgian football-only feed; sport hint only, never league stamp'},
    {'url': 'https://www.record.pt/rss', 'kind': 'mixed', 'enabled': True, 'note': 'Portuguese general sport; classify independently'},
    {'url': 'https://isport.blesk.cz/rss', 'kind': 'mixed', 'enabled': True, 'note': 'Czech general sport; classify independently'},
    {'url': 'https://www.novosti.rs/rss/sport', 'kind': 'mixed', 'enabled': True, 'note': 'Serbian general sport firehose; never stamp SuperLiga'},
    {'url': 'https://www.talkbasket.net/feed', 'kind': 'disabled', 'enabled': False, 'note': 'Runtime robots 403; ESPN basketball feeds remain active'},
    {'url': 'https://www.getfootballnewsfrance.com/feed/', 'kind': 'disabled', 'enabled': False, 'note': 'Extract returns HTTP 403; skip until a usable source exists'},
    {'url': 'https://www.blick.ch/sport/rss.xml', 'kind': 'mixed', 'enabled': True},
    {'url': 'https://www.espn.com/espn/rss/soccer/news', 'kind': 'league', 'sport': 'football', 'enabled': True, 'rss_fallback_only': True, 'note': 'Global football-only feed; sport hint only, never league stamp'},
    {'url': 'https://www.espn.com/espn/rss/mlb/news', 'kind': 'league', 'sport': 'baseball', 'enabled': True, 'rss_fallback_only': True, 'note': 'ESPN baseball-only feed; sport hint only'},
    {'url': 'https://www.espn.com/espn/rss/nfl/news', 'kind': 'league', 'sport': 'american-football', 'enabled': True, 'rss_fallback_only': True, 'note': 'ESPN NFL-only feed; sport hint only'},
    {'url': 'https://www.espn.com/espn/rss/nhl/news', 'kind': 'league', 'sport': 'ice-hockey', 'enabled': True, 'rss_fallback_only': True, 'note': 'ESPN NHL-only feed; sport hint only'},
    {'url': 'https://www.espn.com/espn/rss/golf/news', 'kind': 'league', 'sport': 'golf', 'enabled': True, 'rss_fallback_only': True, 'note': 'ESPN golf-only feed; sport hint only'},
    {'url': 'https://basketnews.com/news/rss', 'kind': 'league', 'sport': 'basketball', 'enabled': True, 'readiness_penalty': 15, 'note': 'Repeated production hero HTTP 403 after initial success on Sep 28-29: prioritize other eligible basketball publishers. Keep all image and originality gates; no league stamp.'},
    {'url': 'https://www.nbl.com.au/news/rss.xml', 'kind': 'league', 'sport': 'basketball', 'enabled': True, 'verified_official': True, 'note': 'Official NBL RSS carries exact GMT publication time; page date alone is insufficient. Podcasts, trackers and highlights are held.'},
    {'url': 'https://www.crvenazvezdafk.com/vesti/rss.xml', 'kind': 'league', 'sport': 'football', 'enabled': True, 'verified_official': True, 'note': 'Official club RSS with exact GMT timestamps; no league stamp; retrospectives and fan polls held.'},
    {'url': 'https://fss.rs/feed/', 'kind': 'league', 'sport': 'football', 'enabled': True, 'verified_official': True, 'note': 'Official federation reporting, youth and senior teams; no league stamp.'},
    {'url': 'https://www.b92.net/rss/sport', 'kind': 'mixed', 'enabled': True, 'note': 'Serbian sports reporting; classify by article evidence and bounded section paths, never stamp football on mixed feed.'},
    {'url': 'https://www.handball-planet.com/feed/', 'kind': 'league', 'sport': 'handball', 'enabled': False, 'note': 'RSS dates and full prose verified; article HTTP 403 and no feed photographs. Hold until a usable article image path is verified.'},
    {'url': 'https://feeds.bbci.co.uk/sport/football/german/rss.xml', 'kind': 'disabled', 'enabled': False, 'note': '404 / mismatched tags; Bundesliga still needs a replacement RSS'},
    {'url': 'https://www.skysports.com/rss/12040', 'kind': 'mixed', 'publisher': 'Sky Sports', 'enabled': True, 'rss_timezone_aliases': {'BST': '+0100'}, 'note': 'Mixed sports only: no automatic football or league stamp. Explicit UK BST offset, scoped article prose and real editorial photos verified; streaming adverts excluded.'},
    {'url': 'https://www.skysports.com/rss/12040/championship', 'kind': 'disabled', 'enabled': False, 'note': 'Not well-formed XML'},
    {'url': 'https://www.bundesliga.com/en/bundesliga/rss-feed', 'kind': 'disabled', 'enabled': False, 'note': 'Not well-formed XML'},
    {'url': 'https://www.kicker.de/bundesliga/rss', 'kind': 'disabled', 'enabled': False, 'note': 'Returns HTML'},
    {'url': 'https://www.kicker.de/2-bundesliga/rss', 'kind': 'disabled', 'enabled': False, 'note': 'Returns HTML'},
    {'url': 'https://www.lequipe.fr/rss/actu_rss_Football.xml', 'kind': 'disabled', 'enabled': False, 'note': 'XML syntax error'},
    {'url': 'https://www.lequipe.fr/rss/actu_rss_Football_Ligue-2.xml', 'kind': 'disabled', 'enabled': False, 'note': 'XML syntax error'},
    {'url': 'https://www.vi.nl/feeds/nieuws', 'kind': 'disabled', 'enabled': False, 'note': 'HTML not RSS'},
    {'url': 'https://www.abola.pt/rss', 'kind': 'disabled', 'enabled': False, 'note': 'XML syntax error'},
    {'url': 'https://www.voetbalprimeur.nl/feed', 'kind': 'disabled', 'enabled': False, 'note': 'HTML not RSS'},
    {'url': 'https://www.uefa.com/rssfeed/uefachampionsleague/rss.xml', 'kind': 'disabled', 'enabled': False, 'note': 'Mismatched tags'},
    {'url': 'https://www.fifa.com/rss-feeds/news', 'kind': 'disabled', 'enabled': False, 'note': 'Not valid RSS'},
]


def news_source_is_excluded(url: str) -> bool:
    """Publisher exclusions apply to News intake and article-page repairs."""
    host = (urlsplit(str(url or "")).hostname or "").lower()
    return any(host == root or host.endswith('.' + root)
               for root in ('bbc.com', 'bbc.co.uk', 'bbci.co.uk'))


def enabled_feeds() -> List[Feed]:
    rows = [feed for feed in FEEDS if feed.get("enabled")]
    if os.getenv("NEWS_EXPANDED_FEEDS_ENABLED") == "1":
        from .news_verified_feeds import VERIFIED_RSS
        rows += [dict(feed) for feed in VERIFIED_RSS]
    if os.getenv("NEWS_FOOTBALL_ONLY") == "1":
        # Retain mixed publishers: final article classification, not the feed
        # name, decides whether a candidate is soccer. Existing rows stay intact.
        rows = [feed for feed in rows if not feed.get('sport') or feed.get('sport') == 'football']
    # Do not fetch identical URLs twice or mutate the static catalog.
    return list({feed["url"]: feed for feed in rows
                 if not news_source_is_excluded(feed["url"])}.values())
