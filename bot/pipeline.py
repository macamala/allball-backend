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

        if not articles:
            return

        # 1) Učitaj sve postojeće external_id i slug iz baze
        existing_external_ids = {
            ext_id for (ext_id,) in db.query(Article.external_id).all()
        }
        existing_slugs = {s for (s,) in db.query(Article.slug).all()}

        # pratimo sve slugove koji postoje + koje pravimo u ovoj turi
        used_slugs = set(existing_slugs)

        for item in articles:
            external_id = item.get("url")
            if not external_id:
                continue

            # skip ako već postoji u bazi
            if external_id in existing_external_ids:
                continue

            title = (item.get("title") or "").strip()
            if not title:
                continue

            # raw text from the source
            raw_text = (
                item.get("content")
                or item.get("description")
                or ""
            )

            long_form = rewrite_to_long_form(title, raw_text)

            base_slug = slugify(title)[:200] or "article"

            # 2) Napravi unikatan slug (baza + ova tura)
            unique_slug = base_slug
            suffix = 1
            while unique_slug in used_slugs:
                if suffix == 1:
                    unique_slug = f"{base_slug}-news"
                else:
                    unique_slug = f"{base_slug}-news-{suffix}"
                suffix += 1

            slug = unique_slug
            used_slugs.add(slug)

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

            # da sledeći put znamo da već postoji
            existing_external_ids.add(external_id)

        db.commit()

    finally:
        db.close()
