from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)

    # URL izvora (BBC/ESPN...) – koristimo ga za deduplikaciju
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

    # da li je članak "aktivan" na sajtu
    is_live = Column(Boolean, default=True)

    # 🆕 vreme objave na IZVORU (BBC/ESPN…), koristimo za svežinu
    published_at = Column(DateTime, index=True, nullable=True)

    # kada smo mi ubacili u bazu
    created_at = Column(DateTime, default=datetime.utcnow)
