from contextlib import asynccontextmanager
from datetime import datetime
import time
from typing import List, Optional
from xml.sax.saxutils import escape

from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, ensure_schema
from models import Article, ArticleMedia, Base
from editorial import (
    attach_inline_media,
    evaluate_quality,
    maybe_related_insert,
    public_media_items,
    sanitize_body,
    sanitize_summary,
    sanitize_title,
    to_blocks,
)
from bot.fetch_sources import LEAGUE_CONFIG
from bot.taxonomy import COMPETITIONS, competition_label, country_label, sport_label
from sports_provider import (
    empty_match_payload,
    empty_scores_payload,
    empty_standings_payload,
    empty_team_payload,
    provider_status,
)

CANONICAL_SITE = "https://ninkosports.com"
MAIN_SPORTS = ("football", "basketball", "tennis", "motorsport")
VIEW_DEDUP_SECONDS = 30 * 60
_recent_views = {}

SPORT_PATHS = {
    "football": "/football",
    "basketball": "/basketball",
    "tennis": "/tennis",
    "motorsport": "/motorsport",
}

# Public URL slugs that map onto stored competition keys.
LEAGUE_PATH_ALIASES = {
    "premier-league": "england-premier-league",
    "champions-league": "uefa-champions-league",
    "la-liga": "spain-la-liga",
    "serie-a": "italy-serie-a",
    "bundesliga": "germany-bundesliga",
    "ligue-1": "france-ligue-1",
    "europa-league": "uefa-europa-league",
    "conference-league": "uefa-conference-league",
    "ncaa": "ncaa-basketball",
}


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


def _reading_minutes(text_value: Optional[str]) -> int:
    words = len((text_value or "").split())
    if words <= 0:
        return 1
    return max(1, round(words / 220))


def serialize_article(
    article: Article,
    include_content: bool = False,
    media_rows: Optional[list] = None,
    related_insert: Optional[dict] = None,
) -> dict:
    raw_body = article.ai_content or article.content or article.summary
    title = sanitize_title(article.title)
    summary = sanitize_summary(article.summary, title=article.title)
    body = sanitize_body(raw_body, title=article.title)
    quality = evaluate_quality(
        title=article.title,
        summary=article.summary,
        body=raw_body,
        image_url=article.image_url,
    )
    media = public_media_items(article.image_url, media_rows)
    hero = next((item for item in media if item.get("is_hero")), media[0] if media else None)
    data = {
        "id": article.id,
        "title": title,
        "slug": article.slug,
        "sport": article.sport,
        "league": article.league,
        "country": article.country,
        "division": article.division,
        "image_url": hero["url"] if hero else None,
        "summary": summary,
        "created_at": article.created_at,
        "published_at": article.published_at or article.created_at,
        "ai_generated": bool(getattr(article, "ai_generated", False)),
        "is_breaking": bool(getattr(article, "is_breaking", False)),
        "sport_label": sport_label(article.sport),
        "league_label": competition_label(article.league),
        "country_label": country_label(article.country),
        "quality_ok": bool(quality["ok"]),
    }
    if include_content:
        blocks = attach_inline_media(to_blocks(raw_body, title=article.title), media)
        blocks = maybe_related_insert(blocks, related_insert)
        data["content"] = body
        data["blocks"] = blocks
        data["media"] = media
        data["reading_time_minutes"] = _reading_minutes(body)
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
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    ai_generated: Optional[bool] = None
    is_breaking: Optional[bool] = False
    sport_label: Optional[str] = None
    league_label: Optional[str] = None
    country_label: Optional[str] = None
    quality_ok: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


def _resolve_league_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return LEAGUE_PATH_ALIASES.get(value, value)


