import os
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
import threading
import time
from typing import List, Optional
from xml.sax.saxutils import escape

from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import SessionLocal, engine, ensure_schema
from models import Article, ArticleMedia, ArticleTaxonomyResolution, ArticleTranslation, Base
from editorial import classify_media_url, sanitize_title
from auth import router as auth_router
from comments_api import router as comments_router
from predictions_api import router as predictions_router
from bot.fetch_sources import LEAGUE_CONFIG
from bot.taxonomy import (
    COMPETITIONS,
    MAIN_SPORT_SLUGS,
    PUBLIC_COMPETITION_ALIASES,
    canonical_competition_key,
    competition_label,
    sport_catalog,
    sport_label,
)
from sports_registry.api import (
    competitions_payload,
    geography_payload,
    providers_payload,
    registry_payload,
)
from sports_registry.schema import CATEGORY_LABELS, SPORT_CATEGORIES
from sports_registry.sports import get_sport as registry_get_sport
from sports_registry.sports import sitemap_sport_paths
from homepage_compose import HOMEPAGE_COMPETITIONS, editorial_score, select_diverse
from entities import extract_entities
from public_cache import cache_generation
from public_index import index_missing, load_cached_resolution
from public_read import (
    apply_scope,
    fetch_public,
    neighbor_article,
    public_query,
    related_cards,
    serialize_card,
    serialize_cards,
    serialize_detail,
)
from taxonomy_resolver import RESOLVER_VERSION, cache_row_to_resolution
from sports_provider import (
    empty_competitions_payload,
    empty_events_payload,
    empty_match_payload,
    empty_scores_payload,
    empty_standings_payload,
    empty_team_payload,
    events_to_legacy_matches,
    get_active_provider,
    partition_score_events,
    provider_status,
)

CANONICAL_SITE = "https://ninkosports.com"
MAIN_SPORTS = MAIN_SPORT_SLUGS
VIEW_DEDUP_SECONDS = 30 * 60
_recent_views = {}

SPORT_PATHS = {
    slug: (registry_get_sport(slug) or {}).get("path") or f"/{slug}"
    for slug in MAIN_SPORTS
}

# Public URL slugs that map onto stored competition keys.
LEAGUE_PATH_ALIASES = dict(PUBLIC_COMPETITION_ALIASES)


def _startup_index():
    db = SessionLocal()
    try:
        while True:
            counted = index_missing(db, limit=400)
            if counted < 400:
                break
    finally:
        db.close()
    from repair_content import repair_contaminated

    repair_contaminated()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    if os.getenv("NINKO_SKIP_STARTUP_INDEX") != "1":
        threading.Thread(target=_startup_index, daemon=True).start()
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
app.include_router(predictions_router)

PUBLIC_CACHE = "public, max-age=5, s-maxage=10, stale-while-revalidate=20"


