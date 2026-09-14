from contextlib import asynccontextmanager
from datetime import datetime
import time
from typing import List, Optional
from xml.sax.saxutils import escape

from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, ensure_schema
from models import Article, ArticleMedia, ArticleTaxonomyResolution, ArticleTranslation, Base
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
from sport_match import MAIN_SPORTS as ISOLATED_SPORTS, isolation_ok
from auth import router as auth_router
from comments_api import router as comments_router
from bot.fetch_sources import LEAGUE_CONFIG
from bot.taxonomy import (
    COMPETITIONS,
    PUBLIC_COMPETITION_ALIASES,
    canonical_competition_key,
    competition_label,
    country_label,
    sport_label,
)
from taxonomy_resolver import (
    RESOLVER_VERSION,
    resolve_article_competition,
    resolve_many,
    title_like_terms,
)
from entities import extract_entities
from homepage_compose import (
    _article_stamp,
    competition_modules,
    editorial_score,
    most_read_truthful,
    select_diverse,
    sport_sections,
)
from related import rank_related
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
LEAGUE_PATH_ALIASES = dict(PUBLIC_COMPETITION_ALIASES)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ninkosports.com",
        "https://www.ninkosports.com",
        "https://allball-frontend-production.up.railway.app",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(comments_router)


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
    resolution=None,
) -> dict:
    raw_body = article.ai_content or article.content or article.summary
    title = sanitize_title(article.title)
    summary = sanitize_summary(article.summary, title=article.title)
    body = sanitize_body(raw_body, title=article.title)
    if summary and body:
        prefix = summary[: min(48, len(summary))].lower()
        if prefix and body.lower().startswith(prefix):
            summary = ""
    quality = evaluate_quality(
        title=article.title,
        summary=article.summary,
        body=raw_body,
        image_url=article.image_url,
    )
    media = public_media_items(article.image_url, media_rows)
    hero = next((item for item in media if item.get("is_hero")), media[0] if media else None)
    resolved = resolution or resolve_article_competition(article)
    public_sport = resolved.sport
    public_comp = resolved.public_competition
    data = {
        "id": article.id,
        "title": title,
        "slug": article.slug,
        "sport": public_sport,
        "league": public_comp,
        "country": article.country,
        "division": article.division,
        "image_url": hero["url"] if hero else None,
        "summary": summary,
        "created_at": article.created_at,
        "published_at": article.published_at or article.created_at,
        "ai_generated": bool(getattr(article, "ai_generated", False)),
        "is_breaking": bool(getattr(article, "is_breaking", False)),
        "sport_label": sport_label(public_sport) if public_sport else None,
        "league_label": competition_label(public_comp) if public_comp else None,
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
        words = len(body.split())
        inline = sum(1 for item in media if not item.get("is_hero"))
        if words < 220:
            data["presentation_type"] = "brief"
        elif words >= 900 or inline:
            data["presentation_type"] = "major"
        else:
            data["presentation_type"] = "standard"
    match_sport = public_sport
    data["sport_match_ok"] = bool(
        match_sport and isolation_ok(article, match_sport, strict=True)
    )
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
    sport_match_ok: Optional[bool] = None
    presentation_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


def _resolve_league_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return canonical_competition_key(value) or LEAGUE_PATH_ALIASES.get(value, value)


def _competition_candidate_query(db: Session, competition_key: str, limit: int = 300):
    key = _resolve_league_key(competition_key)
    if not key:
        return db.query(Article).filter(False)
    likes = []
    for term in title_like_terms(key):
        needle = f"%{term.lower()}%"
        likes.append(func.lower(Article.title).like(needle))
        likes.append(func.lower(func.coalesce(Article.summary, "")).like(needle))
    cached_ids = db.query(ArticleTaxonomyResolution.article_id).filter(
        ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        ArticleTaxonomyResolution.resolved_competition == key,
    )
    clauses = [Article.id.in_(cached_ids), Article.league == key]
    if likes:
        clauses.append(or_(*likes))
    return (
        db.query(Article)
        .filter(or_(*clauses))
        .order_by(_sort_expr().desc())
        .limit(limit)
    )


def _serialize_rows(db: Session, rows: List[Article]) -> List[dict]:
    resolutions = resolve_many(db, rows)
    return [
        serialize_article(row, resolution=resolutions.get(row.id))
        for row in rows
    ]


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


def _premium_rows(
    rows: List[Article],
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    strict: bool = True,
    resolutions: Optional[dict] = None,
) -> List[Article]:
    eligible = []
    for row in rows:
        if not _article_quality(article=row)["ok"]:
            continue
        resolved = None
        if resolutions is not None:
            resolved = resolutions.get(row.id)
        if resolved is None:
            resolved = resolve_article_competition(row)
        target = sport or resolved.sport
        if sport == "other":
            if resolved.sport in MAIN_SPORTS:
                continue
        elif sport and resolved.sport and resolved.sport != sport:
            continue
        if not isolation_ok(row, target, strict=strict):
            continue
        if competition and resolved.public_competition != competition:
            continue
        eligible.append(row)
    return eligible


def _has_image(article: Article) -> bool:
    return bool((article.image_url or "").strip())


def _featured_from(
    rows: List[Article],
    limit: int,
    sport: Optional[str] = None,
    strict: bool = True,
) -> List[Article]:
    eligible = [row for row in _premium_rows(rows, sport=sport, strict=strict) if _has_image(row)]
    return eligible[:limit]


def _neighbor(db: Session, article: Article, newer: bool, resolved) -> Optional[Article]:
    stamp = article.published_at or article.created_at
    if stamp is None or not resolved or not resolved.sport:
        return None
    stamp_col = _sort_expr()

    def scoped():
        query = db.query(Article).filter(Article.id != article.id)
        if newer:
            return query.filter(stamp_col > stamp)
        return query.filter(stamp_col < stamp)

    sport_rows = (
        scoped()
        .filter(Article.sport == resolved.sport)
        .order_by(stamp_col.asc() if newer else stamp_col.desc())
        .limit(80)
        .all()
    )
    cache_rows: List[Article] = []
    if resolved.public_competition:
        cache_rows = (
            scoped()
            .join(
                ArticleTaxonomyResolution,
                ArticleTaxonomyResolution.article_id == Article.id,
            )
            .filter(
                ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
                ArticleTaxonomyResolution.resolved_sport == resolved.sport,
                ArticleTaxonomyResolution.resolved_competition == resolved.public_competition,
            )
            .order_by(stamp_col.asc() if newer else stamp_col.desc())
            .limit(24)
            .all()
        )
    merged = {row.id: row for row in sport_rows}
    for row in cache_rows:
        merged[row.id] = row
    rows = sorted(
        merged.values(),
        key=lambda item: _article_stamp(item),
        reverse=not newer,
    )
    resolutions = resolve_many(db, rows)
    same_comp = []
    same_sport = []
    for row in rows:
        other = resolutions.get(row.id)
        if not other or other.sport != resolved.sport:
            continue
        if not _article_quality(row)["ok"]:
            continue
        if not isolation_ok(row, resolved.sport, strict=True):
            continue
        if (
            resolved.public_competition
            and other.public_competition == resolved.public_competition
        ):
            same_comp.append(row)
        else:
            same_sport.append(row)
    if same_comp:
        return same_comp[0]
    if same_sport:
        return same_sport[0]
    return None


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
    isolated = sport in ISOLATED_SPORTS or sport == "other"
    league_key = _resolve_league_key(league)
    order = _sort_expr().asc() if sort == "oldest" else _sort_expr().desc()
    if league_key:
        rows = _competition_candidate_query(
            db, league_key, limit=min(400, max(limit * 25, offset + limit * 20, 120))
        ).all()
        resolutions = resolve_many(db, rows)
        mapped_sport = (COMPETITIONS.get(league_key) or {}).get("sport") or sport
        rows = _premium_rows(
            rows,
            sport=mapped_sport,
            competition=league_key,
            strict=True,
            resolutions=resolutions,
        )[offset : offset + limit]
        return _serialize_rows(db, rows)
    if isolated:
        cached_ids = db.query(ArticleTaxonomyResolution.article_id).filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.resolved_sport == sport,
        )
        fetch = min(400, max(limit * 25, offset + limit * 20, 120))
        rows = (
            db.query(Article)
            .filter(or_(Article.sport == sport, Article.id.in_(cached_ids)))
            .order_by(order)
            .limit(fetch)
            .all()
        )
        resolutions = resolve_many(db, rows)
        rows = _premium_rows(
            rows, sport=sport, strict=True, resolutions=resolutions
        )[offset : offset + limit]
    else:
        rows = (
            _filtered_query(db, sport, None, country, exclude_leagues)
            .order_by(order)
            .offset(offset)
            .limit(limit)
            .all()
        )
        resolve_many(db, rows)
    return _serialize_rows(db, rows)