def _filtered_query(
    db: Session,
    sport: Optional[str] = None,
    league: Optional[str] = None,
    country: Optional[str] = None,
    exclude_leagues: Optional[str] = None,
):
    query = db.query(Article)
    if sport == "other":
        query = query.filter(
            or_(Article.sport.is_(None), Article.sport.notin_(MAIN_SPORTS))
        )
    elif sport:
        query = query.filter(Article.sport == sport)
    league_key = _resolve_league_key(league)
    if league_key:
        query = query.filter(Article.league == league_key)
    if country:
        query = query.filter(Article.country == country)
    if exclude_leagues:
        keys = [item.strip() for item in exclude_leagues.split(",") if item.strip()]
        keys = [_resolve_league_key(item) for item in keys]
        keys = [item for item in keys if item]
        if keys:
            query = query.filter(or_(Article.league.is_(None), Article.league.notin_(keys)))
    return query


def _search_query(db: Session, q: str, sport: Optional[str], league: Optional[str]):
    term = "".join(ch for ch in q.strip() if ch not in "%_")
    if len(term) < 2:
        return None
    like = f"%{term.lower()}%"
    query = _filtered_query(db, sport=sport, league=league)
    return query.filter(
        or_(
            func.lower(Article.title).like(like),
            func.lower(func.coalesce(Article.summary, "")).like(like),
            func.lower(func.coalesce(Article.sport, "")).like(like),
            func.lower(func.coalesce(Article.league, "")).like(like),
        )
    )


def _article_quality(article: Article) -> dict:
    raw_body = article.ai_content or article.content or article.summary
    return evaluate_quality(
        title=article.title,
        summary=article.summary,
        body=raw_body,
        image_url=article.image_url,
    )


def _premium_rows(rows: List[Article]) -> List[Article]:
    return [row for row in rows if _article_quality(article=row)["ok"]]


def _has_image(article: Article) -> bool:
    return bool((article.image_url or "").strip())


def _featured_from(rows: List[Article], limit: int) -> List[Article]:
    eligible = [
        row
        for row in _premium_rows(rows)
        if _article_quality(row)["ok"] and _has_image(row)
    ]
    return eligible[:limit]


def _neighbor(db: Session, article: Article, newer: bool) -> Optional[Article]:
    stamp = article.published_at or article.created_at
    query = db.query(Article).filter(Article.id != article.id)
    if stamp is None:
        return None
    if newer:
        row = (
            query.filter(_sort_expr() > stamp)
            .order_by(_sort_expr().asc())
            .first()
        )
    else:
        row = (
            query.filter(_sort_expr() < stamp)
            .order_by(_sort_expr().desc())
            .first()
        )
    return row


def _prune_views(now: float):
    stale = [key for key, seen in _recent_views.items() if now - seen > VIEW_DEDUP_SECONDS]
    for key in stale:
        _recent_views.pop(key, None)


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


@app.get("/articles", response_model=List[ArticleOut])
def list_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    exclude_leagues: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = _filtered_query(db, sport, league, country, exclude_leagues)
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


@app.get("/articles/featured", response_model=List[ArticleOut])
def featured_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=12),
):
    rows = (
        _filtered_query(db, sport=sport, league=league)
        .order_by(_sort_expr().desc())
        .limit(max(limit * 8, 40))
        .all()
    )
    return [serialize_article(row) for row in _featured_from(rows, limit)]


@app.get("/articles/breaking", response_model=List[ArticleOut])
def breaking_articles(
    db: Session = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
):
    rows = (
        db.query(Article)
        .filter(Article.is_breaking == True)
        .order_by(_sort_expr().desc())
        .limit(limit)
        .all()
    )
    return [serialize_article(row) for row in rows]


