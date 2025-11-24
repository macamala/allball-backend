from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/articles")
def get_articles(
    sport: Optional[str] = None,
    league: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(Article).filter(Article.is_live == True)
    if sport:
        query = query.filter(Article.sport == sport)
    if league:
        query = query.filter(Article.league == league)

    articles = query.order_by(Article.created_at.desc()).limit(limit).all()
    return articles


@app.get("/article/{slug}")
def get_article(slug: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
