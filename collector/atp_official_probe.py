"""Read-only probe for ATP Tour's public scores payload."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from collector.http import fetch_url
from collector.lock import lock_status
from collector.models import SportsCollectorJob
from collector.util import dump_json, load_json

JOB_KEY = "atp-official-probe-v1"
URLS = (
    "https://www.atptour.com/-/ajax/Scores/GetInitialScores",
    "https://www.atptour.com/en/-/ajax/Scores/GetInitialScores",
)


def _job(db: Session) -> SportsCollectorJob:
    row = db.get(SportsCollectorJob, JOB_KEY)
    if row is None:
        row = SportsCollectorJob(job_key=JOB_KEY, last_status="pending")
        db.add(row)
        db.flush()
    return row


def summarize_payload(payload: Any) -> Dict[str, Any]:
    root = payload if isinstance(payload, dict) else {}
    live = root.get("liveScores") if isinstance(root.get("liveScores"), dict) else {}
    tournaments = live.get("Tournaments") if isinstance(live.get("Tournaments"), list) else []
    match_count = 0
    samples: List[Dict[str, Any]] = []
    for tournament in tournaments:
        if not isinstance(tournament, dict):
            continue
        matches = tournament.get("Matches") if isinstance(tournament.get("Matches"), list) else []
        match_count += len(matches)
        if len(samples) < 4:
            sample_match = next((m for m in matches if isinstance(m, dict)), {})
            samples.append(
                {
                    "event_id": tournament.get("EventId"),
                    "event_year": tournament.get("EventYear"),
                    "name": tournament.get("Name") or tournament.get("SponsorTitle"),
                    "location": tournament.get("Location"),
                    "date": tournament.get("FormattedDate"),
                    "matches": len(matches),
                    "schedule_link": tournament.get("ScheduleLink"),
                    "sample_match_keys": sorted(sample_match.keys())[:80] if sample_match else [],
                    "sample_match": {
                        key: sample_match.get(key)
                        for key in (
                            "Id",
                            "RoundTitle",
                            "MatchType",
                            "Status",
                            "Winner",
                            "MatchTime",
                            "MatchInfo",
                            "StartTime",
                            "Court",
                        )
                        if sample_match.get(key) not in (None, "")
                    },
                }
            )
    return {
        "top_keys": sorted(root.keys()),
        "live_score_keys": sorted(live.keys()),
        "tournaments": len(tournaments),
        "matches": match_count,
        "samples": samples,
    }


def run_probe() -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    for url in URLS:
        result = fetch_url(url)
        summary = summarize_payload(result.payload) if getattr(result, "ok", False) else {}
        attempt = {
            "url": url,
            "http": int(getattr(result, "http_status", 0) or 0),
            "ok": bool(getattr(result, "ok", False)),
            "error": str(getattr(result, "error", "") or "")[:240],
            **summary,
        }
        attempts.append(attempt)
        if attempt.get("tournaments") or attempt.get("matches"):
            break
    best = max(attempts, key=lambda row: (int(row.get("matches") or 0), int(row.get("tournaments") or 0), int(row.get("ok") or 0)))
    return {
        "status": "ok" if best.get("ok") else "unavailable",
        "http": best.get("http"),
        "tournaments": best.get("tournaments", 0),
        "matches": best.get("matches", 0),
        "attempts": attempts,
    }


def run_if_due(
    db: Session,
    *,
    min_interval_minutes: int = 180,
    owner: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        return None
    if owner and status.get("owner_id") != owner:
        return None
    job = _job(db)
    payload = load_json(job.last_error, {}) or {}
    if (
        payload.get("state") == "done"
        and job.last_run_at
        and datetime.utcnow() - job.last_run_at < timedelta(minutes=min_interval_minutes)
    ):
        return None
    stats = run_probe()
    job.last_run_at = datetime.utcnow()
    job.last_status = stats["status"]
    job.items_written = 0
    job.last_error = dump_json({"state": "done", "stats": stats})[:4000]
    db.commit()
    return stats
