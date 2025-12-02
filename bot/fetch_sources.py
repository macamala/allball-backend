import logging
import re
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as date_parser  # pip install python-dateutil
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

logger = logging.getLogger(__name__)

# Maksimalna starost vesti iz RSS-a (u satima)
MAX_AGE_HOURS = 3

# Pokušaj da uvezeš AI rewrite funkciju
try:
    from bot.rewrite_ai import rewrite_to_long_form as ai_rewrite_text
except Exception:
    logger.warning(
        "Could not import bot.rewrite_ai.rewrite_to_long_form. "
        "AI content will fallback to raw text."
    )

    def ai_rewrite_text(title: str, raw_text: str, sport: str = "sports") -> str:
        # fallback – bez AI, samo vrati original
        return raw_text or ""


# ================== LEAGUE CONFIG (SVE LIGE) ==================
LEAGUE_CONFIG: List[Dict] = [
    # Football - England
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
        "query": "EFL Championship football",
    },

    # Football - Spain
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
        "query": "Segunda Division La Liga 2 football",
    },

    # Football - Italy
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

    # Football - Germany
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

    # Football - France
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

    # Football - Netherlands
    {
        "sport": "football",
        "league": "netherlands-eredivisie",
        "country": "netherlands",
        "query": "Eredivisie football",
    },

    # Football - Portugal
    {
        "sport": "football",
        "league": "portugal-primeira-liga",
        "country": "portugal",
        "query": "Primeira Liga football",
    },

    # Football - Belgium
    {
        "sport": "football",
        "league": "belgium-pro-league",
        "country": "belgium",
        "query": "Belgian Pro League football",
    },

    # Football - Turkey
    {
        "sport": "football",
        "league": "turkey-super-lig",
        "country": "turkey",
        "query": "Turkish Super Lig football",
    },

    # Football - Greece
    {
        "sport": "football",
        "league": "greece-super-league",
        "country": "greece",
        "query": "Greek Super League football",
    },

    # Football - Scotland
    {
        "sport": "football",
        "league": "scotland-premiership",
        "country": "scotland",
        "query": "Scottish Premiership football",
    },

    # Football - Switzerland
    {
        "sport": "football",
        "league": "switzerland-super-league",
        "country": "switzerland",
        "query": "Swiss Super League football",
    },

    # Football - Austria
    {
        "sport": "football",
        "league": "austria-bundesliga",
        "country": "austria",
        "query": "Austrian Bundesliga football",
    },

    # Football - Denmark
    {
        "sport": "football",
        "league": "denmark-superliga",
        "country": "denmark",
        "query": "Danish Superliga football",
    },

    # Football - Croatia
    {
        "sport": "football",
        "league": "croatia-hnl",
        "country": "croatia",
        "query": "Croatian HNL football",
    },

    # Football - Serbia
    {
        "sport": "football",
        "league": "serbia-superliga",
        "country": "serbia",
        "query": "Serbian SuperLiga football",
    },

    # Football - Poland
    {
        "sport": "football",
        "league": "poland-ekstraklasa",
        "country": "poland",
        "query": "Ekstraklasa football",
    },

    # Football - Czech Republic
    {
        "sport": "football",
        "league": "czech-first-league",
        "country": "czech-republic",
        "query": "Czech First League football",
    },

    # Football - Russia
    {
        "sport": "football",
        "league": "russia-premier-league",
        "country": "russia",
        "query": "Russian Premier League football",
    },

    # Football - Ukraine
    {
        "sport": "football",
        "league": "ukraine-premier-league",
        "country": "ukraine",
        "query": "Ukrainian Premier League football",
    },

    # Football - Sweden
    {
        "sport": "football",
        "league": "sweden-allsvenskan",
        "country": "sweden",
        "query": "Allsvenskan football",
    },

    # Football - Norway
    {
        "sport": "football",
        "league": "norway-eliteserien",
        "country": "norway",
        "query": "Eliteserien football",
    },

    # Football - USA
    {
        "sport": "football",
        "league": "usa-mls",
        "country": "usa",
        "query": "MLS soccer",
    },

    # Football - Brazil
    {
        "sport": "football",
        "league": "brazil-serie-a",
        "country": "brazil",
        "query": "Brasileirao Serie A football",
    },

    # Football - Argentina
    {
        "sport": "football",
        "league": "argentina-liga-profesional",
        "country": "argentina",
        "query": "Argentina Liga Profesional football",
    },

    # European club competitions
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
        "league": "uefa-super-cup",
        "country": "europe",
        "query": "UEFA Super Cup football",
    },

    # European national team competitions
    {
        "sport": "football",
        "league": "uefa-euro",
        "country": "europe",
        "query": "UEFA Euro national team football",
    },
    {
        "sport": "football",
        "league": "world-cup-qualifiers-europe",
        "country": "europe",
        "query": "World Cup Qualifiers Europe football",
    },
    {
        "sport": "football",
        "league": "uefa-nations-league",
        "country": "europe",
        "query": "UEFA Nations League football",
    },

    # Global national team competitions
    {
        "sport": "football",
        "league": "fifa-world-cup",
        "country": "global",
        "query": "FIFA World Cup national team football",
    },
    {
        "sport": "football",
        "league": "fifa-world-cup-qualifiers",
        "country": "global",
        "query": "World Cup qualifiers football",
    },

    # South America national team competitions
    {
        "sport": "football",
        "league": "copa-america",
        "country": "south-america",
        "query": "Copa America national team football",
    },

    # Africa national team competitions
    {
        "sport": "football",
        "league": "africa-cup-of-nations",
        "country": "africa",
        "query": "Africa Cup of Nations football",
    },

    # Asia national team competitions
    {
        "sport": "football",
        "league": "afc-asian-cup",
        "country": "asia",
        "query": "AFC Asian Cup football",
    },

    # North America national team competitions
    {
        "sport": "football",
        "league": "concacaf-gold-cup",
        "country": "north-america",
        "query": "CONCACAF Gold Cup national team football",
    },

    # South America club competitions
    {
        "sport": "football",
        "league": "copa-libertadores",
        "country": "south-america",
        "query": "Copa Libertadores football",
    },
    {
        "sport": "football",
        "league": "copa-sudamericana",
        "country": "south-america",
        "query": "Copa Sudamericana football",
    },

    # North America club competitions
    {
        "sport": "football",
        "league": "concacaf-champions-cup",
        "country": "north-america",
        "query": "CONCACAF Champions Cup football",
    },

    # Asia club competitions
    {
        "sport": "football",
        "league": "afc-champions-league",
        "country": "asia",
        "query": "AFC Champions League football",
    },

    # Africa club competitions
    {
        "sport": "football",
        "league": "caf-champions-league",
        "country": "africa",
        "query": "CAF Champions League football",
    },

    # Basketball - NBA
    {
        "sport": "basketball",
        "league": "nba",
        "country": "usa",
        "query": "NBA basketball",
    },

    # Basketball - EuroLeague
    {
        "sport": "basketball",
        "league": "euroleague",
        "country": "europe",
        "query": "EuroLeague basketball",
    },

    # Basketball - NCAA College
    {
        "sport": "basketball",
        "league": "ncaa-basketball",
        "country": "usa",
        "query": "NCAA college basketball",
    },
]