@app.get("/articles/most-read", response_model=List[ArticleOut])
def most_read_articles(
    db: Session = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
):
    rows = (
        db.query(Article)
        .filter(Article.view_count > 0)
        .order_by(Article.view_count.desc(), _sort_expr().desc())
        .limit(limit)
        .all()
    )
    return [serialize_article(row) for row in rows]


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    league_key = _resolve_league_key(league)
    rows = (
        db.query(Article)
        .filter(Article.league == league_key)
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
        _filtered_query(db, sport=sport)
        .order_by(_sort_expr().desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [serialize_article(row) for row in rows]


@app.get("/search", response_model=List[ArticleOut])
def search_articles(
    q: str = Query("", min_length=0, max_length=120),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = _search_query(db, q, sport, league)
    if query is None:
        return []
    rows = query.order_by(_sort_expr().desc()).limit(limit).all()
    return [serialize_article(row) for row in rows]


@app.get("/portal/home")
def portal_home(
    db: Session = Depends(get_db),
    latest_limit: int = Query(24, ge=1, le=50),
    featured_limit: int = Query(5, ge=1, le=8),
    sport_limit: int = Query(6, ge=1, le=12),
    league_min: int = Query(3, ge=1, le=10),
):
    latest_pool = (
        db.query(Article).order_by(_sort_expr().desc()).limit(max(latest_limit * 3, 40)).all()
    )
    latest_rows = latest_pool[:latest_limit]
    featured = _featured_from(latest_pool, featured_limit)
    breaking_pool = (
        db.query(Article)
        .filter(Article.is_breaking == True)
        .order_by(_sort_expr().desc())
        .limit(24)
        .all()
    )
    breaking_rows = _premium_rows(breaking_pool)[:8]
    most_read_rows = (
        db.query(Article)
        .filter(Article.view_count > 0)
        .order_by(Article.view_count.desc(), _sort_expr().desc())
        .limit(8)
        .all()
    )
    by_sport = {}
    for sport in MAIN_SPORTS:
        sport_pool = (
            db.query(Article)
            .filter(Article.sport == sport)
            .order_by(_sort_expr().desc())
            .limit(sport_limit * 4)
            .all()
        )
        premium = _premium_rows(sport_pool)[:sport_limit]
        by_sport[sport] = [serialize_article(row) for row in premium]

    count_rows = (
        db.query(Article.league, func.count(Article.id))
        .filter(Article.league.isnot(None), Article.league != "")
        .group_by(Article.league)
        .having(func.count(Article.id) >= league_min)
        .order_by(func.count(Article.id).desc())
        .limit(8)
        .all()
    )
    by_league = []
    for league_key, count in count_rows:
        league_pool = (
            db.query(Article)
            .filter(Article.league == league_key)
            .order_by(_sort_expr().desc())
            .limit(16)
            .all()
        )
        league_rows = _premium_rows(league_pool)[:4]
        if not league_rows:
            continue
        by_league.append(
            {
                "league": league_key,
                "label": competition_label(league_key),
                "sport": league_rows[0].sport if league_rows else None,
                "count": count,
                "articles": [serialize_article(row) for row in league_rows],
            }
        )

    return {
        "featured": [serialize_article(row) for row in featured],
        "latest": [serialize_article(row) for row in latest_rows],
        "breaking": [serialize_article(row) for row in breaking_rows],
        "most_read": [serialize_article(row) for row in most_read_rows],
        "by_sport": by_sport,
        "by_league": by_league,
        "sports_data": provider_status(),
    }


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


@app.post("/articles/{slug}/view")
def record_article_view(slug: str, request: Request, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    now = time.time()
    if len(_recent_views) > 5000:
        _prune_views(now)
    client = request.client.host if request.client else "unknown"
    key = (client, slug)
    if now - _recent_views.get(key, 0) < VIEW_DEDUP_SECONDS:
        return {"ok": True, "counted": False}

    current = int(getattr(article, "view_count", 0) or 0)
    article.view_count = current + 1
    db.add(article)
    db.commit()
    _recent_views[key] = now
    return {"ok": True, "counted": True}


@app.get("/articles/{slug}")
def get_article_by_slug(slug: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    media_rows = (
        db.query(ArticleMedia)
        .filter(ArticleMedia.article_id == article.id)
        .order_by(ArticleMedia.is_hero.desc(), ArticleMedia.sort_order.asc(), ArticleMedia.id.asc())
        .all()
    )
    previous = _neighbor(db, article, newer=False)
    nxt = _neighbor(db, article, newer=True)
    related_insert = None
    related_rows = (
        db.query(Article)
        .filter(Article.id != article.id)
        .filter(Article.league == article.league if article.league else Article.sport == article.sport)
        .order_by(_sort_expr().desc())
        .limit(1)
        .all()
    )
    if related_rows:
        related_insert = serialize_article(related_rows[0])
    data = serialize_article(
        article,
        include_content=True,
        media_rows=media_rows,
        related_insert=related_insert,
    )
    data["previous"] = (
        {"slug": previous.slug, "title": sanitize_title(previous.title)} if previous else None
    )
    data["next"] = {"slug": nxt.slug, "title": sanitize_title(nxt.title)} if nxt else None
    return data


@app.get("/meta/leagues")
def list_leagues():
    return LEAGUE_CONFIG


@app.get("/meta/sports")
def list_sports():
    return sorted({cfg["sport"] for cfg in LEAGUE_CONFIG})


@app.get("/meta/navigation")
def navigation(db: Session = Depends(get_db)):
    counts = dict(
        db.query(Article.league, func.count(Article.id))
        .group_by(Article.league)
        .all()
    )
    sports = []
    for sport in MAIN_SPORTS:
        leagues = []
        for slug, meta in COMPETITIONS.items():
            if meta.get("sport") != sport:
                continue
            leagues.append(
                {
                    "league": slug,
                    "label": meta.get("label") or competition_label(slug),
                    "country": meta.get("country"),
                    "article_count": int(counts.get(slug) or 0),
                }
            )
        sports.append(
            {
                "sport": sport,
                "label": sport_label(sport),
                "path": SPORT_PATHS.get(sport, f"/{sport}"),
                "article_count": int(
                    db.query(func.count(Article.id))
                    .filter(Article.sport == sport)
                    .scalar()
                    or 0
                ),
                "leagues": leagues,
            }
        )
    return {"sports": sports, "league_aliases": LEAGUE_PATH_ALIASES}


@app.get("/sports-data/status")
def sports_data_status():
    return provider_status()


@app.get("/sports-data/scores")
def sports_data_scores():
    return empty_scores_payload()


@app.get("/sports-data/standings")
def sports_data_standings(league: Optional[str] = Query(None)):
    return empty_standings_payload(_resolve_league_key(league))


@app.get("/sports-data/matches/{match_id}")
def sports_data_match(match_id: str):
    return empty_match_payload(match_id)


@app.get("/sports-data/teams/{slug}")
def sports_data_team(slug: str):
    return empty_team_payload(slug)


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    rows = (
        db.query(Article.slug, Article.published_at, Article.created_at)
        .order_by(_sort_expr().desc())
        .limit(5000)
        .all()
    )
    league_rows = (
        db.query(Article.sport, Article.league)
        .filter(Article.league.isnot(None), Article.league != "")
        .distinct()
        .all()
    )

    def url_xml(path: str, changefreq: str = "hourly", lastmod=None):
        lastmod_xml = ""
        if lastmod is not None:
            if hasattr(lastmod, "date") and callable(getattr(lastmod, "date")):
                iso = lastmod.date().isoformat()
            else:
                iso = str(lastmod)[:10]
            lastmod_xml = f"<lastmod>{iso}</lastmod>"
        return (
            "  <url>"
            f"<loc>{CANONICAL_SITE}{path}</loc>"
            f"{lastmod_xml}"
            f"<changefreq>{changefreq}</changefreq>"
            "</url>"
        )

    urls = [
        url_xml("/", "hourly"),
        url_xml("/football", "hourly"),
        url_xml("/basketball", "hourly"),
        url_xml("/tennis", "hourly"),
        url_xml("/motorsport", "hourly"),
        url_xml("/other-sports", "daily"),
        url_xml("/live-scores", "hourly"),
        url_xml("/search", "weekly"),
        url_xml("/my-sports", "weekly"),
    ]
    for sport, league_key in league_rows:
        if not league_key:
            continue
        sport_slug = sport if sport in SPORT_PATHS else None
        if sport_slug:
            urls.append(url_xml(f"/{sport_slug}/{escape(league_key)}", "hourly"))
    for slug, published_at, created_at in rows:
        if not slug:
            continue
        urls.append(
            url_xml(f"/article/{escape(slug)}", "weekly", published_at or created_at)
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