@app.get("/articles/recent", response_model=List[ArticleOut])
def recent_articles(
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    rows = db.query(Article).order_by(_sort_expr().desc()).limit(max(limit * 4, 40)).all()
    resolutions = resolve_many(db, rows)
    rows = _premium_rows(rows, strict=False, resolutions=resolutions)[:limit]
    return _serialize_rows(db, rows)


@app.get("/articles/featured", response_model=List[ArticleOut])
def featured_articles(
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=12),
):
    if league:
        rows = _competition_candidate_query(db, league, limit=max(limit * 20, 80)).all()
        mapped = (COMPETITIONS.get(_resolve_league_key(league)) or {}).get("sport") or sport
        resolutions = resolve_many(db, rows)
        picked = _featured_from(rows, limit, sport=mapped, strict=True)
        picked = [
            row
            for row in picked
            if (resolutions.get(row.id) or resolve_article_competition(row)).public_competition
            == _resolve_league_key(league)
        ][:limit]
        return _serialize_rows(db, picked)
    rows = (
        _filtered_query(db, sport=sport, league=None)
        .order_by(_sort_expr().desc())
        .limit(max(limit * 20, 80))
        .all()
    )
    return _serialize_rows(db, _featured_from(rows, limit, sport=sport))


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
    return _serialize_rows(db, rows)


