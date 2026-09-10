from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
)
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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(500), nullable=False)
    display_name = Column(String(80), nullable=False)
    role = Column(String(20), default="user")
    preferred_language = Column(String(10), default="en")
    avatar_url = Column(String(1000), nullable=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    token_hash = Column(String(128), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "value", name="uq_user_favorite"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    kind = Column(String(20), nullable=False)  # sports | leagues | teams
    value = Column(String(120), nullable=False)


class SavedArticle(Base):
    __tablename__ = "saved_articles"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_saved_article"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    article_id = Column(Integer, ForeignKey("articles.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    body = Column(Text, nullable=False)
    like_count = Column(Integer, default=0)
    hidden = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)


class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="uq_comment_like"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CommentReport(Base):
    __tablename__ = "comment_reports"

    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    reason = Column(String(80), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ArticleTranslation(Base):
    """Cache for a future translation provider. No provider is called in Phase 4."""

    __tablename__ = "article_translations"
    __table_args__ = (
        UniqueConstraint("article_id", "language_code", name="uq_article_translation"),
        Index("ix_translation_status", "language_code", "status"),
    )

    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), index=True, nullable=False)
    language_code = Column(String(10), nullable=False)
    translated_title = Column(Text, nullable=True)
    translated_summary = Column(Text, nullable=True)
    translated_body = Column(Text, nullable=True)
    status = Column(String(20), default="missing")  # missing | pending | ready | failed
    provider = Column(String(80), nullable=True)
    model_name = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
