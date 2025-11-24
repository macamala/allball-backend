from sqlalchemy.orm import Session
from slugify import slugify
from database import SessionLocal
from models import Article
from .fetch_sources import fetch_football_headlines
from .rewrite_ai import rewrite_to_long_form


def run_pipeline():
    db: Session = SessionLocal()
    try:
        articles = fetch_football_headlines()

        for item in articles:
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

            long_form = rewrite_to_long_form(title, raw_text)
            slug = slugify(title)[:200]

            article = Article(
                external_id=external_id,
                title=title,
                slug=slug,
                league="global-football",
                sport="football",
                country="global",
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
