import logging
import re
from typing import List, Dict, Optional

import feedparser
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

logger = logging.getLogger(__name__)

# Import AI rewrite (fallback if missing)
try:
    from bot.rewrite_ai import rewrite_to_long_form as ai_rewrite_text
except Exception:
    logger.warning("AI rewrite not available. Using fallback.")
    def ai_rewrite_text(title: str, raw_text: str, sport: str = "sports") -> str:
        return raw_text or ""


# ==========================================
# LEAGUE CONFIG
# ==========================================
LEAGUE_CONFIG: List[Dict] = [
    # Example:
    # {
    #     "sport": "football",
    #     "league": "england-premier-league",
    #     "country": "england",
    #     "query": "Premier League football"
    # },

    {"sport": "football", "league": "england-premier-league", "country": "england", "query": "Premier League football"},
    {"sport": "football", "league": "england-championship", "country": "england", "query": "EFL Championship football"},

    {"sport": "football", "league": "spain-la-liga", "country": "spain", "query": "La Liga football"},
    {"sport": "football", "league": "spain-la-liga-2", "country": "spain", "query": "Segunda Division La Liga 2 football"},

    {"sport": "football", "league": "italy-serie-a", "country": "italy", "query": "Serie A football"},
    {"sport": "football", "league": "italy-serie-b", "country": "italy", "query": "Serie B football"},

    {"sport": "football", "league": "germany-bundesliga", "country": "germany", "query": "Bundesliga football"},
    {"sport": "football", "league": "germany-2-bundesliga", "country": "germany", "query": "2. Bundesliga football"},

    {"sport": "football", "league": "france-ligue-1", "country": "france", "query": "Ligue 1 football"},
    {"sport": "football", "league": "france-ligue-2", "country": "france", "query": "Ligue 2 football"},

    {"sport": "football", "league": "netherlands-eredivisie", "country": "netherlands", "query": "Eredivisie football"},
    {"sport": "football", "league": "portugal-primeira-liga", "country": "portugal", "query": "Primeira Liga football"},
    {"sport": "football", "league": "belgium-pro-league", "country": "belgium", "query": "Belgian Pro League football"},
    {"sport": "football", "league": "turkey-super-lig", "country": "turkey", "query": "Turkish Super Lig football"},
    {"sport": "football", "league": "greece-super-league", "country": "greece", "query": "Greek Super League football"},
    {"sport": "football", "league": "scotland-premiership", "country": "scotland", "query": "Scottish Premiership football"},
    {"sport": "football", "league": "switzerland-super-league", "country": "switzerland", "query": "Swiss Super League football"},
    {"sport": "football", "league": "austria-bundesliga", "country": "austria", "query": "Austrian Bundesliga football"},
    {"sport": "football", "league": "denmark-superliga", "country": "denmark", "query": "Danish Superliga football"},
    {"sport": "football", "league": "croatia-hnl", "country": "croatia", "query": "Croatian HNL football"},
    {"sport": "football", "league": "serbia-superliga", "country": "serbia", "query": "Serbian SuperLiga football"},
    {"sport": "football", "league": "poland-ekstraklasa", "country": "poland", "query": "Ekstraklasa football"},
    {"sport": "football", "league": "czech-first-league", "country": "czech-republic", "query": "Czech First League football"},
    {"sport": "football", "league": "russia-premier-league", "country": "russia", "query": "Russian Premier League football"},
    {"sport": "football", "league": "ukraine-premier-league", "country": "ukraine", "query": "Ukrainian Premier League football"},
    {"sport": "football", "league": "sweden-allsvenskan", "country": "sweden", "query": "Allsvenskan football"},
    {"sport": "football", "league": "norway-eliteserien", "country": "norway", "query": "Eliteserien football"},
    {"sport": "football", "league": "usa-mls", "country": "usa", "query": "MLS soccer"},
    {"sport": "football", "league": "brazil-serie-a", "country": "brazil", "query": "Brasileirao Serie A football"},
    {"sport": "football", "league": "argentina-liga-profesional", "country": "argentina", "query": "Argentina Liga Profesional football"},

    {"sport": "football", "league": "uefa-champions-league", "country": "europe", "query": "UEFA Champions League football"},
    {"sport": "football", "league": "uefa-europa-league", "country": "europe", "query": "UEFA Europa League football"},
    {"sport": "football", "league": "uefa-conference-league", "country": "europe", "query": "UEFA Conference League football"},
    {"sport": "football", "league": "uefa-super-cup", "country": "europe", "query": "UEFA Super Cup football"},

    {"sport": "football", "league": "uefa-euro", "country": "europe", "query": "UEFA Euro football"},
    {"sport": "football", "league": "world-cup-qualifiers-europe", "country": "europe", "query": "World Cup Qualifiers Europe football"},
    {"sport": "football", "league": "uefa-nations-league", "country": "europe", "query": "UEFA Nations League football"},

    {"sport": "football", "league": "fifa-world-cup", "country": "global", "query": "FIFA World Cup football"},
    {"sport": "football", "league": "fifa-world-cup-qualifiers", "country": "global", "query": "World Cup qualifiers football"},

    {"sport": "football", "league": "copa-america", "country": "south-america", "query": "Copa America football"},
    {"sport": "football", "league": "africa-cup-of-nations", "country": "africa", "query": "Africa Cup of Nations football"},
    {"sport": "football", "league": "afc-asian-cup", "country": "asia", "query": "AFC Asian Cup football"},

    {"sport": "football", "league": "concacaf-gold-cup", "country": "north-america", "query": "CONCACAF Gold Cup football"},
    {"sport": "football", "league": "copa-libertadores", "country": "south-america", "query": "Copa Libertadores football"},
    {"sport": "football", "league": "copa-sudamericana", "country": "south-america", "query": "Copa Sudamericana football"},
    {"sport": "football", "league": "concacaf-champions-cup", "country": "north-america", "query": "CONCACAF Champions Cup football"},

    {"sport": "football", "league": "afc-champions-league", "country": "asia", "query": "AFC Champions League football"},
    {"sport": "football", "league": "caf-champions-league", "country": "africa", "query": "CAF Champions League football"},

    {"sport": "basketball", "league": "nba", "country": "usa", "query": "NBA basketball"},
    {"sport": "basketball", "league": "euroleague", "country": "europe", "query": "EuroLeague basketball"},
    {"sport": "basketball", "league": "ncaa-basketball", "country": "usa", "query": "NCAA basketball"},
]


