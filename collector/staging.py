"""Controlled Railway staging commands. No frontend. No matrix mutation."""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from collector.family_catalog import FAMILY_URLS, JSON_ADAPTERS
from collector.family_plan import family_refresh_class
from collector.flags import flags_payload, scheduler_enabled, writes_enabled
from collector.http import STATS, USER_AGENT, begin_budget, end_budget, reset_http_stats
from collector.matrix_guard import MATRIX_PATH, assert_frozen_matrix, matrix_status

AUDIT_DIR_NAME = "audit"
MAX_REDIRECTS = 5


def _matrix_families() -> Dict[str, Dict[str, str]]:
    data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    comps = data.get("competitions") if isinstance(data, dict) else data
    out: Dict[str, Dict[str, str]] = {}
    for row in comps or []:
        for side in ("primary", "fallback"):
            mapping = row.get(side) or {}
            family = mapping.get("family") or mapping.get("source_family") or ""
            url = mapping.get("url") or FAMILY_URLS.get(family) or ""
            access = mapping.get("access") or mapping.get("source_type") or ""
            if family and url and family not in out:
                out[family] = {"url": url, "access": access}
    return out


def _parser_expectation(family: str, url: str, access: str, content_type: str) -> str:
    blob = f"{family} {url} {access} {content_type}".lower()
    if "wikipedia" in blob or "html" in blob or "text/html" in blob:
        return "HTML_EXPECTED"
    if family in JSON_ADAPTERS or "json" in blob or "api" in blob or "application/json" in blob:
        return "JSON_EXPECTED"
    if "xml" in blob:
        return "XML_EXPECTED"
    if content_type.startswith("text/html"):
        return "HTML_EXPECTED"
    if "json" in content_type:
        return "JSON_EXPECTED"
    return "BYTES_OK"


def _looks_html(body: bytes, content_type: str) -> bool:
    if "html" in (content_type or "").lower():
        return True
    head = body[:400].lower()
    return b"<html" in head or b"<!doctype html" in head


def _looks_json(body: bytes, content_type: str) -> Tuple[bool, Optional[str]]:
    if body[:1] in (b"{", b"["):
        try:
            json.loads(body.decode("utf-8"))
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    if "json" in (content_type or "").lower():
        try:
            json.loads(body.decode("utf-8"))
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    return False, None


def _safe_redirect(current: str, location: str) -> Optional[str]:
    if not location:
        return None
    nxt = urljoin(current, location)
    parsed = urlparse(nxt)
    if parsed.scheme not in {"http", "https"}:
        return None
    return nxt


