import logging
from typing import List, Dict

from sqlalchemy.orm import Session
from slugify import slugify

from database import SessionLocal
from models import Article
from .fetch_sources import fetch_football_headlines  # <- this exists

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """
    Fetch news, rewrite with AI and store new unique articles.
    Currently uses fetch_football_headlines() as the source.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Fetching raw headlines...")
        raw_items: List[Dict] = fetch_football_headlines()

        if not raw_items:
            logger.info("No items fetched from sources.")
            return

        # Load existing external_ids and slugs so we don't insert duplicates
        existing_external_ids = {
            eid for (eid,) in db.query(Article.external_id).all()
        }
        existing_slugs = {
            s for (s,) in db.query(Article.slug).all()
        }

        new_count = 0

        for item in raw_items:
            external_id = item.get("url")
            if not external_id:
                continue

            # Skip if this article already exists in DB
            if external_id in existing_external_ids:
                continue

            title = item.get("title") or ""
            if not title:
                continue

            raw_text = item.get("content") or item.get("description") or ""
            if not raw_text:
                continue

            # Make base slug
            base_slug = slugify(title)[:190]  # keep a bit of room for suffix
            slug = base_slug

            # Ensure slug is unique (avoid ix_articles_slug violation)
            suffix = 2
            while slug in existing_slugs:
                slug = f"{base_slug}-{suffix}"
                suffix += 1

            # Rewrite with OpenAI
            from .rewrite_ai import rewrite_to_long_form  # imported here to avoid cycles
            long_form = rewrite_to_long_form(title, raw_text)

            article = Article(
                external_id=external_id,
                title=title,
                slug=slug,
                sport=item.get("sport") or "football",
                league=item.get("league") or "",
                country=item.get("country") or "",
                division=item.get("division") or 1,
                image_url=item.get("urlToImage"),
                source_url=item.get("url"),
                summary=item.get("description") or "",
                content=long_form,
            )

            db.add(article)

            # Mark as used so we don't create same slug/external_id again
            existing_external_ids.add(external_id)
            existing_slugs.add(slug)
            new_count += 1

        db.commit()
        logger.info(f"Pipeline finished. Inserted {new_count} new articles.")

    except Exception:
        logger.exception("Pipeline run failed.")
        db.rollback()
    finally:
        db.close()
