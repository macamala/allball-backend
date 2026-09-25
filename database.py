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

# Use the driver declared in requirements.txt, independent of SQLAlchemy defaults.
# SQLAlchemy 2.1 changed a bare postgresql:// URL to require psycopg v3.
# Explicit driver URLs are intentionally preserved; no credentials are altered.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len("postgresql://") :]

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
else:
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "5")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_schema(bind=None):
    """Backward-compatible additive schema only. Never drops or rewrites rows.

    Collector tables are created by Base.metadata.create_all when
    collector.models is imported. This function only patches older article
    columns/indexes.
    """
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
    _ensure_collector_columns(bind)


def _ensure_collector_columns(bind):
    """Additive collector columns for existing Postgres databases."""
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    dialect = bind.dialect.name
    bool_default = "BOOLEAN DEFAULT FALSE" if dialect == "postgresql" else "BOOLEAN DEFAULT 0"
    patches = {
        "sports_sources": [
            ("upstream_family", "VARCHAR(80)"),
            ("source_type", "VARCHAR(80)"),
            ("credential_env", "VARCHAR(120)"),
            ("independence_status", "VARCHAR(40)"),
            ("derived_from", "VARCHAR(80)"),
            ("source_id_original", "TEXT"),
        ],
        "sports_source_competitions": [
            ("coverage_scope", "VARCHAR(20)"),
            ("coverage_notes", "TEXT"),
            ("verification", "TEXT"),
            ("polling_class", "VARCHAR(20)"),
            ("source_config_json", "TEXT"),
            ("independence_status", "VARCHAR(40)"),
            ("derived_from", "VARCHAR(80)"),
            ("upstream_family", "VARCHAR(80)"),
        ],
        "sports_events": [
            ("retrieved_at", "TIMESTAMP"),
            ("timezone_name", "VARCHAR(80)"),
            ("stage", "VARCHAR(120)"),
            ("gender", "VARCHAR(20)"),
            ("source_url", "VARCHAR(500)"),
            ("display_eligible", "BOOLEAN DEFAULT TRUE"),
            ("canonical_event_id", "VARCHAR(160)"),
            ("list_extra_json", "TEXT"),
        ],
        "sports_id_map": [
            ("source_entity_id_original", "TEXT"),
        ],
        "sports_event_observations": [
            ("source_event_key", "VARCHAR(80)"),
        ],
        "sports_ingestion_runs": [
            ("jobs", "INTEGER"),
            ("raw_count", "INTEGER"),
            ("normalized", "INTEGER"),
            ("inserted", "INTEGER"),
            ("updated", "INTEGER"),
            ("rejected", "INTEGER"),
            ("provider_failures", "INTEGER"),
            ("db_failures", "INTEGER"),
        ],
        "sports_source_health": [
            ("last_attempt_at", "TIMESTAMP"),
            ("last_latency_ms", "INTEGER"),
            ("last_parse_status", "VARCHAR(40)"),
            ("last_events_returned", "INTEGER"),
            ("last_error_type", "VARCHAR(40)"),
            ("last_success_event_at", "TIMESTAMP"),
        ],
    }
    with bind.begin() as conn:
        try:
            conn.execute(text("SET LOCAL lock_timeout = '3s'"))
            conn.execute(text("SET LOCAL statement_timeout = '8s'"))
        except Exception:
            pass
        for table, columns in patches.items():
            if table not in tables:
                continue
            existing = {col["name"] for col in insp.get_columns(table)}
            for name, coltype in columns:
                if name in existing:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}"))
        if dialect == "postgresql" and "sports_event_observations" in tables:
            obs_cols = {col["name"]: col for col in insp.get_columns("sports_event_observations")}
            source_type = str((obs_cols.get("source_event_id") or {}).get("type") or "").lower()
            if source_type and "text" not in source_type:
                conn.execute(text("ALTER TABLE sports_event_observations ALTER COLUMN source_event_id TYPE TEXT"))
        _ = bool_default
        _ensure_collector_indexes(conn, tables)


def _ensure_collector_indexes(conn, tables):
    """Additive unique indexes only. Never drops rows; skip if duplicates exist."""
    statements = []
    if "sports_events" in tables:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_event_fingerprint ON sports_events (fingerprint)"
        )
    if "sports_entities" in tables:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_entity_identity ON sports_entities (sport_id, kind, slug)"
        )
    if "sports_competitions" in tables:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_comp_sport_slug ON sports_competitions (sport_id, slug)"
        )
    if "sports_id_map" in tables:
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_source_entity ON sports_id_map (entity_kind, source_id, source_entity_id)"
        )
    if "sports_events" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_sports_event_sport_start ON sports_events (sport_id, start_time)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_sports_event_public_start ON sports_events (sport_id, start_time, display_eligible)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_sports_event_canonical ON sports_events (canonical_event_id)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_sports_event_status_start ON sports_events (status, start_time)"
        )
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_sports_event_primary_source ON sports_events (primary_source_id)"
        )
    if "sports_event_observations" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_event_obs_source_key ON sports_event_observations (source_id, source_event_key)"
        )
    if "sports_ingestion_runs" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_ingest_runs_status ON sports_ingestion_runs (status, started_at)"
        )
    if "sports_source_health" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_source_health_status ON sports_source_health (status)"
        )
    if "sports_scheduler_lease" in tables:
        statements.append(
            "CREATE INDEX IF NOT EXISTS ix_scheduler_lease_expires ON sports_scheduler_lease (expires_at)"
        )
    try:
        conn.execute(text("SET LOCAL lock_timeout = '3s'"))
        conn.execute(text("SET LOCAL statement_timeout = '8s'"))
    except Exception:
        pass
    for stmt in statements:
        try:
            conn.execute(text(stmt))
        except Exception:
            # Existing duplicates: keep data, skip the unique index.
            pass
