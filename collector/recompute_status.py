"""Recompute canonical LIVE from stored observation fields, not old keeper status."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from collector.cache import cache_clear
from collector.live_state import (
    UNPROVEN_LIVE,
    has_progress_evidence,
    reconcile_live_status,
)
from collector.models import SportsEvent, SportsEventDetail
from collector.util import dump_json, isoformat, load_json


def _payload_from_row(row: SportsEvent, detail: SportsEventDetail | None) -> Dict[str, Any]:
    extra = load_json(row.extra_json, {}) or {}
    score = load_json(row.score_json, {}) or {}
    payload = {
        "id": row.event_id,
        "sport": row.sport_id,
        "competition": row.competition_id,
        "competition_key": row.competition_id,
        "status": row.status,
        "live": bool(row.live),
        "score": score,
        "start_time": isoformat(row.start_time),
        "source_family": extra.get("source_family"),
        "source_status": extra.get("source_status"),
        "status_inferred": extra.get("status_inferred"),
        "source_fetch_time": extra.get("source_fetch_time") or isoformat(row.retrieved_at),
        "source_event_updated_at": extra.get("source_event_updated_at"),
        "observed_at": extra.get("observed_at"),
        "canonical_last_observed_at": extra.get("canonical_last_observed_at"),
        "incidents": extra.get("incidents") or (load_json(detail.incidents_json) if detail else None),
        "periods": extra.get("periods"),
        "maps": extra.get("maps"),
        "current_set": extra.get("current_set"),
        "innings": extra.get("innings"),
    }
    return payload


def _maybe_restore_null_scores(payload: Dict[str, Any], previous_status: str) -> Dict[str, Any]:
    score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
    if score.get("home") != 0 or score.get("away") != 0:
        return payload
    if has_progress_evidence(payload):
        return payload
    if payload.get("status") == "live":
        return payload
    if previous_status not in {"live", "halftime", "break", "stale"}:
        return payload
    out = dict(payload)
    restored = dict(score)
    restored["home"] = None
    restored["away"] = None
    out["score"] = restored
    return out


def recompute_display_eligible_live(db: Session) -> Dict[str, Any]:
    """Rewrite persisted LIVE using Phase-0 evidence rules. Does not fabricate FT."""
    rows: List[SportsEvent] = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(SportsEvent.status.in_(("live", "halftime", "break", "stale")))
        .all()
    )
    summary = {
        "scanned": 0,
        "confirmed_live": 0,
        "unproven_to_scheduled": 0,
        "stale": 0,
        "unknown": 0,
        "scores_restored_null": 0,
        "unchanged": 0,
        "ids": [],
    }
    for row in rows:
        if row.display_eligible is False:
            continue
        summary["scanned"] += 1
        detail = db.query(SportsEventDetail).filter_by(event_id=row.event_id).first()
        previous_status = row.status
        previous_score = load_json(row.score_json, {}) or {}
        extra = load_json(row.extra_json, {}) or {}
        payload = _payload_from_row(row, detail)
        if previous_status == "stale":
            payload["status"] = extra.get("source_status") or "live"
        payload = reconcile_live_status(payload)
        payload = _maybe_restore_null_scores(payload, previous_status)
        extra["live_class"] = payload.get("live_class")
        extra["status_reconciliation"] = payload.get("status_reconciliation") or extra.get("status_reconciliation")
        extra["source_status"] = extra.get("source_status") or previous_status
        row.status = payload.get("status") or row.status
        row.live = bool(payload.get("live"))
        if payload.get("score") != previous_score:
            row.score_json = dump_json(payload.get("score") or {})
            if (payload.get("score") or {}).get("home") is None and previous_score.get("home") == 0:
                summary["scores_restored_null"] += 1
        row.extra_json = dump_json(extra)
        live_class = payload.get("live_class")
        if row.status == "live" or row.status == "break":
            summary["confirmed_live"] += 1
        elif live_class == UNPROVEN_LIVE or row.status == "scheduled":
            summary["unproven_to_scheduled"] += 1
            summary["ids"].append(row.event_id)
        elif row.status == "stale":
            summary["stale"] += 1
        elif row.status == "unknown":
            summary["unknown"] += 1
        else:
            summary["unchanged"] += 1
    cache_clear(db, prefix="events:")
    db.commit()
    return summary


def main() -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        print(recompute_display_eligible_live(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
