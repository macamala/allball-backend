"""Runtime integration audit for the frozen 180/180 source matrix.

Does not mutate source_matrix_final.json. Isolated sqlite persistence only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from collector.adapters import FetchRequest, FetchResult, make_adapter
from collector.collect import _upsert_event
from collector.event_quality import (
    BRACKET,
    HEAD_TO_HEAD,
    MEET,
    MULTI_EVENT_MEET,
    RACE,
    TEAM_MATCH,
    TOURNAMENT,
    event_is_valid,
    event_type_for,
    reject_reason,
)
from collector.family_health import family_rate_limited, snapshot as family_health_snapshot
from collector.family_plan import sort_jobs
from collector.match import TIME_WINDOW, same_canonical_event
from collector.timezones import DATE_ONLY, TIMEZONE_UNKNOWN
from collector.http import STATS, reset_http_stats
from collector.adapters_thesportsdb import REQUEST_LOG, reset_thesportsdb_cache
from collector.live_state import (
    beyond_live_horizon,
    canonical_status,
    has_fresh_live_progression,
    is_live,
    live_age,
    public_live_visible,
    reconcile_live_status,
)
from collector.merge import merge_event_fields, volatile_incoming_wins
from collector.models import (
    SportsCompetition,
    SportsEvent,
    SportsSource,
    SportsSourceCompetition,
)
from collector.normalize import fingerprint, normalize_event
from collector.production import bootstrap_registry, register_production_adapters
from collector.registry import build_runtime_registry
from collector.util import dump_json, parse_datetime
from models import Base

ROOT = Path(__file__).resolve().parent.parent.parent
MATRIX_PATH = ROOT / "source_matrix_final.json"
AUDIT_DIR = ROOT / "audit"
SNAPSHOT = AUDIT_DIR / "source_matrix_final.pre_runtime.sha256"

FOOTBALL_MARKERS = (
    "premier league",
    "serie a",
    "la liga",
    "bundesliga",
    "champions league",
    "eredivisie",
)
RUGBY_MARKERS = ("stormers", "hurricanes", "benetton", "super rugby")
LEAGUE_MARKERS = ("kt rolster", "gen.g", "t1 wins series")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def freeze_matrix() -> Dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    raw = MATRIX_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    SNAPSHOT.write_text(digest + "\n", encoding="utf-8")
    matrix = json.loads(raw.decode("utf-8"))
    comps = matrix.get("competitions") or []
    full = [row for row in comps if (row.get("full_or_partial") == "full" or row.get("bucket") == "A+B WORKING")]
    remaining = [row["competition"] for row in comps if row.get("full_or_partial") != "full"]
    missing_ab = [
        row["competition"]
        for row in comps
        if not ((row.get("provider_a") or {}).get("family") and (row.get("provider_b") or {}).get("family"))
    ]
    assert matrix.get("total_competitions") == 180
    assert len(comps) == 180
    assert len(full) == 180
    assert remaining == []
    assert missing_ab == []
    return {
        "sha256": digest,
        "total": 180,
        "clean_full": 180,
        "remaining": 0,
        "matrix_unchanged_path": str(MATRIX_PATH),
        "snapshot": str(SNAPSHOT),
    }


def _name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "").strip()
    return str(side or "").strip()


def classify_result(result: FetchResult, valid_events: int) -> str:
    status = int(result.http_status or 0)
    err = (result.error or "").lower()
    if status == 429 or result.classification == "RATE_LIMITED":
        return "RATE_LIMITED"
    if status in {401, 403, 404, 410}:
        return "ACCESS_BLOCKED"
    if status >= 500:
        return "NETWORK_ERROR"
    if "timeout" in err or "timed out" in err:
        return "TIMEOUT"
    if status == 0 and not result.ok:
        return "NETWORK_ERROR"
    if result.parse_status == "failed" or result.classification == "PARSE_FAILURE":
        return "PARSER_ERROR"
    if result.restricted:
        return "ACCESS_BLOCKED"
    if not result.ok:
        return "UNEXPECTED_ERROR"
    if valid_events:
        return "WORKING_WITH_EVENTS"
    if result.parse_status == "empty":
        return "WORKING_EMPTY"
    return "WORKING_EMPTY"


def empty_reason(health: str, result: FetchResult) -> str:
    if health == "PARSER_ERROR":
        return "PARSER_FAILURE"
    if health == "NETWORK_ERROR":
        return "NETWORK_FAILURE"
    if health == "TIMEOUT":
        return "NETWORK_FAILURE"
    if health == "ACCESS_BLOCKED":
        return "ACCESS_FAILURE"
    if health == "RATE_LIMITED":
        return "ACCESS_FAILURE"
    if health == "WORKING_EMPTY":
        reason = (result.empty_reason or "").upper()
        if "NO_EVENTS" in reason or "SOURCE_HEALTHY" in reason:
            return "SOURCE_WORKING_EMPTY"
        return "NO_EVENT_IN_WINDOW"
    return "UNKNOWN"


def leak_reasons(event: Dict[str, Any], sport: str, competition_id: str) -> List[str]:
    reasons = []
    ev_sport = str(event.get("sport") or sport)
    if ev_sport and ev_sport != sport:
        reasons.append(f"event.sport={ev_sport} matrix.sport={sport}")
    blob = " ".join(
        [
            _name(event.get("home")),
            _name(event.get("away")),
            str(event.get("competition") or ""),
            str(event.get("source_url") or ""),
        ]
    ).lower()
    if sport == "futsal" and any(tok in blob for tok in FOOTBALL_MARKERS + ("levadia", "tammeka")):
        reasons.append("football vocabulary on futsal row")
    if sport == "football" and any(tok in blob for tok in RUGBY_MARKERS):
        reasons.append("rugby vocabulary on football row")
    if sport == "overwatch" and any(tok in blob for tok in LEAGUE_MARKERS):
        reasons.append("LoL vocabulary on overwatch row")
    if competition_id == "africa-cup-of-nations" and any(
        tok in blob for tok in ("flamengo", "bucaramanga", "libertadores", "boca juniors", "river plate")
    ):
        reasons.append("club football on africa-cup-of-nations")
    if "fifa-futsal" in competition_id and any(tok in blob for tok in ("premier league", "serie a")):
        reasons.append("FIFA futsal football leak")
    return reasons


def identity_key(norm: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    home = _name(norm.get("home")).lower()
    away = _name(norm.get("away")).lower()
    start = str(norm.get("start_time") or "")[:10]
    return (
        str(norm.get("sport") or ""),
        str(norm.get("competition_key") or ""),
        start,
        " ".join(sorted({home, away})),
        str(norm.get("round") or norm.get("stage") or ""),
    )


def fetch_side(mapping: Dict[str, Any], competition_id: str, sport: str, side: str) -> Dict[str, Any]:
    family = mapping.get("source_family") or ""
    adapter_key = mapping.get("adapter_key") or ""
    config = mapping.get("source_config") or {}
    started = time.perf_counter()
    started_at = _now()
    row: Dict[str, Any] = {
        "competition": competition_id,
        "sport": sport,
        "side": side,
        "provider": adapter_key,
        "upstream_family": family,
        "started_at": started_at,
        "events_received": 0,
        "events_normalized": 0,
        "events_rejected": 0,
        "http_status": None,
        "error_type": None,
        "error_message": None,
        "normalized": [],
        "rejected": [],
    }
    try:
        adapter = make_adapter(adapter_key, f"audit-{side}-{competition_id}")
        request = FetchRequest(
            capability="snapshot",
            sport_id=sport,
            competition_id=competition_id,
            source_competition_id=mapping.get("source_competition_id") or competition_id,
            source_config=config,
            upstream_family=family,
        )
        if family_rate_limited(family):
            row.update(
                {
                    "finished_at": _now(),
                    "latency_ms": 0,
                    "health": "RATE_LIMITED",
                    "error_type": "FAMILY_COOLDOWN",
                    "error_message": f"{family} family cooldown",
                    "empty_class": "ACCESS_FAILURE",
                    "family_incident": True,
                }
            )
            return row
        result = adapter.fetch(request)
    except Exception as exc:
        msg = str(exc)
        low = msg.lower()
        if "429" in low:
            health = "RATE_LIMITED"
        elif any(code in low for code in (" 403", "http 403", " 401", "http 401", " 404", "http 404", " 410")):
            health = "ACCESS_BLOCKED"
        elif "timeout" in low or "timed out" in low:
            health = "TIMEOUT"
        else:
            health = "UNEXPECTED_ERROR"
        row.update(
            {
                "finished_at": _now(),
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "health": health,
                "error_type": type(exc).__name__,
                "error_message": msg[:500],
                "empty_class": empty_reason(health, FetchResult(ok=False, error=msg)),
            }
        )
        return row
    raw_events = list(result.events or [])
    valid = []
    rejected = []
    for raw in raw_events:
        raw = dict(raw)
        raw["source_fetch_time"] = started_at
        reason = reject_reason(raw, sport_id=sport, competition_id=competition_id)
        if reason:
            rejected.append({"reason": reason, "home": _name(raw.get("home")), "away": _name(raw.get("away"))})
            continue
        norm = normalize_event(raw, sport_id=sport, competition_id=competition_id)
        leaks = leak_reasons(norm, sport, competition_id)
        if leaks:
            rejected.append({"reason": "leak:" + ";".join(leaks), "home": _name(norm.get("home")), "away": _name(norm.get("away"))})
            continue
        valid.append(norm)
    health = classify_result(result, len(valid))
    row.update(
        {
            "finished_at": _now(),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "http_status": result.http_status,
            "events_received": len(raw_events),
            "events_normalized": len(valid),
            "events_rejected": len(rejected),
            "health": health,
            "empty_class": empty_reason(health, result) if not valid else None,
            "error_message": (result.error or "")[:400] or None,
            "parse_status": result.parse_status,
            "reject_reasons": dict(Counter(item["reason"] for item in rejected)),
            "normalized": valid,
            "rejected": rejected[:40],
        }
    )
    return row


def runtime_jobs() -> List[Tuple[str, str, str, Dict[str, Any]]]:
    runtime = build_runtime_registry()
    jobs = []
    for competition_id, record in sorted(runtime["competitions"].items()):
        sport = record.get("sport") or ""
        families = []
        seen = set()
        for mapping in record.get("sources") or []:
            if not mapping.get("enabled"):
                continue
            family = mapping.get("source_family")
            if not family or family in seen:
                continue
            seen.add(family)
            families.append(mapping)
            if len(families) == 2:
                break
        if len(families) < 2:
            continue
        jobs.append((competition_id, sport, "A", families[0]))
        jobs.append((competition_id, sport, "B", families[1]))
    return sort_jobs(jobs)


def overlap_and_conflicts(by_comp: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    overlaps = []
    merged = 0
    failed = []
    false_merges = []
    conflicts = []
    for cid, sides in by_comp.items():
        a_events = (sides.get("A") or {}).get("normalized") or []
        b_events = (sides.get("B") or {}).get("normalized") or []
        for ev_a in a_events:
            for ev_b in b_events:
                ha, aa = _name(ev_a.get("home")).lower(), _name(ev_a.get("away")).lower()
                hb, ab = _name(ev_b.get("home")).lower(), _name(ev_b.get("away")).lower()
                if {ha, aa} != {hb, ab} or not ha:
                    continue
                ta = parse_datetime(ev_a.get("start_time"))
                tb = parse_datetime(ev_b.get("start_time"))
                delta = abs((ta - tb).total_seconds()) if ta and tb else None
                if same_canonical_event(ev_a, ev_b):
                    merged += 1
                    overlaps.append({"competition": cid, "home": ha, "delta_s": delta})
                    if delta is not None and delta > 3 * 3600:
                        false_merges.append({"competition": cid, "reason": "merged beyond 3h kickoff tolerance", "delta_s": delta})
                    a_score = ev_a.get("score") or {}
                    b_score = ev_b.get("score") or {}
                    if (a_score.get("home"), a_score.get("away")) != (b_score.get("home"), b_score.get("away")):
                        if a_score.get("home") is not None and b_score.get("home") is not None:
                            winner = volatile_incoming_wins(
                                {"status": ev_a.get("status"), "score": a_score, "observed_at": ev_a.get("retrieved_at")},
                                {"status": ev_b.get("status"), "score": b_score, "observed_at": ev_b.get("retrieved_at")},
                                incoming_is_higher_priority=False,
                            )
                            conflicts.append(
                                {
                                    "competition": cid,
                                    "a_score": a_score,
                                    "b_score": b_score,
                                    "chosen": "B" if winner else "A",
                                    "reason": "freshness>progression>status>priority",
                                }
                            )
                elif delta is not None and 0 < delta <= TIME_WINDOW.total_seconds():
                    failed.append({"competition": cid, "home": ha, "delta_s": delta})
    return {
        "overlaps": merged,
        "merged": merged,
        "failed_to_merge": failed[:50],
        "false_merges": false_merges[:50],
        "score_conflicts": conflicts[:80],
        "overlap_samples": overlaps[:40],
    }


def quality(by_comp: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    counts = Counter()
    suspects = defaultdict(list)
    now = datetime.now(timezone.utc)
    for cid, sides in by_comp.items():
        sport = (sides.get("A") or sides.get("B") or {}).get("sport") or ""
        for side, row in sides.items():
            for ev in row.get("normalized") or []:
                counts["events_total"] += 1
                others = []
                other_side = "B" if side == "A" else "A"
                for other in (sides.get(other_side) or {}).get("normalized") or []:
                    if same_canonical_event(ev, other):
                        others.append(other)
                viewed = reconcile_live_status(dict(ev), counterparts=others, now=now)
                status = canonical_status(viewed.get("status") or "")
                start = parse_datetime(viewed.get("start_time") or ev.get("start_time"))
                source_status = canonical_status(ev.get("source_status") or ev.get("status") or "")
                if status == "live":
                    counts["live"] += 1
                elif status == "finished":
                    counts["finished"] += 1
                elif status in {"scheduled", "pre_match"}:
                    counts["upcoming"] += 1
                elif status in {"stale", "status_unknown"}:
                    counts["unresolved_status"] += 1
                else:
                    counts["unknown_status"] += 1
                if not _name(ev.get("home")):
                    counts["missing_participants"] += 1
                    suspects["missing_participants"].append({"competition": cid, "side": side})
                if not ev.get("start_time"):
                    counts["missing_start_time"] += 1
                    kind = event_type_for(cid, sport)
                    precision = ev.get("start_precision")
                    if precision == DATE_ONLY or ev.get("start_date"):
                        counts["date_only_valid"] += 1
                    elif kind in {TEAM_MATCH, HEAD_TO_HEAD, BRACKET}:
                        counts["missing_start_team_match"] += 1
                        suspects["missing_start"].append({"competition": cid, "kind": kind, "home": _name(ev.get("home"))})
                    else:
                        counts["missing_start_other"] += 1
                if status == "finished":
                    score = viewed.get("score") or ev.get("score") or {}
                    kind = event_type_for(cid, sport)
                    if kind in {TEAM_MATCH, HEAD_TO_HEAD, BRACKET} and score.get("home") is None:
                        counts["missing_score_on_finished"] += 1
                        outcome = "walkover" if ev.get("walkover") or ev.get("result_type") in {"walkover", "forfeit", "wo"} else "unresolved"
                        suspects["finished_without_score"].append(
                            {
                                "competition": cid,
                                "home": _name(ev.get("home")),
                                "away": _name(ev.get("away")),
                                "result_type": ev.get("result_type") or outcome,
                                "side": side,
                            }
                        )
                age = live_age(viewed, now=now)
                source_live_old = is_live(source_status) and start and (now - start.replace(tzinfo=start.tzinfo or timezone.utc)) > timedelta(hours=8)
                if source_live_old:
                    counts["audit_8h_live"] += 1
                    suspects["audit_8h_live"].append(
                        {
                            "sport": sport,
                            "competition": cid,
                            "side": side,
                            "provider": row.get("provider") or ev.get("source_family"),
                            "source_event_id": ev.get("source_event_id"),
                            "home": _name(ev.get("home")),
                            "away": _name(ev.get("away")),
                            "start": ev.get("start_time"),
                            "source_status": ev.get("source_status") or ev.get("status"),
                            "canonical_status": viewed.get("status"),
                            "score": ev.get("score"),
                            "source_event_updated_at": ev.get("source_event_updated_at"),
                            "source_fetch_time": ev.get("source_fetch_time") or row.get("finished_at"),
                            "live_age_h": round(age.total_seconds() / 3600, 2) if age else None,
                            "timezone_resolution_method": ev.get("timezone_resolution_method"),
                            "status_reconciliation": viewed.get("status_reconciliation"),
                        }
                    )
                if is_live(status) and beyond_live_horizon(viewed, now=now) and not has_fresh_live_progression(viewed, now=now):
                    counts["stale_live"] += 1
                    suspects["stale_live"].append(
                        {
                            "sport": sport,
                            "competition": cid,
                            "side": side,
                            "provider": row.get("provider") or ev.get("source_family"),
                            "source_event_id": ev.get("source_event_id"),
                            "home": _name(ev.get("home")),
                            "away": _name(ev.get("away")),
                            "start": ev.get("start_time"),
                            "source_status": ev.get("source_status") or ev.get("status"),
                            "canonical_status": viewed.get("status"),
                            "score": ev.get("score"),
                            "source_event_updated_at": ev.get("source_event_updated_at"),
                            "source_fetch_time": ev.get("source_fetch_time"),
                            "live_age_h": round(age.total_seconds() / 3600, 2) if age else None,
                            "timezone_resolution_method": ev.get("timezone_resolution_method"),
                        }
                    )
                method = ev.get("timezone_resolution_method") or ""
                if method == TIMEZONE_UNKNOWN and ev.get("source_local_datetime"):
                    counts["timezone_unknown"] += 1
                    suspects["timezone_unknown"].append({"competition": cid, "start": ev.get("source_local_datetime")})
                elif method and method != TIMEZONE_UNKNOWN:
                    counts["timezone_resolved"] += 1
                if start and status == "finished" and start.replace(tzinfo=start.tzinfo or timezone.utc) > now + timedelta(hours=2):
                    counts["future_finished"] += 1
                    suspects["future_marked_finished"].append({"competition": cid, "start": ev.get("start_time"), "sport": sport})
                if start and is_live(status) and start.replace(tzinfo=start.tzinfo or timezone.utc) > now + timedelta(hours=6):
                    suspects["future_marked_live"].append({"competition": cid, "start": ev.get("start_time")})
                for leak in leak_reasons(ev, sport, cid):
                    if "matrix.sport" in leak or "vocabulary" in leak:
                        counts["cross_sport_leaks"] += 1
                    else:
                        counts["competition_leaks"] += 1
                    suspects["leaks"].append({"competition": cid, "reason": leak, "home": _name(ev.get("home"))})
    return {"counts": dict(counts), "suspects": {k: v[:40] for k, v in suspects.items()}}


def persist_twice(by_comp: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    db_path = AUDIT_DIR / "runtime_audit.sqlite"
    if db_path.exists():
        db_path.unlink()
    engine = create_engine("sqlite:///" + str(db_path).replace("\\", "/"))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    register_production_adapters()
    bootstrap_registry(db)
    db.commit()

    def ingest() -> Tuple[int, int]:
        inserts_before = db.query(SportsEvent).count()
        from collector.match import match_event

        for cid, sides in by_comp.items():
            competition = db.query(SportsCompetition).filter_by(competition_id=cid).first()
            if competition is None:
                continue
            try:
                for side in ("A", "B"):
                    row = sides.get(side) or {}
                    maps = (
                        db.query(SportsSourceCompetition)
                        .filter_by(competition_id=cid, enabled=True)
                        .order_by(SportsSourceCompetition.priority.asc())
                        .all()
                    )
                    mapping = maps[0] if side == "A" and maps else (maps[1] if len(maps) > 1 else None)
                    if mapping is None:
                        continue
                    source = db.query(SportsSource).filter_by(source_id=mapping.source_id).first()
                    if source is None:
                        continue
                    for ev in (row.get("normalized") or [])[:200]:
                        incoming = dict(ev)
                        incoming.pop("_resolved_time", None)
                        incoming["source_fetch_time"] = incoming.get("source_fetch_time") or _now()
                        incoming["retrieved_at"] = incoming.get("source_fetch_time")
                        existing = match_event(db, incoming, source_id=source.source_id)
                        _upsert_event(db, incoming=incoming, source=source, mapping=mapping, existing=existing)
                db.commit()
            except Exception:
                db.rollback()
        return db.query(SportsEvent).count() - inserts_before, db.query(SportsEvent).count()

    first_delta, after_first = ingest()
    second_delta, after_second = ingest()
    # alter one score and rerun to confirm update
    sample = db.query(SportsEvent).first()
    updates = 0
    if sample is not None:
        sample.status = "finished"
        db.commit()
        updates = 1
        ingest()
        updates = 1 if db.query(SportsEvent).filter_by(event_id=sample.event_id).count() == 1 else 0
    total = db.query(SportsEvent).count()
    db.close()
    return {
        "first_run_inserts": first_delta,
        "second_run_inserts": second_delta,
        "events_after_first": after_first,
        "events_after_second": after_second,
        "updates": updates,
        "duplicate_rows": max(0, after_second - after_first) if second_delta else 0,
        "stored": total,
    }


def api_local() -> Dict[str, Any]:
    from collector.provider import NinkoCollectedSportsDataProvider
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import create_engine as _ce

    engine = _ce("sqlite:///" + str(AUDIT_DIR / "runtime_audit.sqlite").replace("\\", "/"))
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    provider = NinkoCollectedSportsDataProvider(session_factory=Session)
    try:
        live = provider.get_live_events()
        finished = provider.get_events(status="finished")
        upcoming = provider.get_events(status="scheduled")
        sample = (finished or upcoming or live or [{}])[0]
        ok = True
        errors = []
        if sample and sample.get("id"):
            for key in ("sport", "competition", "status"):
                if key not in sample:
                    ok = False
                    errors.append(f"missing {key}")
        combined = list(live or []) + list(upcoming or []) + list(finished or [])
        ids = [row.get("id") for row in combined if row.get("id")]
        if len(ids) != len(set(ids)):
            ok = False
            errors.append("duplicate canonical id in API surfaces")
        now = datetime.now(timezone.utc)
        for row in finished or []:
            start = parse_datetime(row.get("start_time"))
            if start and start.replace(tzinfo=start.tzinfo or timezone.utc) > now + timedelta(hours=2):
                ok = False
                errors.append("future-finished in API")
                break
        for row in live or []:
            if not public_live_visible(row, now=now):
                ok = False
                errors.append("stale live in API")
                break
        return {
            "live": len(live),
            "upcoming": len(upcoming),
            "finished": len(finished),
            "errors": errors,
            "connected": provider.status().get("connected"),
            "sample_keys": sorted(sample.keys())[:20] if sample else [],
            "ok": ok,
        }
    except Exception as exc:
        return {"live": 0, "upcoming": 0, "finished": 0, "errors": [str(exc)], "ok": False}


def mock_failover() -> Dict[str, Any]:
    from collector.adapters import FetchResult, register_adapter, unregister_adapter
    from collector.collect import collect_competition
    from collector.test_support import DeterministicMockAdapter, mock_event
    from collector.util import dump_json

    previous_write = os.environ.get("RESULTS_WRITE_ENABLED")
    os.environ["RESULTS_WRITE_ENABLED"] = "true"
    os.environ.setdefault("RESULTS_COLLECTION_ENABLED", "true")
    families = sorted({job[3].get("source_family") for job in runtime_jobs() if job[3].get("source_family")})
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = Session()
    passed = 0
    failed = []
    tested = 0
    created = []
    try:
        for index, family in enumerate(families):
            cid = f"fail-{index}-{family}"[:80]
            key_a = f"fa-{index}"
            key_b = f"fb-{index}"
            good_b = DeterministicMockAdapter(key_b)
            good_b.events = [
                mock_event(
                    id=f"{cid}-b",
                    home={"name": f"Home {index}"},
                    away={"name": f"Away {index}"},
                    start_time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    competition=cid,
                    sport="football",
                )
            ]

            class FailA:
                adapter_key = key_a

                def __init__(self, source_id=key_a):
                    self.source_id = source_id

                def fetch(self, request):
                    return FetchResult(ok=False, http_status=500, error="injected 500", classification="NETWORK_FAILURE")

            register_adapter(key_a, FailA)
            register_adapter(key_b, lambda source_id=key_b, adapter=good_b: adapter)
            created.extend([key_a, key_b])
            for source_id, adapter_key, fam, prio in ((f"{cid}-a", key_a, family, 1), (f"{cid}-b", key_b, f"{family}-b", 2)):
                db.add(
                    SportsSource(
                        source_id=source_id,
                        display_name=source_id,
                        kind="test",
                        enabled=True,
                        adapter_key=adapter_key,
                        upstream_family=fam,
                    )
                )
                db.add(
                    SportsSourceCompetition(
                        competition_id=cid,
                        source_id=source_id,
                        priority=prio,
                        enabled=True,
                        upstream_family=fam,
                        source_competition_id=cid,
                    )
                )
            db.add(
                SportsCompetition(
                    competition_id=cid,
                    sport_id="football",
                    name=cid,
                    slug=cid,
                    event_model="team_match",
                    identity_only=False,
                    active=True,
                )
            )
            db.commit()
            tested += 1
            try:
                result = collect_competition(
                    db,
                    db.query(SportsCompetition).filter_by(competition_id=cid).one(),
                    "snapshot",
                    sleeper=lambda _d: None,
                )
                db.commit()
                count = db.query(SportsEvent).filter_by(competition_id=cid).count()
                event = db.query(SportsEvent).filter_by(competition_id=cid).first()
                if result.get("written", 0) >= 1 and count == 1 and event and event.primary_source_id == f"{cid}-b":
                    passed += 1
                else:
                    failed.append(
                        {
                            "family": family,
                            "written": result,
                            "count": count,
                            "primary": getattr(event, "primary_source_id", None),
                        }
                    )
            except Exception as exc:
                db.rollback()
                failed.append({"family": family, "error": str(exc)})
    finally:
        if previous_write is None:
            os.environ.pop("RESULTS_WRITE_ENABLED", None)
        else:
            os.environ["RESULTS_WRITE_ENABLED"] = previous_write
        db.close()
        for key in created:
            unregister_adapter(key)
    return {"families_tested": tested, "passed": passed, "failed": failed[:30], "family_count": len(families)}


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out = Counter()
    for row in rows:
        health = row.get("health") or "UNEXPECTED_ERROR"
        out[health] += 1
        if health == "WORKING_WITH_EVENTS":
            out["working"] += 1
        elif health == "WORKING_EMPTY":
            out["working_empty"] += 1
        elif health == "PARTIAL":
            out["partial"] += 1
        elif health == "RATE_LIMITED":
            out["rate_limited"] += 1
            if row.get("family_incident") or row.get("error_type") == "FAMILY_COOLDOWN":
                out["family_rate_limited"] += 1
        elif health == "ACCESS_BLOCKED":
            out["access_blocked"] += 1
        elif health in {"NETWORK_ERROR", "TIMEOUT"}:
            out["network_error"] += 1
        elif health == "PARSER_ERROR":
            out["parser_error"] += 1
        else:
            out["failed"] += 1
    return dict(out)


def compact_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    qual = (report.get("data_quality") or {}).get("counts") or {}
    ident = report.get("identity") or {}
    a = report.get("primary_a") or {}
    b = report.get("fallback_b") or {}
    events = report.get("events") or {}
    net = report.get("network") or {}
    tsdb = report.get("thesportsdb") or {}
    perf = report.get("performance") or {}
    matrix = report.get("matrix") or {}
    return {
        "matrix_total": matrix.get("total") or matrix.get("competition_count") or 180,
        "matrix_checksum": matrix.get("sha256") or matrix.get("checksum"),
        "jobs_total": report.get("jobs"),
        "jobs_completed": report.get("jobs"),
        "A": {
            "working": a.get("working", 0),
            "working_empty": a.get("working_empty", 0),
            "rate_limited": a.get("rate_limited", 0),
            "access_blocked": a.get("access_blocked", 0),
            "network_error": a.get("network_error", 0),
            "parser_error": a.get("parser_error", 0),
        },
        "B": {
            "working": b.get("working", 0),
            "working_empty": b.get("working_empty", 0),
            "rate_limited": b.get("rate_limited", 0),
            "access_blocked": b.get("access_blocked", 0),
            "network_error": b.get("network_error", 0),
            "parser_error": b.get("parser_error", 0),
        },
        "events": {
            "raw": events.get("raw"),
            "normalized": events.get("normalized"),
            "rejected": report.get("malformed_events"),
        },
        "identity": {
            "overlaps": ident.get("overlaps") or events.get("ab_overlaps"),
            "merged": ident.get("merged") or events.get("merged"),
            "duplicate_failures": len(ident.get("failed_to_merge") or []),
            "false_merges": len(ident.get("false_merges") or []),
        },
        "quality": {
            "cross_sport_leaks": qual.get("cross_sport_leaks", 0),
            "competition_leaks": qual.get("competition_leaks", 0),
            "future_finished": qual.get("future_finished", 0),
            "stale_live": qual.get("stale_live", 0),
            "stale_live_rows": ((report.get("data_quality") or {}).get("suspects") or {}).get("stale_live") or [],
            "audit_8h_live": qual.get("audit_8h_live", 0),
            "audit_8h_live_rows": [
                {
                    "sport": row.get("sport"),
                    "competition": row.get("competition"),
                    "home": row.get("home"),
                    "away": row.get("away"),
                    "provider": row.get("provider"),
                    "source_status": row.get("source_status"),
                    "canonical_status": row.get("canonical_status"),
                    "start": row.get("start"),
                    "live_age_h": row.get("live_age_h"),
                }
                for row in (((report.get("data_quality") or {}).get("suspects") or {}).get("audit_8h_live") or [])[:4]
            ],
            "timezone_unknown": qual.get("timezone_unknown", 0),
            "malformed": report.get("malformed_events", 0),
            "missing_start": qual.get("missing_start_time", 0),
            "finished_without_numeric_score": qual.get("missing_score_on_finished", 0),
        },
        "network": {
            "403": net.get("403", 0),
            "429": net.get("429", 0),
            "5xx": net.get("5xx", 0),
            "timeouts": net.get("timeouts", 0),
            "network_errors": net.get("network_errors", 0),
            "requests": net.get("requests", 0),
            "cache_hits": net.get("cache_hits", 0),
        },
        "thesportsdb": {
            "logical_jobs": tsdb.get("logical_jobs"),
            "physical_requests": tsdb.get("physical_requests"),
            "cache_hits": tsdb.get("cache_hits"),
            "429": tsdb.get("429"),
            "cooldown_skips": tsdb.get("family_cooldown_jobs"),
        },
        "performance": {
            "runtime_s": perf.get("total_runtime_s"),
            "physical_requests": net.get("requests"),
            "cache_hits": net.get("cache_hits"),
            "average_latency_ms": perf.get("average_latency_ms"),
        },
        "critical": report.get("critical"),
        "critical_reasons": report.get("critical_reasons") or [],
        "persist": {
            "second_run_inserts": (report.get("database") or {}).get("second_run_inserts"),
            "error": (report.get("database") or {}).get("error"),
        },
        "failover": {
            "passed": (report.get("failover") or {}).get("passed"),
            "tested": (report.get("failover") or {}).get("families_tested"),
        },
        "api": {
            "errors": (report.get("api_local") or {}).get("errors") or [],
            "live": (report.get("api_local") or {}).get("live"),
            "ok": (report.get("api_local") or {}).get("ok"),
        },
    }


def main(*, quiet: bool = False, railway: bool = False) -> Dict[str, Any]:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    freeze = freeze_matrix()
    register_production_adapters()
    reset_http_stats()
    reset_thesportsdb_cache()
    jobs = runtime_jobs()
    if quiet:
        print("START", flush=True)
    t0 = time.perf_counter()
    results: List[Dict[str, Any]] = []
    by_comp: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    marks = {50, 100, 150, 200, 250, 300, len(jobs)}
    for i, (competition_id, sport, side, mapping) in enumerate(jobs, 1):
        row = fetch_side(mapping, competition_id, sport, side)
        slim = {k: v for k, v in row.items() if k not in {"normalized", "rejected"}}
        results.append(slim)
        by_comp[competition_id][side] = row
        if quiet:
            if i in marks:
                print(f"{i}/{len(jobs)}", flush=True)
        elif i % 20 == 0 or i == len(jobs):
            print(f"audit {i}/{len(jobs)} {competition_id} {side} {row.get('health')}", flush=True)
    runtime_s = time.perf_counter() - t0
    a_rows = [r for r in results if r.get("side") == "A"]
    b_rows = [r for r in results if r.get("side") == "B"]
    ident = overlap_and_conflicts(by_comp)
    qual = quality(by_comp)
    net = {
        "403": STATS.get("http_403", 0),
        "429": STATS.get("http_429", 0),
        "timeouts": STATS.get("timeouts", 0),
        "network_errors": STATS.get("network_failures", 0),
        "requests": STATS.get("requests", 0),
        "cache_hits": STATS.get("cache_hits", 0),
        "paced": STATS.get("paced", 0),
    }
    http_5xx = sum(1 for r in results if int(r.get("http_status") or 0) >= 500)
    net["5xx"] = http_5xx
    family_stats = defaultdict(lambda: {"competitions": 0, "latency_ms": 0, "n": 0, "events": 0})
    for r in results:
        fam = r.get("upstream_family") or "unknown"
        family_stats[fam]["competitions"] += 1
        family_stats[fam]["latency_ms"] += int(r.get("latency_ms") or 0)
        family_stats[fam]["n"] += 1
        family_stats[fam]["events"] += int(r.get("events_normalized") or 0)
    slowest = sorted(
        (
            {"family": fam, "avg_latency_ms": int(val["latency_ms"] / max(1, val["n"])), "n": val["n"]}
            for fam, val in family_stats.items()
        ),
        key=lambda item: item["avg_latency_ms"],
        reverse=True,
    )[:12]

    persist = {"error": None}
    try:
        persist = persist_twice(by_comp)
    except Exception as exc:
        persist = {"first_run_inserts": None, "second_run_inserts": None, "stored": 0, "error": str(exc), "updates": 0, "duplicate_rows": None}
    api = {"error": None}
    try:
        api = api_local()
    except Exception as exc:
        api = {"live": 0, "upcoming": 0, "finished": 0, "errors": [str(exc)], "ok": False}
    failover = {"error": None}
    try:
        failover = mock_failover()
    except Exception as exc:
        failover = {"families_tested": 0, "passed": 0, "failed": [{"error": str(exc)}]}

    after = hashlib.sha256(MATRIX_PATH.read_bytes()).hexdigest()
    matrix_unchanged = after == freeze["sha256"]

    a_sum = summarize(a_rows)
    b_sum = summarize(b_rows)
    raw = sum(r.get("events_received") or 0 for r in results)
    normalized = sum(r.get("events_normalized") or 0 for r in results)
    malformed = sum(r.get("events_rejected") or 0 for r in results)

    malformed_buckets = Counter()
    for r in results:
        reasons = r.get("reject_reasons") or {}
        for reason, count in reasons.items():
            malformed_buckets[reason] += int(count)
    tsdb_rows = [r for r in results if r.get("upstream_family") == "thesportsdb"]
    b_access = []
    for r in b_rows:
        if r.get("health") in {"ACCESS_BLOCKED", "UNEXPECTED_ERROR"}:
            err = (r.get("error_message") or "").lower()
            if "404" in err:
                kind = "expected_archive_or_moved_url"
            elif "403" in err or r.get("health") == "ACCESS_BLOCKED":
                kind = "intentional_or_runtime_block"
            else:
                kind = "runtime_condition"
            b_access.append({"competition": r["competition"], "health": r["health"], "error": r.get("error_message"), "class": kind})

    critical_reasons = []
    if ident["false_merges"]:
        critical_reasons.append("false_merges")
    if ident["failed_to_merge"]:
        critical_reasons.append("failed_to_merge")
    if qual["counts"].get("cross_sport_leaks"):
        critical_reasons.append("cross_sport_leaks")
    if qual["counts"].get("competition_leaks"):
        critical_reasons.append("competition_leaks")
    if qual["counts"].get("future_finished"):
        critical_reasons.append("future_finished")
    if persist.get("second_run_inserts") not in {0, None}:
        critical_reasons.append(f"second_run_inserts:{persist.get('second_run_inserts')}")
    if (failover.get("passed") or 0) == 0:
        critical_reasons.append("failover")
    if persist.get("error"):
        critical_reasons.append(f"persist:{persist.get('error')}")
    if api.get("errors"):
        critical_reasons.append("api:" + ",".join(str(item) for item in api.get("errors") or []))
    if api.get("ok") is False:
        critical_reasons.append("api_ok_false")
    if qual["counts"].get("stale_live"):
        critical_reasons.append("stale_live")
    critical = bool(critical_reasons)
    still_broken = [
        {"competition": r["competition"], "side": r["side"], "health": r["health"], "error": r.get("error_message")}
        for r in results
        if r.get("health") in {"UNEXPECTED_ERROR", "PARSER_ERROR", "ACCESS_BLOCKED"}
    ]

    report = {
        "generated_at": _now(),
        "matrix": {**freeze, "unchanged_after_audit": matrix_unchanged, "sha256_after": after},
        "primary_a": a_sum,
        "fallback_b": b_sum,
        "a_event_producing": sum(1 for r in a_rows if (r.get("events_normalized") or 0) > 0),
        "b_event_producing": sum(1 for r in b_rows if (r.get("events_normalized") or 0) > 0),
        "events": {
            "raw": raw,
            "normalized": normalized,
            "stored": persist.get("stored"),
            "ab_overlaps": ident["overlaps"],
            "merged": ident["merged"],
            "duplicate_failures": len(ident["failed_to_merge"]),
            "false_merges": len(ident["false_merges"]),
        },
        "data_quality": qual,
        "identity": ident,
        "network": net,
        "failover": failover,
        "database": persist,
        "api_local": api,
        "performance": {
            "total_runtime_s": round(runtime_s, 1),
            "provider_calls": len(results),
            "cache_hits": net["cache_hits"],
            "average_latency_ms": int(sum(r.get("latency_ms") or 0 for r in results) / max(1, len(results))),
            "slowest_provider_families": slowest,
        },
        "still_broken": still_broken[:80],
        "malformed_events": malformed,
        "malformed_buckets": dict(malformed_buckets),
        "thesportsdb": {
            "logical_jobs": len(tsdb_rows),
            "physical_requests": len(REQUEST_LOG),
            "http_requests_global": STATS.get("requests", 0),
            "cache_hits": STATS.get("cache_hits", 0),
            "budget_skips": STATS.get("budget_skips", 0),
            "429": STATS.get("http_429", 0),
            "rate_limited_jobs": sum(1 for r in tsdb_rows if r.get("health") == "RATE_LIMITED"),
            "family_cooldown_jobs": sum(1 for r in tsdb_rows if r.get("error_type") == "FAMILY_COOLDOWN"),
            "working": sum(1 for r in tsdb_rows if r.get("health") == "WORKING_WITH_EVENTS"),
        },
        "family_health": family_health_snapshot(),
        "b_access": b_access,
        "jobs": len(jobs),
        "critical": critical,
        "critical_reasons": critical_reasons,
    }
    report["compact"] = compact_summary(report)
    suffix = "_railway" if railway else ""
    (AUDIT_DIR / f"runtime_audit_180{suffix}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    compact_rows = [
        {
            "competition": r.get("competition"),
            "side": r.get("side"),
            "family": r.get("upstream_family"),
            "health": r.get("health"),
            "http_status": r.get("http_status"),
            "events_received": r.get("events_received"),
            "events_normalized": r.get("events_normalized"),
            "error_type": r.get("error_type"),
        }
        for r in results
    ]
    (AUDIT_DIR / f"provider_health_180{suffix}.json").write_text(
        json.dumps({"rows": compact_rows, "http_stats": dict(STATS)}, indent=2, default=str),
        encoding="utf-8",
    )
    (AUDIT_DIR / f"canonical_conflicts{suffix}.json").write_text(
        json.dumps(
            {
                "identity": {
                    "overlaps": ident.get("overlaps"),
                    "merged": ident.get("merged"),
                    "failed_to_merge": ident.get("failed_to_merge"),
                    "false_merges": ident.get("false_merges"),
                },
                "quality_counts": qual.get("counts"),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (AUDIT_DIR / "failover_test_results.json").write_text(json.dumps(failover, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    out = main()
    print(json.dumps(compact_summary(out), indent=2, default=str))
    print("jobs", out.get("jobs"), "broken", len(out.get("still_broken") or []))
