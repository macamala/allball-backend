from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Article
from bot.fetch_sources import LEAGUE_CONFIG

app = FastAPI()

# ----------- CORS FIX (bitno za frontend!) ------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # možeš kasnije ograničiti samo na frontend domen
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# ---------- Glavni /articles endpoint ----------
@app.get("/articles", response_model=List[ArticleOut])
def list_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    sort: str = Query("newest", regex="^(newest|oldest)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
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

    return query.offset(offset).limit(limit).all()


# ---------- Shortcut rute ----------
@app.get("/articles/recent", response_model=List[ArticleOut])
def recent_articles(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    return (
        db.query(Article)
        .order_by(Article.created_at.desc())
        .limit(limit)
        .all()
    )


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return (
        db.query(Article)
        .filter(Article.league == league)
        .order_by(Article.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.get("/articles/by-sport/{sport}", response_model=List[ArticleOut])
def articles_by_sport(
    sport: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return (
        db.query(Article)
        .filter(Article.sport == sport)
        .order_by(Article.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# ---------- NOVA RUTA: jedan članak po slug-u ----------
@app.get("/articles/{slug}")
def get_article_by_slug(slug: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # vraćamo AI content ako postoji, fallback na content/summary
    full_text = article.ai_content or article.content or article.summary

    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "sport": article.sport,
        "league": article.league,
        "country": article.country,
        "division": article.division,
        "image_url": article.image_url,
        "source_url": article.source_url,
        "created_at": article.created_at,
        "content": full_text,
        "ai_generated": getattr(article, "ai_generated", False),
    }


# ---------- Meta rute ----------
@app.get("/meta/leagues")
def list_leagues():
    return LEAGUE_CONFIG


@app.get("/meta/sports")
def list_sports():
    return sorted({cfg["sport"] for cfg in LEAGUE_CONFIG})
