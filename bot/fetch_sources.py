import logging
import re
from typing import List, Dict, Optional

import feedparser
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

logger = logging.getLogger(__name__)

# Try to import AI rewrite function
try:
    from bot.rewrite_ai import rewrite_to_long_form as ai_rewrite_text
except Exception:
    logger.warning(
        "Could not import bot.rewrite_ai.rewrite_to_long_form. "
        "AI content will fallback to raw text."
    )

    def ai_rewrite_text(title: str, raw_text: str, sport: str = "sports") -> str:
        # Fallback: return original text
        return raw_text or ""


# ================== LEAGUE CONFIG (ALL LEAGUES WE SUPPORT NOW) ==================
LEAGUE_CONFIG: List[Dict] = [
    # ========= TOP 5 + EUROPE MAIN =========

    # England
    {
        "sport": "football",
        "league": "england-premier-league",
        "country": "england",
        "query": "Premier League football",
    },
    {
        "sport": "football",
        "league": "england-championship",
        "country": "england",
        "query": "Championship football",
    },

    # Spain
    {
        "sport": "football",
        "league": "spain-la-liga",
        "country": "spain",
        "query": "La Liga football",
    },
    {
        "sport": "football",
        "league": "spain-la-liga-2",
        "country": "spain",
        "query": "Segunda Division football",
    },

    # Italy
    {
        "sport": "football",
        "league": "italy-serie-a",
        "country": "italy",
        "query": "Serie A football",
    },
    {
        "sport": "football",
        "league": "italy-serie-b",
        "country": "italy",
        "query": "Serie B football",
    },

    # Germany
    {
        "sport": "football",
        "league": "germany-bundesliga",
        "country": "germany",
        "query": "Bundesliga football",
    },
    {
        "sport": "football",
        "league": "germany-2-bundesliga",
        "country": "germany",
        "query": "2. Bundesliga football",
    },

    # France
    {
        "sport": "football",
        "league": "france-ligue-1",
        "country": "france",
        "query": "Ligue 1 football",
    },
    {
        "sport": "football",
        "league": "france-ligue-2",
        "country": "france",
        "query": "Ligue 2 football",
    },

    # Netherlands
    {
        "sport": "football",
        "league": "netherlands-eredivisie",
        "country": "netherlands",
        "query": "Eredivisie football",
    },

    # Portugal
    {
        "sport": "football",
        "league": "portugal-primeira-liga",
        "country": "portugal",
        "query": "Primeira Liga football",
    },

    # Belgium
    {
        "sport": "football",
        "league": "belgium-pro-league",
        "country": "belgium",
        "query": "Belgian Pro League football",
    },

    # Turkey
    {
        "sport": "football",
        "league": "turkey-super-lig",
        "country": "turkey",
        "query": "Turkish Super Lig football",
    },

    # Greece
    {
        "sport": "football",
        "league": "greece-super-league",
        "country": "greece",
        "query": "Greek Super League football",
    },

    # Scotland
    {
        "sport": "football",
        "league": "scotland-premiership",
        "country": "scotland",
        "query": "Scottish Premiership football",
    },

    # Switzerland
    {
        "sport": "football",
        "league": "switzerland-super-league",
        "country": "switzerland",
        "query": "Swiss Super League football",
    },

    # Croatia
    {
        "sport": "football",
        "league": "croatia-hnl",
        "country": "croatia",
        "query": "Croatian HNL football",
    },

    # Serbia
    {
        "sport": "football",
        "league": "serbia-superliga",
        "country": "serbia",
        "query": "Serbian SuperLiga football",
    },

    # Poland
    {
        "sport": "football",
        "league": "poland-ekstraklasa",
        "country": "poland",
        "query": "Ekstraklasa football",
    },

    # Czech
    {
        "sport": "football",
        "league": "czech-first-league",
        "country": "czech-republic",
        "query": "Czech First League football",
    },

    # ========== OUTSIDE EUROPE MAIN LEAGUES ==========

    # USA
    {
        "sport": "football",
        "league": "usa-mls",
        "country": "usa",
        "query": "MLS soccer",
    },

    # Brazil
    {
        "sport": "football",
        "league": "brazil-serie-a",
        "country": "brazil",
        "query": "Brasileirao Serie A football",
    },

    # Argentina
    {
        "sport": "football",
        "league": "argentina-liga-profesional",
        "country": "argentina",
        "query": "Argentina Liga Profesional football",
    },

    # ========== BIG INTERNATIONAL COMPETITIONS ==========

    {
        "sport": "football",
        "league": "uefa-champions-league",
        "country": "europe",
        "query": "UEFA Champions League football",
    },
    {
        "sport": "football",
        "league": "uefa-europa-league",
        "country": "europe",
        "query": "UEFA Europa League football",
    },
    {
        "sport": "football",
        "league": "uefa-conference-league",
        "country": "europe",
        "query": "UEFA Conference League football",
    },
    {
        "sport": "football",
        "league": "uefa-euro",
        "country": "europe",
        "query": "UEFA Euro national team football",
    },
    {
        "sport": "football",
        "league": "fifa-world-cup",
        "country": "global",
        "query": "FIFA World Cup football",
    },

    # ========== BASKETBALL ==========

    {
        "sport": "basketball",
        "league": "nba",
        "country": "usa",
        "query": "NBA basketball",
    },
    {
        "sport": "basketball",
        "league": "euroleague",
        "country": "europe",
        "query": "EuroLeague basketball",
    },
    {
        "sport": "basketball",
        "league": "ncaa-basketball",
        "country": "usa",
        "query": "NCAA college basketball",
    },
]

