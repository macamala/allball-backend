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
    if "published_at" not in columns:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE articles ADD COLUMN published_at TIMESTAMP"))
