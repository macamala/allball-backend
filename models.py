from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)

    external_id = Column(String(500), unique=True, index=True)
    title = Column(String(500))
    slug = Column(String(300), unique=True, index=True)

    sport = Column(String(50))
    league = Column(String(100))
    country = Column(String(100))
    division = Column(Integer, default=1)

    image_url = Column(String(500))
    source_url = Column(String(500))

    summary = Column(Text)
    content = Column(Text)

    # naš AI prošireni tekst (300–500+ reči)
    ai_content = Column(Text, nullable=True)

    # da znamo da li je generisan AI tekst
    ai_generated = Column(Boolean, default=False)

    is_live = Column(Boolean, default=True)

    # Phase 3 flags: additive defaults only. Never backfill historical rows.
    is_breaking = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)

    media_items = relationship("ArticleMedia", back_populates="article")


class ArticleMedia(Base):
    """Additive media rows. Never migrates or replaces Article.image_url."""

    __tablename__ = "article_media"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), index=True, nullable=False)
    media_type = Column(String(50), default="image")
    url = Column(String(1000))
    caption = Column(Text, nullable=True)
    # Internal licensing/provenance. Not serialized on public APIs.
    credit = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    provider_media_id = Column(String(200), nullable=True)
    is_hero = Column(Boolean, default=False)

    article = relationship("Article", back_populates="media_items")
