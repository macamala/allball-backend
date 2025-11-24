from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), unique=True, index=True)
    title = Column(String(512), index=True)
    slug = Column(String(512), unique=True, index=True)
    league = Column(String(128), index=True)
    sport = Column(String(64), index=True)
    country = Column(String(64), index=True)
    division = Column(Integer, default=1)
    image_url = Column(String(1024))
    source_url = Column(String(1024))
    summary = Column(Text)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    is_live = Column(Boolean, default=True)
