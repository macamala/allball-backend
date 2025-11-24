from sqlalchemy.orm import Session
from slugify import slugify
from database import SessionLocal
from models import Article
from .fetch_sources import fetch_all_sports_headlines
from .rewrite_ai import rewrite_to_long_form


def run_pipeline():
    db: Session = SessionLocal()
    try:
        # fetch max 20 articles total from all leagues
        articles = fetch_all_sports_headlines(
            max_per_league=3,
            hard_limit=20
        )

        for item in articles:
            external_id = item.get("url")
            if not external_id:
                continue

            # skip if already exists
            existing = (
                db.query(Article)
                .filter(Article.external_id == external_id)
                .first()
            )
            if existing:
                continue

            title = item.get("title") or ""
            if not title.strip():
                continue

            # raw text from the source
            raw_text = (
                item.get("content")
                or item.get("description")
                or ""
            )

            long_form = rewrite_to_long_form(title, raw_text)
            slug = slugify(title)[:200]

            # prevent slug collisions
            duplicate = (
                db.query(Article)
                .filter(Article.slug == slug)
                .first()
            )
            if duplicate:
                slug = slug + "-news"

            article = Article(
                external_id=external_id,
                title=title,
                slug=slug,
                sport=item.get("sport"),
                league=item.get("league"),
                country=item.get("country"),
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
