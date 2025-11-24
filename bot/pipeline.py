from typing import List, Dict

from sqlalchemy.orm import Session
from slugify import slugify

from database import SessionLocal
from models import Article
from .fetch_sources import fetch_all_sports_headlines
from .rewrite_ai import rewrite_to_long_form

MAX_ARTICLES_PER_RUN = 20


def run_pipeline(max_articles: int = MAX_ARTICLES_PER_RUN) -> None:
    """
    Main AllBall pipeline:
    - Fetch multi-sport, multi-league headlines.
    - Skip duplicates (based on external_id = url).
    - Rewrite to long-form with AI.
    - Insert into database.
    """
    db: Session = SessionLocal()
    try:
        raw_articles: List[Dict] = fetch_all_sports_headlines(
            max_per_league=3,
            hard_limit=max_articles,
        ) or []

        raw_articles = raw_articles[:max_articles]

        for item in raw_articles:
            external_id = item.get("url")
            if not external_id:
                continue

            existing = db.query(Article).filter_by(external_id=external_id).first()
            if existing:
                continue

            title = item.get("title") or ""
            if not title:
                continue

            raw_text = item.get("content") or item.get("description") or ""
            if not raw_text:
                continue

            sport = item.get("sport") or "sports"
            league = item.get("league") or "general"
            country = item.get("country") or "global"

            long_form = rewrite_to_long_form(title, raw_text, sport=sport)
            slug = slugify(title)[:200]

            article = Article(
                external_id=external_id,
                title=title,
                slug=slug,
                league=league,
                sport=sport,
                country=country,
                division=1,
                image_url=item.get("urlToImage"),
                source_url=item.get("url"),
                summary=item.get("description") or "",
                content=long_form,
            )

            db.add(article)

        db.commit()
    finally:
        db.close()
