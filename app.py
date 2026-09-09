from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
from xml.sax.saxutils import escape

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, ensure_schema
from models import Article, Base
from bot.fetch_sources import LEAGUE_CONFIG
from bot.taxonomy import competition_label, country_label, sport_label

CANONICAL_SITE = "https://ninkosports.com"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sort_expr():
    return func.coalesce(Article.published_at, Article.created_at)


def serialize_article(article: Article, include_content: bool = False) -> dict:
    full_text = article.ai_content or article.content or article.summary
    data = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "sport": article.sport,
        "league": article.league,
        "country": article.country,
        "division": article.division,
        "image_url": article.image_url,
        "source_url": article.source_url,
        "summary": article.summary,
        "created_at": article.created_at,
        "published_at": article.published_at or article.created_at,
        "ai_generated": bool(getattr(article, "ai_generated", False)),
        "sport_label": sport_label(article.sport),
        "league_label": competition_label(article.league),
        "country_label": country_label(article.country),
    }
    if include_content:
        data["content"] = full_text
    return data


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
    published_at: Optional[datetime] = None
    ai_generated: Optional[bool] = None
    sport_label: Optional[str] = None
    league_label: Optional[str] = None
    country_label: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <h1>NinkoSports backend is running</h1>
    <p>Try <a href="/health">/health</a> or <a href="/articles">/articles</a></p>
    """


@app.get("/health")
def health():
    db_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "allball-backend",
        "database": "ok" if db_ok else "error",
    }


def _filtered_query(
    db: Session,
    sport: Optional[str] = None,
    league: Optional[str] = None,
    country: Optional[str] = None,
):
    query = db.query(Article)
    if sport:
        query = query.filter(Article.sport == sport)
    if league:
        query = query.filter(Article.league == league)
    if country:
        query = query.filter(Article.country == country)
    return query


@app.get("/articles", response_model=List[ArticleOut])
def list_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = _filtered_query(db, sport, league, country)
    order = _sort_expr().asc() if sort == "oldest" else _sort_expr().desc()
    rows = query.order_by(order).offset(offset).limit(limit).all()
    return [serialize_article(row) for row in rows]


@app.get("/articles/recent", response_model=List[ArticleOut])
def recent_articles(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    rows = db.query(Article).order_by(_sort_expr().desc()).limit(limit).all()
    return [serialize_article(row) for row in rows]


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = (
        db.query(Article)
        .filter(Article.league == league)
        .order_by(_sort_expr().desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [serialize_article(row) for row in rows]


@app.get("/articles/by-sport/{sport}", response_model=List[ArticleOut])
def articles_by_sport(
    sport: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    rows = (
        db.query(Article)
        .filter(Article.sport == sport)
        .order_by(_sort_expr().desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [serialize_article(row) for row in rows]


@app.get("/articles/{slug}/related", response_model=List[ArticleOut])
def related_articles(
    slug: str,
    db: Session = Depends(get_db),
    limit: int = Query(6, ge=1, le=20),
):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    related: List[Article] = []
    seen = {article.id}
    if article.league:
        related = (
            db.query(Article)
            .filter(Article.league == article.league, Article.id != article.id)
            .order_by(_sort_expr().desc())
            .limit(limit)
            .all()
        )
        seen.update(a.id for a in related)

    if len(related) < limit and article.sport:
        extra = (
            db.query(Article)
            .filter(Article.sport == article.sport, Article.id.notin_(seen))
            .order_by(_sort_expr().desc())
            .limit(limit - len(related))
            .all()
        )
        related.extend(extra)

    return [serialize_article(row) for row in related[:limit]]


@app.get("/articles/{slug}")
def get_article_by_slug(slug: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return serialize_article(article, include_content=True)


@app.get("/meta/leagues")
def list_leagues():
    return LEAGUE_CONFIG


@app.get("/meta/sports")
def list_sports():
    return sorted({cfg["sport"] for cfg in LEAGUE_CONFIG})


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    rows = (
        db.query(Article.slug, Article.published_at, Article.created_at)
        .order_by(_sort_expr().desc())
        .limit(5000)
        .all()
    )
    urls = [
        "  <url>"
        f"<loc>{CANONICAL_SITE}/</loc>"
        "<changefreq>hourly</changefreq>"
        "</url>"
    ]
    for slug, published_at, created_at in rows:
        if not slug:
            continue
        lastmod = published_at or created_at
        lastmod_xml = ""
        if lastmod is not None:
            if hasattr(lastmod, "date") and callable(getattr(lastmod, "date")):
                iso = lastmod.date().isoformat()
            else:
                iso = str(lastmod)[:10]
            lastmod_xml = f"<lastmod>{iso}</lastmod>"
        urls.append(
            "  <url>"
            f"<loc>{CANONICAL_SITE}/article/{escape(slug)}</loc>"
            f"{lastmod_xml}"
            "</url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