# ================== RSS CONFIG ==================

# Generic fallback feeds (only used if league is not in RSS_OVERRIDE)
COMMON_FOOTBALL_FEEDS = [
    "https://www.espn.com/espn/rss/soccer/news",
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
]

COMMON_BASKETBALL_FEEDS = [
    "https://www.espn.com/espn/rss/nba/news",
]

NBA_FEEDS = [
    "https://www.espn.com/espn/rss/nba/news",
]

NCAA_FEEDS = [
    "https://www.espn.com/espn/rss/ncb/news",
]

EUROLEAGUE_FEEDS = [
    "https://www.euroleaguebasketball.net/euroleague/rss",
]

# League-specific RSS overrides
RSS_OVERRIDE: Dict[str, List[str]] = {
    # ===== ENGLAND =====
    "england-premier-league": [
        "https://www.skysports.com/rss/12040",
        "https://feeds.bbci.co.uk/sport/football/premier-league/rss.xml",
    ],
    "england-championship": [
        "https://www.skysports.com/rss/12040/championship",
        "https://feeds.bbci.co.uk/sport/football/championship/rss.xml",
    ],

    # ===== SPAIN =====
    "spain-la-liga": [
        "https://as.com/rss/futbol/primera.xml",
        "https://www.marca.com/en/rss/futbol/primera-division.xml",
    ],
    "spain-la-liga-2": [
        "https://as.com/rss/futbol/segunda.xml",
    ],

    # ===== ITALY =====
    "italy-serie-a": [
        "https://www.gazzetta.it/rss/home.xml",
        "https://www.football-italia.net/feed",
    ],
    "italy-serie-b": [
        "https://www.gazzetta.it/rss/calcio/serie-b.xml",
    ],

    # ===== GERMANY =====
    "germany-bundesliga": [
        "https://www.bundesliga.com/en/bundesliga/rss-feed",
        "https://www.kicker.de/bundesliga/rss",
    ],
    "germany-2-bundesliga": [
        "https://www.kicker.de/2-bundesliga/rss",
    ],

    # ===== FRANCE =====
    "france-ligue-1": [
        "https://www.lequipe.fr/rss/actu_rss_Football.xml",
        "https://www.getfootballnewsfrance.com/feed/",
    ],
    "france-ligue-2": [
        "https://www.lequipe.fr/rss/actu_rss_Football_Ligue-2.xml",
    ],

    # ===== NETHERLANDS =====
    "netherlands-eredivisie": [
        "https://www.ad.nl/sport/voetbal/eredivisie/rss.xml",
        "https://www.vi.nl/feeds/nieuws",
    ],

    # ===== PORTUGAL =====
    "portugal-primeira-liga": [
        "https://www.abola.pt/rss",
        "https://www.record.pt/rss",
    ],

    # ===== BELGIUM =====
    "belgium-pro-league": [
        "https://www.hln.be/sport/voetbal/rss.xml",
        "https://www.voetbalprimeur.nl/feed",
    ],

    # ===== TURKEY =====
    "turkey-super-lig": [
        "https://www.fanatik.com.tr/rss",
        "https://www.ntvspor.net/rss",
    ],

    # ===== GREECE =====
    "greece-super-league": [
        "https://www.sport24.gr/rss",
        "https://www.gazzetta.gr/rss",
    ],

    # ===== SCOTLAND =====
    "scotland-premiership": [
        "https://www.skysports.com/rss/29328",
        "https://www.bbc.co.uk/sport/football/scottish-premiership/rss.xml",
    ],

    # ===== SWITZERLAND =====
    "switzerland-super-league": [
        "https://www.blick.ch/sport/rss.xml",
    ],

    # ===== CROATIA =====
    "croatia-hnl": [
        "https://www.24sata.hr/feeds/sport.xml",
        "https://www.index.hr/rss/sport",
    ],

    # ===== SERBIA =====
    "serbia-superliga": [
        "https://www.mozzartsport.com/rss",
        "https://www.novosti.rs/rss/sport",
    ],

    # ===== POLAND =====
    "poland-ekstraklasa": [
        "https://sport.tvp.pl/rss",
        "https://www.przegladsportowy.pl/rss,pi",
    ],

    # ===== CZECH =====
    "czech-first-league": [
        "https://isport.blesk.cz/rss",
    ],

    # ===== USA / AMERICAS =====
    "usa-mls": [
        "https://www.mlssoccer.com/rss",
    ],
    "brazil-serie-a": [
        "https://ge.globo.com/dynamo/rss/futebol/brasileirao-serie-a/",
    ],
    "argentina-liga-profesional": [
        "https://www.tycsports.com/rss",
    ],

    # ===== INTERNATIONAL COMPETITIONS =====
    "uefa-champions-league": [
        "https://www.uefa.com/rssfeed/uefachampionsleague/rss.xml",
    ],
    "uefa-europa-league": [
        "https://www.uefa.com/rssfeed/uefaeuropaleague/rss.xml",
    ],
    "uefa-conference-league": [
        "https://www.uefa.com/rssfeed/uefaconferenceleague/rss.xml",
    ],
    "uefa-euro": [
        "https://www.uefa.com/uefaeuro/rss.xml",
    ],
    "fifa-world-cup": [
        "https://www.fifa.com/rss-feeds/news",
    ],

    # ===== BASKETBALL =====
    "nba": NBA_FEEDS,
    "ncaa-basketball": NCAA_FEEDS,
    "euroleague": EUROLEAGUE_FEEDS,
}


