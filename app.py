from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from typing import Optional, List

from database import SessionLocal, engine
from models import Base, Article

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AllBallSports API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/articles")
def get_articles(
    sport: Optional[str] = None,
    league: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    q = db.query(Article).filter(Article.is_live == True)

    if sport:
        q = q.filter(Article.sport == sport)

    if league:
        q = q.filter(Article.league == league)

    if country:
        q = q.filter(Article.country == country)

    q = q.order_by(Article.created_at.desc()).limit(limit)
    return q.all()


@app.get("/article/{slug}")
def get_article(slug: str, db: Session = Depends(get_db)):
    return db.query(Article).filter(Article.slug == slug).first()


@app.get("/health")
def health():
    return {"status": "ok"}
