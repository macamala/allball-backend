from datetime import datetime

from bot.dedupe import existing_by_url, existing_near_duplicate
from database import SessionLocal, engine
from models import Article, Base


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_url_and_title_dedupe():
    db = SessionLocal()
    try:
        article = Article(
            external_id="https://example.com/villa",
            source_url="https://example.com/villa",
            title="Aston Villa hold Arsenal in Premier League clash",
            slug="villa-hold-arsenal",
            sport="football",
            league="england-premier-league",
            created_at=datetime.utcnow(),
        )
        db.add(article)
        db.commit()
        assert existing_by_url(db, "https://example.com/villa") is not None
        dup = existing_near_duplicate(
            db,
            "Aston Villa hold Arsenal in Premier League clash",
            datetime.utcnow(),
        )
        assert dup is not None
        different = existing_near_duplicate(
            db,
            "Bayern Munich beat Schalke in another story entirely",
            datetime.utcnow(),
        )
        assert different is None
    finally:
        db.close()
