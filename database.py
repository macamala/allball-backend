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
