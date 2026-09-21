"""Additive indexes for dated public event lists. create_all does not alter existing tables."""

from __future__ import annotations

from sqlalchemy import text


def ensure_event_list_indexes(engine) -> None:
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_sports_event_start_canonical ON sports_events (start_time, canonical_event_id)",
        "CREATE INDEX IF NOT EXISTS ix_sports_event_comp_status_start ON sports_events (competition_id, status, start_time)",
        "CREATE INDEX IF NOT EXISTS ix_sports_event_sport_start ON sports_events (sport_id, start_time)",
        "CREATE INDEX IF NOT EXISTS ix_sports_event_public_window ON sports_events (start_time) WHERE canonical_event_id IS NULL",
    )
    with engine.begin() as conn:
        for sql in statements:
            try:
                conn.execute(text(sql))
            except Exception:
                continue