def _extract_image_url(entry) -> Optional[str]:
    """
    Try to extract an image URL from an RSS entry.
    Checks media:content, media:thumbnail, enclosure, or <img> in summary.
    """
    # 1) media_content
    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        for m in media_content:
            url = m.get("url")
            if url:
                return url

    # 2) media_thumbnail
    media_thumb = entry.get("media_thumbnail")
    if media_thumb and isinstance(media_thumb, list):
        for m in media_thumb:
            url = m.get("url")
            if url:
                return url

    # 3) enclosure in links
    links = entry.get("links") or []
    for link in links:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            url = link.get("href")
            if url:
                return url

    # 4) <img src="..."> in summary/description
    summary = entry.get("summary") or entry.get("description") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if match:
        return match.group(1)

    return None


def _get_rss_urls_for_config(config: Dict) -> List[str]:
    """
    Return the list of RSS URLs for given league config.
    1) If league is in RSS_OVERRIDE -> use that
    2) If sport is football -> COMMON_FOOTBALL_FEEDS
    3) If sport is basketball -> COMMON_BASKETBALL_FEEDS
    """
    league = config["league"]
    sport = config["sport"]

    if league in RSS_OVERRIDE:
        return RSS_OVERRIDE[league]

    if sport == "football":
        return COMMON_FOOTBALL_FEEDS

    if sport == "basketball":
        return COMMON_BASKETBALL_FEEDS

    return []


def _fetch_for_league(config: Dict, max_articles: int) -> List[Dict]:
    """
    Fetch articles for a single league via RSS.
    """
    league_key = config["league"]
    rss_urls = _get_rss_urls_for_config(config)

    if not rss_urls:
        logger.info(f"[fetch_sources] No RSS configured for league={league_key}")
        return []

    normalized: List[Dict] = []

    per_feed_limit = max_articles
    if max_articles and len(rss_urls) > 0:
        per_feed_limit = max(1, max_articles // len(rss_urls))

    for url in rss_urls:
        try:
            logger.info(f"[fetch_sources] Fetching RSS for league={league_key} url={url}")
            feed = feedparser.parse(url)

            if getattr(feed, "bozo", False):
                logger.warning(f"[fetch_sources] RSS parse issue for {url}: {feed.bozo_exception}")
                continue

            entries = feed.entries
            if per_feed_limit:
                entries = entries[:per_feed_limit]

            for entry in entries:
                title = entry.get("title")
                summary = entry.get("summary") or entry.get("description", "")
                link = entry.get("link")

                if not link or not title:
                    continue

                image_url = _extract_image_url(entry)

                normalized.append(
                    {
                        "title": title,
                        "description": summary,
                        "content": summary,
                        "url": link,
                        "urlToImage": image_url,
                        "sport": config["sport"],
                        "league": config["league"],
                        "country": config["country"],
                    }
                )
        except Exception as e:
            logger.error(f"[fetch_sources] Error reading RSS for {league_key} ({url}): {e}")

    if max_articles:
        return normalized[:max_articles]
    return normalized


def fetch_all_sports_headlines(
    max_per_league: int = 3,
    hard_limit: int = 20,
) -> List[Dict]:
    """
    Return a list of normalized article dicts for all leagues.
    This is a light version, does not write to DB.
    """
    all_articles: List[Dict] = []

    for config in LEAGUE_CONFIG:
        if len(all_articles) >= hard_limit:
            break

        remaining = hard_limit - len(all_articles)
        limit_for_this_league = min(max_per_league, remaining)

        league_articles = _fetch_for_league(config, limit_for_this_league)
        all_articles.extend(league_articles)

    return all_articles[:hard_limit]


def _slugify(title: str, fallback: str = "") -> str:
    """
    Simple slug generator: lowercase, alphanumeric and dashes.
    """
    if not title:
        title = fallback or "article"

    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title)
    slug = slug.strip().lower()
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug or "article"