# ==========================================
# RSS FEEDS
# ==========================================

COMMON_FOOTBALL_FEEDS = [
    "https://www.espn.com/espn/rss/soccer/news",
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
]

COMMON_BASKETBALL_FEEDS = [
    "https://www.espn.com/espn/rss/nba/news",
]

NBA_FEEDS = ["https://www.espn.com/espn/rss/nba/news"]
NCAA_FEEDS = ["https://www.espn.com/espn/rss/ncb/news"]
EUROLEAGUE_FEEDS = ["https://www.euroleaguebasketball.net/euroleague/rss"]

RSS_OVERRIDE: Dict[str, List[str]] = {
    "nba": NBA_FEEDS,
    "ncaa-basketball": NCAA_FEEDS,
    "euroleague": EUROLEAGUE_FEEDS,
}


# ==========================================
# IMAGE EXTRACTOR
# ==========================================
def _extract_image_url(entry) -> Optional[str]:
    media = entry.get("media_content")
    if media and isinstance(media, list):
        for m in media:
            if m.get("url"):
                return m["url"]

    thumb = entry.get("media_thumbnail")
    if thumb and isinstance(thumb, list):
        for m in thumb:
            if m.get("url"):
                return m["url"]

    links = entry.get("links") or []
    for link in links:
        if link.get("rel") == "enclosure" and "image" in str(link.get("type", "")):
            return link.get("href")

    summary = entry.get("summary") or entry.get("description") or ""
    match = re.search(r'<img[^>]+src="([^"]+)"', summary)
    if match:
        return match.group(1)

    return None


# ==========================================
# GET RSS URLS FOR LEAGUE
# ==========================================
def _get_rss_urls_for_config(config: Dict) -> List[str]:
    league = config["league"]
    sport = config["sport"]

    if league in RSS_OVERRIDE:
        return RSS_OVERRIDE[league]

    if sport == "football":
        return COMMON_FOOTBALL_FEEDS

    if sport == "basketball":
        return COMMON_BASKETBALL_FEEDS

    return []