# ================== RSS KONFIG ==================

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

# Specijalni feedovi po ligi (ako treba override)
RSS_OVERRIDE: Dict[str, List[str]] = {
    "nba": NBA_FEEDS,
    "ncaa-basketball": NCAA_FEEDS,
    "euroleague": EUROLEAGUE_FEEDS,
}


def _extract_image_url(entry) -> Optional[str]:
    """
    Pokušava da izvuče URL slike iz RSS entry-ja.
    Gleda media:content, media:thumbnail, enclosure, image linkove i <img> u summary-ju.
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

    # 3) enclosure u links
    links = entry.get("links") or []
    for link in links:
        link_type = str(link.get("type", ""))
        href = link.get("href")
        if href and (link.get("rel") == "enclosure" and link_type.startswith("image")):
            return href

    # 4) bilo koji image-like link (često .jpg/.png)
    for link in links:
        href = link.get("href")
        if href and any(href.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            return href

    # 5) <img src="..."> iz summary/description
    summary = entry.get("summary") or entry.get("description") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if match:
        return match.group(1)

    return None


def _get_rss_urls_for_config(config: Dict) -> List[str]:
    """
    Vrati listu RSS url-ova za dati config.
    1) ako postoji u RSS_OVERRIDE → koristi to
    2) ako je sport football → COMMON_FOOTBALL_FEEDS
    3) ako je sport basketball → COMMON_BASKETBALL_FEEDS
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


def _parse_published(entry) -> Optional[datetime]:
    """
    Pokušava da pročita vreme objave vesti iz RSS entry-ja i vrati ga kao UTC datetime.
    """
    # 1) published_parsed / updated_parsed (time.struct_time)
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                ts = time.mktime(parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass

    # 2) string published / updated
    for key in ("published", "updated"):
        val = entry.get(key)
        if val:
            try:
                dt = date_parser.parse(val)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                pass

    return None


def _fetch_for_league(config: Dict, max_articles: int) -> List[Dict]:
    """
    Fetch za jednu ligu preko RSS-a. Nema više NewsAPI-ja.
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

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

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

                # vreme objave
                published_at = _parse_published(entry)
                # ako nema datum ili je starije od cutoff-a → preskoči
                if not published_at or published_at < cutoff:
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
                        "published_at": published_at,
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
    Vraća listu dict-ova sa osnovnim info o člancima, preko RSS-a.
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
    Jednostavan slug generator: mala slova, slova-brojevi, crtice.
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
    Proverava da li već postoji Article za dati source_url (external_id),
    ako ne postoji – kreira novi.
    """
    source_url = item.get("url")
    if not source_url:
        return None

    existing = db.query(Article).filter(Article.external_id == source_url).first()
    if existing:
        # ako stari nema published_at, a novi ima – upiši
        if not existing.published_at and item.get("published_at"):
            existing.published_at = item["published_at"]
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return existing

    title = item.get("title") or "Untitled"
    summary = item.get("description") or item.get("content") or ""
    content = item.get("content") or summary

    slug_base = _slugify(title)
    slug = slug_base
    counter = 1

    # obezbedi da slug bude unikatan
    while db.query(Article).filter(Article.slug == slug).first() is not None:
        counter += 1
        slug = f"{slug_base}-{counter}"

    published_at = item.get("published_at")
    if not published_at:
        published_at = datetime.utcnow()

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
        published_at=published_at,
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
    Glavna funkcija za bota:
    - povuče vesti za sve lige iz LEAGUE_CONFIG (preko RSS-a)
    - kreira Article ako ne postoji
    - generiše AI tekst (ai_content) i setuje ai_generated = True
    - vraća broj artikala za koje je urađen AI rewrite
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