@app.get("/articles/most-read", response_model=List[ArticleOut])
def most_read_articles(
    db: Session = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
):
    rows = (
        db.query(Article)
        .filter(Article.view_count > 0)
        .order_by(Article.view_count.desc(), _sort_expr().desc())
        .limit(max(limit * 6, 24))
        .all()
    )
    rows = _premium_rows(rows, strict=False, resolutions=resolve_many(db, rows))[:limit]
    return _serialize_rows(db, rows)


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    league_key = _resolve_league_key(league)
    mapped = (COMPETITIONS.get(league_key) or {}).get("sport")
    rows = _competition_candidate_query(
        db, league_key, limit=min(400, max(limit * 25, offset + limit * 20, 120))
    ).all()
    resolutions = resolve_many(db, rows)
    rows = _premium_rows(
        rows,
        sport=mapped,
        competition=league_key,
        strict=True,
        resolutions=resolutions,
    )[offset : offset + limit]
    return _serialize_rows(db, rows)


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
        .limit(min(400, max(limit * 25, offset + limit * 20, 120)))
        .all()
    )
    cached_ids = db.query(ArticleTaxonomyResolution.article_id).filter(
        ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
        ArticleTaxonomyResolution.resolved_sport == sport,
    )
    extra = (
        db.query(Article)
        .filter(Article.id.in_(cached_ids))
        .order_by(_sort_expr().desc())
        .limit(80)
        .all()
    )
    merged = {row.id: row for row in rows}
    for row in extra:
        merged[row.id] = row
    rows = sorted(
        merged.values(),
        key=lambda item: _article_stamp(item),
        reverse=True,
    )
    resolutions = resolve_many(db, rows)
    rows = _premium_rows(
        rows, sport=sport, strict=True, resolutions=resolutions
    )[offset : offset + limit]
    return _serialize_rows(db, rows)


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
    return _serialize_rows(db, rows)


