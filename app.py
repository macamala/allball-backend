from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article
from bot.fetch_sources import LEAGUE_CONFIG

app = FastAPI()


# ---------- DB dependency ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- Pydantic schema za izlaz ----------

class ArticleOut(BaseModel):
    id: int
    title: str
    slug: str
    sport: Optional[str] = None
    league: Optional[str] = None
    country: Optional[str] = None
    division: Optional[int] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ---------- Root i health ----------

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <h1>AllBallSports backend is running ✅</h1>
    <p>Try <a href="/health">/health</a> or <a href="/articles">/articles</a></p>
    """


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Glavni /articles endpoint sa sortiranjem i filterima ----------

@app.get("/articles", response_model=List[ArticleOut])
def list_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None, description="football, basketball, ..."),
    league: Optional[str] = Query(None, description="npr. england-premier-league"),
    country: Optional[str] = Query(None, description="england, spain, usa, ..."),
    sort: str = Query("newest", regex="^(newest|oldest)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Glavni listing artikala.

    Primeri:
    - /articles
    - /articles?sport=football
    - /articles?league=england-premier-league&limit=10
    - /articles?country=england&sport=football&sort=oldest
    """
    query = db.query(Article)

    if sport:
        query = query.filter(Article.sport == sport)

    if league:
        query = query.filter(Article.league == league)

    if country:
        query = query.filter(Article.country == country)

    if sort == "oldest":
        query = query.order_by(Article.created_at.asc())
    else:
        query = query.order_by(Article.created_at.desc())

    articles = query.offset(offset).limit(limit).all()
    return articles


# ---------- Shortcut rute ----------

@app.get("/articles/recent", response_model=List[ArticleOut])
def recent_articles(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Najnovije vesti globalno.
    /articles/recent?limit=10
    """
    articles = (
        db.query(Article)
        .order_by(Article.created_at.desc())
        .limit(limit)
        .all()
    )
    return articles


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Sve vesti za jednu ligu:
    /articles/by-league/england-premier-league
    """
    query = (
        db.query(Article)
        .filter(Article.league == league)
        .order_by(Article.created_at.desc())
    )
    return query.offset(offset).limit(limit).all()


@app.get("/articles/by-sport/{sport}", response_model=List[ArticleOut])
def articles_by_sport(
    sport: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    Sve vesti za jedan sport:
    /articles/by-sport/football
    /articles/by-sport/basketball
    """
    query = (
        db.query(Article)
        .filter(Article.sport == sport)
        .order_by(Article.created_at.desc())
    )
    return query.offset(offset).limit(limit).all()


# ---------- Meta rute za frontend filtere ----------

@app.get("/meta/leagues")
def list_leagues():
    """
    Sve lige iz LEAGUE_CONFIG (sport, league, country, query).
    Frontend može da puni drop-down odavde.
    """
    return LEAGUE_CONFIG


@app.get("/meta/sports")
def list_sports():
    """
    Jedinstveni sportovi (football, basketball, ...).
    """
    sports = sorted({cfg["sport"] for cfg in LEAGUE_CONFIG})
    return sports
