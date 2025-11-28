import os
import logging
from typing import List, Dict, Optional
import re

import requests
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article

logger = logging.getLogger(__name__)

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

if not NEWS_API_KEY:
    logger.warning("NEWS_API_KEY is not set. News fetching will fail.")

# Pokušaj da uvezeš AI rewrite funkciju, ako postoji
try:
    from bot.rewrite_ai import rewrite_text as ai_rewrite_text
except Exception:
    logger.warning("Could not import bot.rewrite_ai.rewrite_text. AI content will fallback to summary/content.")

    def ai_rewrite_text(text: str) -> str:
        """
        Fallback ako rewrite_ai nije dostupan – samo vrati originalni tekst.
        Možeš kasnije povezati pravi OpenAI poziv ovde.
        """
        return text or ""


# Top 30 football leagues + European and global competitions + NBA, EuroLeague, NCAA
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


def _fetch_for_league(config: Dict, max_articles: int) -> List[Dict]:
    """
    Fetch news articles for a specific league configuration using NewsAPI.
    """
    if not NEWS_API_KEY:
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": config["query"],
        "language": "en",
        "pageSize": max_articles,
        "sortBy": "publishedAt",
        "apiKey": NEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", []) or []
        normalized: List[Dict] = []

        for item in articles:
            normalized.append(
                {
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "content": item.get("content"),
                    "url": item.get("url"),
                    "urlToImage": item.get("urlToImage"),
                    "sport": config["sport"],
                    "league": config["league"],
                    "country": config["country"],
                }
            )

        return normalized
    except Exception as e:
        logger.error(f"Error fetching news for {config.get('league')}: {e}")
        return []


def fetch_all_sports_headlines(
    max_per_league: int = 3,
    hard_limit: int = 20,
) -> List[Dict]:
    """
    Fetch headlines for all configured leagues.
    max_per_league: max articles per league per run.
    hard_limit: max total articles per run.

    Ovo je stari helper koji samo vraća listu dictova – ostavljam ga
    zbog kompatibilnosti, ako ga koristiš negde drugde.
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


# ------------- NOVO: helper za slug i DB upis -------------


def _slugify(title: str, fallback: str = "") -> str:
    """
    Jednostavan slug generator: mala slova, slova-brojevi, crtice.
    """
    if not title:
        title = fallback or "article"

    # samo slova, brojevi i razmaci
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

    # Koristimo source_url kao external_id – unikatan je po članku
    existing = (
        db.query(Article).filter(Article.external_id == source_url).first()
    )
    if existing:
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
    hard_limit: int = 20,
    use_ai: bool = True,
    max_ai_chars: int = 3000,
) -> int:
    """
    Glavna funkcija za bota:
    - povuče vesti za sve lige
    - kreira Article ako ne postoji
    - generiše AI tekst (ai_content) i setuje ai_generated = True
    - vraća broj novih/svežih artikala (koji su prošli kroz proces)
    """
    db = SessionLocal()
    created_or_updated = 0

    try:
        all_articles = []

        for config in LEAGUE_CONFIG:
            if len(all_articles) >= hard_limit:
                break

            remaining = hard_limit - len(all_articles)
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

        for item in all_articles[:hard_limit]:
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

            # Ako već ima AI content, preskoči
            if use_ai and not article.ai_generated:
                base_text = article.content or article.summary or article.title
                if base_text:
                    # Ograniči tekst koji šalješ AI-u
                    text_for_ai = base_text[:max_ai_chars]
                    try:
                        ai_text = ai_rewrite_text(text_for_ai)
                        if ai_text and ai_text.strip():
                            article.ai_content = ai_text.strip()
                            article.ai_generated = True
                            db.add(article)
                            db.commit()
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
