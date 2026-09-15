import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Railway (and Heroku-style hosts) often provide postgres:// which SQLAlchemy rejects.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_schema(bind=None):
    """Backward-compatible additive schema only. Never drops or rewrites rows."""
    bind = bind or engine
    insp = inspect(bind)
    if "articles" not in insp.get_table_names():
        return
    columns = {col["name"] for col in insp.get_columns("articles")}
    dialect = bind.dialect.name
    additions = []
    if "published_at" not in columns:
        additions.append("ALTER TABLE articles ADD COLUMN published_at TIMESTAMP")
    if "is_breaking" not in columns:
        if dialect == "postgresql":
            additions.append(
                "ALTER TABLE articles ADD COLUMN is_breaking BOOLEAN DEFAULT FALSE"
            )
        else:
            additions.append(
                "ALTER TABLE articles ADD COLUMN is_breaking BOOLEAN DEFAULT 0"
            )
    if "view_count" not in columns:
        if dialect == "postgresql":
            additions.append(
                "ALTER TABLE articles ADD COLUMN view_count INTEGER DEFAULT 0"
            )
        else:
            additions.append(
                "ALTER TABLE articles ADD COLUMN view_count INTEGER DEFAULT 0"
            )
    if additions:
        with bind.begin() as conn:
            for stmt in additions:
                conn.execute(text(stmt))

    index_stmts = [
        "CREATE INDEX IF NOT EXISTS ix_articles_sport_published ON articles (sport, published_at)",
        "CREATE INDEX IF NOT EXISTS ix_articles_league_published ON articles (league, published_at)",
        "CREATE INDEX IF NOT EXISTS ix_articles_published_at ON articles (published_at)",
        "CREATE INDEX IF NOT EXISTS ix_articles_breaking_published ON articles (is_breaking, published_at)",
        "CREATE INDEX IF NOT EXISTS ix_articles_view_count ON articles (view_count)",
        "CREATE INDEX IF NOT EXISTS ix_articles_stamp ON articles (COALESCE(published_at, created_at))",
    ]
    with bind.begin() as conn:
        for stmt in index_stmts:
            conn.execute(text(stmt))
        tables = set(insp.get_table_names())
        if "article_taxonomy_resolutions" in tables:
            tax_cols = {col["name"] for col in insp.get_columns("article_taxonomy_resolutions")}
            tax_adds = []
            if "quality_ok" not in tax_cols:
                tax_adds.append(
                    "ALTER TABLE article_taxonomy_resolutions ADD COLUMN quality_ok BOOLEAN DEFAULT 0"
                    if dialect != "postgresql"
                    else "ALTER TABLE article_taxonomy_resolutions ADD COLUMN quality_ok BOOLEAN DEFAULT FALSE"
                )
            if "public_ok" not in tax_cols:
                tax_adds.append(
                    "ALTER TABLE article_taxonomy_resolutions ADD COLUMN public_ok BOOLEAN DEFAULT 0"
                    if dialect != "postgresql"
                    else "ALTER TABLE article_taxonomy_resolutions ADD COLUMN public_ok BOOLEAN DEFAULT FALSE"
                )
            if "hero_media_kind" not in tax_cols:
                tax_adds.append(
                    "ALTER TABLE article_taxonomy_resolutions ADD COLUMN hero_media_kind VARCHAR(40)"
                )
            if "word_count" not in tax_cols:
                tax_adds.append(
                    "ALTER TABLE article_taxonomy_resolutions ADD COLUMN word_count INTEGER DEFAULT 0"
                )
            for stmt in tax_adds:
                conn.execute(text(stmt))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_taxonomy_resolved_comp_lookup "
                    "ON article_taxonomy_resolutions (resolver_version, resolved_competition)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_taxonomy_public_sport "
                    "ON article_taxonomy_resolutions (resolver_version, public_ok, resolved_sport)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_taxonomy_public_comp "
                    "ON article_taxonomy_resolutions (resolver_version, public_ok, resolved_competition)"
                )
            )