@app.middleware("http")
async def public_read_cache(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if request.method != "GET":
        return response
    if path.startswith("/auth") or "/comments" in path or path.endswith("/view"):
        response.headers["Cache-Control"] = "private, no-store"
        return response
    if (
        path == "/portal/home"
        or path.startswith("/articles")
        or path.startswith("/search")
        or path.startswith("/meta/")
    ):
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", PUBLIC_CACHE)
        elif response.status_code == 404:
            response.headers.setdefault("Cache-Control", "public, max-age=10")
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sort_expr():
    return func.coalesce(Article.published_at, Article.created_at)


def serialize_article(
    article: Article,
    include_content: bool = False,
    media_rows: Optional[list] = None,
    related_insert: Optional[dict] = None,
    resolution=None,
) -> dict:
    """Auth/saved compatibility. Public list/detail use public_read serializers."""
    tax = resolution if hasattr(resolution, "public_ok") else None
    if include_content:
        return serialize_detail(
            article, tax, media_rows=media_rows, related_insert=related_insert
        )
    if tax is not None:
        return serialize_card(article, tax)
    stub = SimpleNamespace(
        resolved_sport=None,
        resolved_competition=None,
        hero_media_kind=classify_media_url(article.image_url),
        quality_ok=False,
        public_ok=False,
    )
    return serialize_card(article, stub)


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
    hero_media_kind: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


def _resolve_league_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return canonical_competition_key(value) or LEAGUE_PATH_ALIASES.get(value, value)


def _cache_headers(response: Response, pairs_or_article=None):
    response.headers["Cache-Control"] = PUBLIC_CACHE
    gen = cache_generation()
    if isinstance(pairs_or_article, list) and pairs_or_article:
        row = (
            pairs_or_article[0][0]
            if isinstance(pairs_or_article[0], tuple)
            else pairs_or_article[0]
        )
        stamp = getattr(row, "published_at", None) or getattr(row, "created_at", None)
        response.headers["ETag"] = f'W/"{gen}-{getattr(row, "id", "x")}-{stamp}"'
    elif pairs_or_article is not None and getattr(pairs_or_article, "id", None):
        stamp = pairs_or_article.published_at or pairs_or_article.created_at
        response.headers["ETag"] = f'W/"{gen}-{pairs_or_article.id}-{stamp}"'
    else:
        response.headers["ETag"] = f'W/"home-{gen}"'


def _search_public(db: Session, q: str, sport: Optional[str], league: Optional[str], limit: int):
    term = "".join(ch for ch in q.strip() if ch not in "%_")
    if len(term) < 2:
        return []
    like = f"%{term.lower()}%"
    return (
        apply_scope(
            public_query(db, cards=True),
            sport=sport,
            competition=_resolve_league_key(league),
        )
        .filter(func.lower(Article.title).like(like))
        .order_by(_sort_expr().desc())
        .limit(limit)
        .all()
    )


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
    response: Response,
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    exclude_leagues: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    excluded = None
    if exclude_leagues:
        excluded = [
            _resolve_league_key(item.strip())
            for item in exclude_leagues.split(",")
            if item.strip()
        ]
    pairs = fetch_public(
        db,
        sport=sport,
        competition=_resolve_league_key(league),
        exclude_competitions=excluded,
        limit=limit,
        offset=offset,
        sort=sort,
    )
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/recent", response_model=List[ArticleOut])
def recent_articles(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    pairs = fetch_public(db, limit=limit)
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/featured", response_model=List[ArticleOut])
def featured_articles(
    response: Response,
    db: Session = Depends(get_db),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=12),
):
    pairs = fetch_public(
        db,
        sport=sport,
        competition=_resolve_league_key(league),
        require_photo=True,
        limit=limit,
    )
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/breaking", response_model=List[ArticleOut])
def breaking_articles(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
):
    pairs = fetch_public(db, breaking=True, limit=limit)
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/most-read", response_model=List[ArticleOut])
def most_read_articles(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(8, ge=1, le=20),
):
    pairs = fetch_public(db, viewed=True, limit=limit)
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/by-league/{league}", response_model=List[ArticleOut])
def articles_by_league(
    league: str,
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    pairs = fetch_public(
        db,
        competition=_resolve_league_key(league),
        limit=limit,
        offset=offset,
    )
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/articles/by-sport/{sport}", response_model=List[ArticleOut])
def articles_by_sport(
    sport: str,
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    pairs = fetch_public(db, sport=sport, limit=limit, offset=offset)
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/search", response_model=List[ArticleOut])
def search_articles(
    response: Response,
    q: str = Query("", min_length=0, max_length=120),
    sport: Optional[str] = Query(None),
    league: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    pairs = _search_public(db, q, sport, league, limit)
    _cache_headers(response, pairs)
    return serialize_cards(pairs)


@app.get("/portal/home")
def portal_home(
    response: Response,
    db: Session = Depends(get_db),
    latest_limit: int = Query(10, ge=1, le=50),
    featured_limit: int = Query(5, ge=1, le=8),
    sport_limit: int = Query(4, ge=1, le=12),
    league_min: int = Query(3, ge=1, le=10),
):
    featured_pairs = fetch_public(db, require_photo=True, limit=max(featured_limit * 4, 16))
    ranked = []
    for article, tax in featured_pairs:
        ranked.append(
            editorial_score(
                article,
                cache_row_to_resolution(tax),
                {"ok": True, "word_count": int(tax.word_count or 0), "flags": []},
                extract_entities(article.title, article.summary),
            )
        )
    used = set()
    featured_items = select_diverse(
        ranked,
        featured_limit,
        used,
        max_per_team=2,
        max_per_competition=3,
        prefer_sport_mix=True,
        require_image=True,
    )
    featured_ids = {item.id for item in featured_items}
    tax_by_id = {article.id: tax for article, tax in featured_pairs}

    latest_pairs = fetch_public(db, limit=latest_limit + len(featured_ids) + 8)
    latest_kept = [
        (row, tax) for row, tax in latest_pairs if row.id not in featured_ids
    ][:latest_limit]
    breaking_pairs = fetch_public(db, breaking=True, limit=8)
    breaking_kept = [
        (row, tax) for row, tax in breaking_pairs if row.id not in featured_ids
    ][:8]
    most_read_pairs = fetch_public(db, viewed=True, limit=8 + len(featured_ids))
    most_read_kept = [
        (row, tax) for row, tax in most_read_pairs if row.id not in featured_ids
    ][:8]

    by_sport = {}
    for sport in MAIN_SPORTS:
        by_sport[sport] = serialize_cards(fetch_public(db, sport=sport, limit=sport_limit))

    by_league = []
    for key in HOMEPAGE_COMPETITIONS:
        rows = fetch_public(db, competition=key, limit=4)
        if len(rows) < league_min:
            continue
        by_league.append(
            {
                "league": key,
                "label": competition_label(key),
                "sport": rows[0][1].resolved_sport,
                "count": len(rows),
                "articles": serialize_cards(rows),
            }
        )
        if len(by_league) >= 4:
            break

    featured_out = [
        serialize_card(item.article, tax_by_id[item.id])
        for item in featured_items
        if item.id in tax_by_id
    ]
    payload = {
        "featured": featured_out,
        "latest": serialize_cards(latest_kept),
        "breaking": serialize_cards(breaking_kept),
        "most_read": serialize_cards(most_read_kept),
        "by_sport": by_sport,
        "by_league": by_league,
        "sports_data": provider_status(),
    }
    _cache_headers(response, featured_pairs or latest_pairs)
    return payload


@app.get("/articles/{slug}/related", response_model=List[ArticleOut])
def related_articles(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    limit: int = Query(6, ge=1, le=20),
):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    tax = load_cached_resolution(db, article)
    cards = related_cards(db, article, tax, limit=limit)
    _cache_headers(response)
    return cards


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
def get_article_by_slug(slug: str, response: Response, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.slug == slug).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    media_rows = (
        db.query(ArticleMedia)
        .filter(ArticleMedia.article_id == article.id)
        .order_by(
            ArticleMedia.is_hero.desc(),
            ArticleMedia.sort_order.asc(),
            ArticleMedia.id.asc(),
        )
        .all()
    )
    tax = load_cached_resolution(db, article)
    previous = neighbor_article(db, article, tax, newer=False)
    nxt = neighbor_article(db, article, tax, newer=True)
    related_insert = None
    related = related_cards(db, article, tax, limit=1)
    if related:
        related_insert = related[0]
    data = serialize_detail(
        article, tax, media_rows=media_rows, related_insert=related_insert
    )
    data["previous"] = (
        {"slug": previous.slug, "title": sanitize_title(previous.title)} if previous else None
    )
    data["next"] = {"slug": nxt.slug, "title": sanitize_title(nxt.title)} if nxt else None
    _cache_headers(response, article)
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
    return [row["sport"] for row in sport_catalog()]


@app.get("/meta/taxonomy")
def taxonomy_meta(db: Session = Depends(get_db)):
    counts = dict(
        db.query(
            ArticleTaxonomyResolution.resolved_sport,
            func.count(ArticleTaxonomyResolution.id),
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
        )
        .group_by(ArticleTaxonomyResolution.resolved_sport)
        .all()
    )
    competition_counts = dict(
        db.query(
            ArticleTaxonomyResolution.resolved_competition,
            func.count(ArticleTaxonomyResolution.id),
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
            ArticleTaxonomyResolution.resolved_competition.isnot(None),
        )
        .group_by(ArticleTaxonomyResolution.resolved_competition)
        .all()
    )
    sports = []
    for row in sport_catalog():
        slug = row["sport"]
        competitions = []
        for key, meta in COMPETITIONS.items():
            if meta.get("sport") != slug:
                continue
            competitions.append(
                {
                    "competition": key,
                    "label": meta.get("label") or competition_label(key),
                    "country": meta.get("country"),
                    "article_count": int(competition_counts.get(key) or 0),
                }
            )
        sports.append(
            {
                **row,
                "article_count": int(counts.get(slug) or 0),
                "competitions": competitions,
            }
        )
    return {
        "sports": sports,
        "league_aliases": LEAGUE_PATH_ALIASES,
        "categories": [
            {"id": key, "label": CATEGORY_LABELS[key]} for key in SPORT_CATEGORIES
        ],
        "registry": registry_payload(),
    }


@app.get("/meta/navigation")
def navigation(db: Session = Depends(get_db)):
    counts = dict(
        db.query(
            ArticleTaxonomyResolution.resolved_competition,
            func.count(ArticleTaxonomyResolution.id),
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
        )
        .group_by(ArticleTaxonomyResolution.resolved_competition)
        .all()
    )
    sport_counts = dict(
        db.query(
            ArticleTaxonomyResolution.resolved_sport,
            func.count(ArticleTaxonomyResolution.id),
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
        )
        .group_by(ArticleTaxonomyResolution.resolved_sport)
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
                "article_count": int(sport_counts.get(sport) or 0),
                "leagues": leagues,
            }
        )
    return {"sports": sports, "league_aliases": LEAGUE_PATH_ALIASES}


@app.get("/registry/sports")
def registry_sports(sport: Optional[str] = Query(None)):
    return registry_payload(sport)


@app.get("/registry/geography")
def registry_geography():
    return geography_payload()


@app.get("/registry/competitions")
def registry_competitions(sport: Optional[str] = Query(None)):
    return competitions_payload(sport)


@app.get("/registry/providers")
def registry_providers():
    return providers_payload()


@app.get("/sports-data/status")
def sports_data_status():
    return get_active_provider().status()


@app.get("/sports-data/scores")
def sports_data_scores():
    provider = get_active_provider()
    payload = empty_scores_payload()
    payload.update(provider.status())
    events = provider.get_events()
    live = provider.get_live_events()
    payload["events"] = events
    payload["matches"] = events_to_legacy_matches(events)
    buckets = partition_score_events(events)
    payload["live"] = events_to_legacy_matches(live) or buckets["live"]
    payload["today"] = buckets["today"]
    payload["tomorrow"] = buckets["tomorrow"]
    payload["finished"] = buckets["finished"]
    return payload


@app.get("/sports-data/standings")
def sports_data_standings(league: Optional[str] = Query(None)):
    provider = get_active_provider()
    payload = empty_standings_payload(_resolve_league_key(league))
    payload.update(provider.status())
    payload["rows"] = provider.get_standings(_resolve_league_key(league))
    return payload


@app.get("/sports-data/competitions")
def sports_data_competitions(sport: Optional[str] = Query(None)):
    provider = get_active_provider()
    payload = empty_competitions_payload(sport)
    payload.update(provider.status())
    payload["competitions"] = provider.get_competitions(sport)
    return payload


@app.get("/sports-data/events")
def sports_data_events(
    sport: Optional[str] = Query(None),
    competition: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    provider = get_active_provider()
    payload = empty_events_payload(sport, competition, status)
    payload.update(provider.status())
    events = provider.get_events(
        sport=sport,
        competition=competition,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    payload["events"] = events
    payload["matches"] = events_to_legacy_matches(events)
    return payload


@app.get("/sports-data/matches/{match_id}")
def sports_data_match(match_id: str):
    provider = get_active_provider()
    payload = empty_match_payload(match_id)
    payload.update(provider.status())
    event = provider.get_event(match_id)
    if event:
        payload["event"] = event
        payload["header"] = event
        payload["statistics"] = provider.get_statistics(match_id)
        payload["availability"] = provider.get_availability(match_id) or []
    return payload


@app.get("/sports-data/teams/{slug}")
def sports_data_team(slug: str):
    return empty_team_payload(slug)


@app.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    rows = (
        db.query(Article.slug, Article.published_at, Article.created_at)
        .join(
            ArticleTaxonomyResolution,
            ArticleTaxonomyResolution.article_id == Article.id,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
        )
        .order_by(_sort_expr().desc())
        .limit(5000)
        .all()
    )
    league_rows = (
        db.query(
            ArticleTaxonomyResolution.resolved_sport,
            ArticleTaxonomyResolution.resolved_competition,
        )
        .filter(
            ArticleTaxonomyResolution.resolver_version == RESOLVER_VERSION,
            ArticleTaxonomyResolution.public_ok == True,
            ArticleTaxonomyResolution.resolved_competition.isnot(None),
            ArticleTaxonomyResolution.resolved_competition != "",
        )
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
        url_xml("/predictions", "hourly"),
        url_xml("/search", "weekly"),
        url_xml("/my-sports", "weekly"),
    ]
    seen_paths = {
        "/",
        "/football",
        "/basketball",
        "/tennis",
        "/motorsport",
        "/other-sports",
        "/live-scores",
        "/predictions",
        "/search",
        "/my-sports",
    }
    for path in sitemap_sport_paths():
        if path in seen_paths:
            continue
        seen_paths.add(path)
        urls.append(url_xml(path, "daily"))
    for sport, league_key in league_rows:
        if not league_key:
            continue
        sport_slug = sport if sport in SPORT_PATHS else None
        if sport_slug:
            urls.append(url_xml(f"/{sport_slug}/{escape(league_key)}", "hourly"))
        else:
            urls.append(url_xml(f"/{escape(sport or 'other-sports')}", "daily"))
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