# ==========================================
# FETCH FOR ONE LEAGUE
# ==========================================
def _fetch_for_league(config: Dict, max_articles: int) -> List[Dict]:
    league = config["league"]
    rss_urls = _get_rss_urls_for_config(config)

    if not rss_urls:
        return []

    normalized: List[Dict] = []

    per_feed_limit = max_articles
    if max_articles and len(rss_urls) > 0:
        per_feed_limit = max(1, max_articles // len(rss_urls))

    for url in rss_urls:
        try:
            logger.info(f"Fetching RSS for league={league} url={url}")
            feed = feedparser.parse(url)

            if getattr(feed, "bozo", False):
                logger.warning(f"RSS parse issue for {url}: {feed.bozo_exception}")
                continue

            entries = feed.entries[:per_feed_limit]

            for entry in entries:
                title = entry.get("title")
                summary = entry.get("summary") or entry.get("description", "")
                link = entry.get("link")

                if not link or not title:
                    continue

                normalized.append(
                    {
                        "title": title,
                        "description": summary,
                        "content": summary,
                        "url": link,
                        "urlToImage": _extract_image_url(entry),
                        "sport": config["sport"],
                        "league": config["league"],
                        "country": config["country"],
                    }
                )
        except Exception as e:
            logger.error(f"RSS error for league={league}: {e}")

    return normalized[:max_articles]


# ==========================================
# SLUGIFY
# ==========================================
def _slugify(text: str, fallback: str = "") -> str:
    if not text:
        text = fallback or "article"

    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug or "article"


# ==========================================
# GET OR CREATE ARTICLE
# ==========================================
def _get_or_create_article(db: Session, item: Dict) -> Optional[Article]:
    url = item.get("url")
    if not url:
        return None

    existing = db.query(Article).filter(Article.external_id == url).first()
    if existing:
        return existing

    title = item.get("title")
    summary = item.get("description") or item.get("content") or ""

    slug_base = _slugify(title)
    slug = slug_base
    counter = 1

    while db.query(Article).filter(Article.slug == slug).first():
        counter += 1
        slug = f"{slug_base}-{counter}"

    article = Article(
        external_id=url,
        title=title,
        slug=slug,
        sport=item.get("sport"),
        league=item.get("league"),
        country=item.get("country"),
        division=1,
        image_url=item.get("urlToImage"),
        source_url=url,
        summary=summary,
        content=summary,
        is_live=True,
    )

    db.add(article)
    db.commit()
    db.refresh(article)

    return article


# ==========================================
# MAIN BOT FUNCTION
# ==========================================
def fetch_and_store_all_articles(
    max_per_league: int = 3,
    hard_limit: Optional[int] = None,
    use_ai: bool = True,
    max_ai_chars: int = 3000,
    max_ai_articles: Optional[int] = None,
) -> int:
    db = SessionLocal()
    ai_used = 0

    try:
        collected = []

        for config in LEAGUE_CONFIG:
            if hard_limit is not None and len(collected) >= hard_limit:
                break

            limit = max_per_league
            if hard_limit is not None:
                limit = min(limit, hard_limit - len(collected))

            league_articles = _fetch_for_league(config, limit)
            for a in league_articles:
                a["sport"] = config["sport"]
                a["league"] = config["league"]
                a["country"] = config["country"]

            collected.extend(league_articles)

        if hard_limit is not None:
            collected = collected[:hard_limit]

        created_count = 0

        for item in collected:
            article = _get_or_create_article(db, item)
            if not article:
                continue

            # AI rewrite
            if use_ai and not article.ai_generated:
                if max_ai_articles is not None and ai_used >= max_ai_articles:
                    continue

                base_text = article.content or article.summary or article.title
                if base_text:
                    raw_text = base_text[:max_ai_chars]

                    try:
                        new_text = ai_rewrite_text(article.title, raw_text, article.sport)
                        if new_text and new_text.strip():
                            article.ai_content = new_text.strip()
                            article.ai_generated = True
                            db.add(article)
                            db.commit()
                            ai_used += 1
                            created_count += 1
                    except Exception as e:
                        logger.error(f"AI rewrite failed for article {article.id}: {e}")

        return created_count

    finally:
        db.close()
