from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base
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

    # 👉 NOVO: naš AI prošireni tekst (300–500+ reči)
    ai_content = Column(Text, nullable=True)

    # (opciono, ali korisno) da znamo da li je generisan AI tekst
    ai_generated = Column(Boolean, default=False)

    is_live = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
