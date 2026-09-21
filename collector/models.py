"""Canonical sports-data tables. Created additively via SQLAlchemy create_all.

These tables store identity, source mappings, raw ingest, and merged events.
They are empty until a collector cycle writes rows. No fixtures are seeded.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from models import Base


class SportsSource(Base):
    """Registered collection source. Licensed sources stay disabled without credentials."""

    __tablename__ = "sports_sources"

    source_id = Column(String(80), primary_key=True)
    source_id_original = Column(Text, nullable=True)
    display_name = Column(String(200), nullable=False)
    kind = Column(String(40), nullable=False)
    enabled = Column(Boolean, default=False)
    requires_credentials = Column(Boolean, default=False)
    licensed = Column(Boolean, default=False)
    sports_supported_json = Column(Text, nullable=True)
    capabilities_json = Column(Text, nullable=True)
    adapter_key = Column(String(120), nullable=False)
    attribution_required = Column(Boolean, default=False)
    attribution_text = Column(Text, nullable=True)
    attribution_url = Column(String(500), nullable=True)
    license_name = Column(String(120), nullable=True)
    public_branding_required = Column(Boolean, default=False)
    rate_limit_per_minute = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    upstream_family = Column(String(80), nullable=True)
    source_type = Column(String(80), nullable=True)
    credential_env = Column(String(120), nullable=True)
    independence_status = Column(String(40), nullable=True)
    derived_from = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SportsCompetition(Base):
    """Canonical competition identity. Mapping a source is separate from coverage."""

    __tablename__ = "sports_competitions"
    __table_args__ = (
        UniqueConstraint("sport_id", "slug", name="uq_sports_comp_sport_slug"),
        Index("ix_sports_comp_sport", "sport_id"),
        Index("ix_sports_comp_series", "series_id"),
        Index("ix_sports_comp_game", "game_id"),
        Index("ix_sports_comp_country", "country_id"),
    )

    competition_id = Column(String(120), primary_key=True)
    sport_id = Column(String(50), nullable=False)
    name = Column(String(200), nullable=False)
    official_name = Column(String(200), nullable=True)
    slug = Column(String(160), nullable=False)
    country_id = Column(String(40), nullable=True)
    region_id = Column(String(40), nullable=True)
    series_id = Column(String(80), nullable=True)
    game_id = Column(String(80), nullable=True)
    parent_sport_id = Column(String(50), nullable=True)
    country_based = Column(Boolean, default=False)
    event_model = Column(String(40), nullable=False)
    competition_type = Column(String(40), nullable=True)
    gender = Column(String(20), nullable=True)
    level = Column(String(40), nullable=True)
    active = Column(Boolean, default=True)
    news_taxonomy = Column(Boolean, default=False)
    identity_only = Column(Boolean, default=True)


class SportsSourceCompetition(Base):
    """sport → competition → ordered sources. Lower priority value is tried first."""

    __tablename__ = "sports_source_competitions"
    __table_args__ = (
        UniqueConstraint("competition_id", "source_id", name="uq_source_competition"),
        Index("ix_source_comp_priority", "competition_id", "priority"),
    )

    id = Column(Integer, primary_key=True)
    competition_id = Column(String(120), nullable=False)
    source_id = Column(String(80), nullable=False)
    priority = Column(Integer, nullable=False, default=100)
    source_competition_id = Column(String(160), nullable=True)
    enabled = Column(Boolean, default=True)
    is_licensed_fallback = Column(Boolean, default=False)
    capabilities_json = Column(Text, nullable=True)
    coverage_scope = Column(String(20), default="full")
    coverage_notes = Column(Text, nullable=True)
    verification = Column(Text, nullable=True)
    polling_class = Column(String(20), default="NORMAL")
    source_config_json = Column(Text, nullable=True)
    independence_status = Column(String(40), nullable=True)
    derived_from = Column(String(80), nullable=True)
    upstream_family = Column(String(80), nullable=True)


class SportsEntity(Base):
    __tablename__ = "sports_entities"
    __table_args__ = (
        UniqueConstraint("sport_id", "kind", "slug", name="uq_sports_entity_identity"),
        Index("ix_sports_entity_slug", "sport_id", "slug"),
        Index("ix_sports_entity_kind", "kind"),
    )

    entity_id = Column(String(160), primary_key=True)
    sport_id = Column(String(50), nullable=False)
    kind = Column(String(40), nullable=False)
    name = Column(String(200), nullable=False)
    slug = Column(String(160), nullable=False)
    country_id = Column(String(40), nullable=True)
    extra_json = Column(Text, nullable=True)


class SportsParticipantAlias(Base):
    """Persisted participant name crosswalk. Never merge on similarity alone."""

    __tablename__ = "sports_participant_aliases"
    __table_args__ = (
        UniqueConstraint("sport_id", "alias_folded", name="uq_participant_alias_fold"),
        Index("ix_participant_alias_canonical", "sport_id", "canonical_folded"),
    )

    id = Column(Integer, primary_key=True)
    sport_id = Column(String(50), nullable=False)
    canonical_folded = Column(String(200), nullable=False)
    alias_folded = Column(String(200), nullable=False)
    canonical_display_name = Column(String(200), nullable=False)
    source_family = Column(String(80), nullable=True)
    source_participant_id = Column(String(160), nullable=True)
    evidence_json = Column(Text, nullable=True)
    confidence = Column(Integer, default=90)
    created_at = Column(DateTime, default=datetime.utcnow)


class SportsEvent(Base):
    __tablename__ = "sports_events"
    __table_args__ = (
        Index("ix_sports_event_sport_status", "sport_id", "status"),
        Index("ix_sports_event_comp_start", "competition_id", "start_time"),
        Index("ix_sports_event_fingerprint", "fingerprint"),
        Index("uq_sports_event_fingerprint", "fingerprint", unique=True),
        Index("ix_sports_event_sport_start", "sport_id", "start_time"),
        Index("ix_sports_event_live", "live"),
        Index("ix_sports_event_public_start", "sport_id", "start_time", "display_eligible"),
        Index("ix_sports_event_canonical", "canonical_event_id"),
        Index("ix_sports_event_status_start", "status", "start_time"),
        Index("ix_sports_event_updated", "updated_at"),
        Index("ix_sports_event_start_canonical", "start_time", "canonical_event_id"),
        Index("ix_sports_event_comp_status_start", "competition_id", "status", "start_time"),
    )

    event_id = Column(String(160), primary_key=True)
    sport_id = Column(String(50), nullable=False)
    competition_id = Column(String(120), nullable=False)
    event_family = Column(String(40), nullable=False)
    status = Column(String(40), nullable=False, default="scheduled")
    start_time = Column(DateTime, nullable=True)
    season = Column(String(40), nullable=True)
    venue = Column(String(200), nullable=True)
    home_entity_id = Column(String(160), nullable=True)
    away_entity_id = Column(String(160), nullable=True)
    score_json = Column(Text, nullable=True)
    participants_json = Column(Text, nullable=True)
    series_id = Column(String(80), nullable=True)
    session_type = Column(String(40), nullable=True)
    game_id = Column(String(80), nullable=True)
    country_id = Column(String(40), nullable=True)
    meeting_id = Column(String(120), nullable=True)
    extra_json = Column(Text, nullable=True)
    list_extra_json = Column(Text, nullable=True)
    fingerprint = Column(String(80), nullable=True)
    primary_source_id = Column(String(80), nullable=True)
    contributing_sources_json = Column(Text, nullable=True)
    display_eligible = Column(Boolean, default=True)
    canonical_event_id = Column(String(160), nullable=True)
    live = Column(Boolean, default=False)
    retrieved_at = Column(DateTime, nullable=True)
    timezone_name = Column(String(80), nullable=True)
    stage = Column(String(120), nullable=True)
    gender = Column(String(20), nullable=True)
    source_url = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class SportsEventDetail(Base):
    __tablename__ = "sports_event_details"

    event_id = Column(String(160), primary_key=True)
    lineups_json = Column(Text, nullable=True)
    statistics_json = Column(Text, nullable=True)
    incidents_json = Column(Text, nullable=True)
    availability_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SportsStandingSnapshot(Base):
    __tablename__ = "sports_standings"
    __table_args__ = (
        Index("ix_sports_standings_comp", "competition_id", "captured_at"),
    )

    id = Column(Integer, primary_key=True)
    competition_id = Column(String(120), nullable=False)
    sport_id = Column(String(50), nullable=True)
    season = Column(String(40), nullable=True)
    source_id = Column(String(80), nullable=True)
    rows_json = Column(Text, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow)


class SportsRankingSnapshot(Base):
    __tablename__ = "sports_rankings"
    __table_args__ = (Index("ix_sports_rankings_sport", "sport_id", "captured_at"),)

    id = Column(Integer, primary_key=True)
    sport_id = Column(String(50), nullable=False)
    competition_id = Column(String(120), nullable=True)
    source_id = Column(String(80), nullable=True)
    rows_json = Column(Text, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow)


class SportsIdMap(Base):
    __tablename__ = "sports_id_map"
    __table_args__ = (
        UniqueConstraint(
            "entity_kind", "source_id", "source_entity_id", name="uq_source_entity"
        ),
        Index("ix_sports_id_ninko", "entity_kind", "ninko_id"),
    )

    id = Column(Integer, primary_key=True)
    entity_kind = Column(String(40), nullable=False)
    ninko_id = Column(String(160), nullable=False)
    source_id = Column(String(80), nullable=False)
    source_entity_id = Column(String(200), nullable=False)
    source_entity_id_original = Column(Text, nullable=True)


class SportsRawIngest(Base):
    __tablename__ = "sports_raw_ingest"
    __table_args__ = (
        Index("ix_raw_ingest_source", "source_id", "fetched_at"),
        Index("ix_raw_ingest_hash", "payload_hash"),
    )

    id = Column(Integer, primary_key=True)
    source_id = Column(String(80), nullable=False)
    entity_kind = Column(String(40), nullable=False)
    source_entity_id = Column(String(200), nullable=True)
    competition_id = Column(String(120), nullable=True)
    capability = Column(String(40), nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    http_status = Column(Integer, nullable=True)
    payload_hash = Column(String(64), nullable=True)
    payload = Column(Text, nullable=True)
    restricted = Column(Boolean, default=False)
    error = Column(Text, nullable=True)


class SportsSourceHealth(Base):
    __tablename__ = "sports_source_health"

    source_id = Column(String(80), primary_key=True)
    status = Column(String(20), default="unknown")
    last_success_at = Column(DateTime, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, default=0)
    rate_limited_until = Column(DateTime, nullable=True)
    last_http_status = Column(Integer, nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    last_latency_ms = Column(Integer, nullable=True)
    last_parse_status = Column(String(40), nullable=True)
    last_events_returned = Column(Integer, nullable=True)
    last_error_type = Column(String(40), nullable=True)
    last_success_event_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SportsEventObservation(Base):
    __tablename__ = "sports_event_observations"
    __table_args__ = (
        Index("ix_event_obs_event", "event_id", "retrieved_at"),
        Index("ix_event_obs_source", "source_id", "retrieved_at"),
        Index("ix_event_obs_source_key", "source_id", "source_event_key"),
    )

    id = Column(Integer, primary_key=True)
    event_id = Column(String(160), nullable=False)
    source_id = Column(String(80), nullable=False)
    source_family = Column(String(80), nullable=True)
    source_event_id = Column(Text, nullable=True)
    source_event_key = Column(String(80), nullable=True)
    source_url = Column(String(500), nullable=True)
    payload_json = Column(Text, nullable=True)
    retrieved_at = Column(DateTime, default=datetime.utcnow)


class SportsCompetitionHealth(Base):
    __tablename__ = "sports_competition_health"

    competition_id = Column(String(120), primary_key=True)
    primary_status = Column(String(40), default="unknown")
    fallback_status = Column(String(40), default="unknown")
    active_source_id = Column(String(80), nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    events_ingested = Column(Integer, default=0)
    duplicates_merged = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_classification = Column(String(40), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SportsIngestionRun(Base):
    __tablename__ = "sports_ingestion_runs"
    __table_args__ = (Index("ix_ingest_runs_status", "status", "started_at"),)

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    scope = Column(String(40), nullable=True)
    status = Column(String(20), default="running")
    competitions_attempted = Column(Integer, default=0)
    events_written = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    jobs = Column(Integer, default=0)
    raw_count = Column(Integer, default=0)
    normalized = Column(Integer, default=0)
    inserted = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    rejected = Column(Integer, default=0)
    provider_failures = Column(Integer, default=0)
    db_failures = Column(Integer, default=0)
    summary_json = Column(Text, nullable=True)


class SportsIngestionError(Base):
    __tablename__ = "sports_ingestion_errors"
    __table_args__ = (Index("ix_ingest_err_comp", "competition_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, nullable=True)
    competition_id = Column(String(120), nullable=True)
    source_id = Column(String(80), nullable=True)
    error_type = Column(String(40), nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SportsCollectorJob(Base):
    __tablename__ = "sports_collector_jobs"

    job_key = Column(String(80), primary_key=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(20), nullable=True)
    last_error = Column(Text, nullable=True)
    items_written = Column(Integer, default=0)


class SportsReadCache(Base):
    __tablename__ = "sports_read_cache"

    cache_key = Column(String(200), primary_key=True)
    payload = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class SportsSchedulerLease(Base):
    __tablename__ = "sports_scheduler_lease"

    lock_name = Column(String(80), primary_key=True)
    owner_id = Column(String(200), nullable=True)
    acquired_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class SportsSchedulerSlot(Base):
    """Compact due-slot per competition/family. Upserted; not an unbounded job log."""

    __tablename__ = "sports_scheduler_slots"
    __table_args__ = (
        Index("ix_sched_slot_due", "next_due_at"),
        Index("ix_sched_slot_comp", "competition_id", "family"),
    )

    job_key = Column(String(200), primary_key=True)
    kind = Column(String(20), nullable=True)
    competition_id = Column(String(120), nullable=True)
    family = Column(String(80), nullable=True)
    urgency = Column(String(40), nullable=True)
    reason = Column(String(200), nullable=True)
    priority = Column(Integer, default=50)
    next_due_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(40), nullable=True)
    http_calls = Column(Integer, default=0)
    events_changed = Column(Integer, default=0)


class SportsLiveWatch(Base):
    """Polling watch set. Membership is not canonical LIVE."""

    __tablename__ = "sports_live_watch"
    __table_args__ = (
        Index("ix_live_watch_comp", "competition_id"),
        Index("ix_live_watch_sport", "sport_id"),
        Index("ix_live_watch_expires", "expires_at"),
    )

    event_id = Column(String(160), primary_key=True)
    competition_id = Column(String(120), nullable=True)
    sport_id = Column(String(50), nullable=True)
    reason = Column(String(40), nullable=False)
    entered_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_polled_at = Column(DateTime, nullable=True)

