"""Canonical event status. LIVE requires source evidence, never elapsed time."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

CANONICAL_STATUSES = (
    "scheduled",
    "live",
    "break",
    "finished",
    "postponed",
    "delayed",
    "suspended",
    "abandoned",
    "cancelled",
    "walkover",
    "unknown",
)

STATUS_RANK = {
    "scheduled": 10,
    "pre_match": 12,
    "delayed": 14,
    "postponed": 15,
    "unknown": 16,
    "status_unknown": 16,
    "stale": 16,
    "suspended": 18,
    "live": 30,
    "halftime": 32,
    "break": 32,
    "finished": 50,
    "cancelled": 50,
    "abandoned": 50,
    "walkover": 50,
}

LIVE_STATUSES = {"live", "inplay", "1h", "2h", "in_play", "playing"}
HALFTIME_STATUSES = {"ht", "halftime", "half-time", "half_time", "break"}
FINISHED_STATUSES = {
    "finished",
    "ft",
    "final",
    "ended",
    "complete",
    "completed",
    "fulltime",
    "full-time",
    "aet",
    "pen",
}
DELAYED_STATUSES = {"delayed", "delay"}
SUSPENDED_STATUSES = {"suspended", "susp"}
CANCELLED_STATUSES = {"cancelled", "canceled"}
ABANDONED_STATUSES = {"abandoned", "abnd", "abd", "abandon"}
WALKOVER_STATUSES = {"walkover", "wo", "w/o", "retired"}
PRE_MATCH_STATUSES = {"pre_match", "pre-match", "prematch", "warmup"}
AUTHORITATIVE_END = {"finished", "cancelled", "postponed", "abandoned", "walkover"}
UNRESOLVED_STATUSES = {"stale", "unknown", "status_unknown"}

AUTHORITATIVE_FINISHED = FINISHED_STATUSES | {"ft", "aet", "pen", "fulltime"}

FRESH_PROGRESSION_WINDOW = timedelta(hours=2)

CONFIRMED_LIVE = "CONFIRMED_LIVE"
STALE_LIVE = "STALE_LIVE"
UNPROVEN_LIVE = "UNPROVEN_LIVE"
STATUS_CONFLICT = "STATUS_CONFLICT"


def canonical_status(raw: str) -> str:
    value = str(raw or "scheduled").strip().lower().replace(" ", "_")
    if value in LIVE_STATUSES:
        return "live"
    if value in HALFTIME_STATUSES:
        return "break"
    if value in FINISHED_STATUSES:
        return "finished"
    if value in DELAYED_STATUSES:
        return "delayed"
    if value in SUSPENDED_STATUSES:
        return "suspended"
    if value in {"postponed"}:
        return "postponed"
    if value in ABANDONED_STATUSES:
        return "abandoned"
    if value in WALKOVER_STATUSES:
        return "walkover"
    if value in CANCELLED_STATUSES:
        return "cancelled"
    if value in PRE_MATCH_STATUSES:
        return "scheduled"
    if value in {"stale"}:
        return "stale"
    if value in {"status_unknown", "unknown"}:
        return "unknown"
    if value in STATUS_RANK:
        return value
    return "scheduled"


def is_live(status: str) -> bool:
    return canonical_status(status) in {"live", "halftime", "break"}


def can_replace_status(current: str, incoming: str, incoming_is_higher_priority: bool) -> bool:
    cur = canonical_status(current)
    nxt = canonical_status(incoming)
    if incoming_is_higher_priority:
        return True
    return STATUS_RANK.get(nxt, 0) >= STATUS_RANK.get(cur, 0)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_ts(value: Any) -> Optional[datetime]:
    from collector.util import parse_datetime

    if isinstance(value, datetime):
        return _aware(value)
    parsed = parse_datetime(value)
    return _aware(parsed)


def source_fetch_time(event: Dict[str, Any]) -> Optional[datetime]:
    return parse_ts(event.get("source_fetch_time") or event.get("retrieved_at") or event.get("updated_at"))


def source_event_updated_at(event: Dict[str, Any]) -> Optional[datetime]:
    return parse_ts(event.get("source_event_updated_at") or event.get("event_updated_at"))


def observation_time(event: Dict[str, Any]) -> Optional[datetime]:
    """Provider event/status observation — not merely when we fetched."""
    return source_event_updated_at(event) or parse_ts(
        event.get("observed_at") or event.get("canonical_last_observed_at")
    )


def observation_or_min(event: Dict[str, Any]) -> datetime:
    return observation_time(event) or datetime.min.replace(tzinfo=timezone.utc)


def _filled(value: Any) -> bool:
    return value is not None and value != ""


def has_progress_evidence(event: Dict[str, Any]) -> bool:
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    if any(_filled(score.get(key)) for key in ("clock", "minute", "period", "quarter", "set", "inning")):
        return True
    if event.get("current_set") or event.get("serving") or event.get("innings"):
        return True
    incidents = event.get("incidents")
    if isinstance(incidents, list) and incidents:
        return True
    periods = event.get("periods") or score.get("sets") or score.get("periods")
    if isinstance(periods, list) and periods:
        return True
    maps = event.get("maps")
    if isinstance(maps, list) and maps:
        return True
    return False


def has_explicit_live_status(event: Dict[str, Any]) -> bool:
    """Stored canonical/source_status=live is not evidence by itself.

    Families that cannot emit an independent live flag (elapsed-time inference)
    must supply progress fields. Missing family on a persisted LIVE row is not
    independent evidence.
    """
    if event.get("status_inferred"):
        return False
    family = str(event.get("source_family") or event.get("provider") or "").strip()
    if not family:
        return False
    try:
        from collector.family_caps import family_caps

        if not family_caps(family).get("explicit_live_status"):
            return False
    except Exception:
        return False
    raw = str(event.get("source_status") or "").strip().lower()
    token = raw.replace(" ", "_")
    return token in LIVE_STATUSES or token in HALFTIME_STATUSES or token in {"live", "break", "halftime"}


def has_live_source_evidence(event: Dict[str, Any]) -> bool:
    """LIVE may not be inferred from current_time > start_time."""
    if has_explicit_live_status(event):
        return True
    if has_progress_evidence(event):
        return True
    return False


def has_fresh_live_progression(event: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    current = _aware(now) or datetime.now(timezone.utc)
    updated = source_event_updated_at(event)
    if updated is None:
        return False
    return (current - updated) <= FRESH_PROGRESSION_WINDOW and is_live(event.get("status") or "")


def live_age(event: Dict[str, Any], now: Optional[datetime] = None) -> Optional[timedelta]:
    start = parse_ts(event.get("start_time"))
    if start is None:
        return None
    current = _aware(now) or datetime.now(timezone.utc)
    return current - start


def _family_stale_threshold(event: Dict[str, Any]) -> Optional[timedelta]:
    family = str(event.get("source_family") or event.get("provider") or "")
    if not family:
        return None
    try:
        from collector.family_caps import family_caps

        seconds = family_caps(family).get("stale_after_seconds")
        if seconds:
            return timedelta(seconds=int(seconds))
    except Exception:
        return None
    return None


def beyond_live_horizon(event: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    from collector.live_horizon import live_horizon

    current = _aware(now) or datetime.now(timezone.utc)
    observed = observation_time(event) or source_fetch_time(event)
    family_limit = _family_stale_threshold(event)
    if observed is not None and family_limit is not None and (current - observed) > family_limit:
        if not has_fresh_live_progression(event, now=current):
            return True
    age = live_age(event, now=now)
    if age is None:
        return False
    horizon = live_horizon(
        sport_id=str(event.get("sport") or ""),
        competition_id=str(event.get("competition_key") or event.get("competition") or ""),
        provider=str(event.get("source_family") or event.get("provider") or ""),
        event=event,
    )
    return age > horizon


def public_live_visible(event: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    if not is_live(event.get("status") or ""):
        return False
    if event.get("live_class") in {STALE_LIVE, UNPROVEN_LIVE, STATUS_CONFLICT}:
        return False
    if beyond_live_horizon(event, now=now) and not has_fresh_live_progression(event, now=now):
        return False
    return True


def _pick_authoritative_end(event: Dict[str, Any], counterparts: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_ts = datetime.min.replace(tzinfo=timezone.utc)
    own_ts = observation_or_min(event)
    for other in counterparts:
        status = canonical_status(other.get("status") or "")
        if status not in AUTHORITATIVE_END:
            continue
        other_ts = observation_or_min(other)
        if other_ts < own_ts and other_ts != datetime.min.replace(tzinfo=timezone.utc) and own_ts != datetime.min.replace(
            tzinfo=timezone.utc
        ):
            continue
        if best is None or other_ts >= best_ts:
            best = other
            best_ts = other_ts
    return best


def _status_conflict(event: Dict[str, Any], counterparts: Iterable[Dict[str, Any]]) -> bool:
    statuses = {canonical_status(event.get("status") or "")}
    for other in counterparts:
        statuses.add(canonical_status(other.get("status") or ""))
    live_like = statuses & {"live", "break", "halftime"}
    terminal = statuses & AUTHORITATIVE_END
    scheduled = statuses & {"scheduled", "delayed", "postponed"}
    return bool(live_like and terminal) or bool(len(statuses) >= 3 and live_like and scheduled)


def reconcile_live_status(
    event: Dict[str, Any],
    *,
    counterparts: Optional[Iterable[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Move a source-stale or unproven LIVE row off public live without fabricating a result."""
    out = dict(event)
    if not out.get("source_status"):
        out["source_status"] = event.get("status")
    current = _aware(now) or datetime.now(timezone.utc)
    others = list(counterparts or [])
    status = canonical_status(out.get("status") or "")
    out["status"] = status
    winner = _pick_authoritative_end(out, others)
    if winner is not None:
        out["status"] = canonical_status(winner.get("status") or "finished")
        out["live"] = False
        out["live_class"] = STATUS_CONFLICT if is_live(status) else out.get("live_class")
        out["status_reconciliation"] = "authoritative_end_from_independent_source"
        other_score = winner.get("score") if isinstance(winner.get("score"), dict) else {}
        own_score = out.get("score") if isinstance(out.get("score"), dict) else {}
        if other_score.get("home") is not None or other_score.get("away") is not None:
            merged_score = dict(own_score)
            for key, value in other_score.items():
                if value is not None:
                    merged_score[key] = value
            out["score"] = merged_score
        out["canonical_last_observed_at"] = (
            (observation_time(winner) or observation_time(out) or current).isoformat().replace("+00:00", "Z")
        )
        return out
    if _status_conflict(out, others) and is_live(status):
        out["live_class"] = STATUS_CONFLICT
        out["status_reconciliation"] = "cross_provider_status_conflict"
    candidate_live = is_live(status) or status == "stale"
    if not candidate_live:
        out["live"] = False
        return out
    if not has_live_source_evidence(out):
        out["status"] = "scheduled"
        out["live"] = False
        out["live_class"] = UNPROVEN_LIVE
        out["status_reconciliation"] = "live_without_source_evidence"
        return out
    if beyond_live_horizon(out, now=current) and not has_fresh_live_progression(out, now=current):
        out["status"] = "stale"
        out["live"] = False
        out["live_class"] = STALE_LIVE
        out["status_reconciliation"] = "horizon_exceeded_source_still_live"
        return out
    out["status"] = "live" if status == "stale" else status
    out["live"] = True
    out["live_class"] = CONFIRMED_LIVE
    return out


def guard_future_status(
    status: str,
    start_time: Optional[str],
    *,
    inferred: bool = False,
    sport_id: str = "",
    now=None,
) -> str:
    """A kickoff still in the future cannot be FINISHED. LIVE is never inferred from elapsed time."""
    canon = canonical_status(status)
    start = parse_ts(start_time)
    current = _aware(now) or datetime.now(timezone.utc)
    if canon != "finished":
        return canon
    if start is None:
        return canon
    if start > current + timedelta(hours=2):
        return "scheduled"
    if inferred and start > current:
        return "scheduled"
    return canon