def _get_or_create_article(
    db: Session, item: Dict, sport: str, league: str, country: str
) -> Optional[Article]:
    """
    Check if Article with given external_id already exists.
    If not, create a new one.
    """
    source_url = item.get("url")
    if not source_url:
        return None

    existing = db.query(Article).filter(Article.external_id == source_url).first()
    if existing:
        return existing

    title = item.get("title") or "Untitled"
    summary = item.get("description") or item.get("content") or ""
    content = item.get("content") or summary

    slug_base = _slugify(title)
    slug = slug_base
    counter = 1

    # Ensure slug is unique
    while db.query(Article).filter(Article.slug == slug).first() is not None:
        counter += 1
        slug = f"{slug_base}-{counter}"

    article = Article(
        external_id=source_url,
        title=title,
        slug=slug,
        sport=sport,
        league=league,
        country=country,
        division=1,
        image_url=item.get("urlToImage"),
        source_url=source_url,
        summary=summary,
        content=content,
        is_live=True,
    )

    db.add(article)
    db.commit()
    db.refresh(article)

    return article


def fetch_and_store_all_articles(
    max_per_league: int = 3,
    hard_limit: Optional[int] = None,
    use_ai: bool = True,
    max_ai_chars: int = 3000,
    max_ai_articles: Optional[int] = None,
) -> int:
    """
    Main bot function:
    - fetches RSS articles for all leagues in LEAGUE_CONFIG
    - creates Article records if they do not exist
    - optionally generates AI long-form content into ai_content
    - returns number of articles that were AI rewritten
    """
    db = SessionLocal()
    created_or_updated = 0
    ai_used = 0

    try:
        all_articles: List[Dict] = []

        for config in LEAGUE_CONFIG:
            if hard_limit is not None and len(all_articles) >= hard_limit:
                break

            remaining = None
            if hard_limit is not None:
                remaining = hard_limit - len(all_articles)

            limit_for_this_league = max_per_league
            if remaining is not None:
                limit_for_this_league = min(max_per_league, remaining)

            league_articles = _fetch_for_league(config, limit_for_this_league)
            all_articles.extend(
                [
                    {
                        **a,
                        "sport": config["sport"],
                        "league": config["league"],
                        "country": config["country"],
                    }
                    for a in league_articles
                ]
            )

        if hard_limit is not None:
            all_articles = all_articles[:hard_limit]

        for item in all_articles:
            sport = item.get("sport")
            league = item.get("league")
            country = item.get("country")

            article = _get_or_create_article(
                db=db,
                item=item,
                sport=sport,
                league=league,
                country=country,
            )

            if not article:
                continue

            if use_ai and not article.ai_generated:
                if max_ai_articles is not None and ai_used >= max_ai_articles:
                    continue

                base_text = article.content or article.summary or article.title
                if base_text:
                    text_for_ai = base_text[:max_ai_chars]
                    try:
                        ai_text = ai_rewrite_text(
                            title=article.title,
                            raw_text=text_for_ai,
                            sport=article.sport or "sports",
                        )
                        if ai_text and ai_text.strip():
                            article.ai_content = ai_text.strip()
                            article.ai_generated = True
                            db.add(article)
                            db.commit()
                            ai_used += 1
                            created_or_updated += 1
                    except Exception as e:
                        logger.error(
                            f"AI rewrite failed for article {article.id}: {e}"
                        )
                else:
                    logger.info(
                        f"No base text for AI rewrite for article {article.id}"
                    )

        return created_or_updated

    finally:
        db.close()