@app.get("/portal/home")
def portal_home(
    db: Session = Depends(get_db),
    latest_limit: int = Query(10, ge=1, le=50),
    featured_limit: int = Query(5, ge=1, le=8),
    sport_limit: int = Query(4, ge=1, le=12),
    league_min: int = Query(3, ge=1, le=10),
):
    recent = db.query(Article).order_by(_sort_expr().desc()).limit(180).all()
    breaking_pool = (
        db.query(Article)
        .filter(Article.is_breaking == True)
        .order_by(_sort_expr().desc())
        .limit(24)
        .all()
    )
    most_read_pool = (
        db.query(Article)
        .filter(Article.view_count > 0)
        .order_by(Article.view_count.desc(), _sort_expr().desc())
        .limit(24)
        .all()
    )
    merged = {row.id: row for row in recent}
    for row in list(breaking_pool) + list(most_read_pool):
        merged[row.id] = row
    pool = list(merged.values())
    resolutions = resolve_many(db, pool)
    ranked = []
    for row in pool:
        resolved = resolutions.get(row.id) or resolve_article_competition(row)
        quality = _article_quality(row)
        if not quality["ok"]:
            continue
        if resolved.sport in MAIN_SPORTS and not isolation_ok(row, resolved.sport, strict=True):
            continue
        if not resolved.sport:
            continue
        ranked.append(
            editorial_score(
                row,
                resolved,
                quality,
                extract_entities(row.title, row.summary),
            )
        )

    used: set = set()
    featured_items = select_diverse(
        ranked,
        featured_limit,
        used,
        max_per_team=2,
        max_per_competition=3,
        prefer_sport_mix=True,
        require_image=True,
    )
    hero_id = featured_items[0].id if featured_items else None
    prominent = {item.id for item in featured_items}

    breaking_ranked = [
        item for item in ranked if bool(getattr(item.article, "is_breaking", False))
    ]
    breaking_items = []
    breaking_used = set(prominent)
    for item in sorted(
        breaking_ranked,
        key=lambda row: _article_stamp(row.article),
        reverse=True,
    ):
        if item.id in breaking_used:
            continue
        breaking_items.append(item)
        breaking_used.add(item.id)
        if len(breaking_items) >= 8:
            break

    latest_used = set(prominent) | {item.id for item in breaking_items}
    latest_items = []
    for item in sorted(
        ranked,
        key=lambda row: _article_stamp(row.article),
        reverse=True,
    ):
        if item.id in latest_used:
            continue
        latest_items.append(item)
        latest_used.add(item.id)
        if len(latest_items) >= latest_limit:
            break

    most_read_items = most_read_truthful(ranked, 8, hero_id)
    sport_block_ids = set(prominent) | {item.id for item in breaking_items}
    by_sport_ranked = sport_sections(ranked, sport_block_ids, sport_limit)
    by_sport = {sport: [] for sport in MAIN_SPORTS}
    for sport, rows in by_sport_ranked.items():
        by_sport[sport] = _serialize_rows(db, [item.article for item in rows])
    modules = competition_modules(ranked, prominent, league_min)
    by_league = [
        {
            "league": module["league"],
            "label": module["label"],
            "sport": module["sport"],
            "count": module["count"],
            "articles": _serialize_rows(db, [item.article for item in module["stories"]]),
        }
        for module in modules
    ]

    return {
        "featured": _serialize_rows(db, [item.article for item in featured_items]),
        "latest": _serialize_rows(db, [item.article for item in latest_items]),
        "breaking": _serialize_rows(db, [item.article for item in breaking_items]),
        "most_read": _serialize_rows(db, [item.article for item in most_read_items]),
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

    source = resolve_article_competition(article)
    pool: List[Article] = []
    seen = {article.id}
    if source.public_competition:
        pool.extend(
            _competition_candidate_query(db, source.public_competition, limit=max(limit * 8, 32)).all()
        )
        seen.update(a.id for a in pool)
    if source.sport:
        extra = (
            db.query(Article)
            .filter(Article.sport == source.sport, Article.id.notin_(seen))
            .order_by(_sort_expr().desc())
            .limit(max(limit * 8, 32))
            .all()
        )
        pool.extend(extra)
    pool = [row for row in pool if row.id != article.id]
    resolutions = resolve_many(db, pool)
    related = rank_related(
        article,
        source,
        pool,
        resolutions,
        quality_ok=lambda row: _article_quality(row)["ok"],
        isolation_ok=isolation_ok,
        limit=limit,
    )
    return _serialize_rows(db, related)


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
    resolved = resolve_article_competition(article)
    previous = _neighbor(db, article, newer=False, resolved=resolved)
    nxt = _neighbor(db, article, newer=True, resolved=resolved)
    related_insert = None
    related_pool = (
        db.query(Article)
        .filter(Article.id != article.id)
        .order_by(_sort_expr().desc())
        .limit(40)
        .all()
    )
    related_res = resolve_many(db, related_pool)
    insert_rows = rank_related(
        article,
        resolved,
        related_pool,
        related_res,
        quality_ok=lambda row: _article_quality(row)["ok"],
        isolation_ok=isolation_ok,
        limit=1,
    )
    body_preview = sanitize_body(article.ai_content or article.content or article.summary or "", title=article.title)
    if insert_rows and len(body_preview.split()) >= 220:
        related_insert = serialize_article(insert_rows[0], resolution=related_res.get(insert_rows[0].id))
    data = serialize_article(
        article,
        include_content=True,
        media_rows=media_rows,
        related_insert=related_insert,
        resolution=resolved,
    )
    data["previous"] = (
        {"slug": previous.slug, "title": sanitize_title(previous.title)} if previous else None
    )
    data["next"] = {"slug": nxt.slug, "title": sanitize_title(nxt.title)} if nxt else None
    return data


@app.get("/articles/{slug}/translation/{language}")
def article_translation(slug: str, language: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    row = (
        db.query(ArticleTranslation)
        .filter(
            ArticleTranslation.article_id == article.id,
            ArticleTranslation.language_code == language,
            ArticleTranslation.status == "ready",
        )
        .first()
    )
    if not row:
        return {
            "available": False,
            "language": language,
            "status": "missing",
            "message": "English article is shown until a translation is ready.",
        }
    return {
        "available": True,
        "language": language,
        "status": row.status,
        "title": row.translated_title,
        "summary": row.translated_summary,
        "body": row.translated_body,
    }


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