def probe_url(url: str, timeout: int = 20) -> Dict[str, Any]:
    """Transport probe. Follows normal GET redirects. Does not require JSON."""
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
    current = url
    hops = 0
    started = time.perf_counter()
    ctx = ssl.create_default_context()
    last_status = 0
    content_type = ""
    body = b""
    final_url = url
    try:
        while hops <= MAX_REDIRECTS:
            req = urllib.request.Request(current, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    raw = resp.read()
                    encoding = (resp.headers.get("Content-Encoding") or "").lower()
                    if encoding == "gzip":
                        import gzip

                        raw = gzip.decompress(raw)
                    last_status = int(getattr(resp, "status", 200) or 200)
                    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    body = raw
                    final_url = resp.geturl() or current
                    break
            except urllib.error.HTTPError as exc:
                last_status = int(exc.code or 0)
                content_type = ((exc.headers.get("Content-Type") if exc.headers else "") or "").split(";")[0].strip().lower()
                body = exc.read() or b""
                if last_status in {301, 302, 303, 307, 308}:
                    loc = (exc.headers.get("Location") if exc.headers else None) or ""
                    nxt = _safe_redirect(current, loc)
                    hops += 1
                    if not nxt or hops > MAX_REDIRECTS:
                        break
                    current = nxt
                    continue
                break
        latency_ms = int((time.perf_counter() - started) * 1000)
        if last_status == 0:
            transport = "NETWORK_ERROR"
        elif last_status in {401, 403, 404, 410}:
            transport = "BLOCKED"
        elif last_status == 429:
            transport = "RATE_LIMITED"
        elif last_status >= 500:
            transport = "SERVER_ERROR"
        elif 200 <= last_status < 400:
            transport = "REACHABLE"
        else:
            transport = "HTTP_ERROR"
        return {
            "http_status": last_status,
            "content_type": content_type,
            "final_url": final_url,
            "redirects": hops,
            "latency_ms": latency_ms,
            "transport": transport,
            "body_prefix": body[:80],
            "body": body,
        }
    except Exception as exc:  # noqa: BLE001
        err = str(exc).lower()
        kind = "TIMEOUT" if "timed" in err or "timeout" in err else "NETWORK_ERROR"
        return {
            "http_status": 0,
            "content_type": "",
            "final_url": current,
            "redirects": hops,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "transport": kind,
            "error": str(exc),
            "body": b"",
            "body_prefix": b"",
        }


def smoke(max_families: int = 0) -> Dict[str, Any]:
    """One URL per provider family. No DB writes. Transport vs parser split."""
    assert_frozen_matrix()
    reset_http_stats()
    begin_budget(max_requests=250, max_seconds=900.0)
    families = _matrix_families()
    items = list(families.items())
    if max_families:
        items = items[:max_families]
    by_family: Dict[str, Dict[str, Any]] = {}
    blocked_families = set()
    for family, spec in items:
        kind = family_refresh_class(family)
        if family in blocked_families:
            by_family[family] = {"family": family, "skipped": "family_blocked", "class": kind}
            continue
        probe = probe_url(spec["url"])
        body = probe.pop("body", b"")
        content_type = probe.get("content_type") or ""
        expected = _parser_expectation(family, spec["url"], spec.get("access") or "", content_type)
        transport = probe.get("transport")
        parser_result = "SKIPPED"
        if transport == "REACHABLE":
            if expected == "HTML_EXPECTED":
                parser_result = "HTML_OK" if (_looks_html(body, content_type) or body or content_type.startswith("text/")) else "EMPTY"
            elif expected == "JSON_EXPECTED":
                ok, err = _looks_json(body, content_type)
                parser_result = "JSON_OK" if ok else "PARSER_ERROR"
            else:
                parser_result = "BODY_OK" if body or content_type else "EMPTY"
        bucket = "reachable"
        if transport == "BLOCKED":
            bucket = "blocked"
            blocked_families.add(family)
        elif transport == "RATE_LIMITED":
            bucket = "rate_limited"
            blocked_families.add(family)
        elif transport in {"NETWORK_ERROR", "TIMEOUT"}:
            bucket = "network_error"
        elif transport == "SERVER_ERROR":
            bucket = "server_error"
        elif parser_result == "PARSER_ERROR":
            bucket = "parser_error"
        elif parser_result == "EMPTY":
            bucket = "empty"
        row = {
            "family": family,
            "class": kind,
            "url_host": urlparse(spec["url"]).hostname,
            "http_status": probe.get("http_status"),
            "content_type": content_type,
            "transport": transport,
            "parser_expectation": expected,
            "parser_result": parser_result,
            "redirects": probe.get("redirects"),
            "latency_ms": probe.get("latency_ms"),
            "bucket": bucket,
            "error": probe.get("error"),
        }
        by_family[family] = row
    end_budget()
    grouped: Dict[str, List[str]] = defaultdict(list)
    for family, row in by_family.items():
        grouped[row.get("bucket") or "unknown"].append(family)
    report = {
        "matrix": matrix_status(),
        "flags": flags_payload(),
        "writes_enabled": writes_enabled(),
        "families_tested": len(by_family),
        "grouped_counts": {k: len(v) for k, v in grouped.items()},
        "grouped": {k: sorted(v) for k, v in grouped.items()},
        "families": by_family,
    }
    from pathlib import Path

    path = Path(AUDIT_DIR_NAME)
    path.mkdir(parents=True, exist_ok=True)
    (path / "railway_network_summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def dry_run() -> Dict[str, Any]:
    """Full 180 A/B from this network. Isolated sqlite. No production writes."""
    assert_frozen_matrix()
    if writes_enabled():
        raise RuntimeError("STOP: dry-run refuses to start while RESULTS_WRITE_ENABLED=true")
    from collector.audit.runtime_audit import compact_summary, main as audit_main

    report = audit_main(quiet=True, railway=True)
    print("SUMMARY", flush=True)
    compact = report.get("compact") or compact_summary(report)
    print(json.dumps(compact, indent=2, default=str), flush=True)
    return compact


def _side_ok(compact: Dict[str, Any]) -> Tuple[bool, List[str]]:
    fails = []
    matrix = compact
    if matrix.get("matrix_total") != 180:
        fails.append("matrix_total")
    from collector.matrix_guard import FROZEN_CHECKSUM

    if matrix.get("matrix_checksum") != FROZEN_CHECKSUM:
        fails.append("checksum")
    if matrix.get("jobs_completed") != 360:
        fails.append("jobs")
    ident = matrix.get("identity") or {}
    qual = matrix.get("quality") or {}
    if ident.get("duplicate_failures"):
        fails.append("duplicate_failures")
    if ident.get("false_merges"):
        fails.append("false_merges")
    if qual.get("cross_sport_leaks"):
        fails.append("cross_sport_leaks")
    if qual.get("competition_leaks"):
        fails.append("competition_leaks")
    if qual.get("future_finished"):
        fails.append("future_finished")
    if qual.get("stale_live"):
        fails.append("stale_live")
    a = matrix.get("A") or {}
    b = matrix.get("B") or {}
    if a.get("parser_error") or b.get("parser_error"):
        fails.append("parser_errors")
    return (not fails, fails)


def lock_probe() -> Dict[str, Any]:
    from database import SessionLocal, engine, ensure_schema
    from models import Base
    import collector.models  # noqa: F401
    from collector.lock import acquire_scheduler_lock, lock_status, release_scheduler_lock

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    db = SessionLocal()
    try:
        a = acquire_scheduler_lock(db, owner="worker-a-test", ttl_seconds=60)
        db.commit()
        b = acquire_scheduler_lock(db, owner="worker-b-test", ttl_seconds=60)
        db.commit()
        status = lock_status(db)
        release_scheduler_lock(db, owner="worker-a-test")
        db.commit()
        return {"worker_a_acquired": a, "worker_b_acquired": b, "lock": status}
    finally:
        db.close()


def lock_hold(seconds: int = 90) -> Dict[str, Any]:
    from database import SessionLocal, engine, ensure_schema
    from models import Base
    import collector.models  # noqa: F401
    from collector.lock import acquire_scheduler_lock, lock_status, postgres_try_advisory, postgres_advisory_unlock, release_scheduler_lock, owner_identity

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    db = SessionLocal()
    owner = owner_identity() + ":lock-hold"
    try:
        held = acquire_scheduler_lock(db, owner=owner, ttl_seconds=seconds + 30)
        db.commit()
        advisory = postgres_try_advisory(db)
        print(json.dumps({"lock_hold": held, "advisory": advisory, "owner": owner, "status": lock_status(db)}), flush=True)
        time.sleep(max(20, seconds))
        return {"held": held, "advisory": advisory, "status": lock_status(db)}
    finally:
        try:
            postgres_advisory_unlock(db)
            release_scheduler_lock(db, owner=owner)
            db.commit()
        except Exception:
            db.rollback()
        db.close()


def _constraint_audit(db) -> Dict[str, Any]:
    from collector.models import SportsEvent, SportsIdMap, SportsCompetition, SportsEntity
    from sqlalchemy import func

    event_ids = db.query(SportsEvent.event_id, func.count(SportsEvent.event_id)).group_by(SportsEvent.event_id).having(func.count(SportsEvent.event_id) > 1).all()
    src = (
        db.query(SportsIdMap.source_id, SportsIdMap.source_entity_id, SportsIdMap.entity_kind, func.count())
        .group_by(SportsIdMap.source_id, SportsIdMap.source_entity_id, SportsIdMap.entity_kind)
        .having(func.count() > 1)
        .all()
    )
    comps = {row.competition_id for row in db.query(SportsCompetition).all()}
    orphan_comp = db.query(SportsEvent).filter(~SportsEvent.competition_id.in_(comps)).count() if comps else 0
    ents = {row.entity_id for row in db.query(SportsEntity).all()}
    orphan_ent = 0
    if ents:
        orphan_ent = db.query(SportsEvent).filter(
            ((SportsEvent.home_entity_id.isnot(None)) & (~SportsEvent.home_entity_id.in_(ents)))
            | ((SportsEvent.away_entity_id.isnot(None)) & (~SportsEvent.away_entity_id.in_(ents)))
        ).count()
    fingerprints = (
        db.query(SportsEvent.fingerprint, func.count())
        .filter(SportsEvent.fingerprint.isnot(None))
        .group_by(SportsEvent.fingerprint)
        .having(func.count() > 1)
        .all()
    )
    return {
        "duplicate_event_pk": len(event_ids),
        "duplicate_source_ids": len(src),
        "orphan_competitions": orphan_comp,
        "orphan_entities": orphan_ent,
        "duplicate_fingerprints": len(fingerprints),
        "events": db.query(SportsEvent).count(),
    }


def write_once(pass_name: str = "1") -> Dict[str, Any]:
    from pathlib import Path

    from database import SessionLocal, engine, ensure_schema
    from models import Base
    import collector.models  # noqa: F401
    from collector.collect import run_cycle
    from collector.flags import collection_enabled
    from collector.models import SportsEvent, SportsEventObservation, SportsIngestionRun
    from collector.production import bootstrap_registry, register_production_adapters
    from collector.progress import peak_rss_mb, reset_progress, stage, stages
    from collector.sql_profile import attach_sql_profile, reset_sql_profile, snapshot
    from collector.validate_store import validate_store

    if not collection_enabled() or not writes_enabled():
        raise RuntimeError("STOP: write-once requires COLLECTION and WRITE enabled")
    if scheduler_enabled():
        raise RuntimeError("STOP: scheduler must stay off during manual writes")
    reset_progress()
    reset_sql_profile()
    attach_sql_profile(engine)
    stage("PROCESS START", pass_name=pass_name)
    register_production_adapters()
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    stage("SCHEMA CHECK")
    db = SessionLocal()
    audit = Path(AUDIT_DIR_NAME)
    audit.mkdir(parents=True, exist_ok=True)
    ids_path = audit / "write1_event_ids.json"
    try:
        stage("DB CONNECT")
        stage("REGISTRY BOOTSTRAP")
        bootstrap_registry(db)
        db.commit()
        before = {row.event_id for row in db.query(SportsEvent.event_id).all()}
        obs_before = db.query(SportsEventObservation).count()
        stage("COLLECTION START")
        summary = run_cycle(
            db,
            capabilities=["live_scores", "fixtures", "results"],
            force=True,
        )
        db.commit()
        stage("COMMIT")
        after_rows = db.query(SportsEvent).all()
        after = {row.event_id for row in after_rows}
        inserted_ids = sorted(after - before)
        run = db.query(SportsIngestionRun).order_by(SportsIngestionRun.id.desc()).first()
        constraints = _constraint_audit(db)
        validation = validate_store(db)
        stage("POST-WRITE VALIDATION", events=len(after))
        new_class: Dict[str, int] = {"GENUINELY_NEW_EVENT": 0, "DUPLICATE_IDENTITY_FAILURE": 0}
        if pass_name == "2":
            first_ids = set(json.loads(ids_path.read_text(encoding="utf-8"))) if ids_path.exists() else set(before)
            from collector.match import match_event
            from collector.util import load_json

            for event_id in inserted_ids:
                row = db.query(SportsEvent).filter_by(event_id=event_id).first()
                incoming = {
                    "sport": row.sport_id,
                    "competition_key": row.competition_id,
                    "season": row.season,
                    "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
                    "home": (load_json(row.participants_json, {}) or {}).get("home") or {"name": ""},
                    "away": (load_json(row.participants_json, {}) or {}).get("away") or {"name": ""},
                    "event_family": row.event_family,
                }
                existing = match_event(db, incoming, source_id=row.primary_source_id)
                if existing is not None and existing.event_id != row.event_id and existing.event_id in first_ids:
                    new_class["DUPLICATE_IDENTITY_FAILURE"] += 1
                else:
                    new_class["GENUINELY_NEW_EVENT"] += 1
        else:
            ids_path.write_text(json.dumps(sorted(after)), encoding="utf-8")
        sql = snapshot()
        payload = {
            "pass": pass_name,
            "collection_run_id": run.id if run else None,
            "summary": summary,
            "inserted": len(inserted_ids),
            "updated_estimate": int((run.events_written or 0) - len(inserted_ids)) if run else None,
            "rejected": run.rejected if run else 0,
            "observations": db.query(SportsEventObservation).count() - obs_before,
            "canonical_events": len(after),
            "constraints": constraints,
            "validation": validation,
            "new_insert_class": new_class if pass_name == "2" else None,
            "sql_profile": sql,
            "stages": [
                {
                    "stage": row.get("stage"),
                    "since_start_s": row.get("since_start_s"),
                    "rss_mb": row.get("rss_mb"),
                    "batch": row.get("batch"),
                    "written": row.get("written"),
                }
                for row in stages()
            ],
            "peak_rss_mb": peak_rss_mb(),
            "flags": flags_payload(),
        }
        stage("SUMMARY", inserted=len(inserted_ids), events=len(after))
        stage("PROCESS END")
        (audit / f"production_write_{pass_name}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(json.dumps(payload, indent=2, default=str), flush=True)
        return payload
    finally:
        db.close()


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "smoke"
    if cmd == "smoke":
        report = smoke()
        print(
            json.dumps(
                {
                    "families_tested": report["families_tested"],
                    "grouped_counts": report["grouped_counts"],
                    "matrix": report["matrix"],
                },
                indent=2,
            ),
            flush=True,
        )
        print("SMOKE_DONE", flush=True)
        return 0
    if cmd in {"dry-run", "dry_run"}:
        compact = dry_run()
        ok, fails = _side_ok(compact)
        print("GATE", "PASS" if ok else "FAIL", ",".join(fails) or "ok", flush=True)
        if compact.get("critical_reasons"):
            print("CRITICAL_REASONS", json.dumps(compact.get("critical_reasons")), flush=True)
        return 0 if ok else 3
    if cmd in {"lock-probe", "lock"}:
        print(json.dumps(lock_probe(), indent=2, default=str))
        return 0
    if cmd == "lock-hold":
        print(json.dumps(lock_hold(), indent=2, default=str))
        return 0
    if cmd == "write-once":
        write_once("1")
        return 0
    if cmd == "write-twice":
        write_once("2")
        return 0
    if cmd in {"validate-store", "validate"}:
        from database import SessionLocal, engine, ensure_schema
        from models import Base
        import collector.models  # noqa: F401
        from collector.validate_store import validate_store

        Base.metadata.create_all(bind=engine)
        ensure_schema(engine)
        db = SessionLocal()
        try:
            report = validate_store(db)
            print(json.dumps(report, indent=2, default=str), flush=True)
            return 0
        finally:
            db.close()
    if cmd == "schema-drift":
        from database import engine, ensure_schema
        from models import Base
        import collector.models  # noqa: F401
        from collector.schema_drift import schema_drift_report

        Base.metadata.create_all(bind=engine)
        ensure_schema(engine)
        print(json.dumps(schema_drift_report(engine), indent=2, default=str), flush=True)
        return 0
    if cmd == "write-lock-probe":
        from database import SessionLocal, engine, ensure_schema
        from models import Base
        import collector.models  # noqa: F401
        from collector.lock import acquire_write_lock, release_write_lock, write_lock_status

        Base.metadata.create_all(bind=engine)
        ensure_schema(engine)
        db_a = SessionLocal()
        db_b = SessionLocal()
        try:
            a = acquire_write_lock(db_a, owner="worker-a", ttl_seconds=120)
            db_a.commit()
            b = acquire_write_lock(db_b, owner="worker-b", ttl_seconds=120)
            payload = {"A": a, "B": b, "status": write_lock_status(db_a)}
            print(json.dumps(payload, indent=2, default=str), flush=True)
            release_write_lock(db_a, owner="worker-a")
            db_a.commit()
            return 0 if a and not b else 3
        finally:
            db_a.close()
            db_b.close()
    if cmd == "matrix":
        print(json.dumps(matrix_status(), indent=2))
        return 0
    print("usage: python -m collector.staging [smoke|dry-run|lock-probe|lock-hold|write-once|write-twice|validate-store|schema-drift|write-lock-probe|matrix]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
