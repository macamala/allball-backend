"""Scoreboard completeness auditor: source → public canonical fixtures.

This is a diagnostic product test, not a provider-health check.
HTTP 200 / STRUCTURALLY_LIVE / adapter registration are not success.
"""

from __future__ import annotations

import json
import os
import hashlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from collector.duplicate_audit import audit_duplicates
from collector.matrix_guard import MATRIX_PATH, matrix_checksum
from collector.participant_alias import names_equivalent

ROOT = Path(__file__).resolve().parent.parent
PAIR_SCORE_SPORTS = {
    "football",
    "futsal",
    "rugby",
    "rugby-league",
    "basketball",
    "ice-hockey",
    "handball",
    "volleyball",
    "water-polo",
    "field-hockey",
    "australian-rules",
    "netball",
    "lacrosse",
    "american-football",
    "baseball",
    "tennis",
    "table-tennis",
    "badminton",
    "snooker",
    "darts",
    "boxing",
    "mma",
    "ea-sports-fc",
    "counter-strike",
    "league-of-legends",
    "dota-2",
    "valorant",
    "call-of-duty",
    "overwatch",
    "rocket-league",
}
BOARD_RESULT_SPORTS = {
    "golf",
    "motorsport",
    "horse-racing",
    "greyhound-racing",
    "harness-racing",
    "cycling",
    "athletics",
    "swimming",
    "winter-sports",
    "cricket",
}
FINISHED = {"finished", "ft", "final", "ended", "complete", "completed", "aet", "pen", "awarded"}
LIVE = {"live", "inplay", "in_play", "halftime", "ht", "break"}
SCHEDULED = {"scheduled", "not_started", "ns", "fixture", "pre_match"}


def load_matrix() -> Dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def competition_rows() -> List[Dict[str, Any]]:
    matrix = load_matrix()
    return list(matrix.get("competitions") or [])


def _filled(value: Any) -> bool:
    return value not in (None, "", [], {})


def pair_score(event: Dict[str, Any]) -> bool:
    score = event.get("score") or {}
    return _filled(score.get("home")) and _filled(score.get("away"))


def has_valid_result(event: Dict[str, Any]) -> bool:
    sport = str(event.get("sport") or "")
    if pair_score(event):
        return True
    if sport in BOARD_RESULT_SPORTS or sport not in PAIR_SCORE_SPORTS:
        if event.get("winner") or event.get("classification") or event.get("runners"):
            return True
        if event.get("leaderboard") or event.get("maps"):
            return True
        score = event.get("score") or {}
        if _filled(score.get("runs")) or _filled(score.get("placing")):
            return True
    return False


def canonical_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in FINISHED:
        return "finished"
    if raw in LIVE:
        return "live" if raw not in {"halftime", "ht", "break"} else "break"
    if raw in SCHEDULED:
        return "scheduled"
    if raw in {"postponed", "cancelled", "canceled", "delayed", "suspended", "abandoned", "walkover"}:
        return "cancelled" if raw == "canceled" else raw
    return raw or "unknown"


def local_day_bounds(day: str, tz_offset_hours: int) -> Tuple[str, str]:
    start = datetime.fromisoformat(day + "T00:00:00") - timedelta(hours=tz_offset_hours)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return (
        start.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def fetch_json(url: str, timeout: int = 40) -> Dict[str, Any]:
    req = Request(url, headers={"User-Agent": "NinkoSportsCompletenessAudit/1.0"})
    with urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_events(base: str, **params) -> List[Dict[str, Any]]:
    query = urlencode({k: v for k, v in params.items() if v not in (None, "")})
    payload = fetch_json(f"{base}/sports-data/events?{query}")
    return payload.get("events") or payload.get("matches") or []


def date_window(today: Optional[datetime] = None) -> List[str]:
    now = today or datetime.now(timezone.utc)
    days = [(now.date() + timedelta(days=offset)).isoformat() for offset in (-3, -2, -1, 0, 1, 2)]
    return days


def summarize_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter()
    ft_missing = []
    scheduled_missing_start = 0
    scheduled_with_start = 0
    live_missing_score = 0
    live_with_score = 0
    finished_missing = 0
    finished_with = 0
    for event in events:
        status = canonical_status(event.get("status"))
        counts[status] += 1
        counts["public"] += 1
        if status == "scheduled":
            if event.get("start_time"):
                scheduled_with_start += 1
            else:
                scheduled_missing_start += 1
        if status in {"live", "break"}:
            if pair_score(event) or has_valid_result(event):
                live_with_score += 1
            else:
                live_missing_score += 1
        if status == "finished":
            if has_valid_result(event):
                finished_with += 1
            else:
                finished_missing += 1
                if str(event.get("sport") or "") in PAIR_SCORE_SPORTS:
                    ft_missing.append(
                        {
                            "id": event.get("id"),
                            "sport": event.get("sport"),
                            "competition": event.get("competition_key") or event.get("competition"),
                            "home": (event.get("home") or {}).get("name"),
                            "away": (event.get("away") or {}).get("name"),
                            "start_time": event.get("start_time"),
                        }
                    )
    dupes = audit_duplicates(list(events))
    return {
        "public_event_count": counts["public"],
        "scheduled_with_start": scheduled_with_start,
        "scheduled_missing_start": scheduled_missing_start,
        "live_count": counts["live"] + counts["break"],
        "live_with_score": live_with_score,
        "live_missing_score": live_missing_score,
        "finished_count": counts["finished"],
        "finished_with_score": finished_with,
        "finished_missing_score": finished_missing,
        "postponed": counts["postponed"],
        "cancelled": counts["cancelled"],
        "delayed": counts["delayed"],
        "suspended": counts["suspended"],
        "duplicate_candidates": dupes["exact_count"] + dupes["probable_count"],
        "duplicate_audit": {
            "exact_count": dupes["exact_count"],
            "probable_count": dupes["probable_count"],
            "samples": (dupes["exact_duplicates"] + dupes["probable_duplicates"])[:8],
        },
        "ft_missing_samples": ft_missing[:12],
        "ft_missing_count": len(ft_missing),
        "status_counts": dict(counts),
    }


def competition_row_status(summary: Dict[str, Any], capability: str) -> str:
    if summary.get("ft_missing_count"):
        return "FT_MISSING_RESULT"
    if summary.get("duplicate_candidates"):
        return "DUPLICATE_CANDIDATES"
    if summary.get("live_missing_score") and capability in {"LIVE", "STRUCTURALLY_LIVE"}:
        return "LIVE_MISSING_SCORE"
    if summary.get("public_event_count") == 0:
        return "NO_PUBLIC_EVENTS_IN_WINDOW"
    return "OK"


def ratio(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return round(num / den, 4)


def freeze_state(base: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    health = fetch_json(f"{base}/health")
    status = fetch_json(f"{base}/sports-data/status")
    matrix = load_matrix()
    payload = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "source_matrix_checksum": matrix_checksum(),
        "frozen_competition_count": matrix.get("total_competitions"),
        "health": health,
        "public_status": status,
        "extra": extra or {},
    }
    return payload


def audit_production(
    base: str,
    *,
    tz_offset_hours: int = 10,
    days: Optional[List[str]] = None,
    fetch_upstream: bool = False,
) -> Dict[str, Any]:
    rows = competition_rows()
    days = days or date_window()
    freeze = freeze_state(base)
    by_comp: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    errors = []

    def one(row: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        cid = row["competition"]
        events: List[Dict[str, Any]] = []
        seen = set()
        err = None
        start = days[0]
        end = days[-1]
        date_from, _ = local_day_bounds(start, tz_offset_hours)
        _, date_to = local_day_bounds(end, tz_offset_hours)
        try:
            for event in fetch_events(base, competition=cid, date_from=date_from, date_to=date_to):
                eid = event.get("id")
                if eid in seen:
                    continue
                seen.add(eid)
                events.append(event)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
        return cid, events, err

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(one, row) for row in rows]
        for fut in as_completed(futs):
            cid, events, err = fut.result()
            by_comp[cid] = events
            if err:
                errors.append({"competition": cid, "error": err})

    try:
        live_payload = fetch_json(f"{base}/sports-data/live")
        for event in live_payload.get("events") or []:
            cid = str(event.get("competition_key") or event.get("competition") or "")
            if not cid:
                continue
            ids = {item.get("id") for item in by_comp.get(cid) or []}
            if event.get("id") not in ids:
                by_comp[cid].append(event)
    except Exception as exc:  # noqa: BLE001
        errors.append({"competition": "_live", "error": str(exc)})

    table = []
    totals = Counter()
    for row in rows:
        cid = row["competition"]
        events = by_comp.get(cid) or []
        summary = summarize_events(events)
        capability = str(row.get("capability") or row.get("live_capability") or "")
        if not capability:
            buckets = row.get("capability") if isinstance(row.get("capability"), str) else ""
            capability = buckets or str((row.get("primary") or {}).get("coverage") or "")
        status = competition_row_status(summary, capability)
        if summary["public_event_count"] == 0:
            status = "NO_PUBLIC_EVENTS_IN_WINDOW"
            if str(row.get("capability_class") or "") in {"RESULTS_ONLY", "RAPID_RESULT"}:
                status = "NO_PUBLIC_EVENTS_IN_WINDOW"
        rec = {
            "sport": row.get("sport"),
            "competition": cid,
            "primary_provider": (row.get("primary") or {}).get("family"),
            "fallback_providers": [
                item.get("family")
                for item in ([row.get("fallback")] if row.get("fallback") else [])
                + list(row.get("optional_additional") or [])
                if item
            ],
            "capability": row.get("capability") or row.get("live_capability") or row.get("bucket"),
            "dates_checked": days,
            "upstream_fixtures": None,
            "public_fixtures": summary["public_event_count"],
            "fixture_recall": None,
            "upstream_finished": None,
            "public_finished": summary["finished_count"],
            "finished_with_result": summary["finished_with_score"],
            "finished_result_completeness": ratio(summary["finished_with_score"], summary["finished_count"]),
            "upstream_live": None,
            "public_live": summary["live_count"],
            "live_with_score": summary["live_with_score"],
            "live_score_completeness": ratio(summary["live_with_score"], summary["live_count"]),
            "scheduled_time_completeness": ratio(
                summary["scheduled_with_start"],
                summary["scheduled_with_start"] + summary["scheduled_missing_start"],
            ),
            "duplicates": summary["duplicate_candidates"],
            "mapping_failures": 0,
            "ft_missing_result": summary["ft_missing_count"],
            "status": status,
            "root_cause": None
            if status in {"OK", "NO_PUBLIC_EVENTS_IN_WINDOW"}
            else status,
            "ft_missing_samples": summary["ft_missing_samples"],
            "duplicate_samples": summary["duplicate_audit"]["samples"],
        }
        if fetch_upstream:
            rec.update(_upstream_for(row, days, tz_offset_hours, events))
        table.append(rec)
        totals["competitions"] += 1
        totals["public_fixtures"] += summary["public_event_count"]
        totals["finished"] += summary["finished_count"]
        totals["finished_with_result"] += summary["finished_with_score"]
        totals["live"] += summary["live_count"]
        totals["live_with_score"] += summary["live_with_score"]
        totals["duplicates"] += summary["duplicate_candidates"]
        totals["ft_missing"] += summary["ft_missing_count"]
        totals[status] += 1

    return {
        "freeze": freeze,
        "dates_checked": days,
        "tz_offset_hours": tz_offset_hours,
        "errors": errors,
        "totals": dict(totals),
        "competitions": table,
        "fetch_upstream": fetch_upstream,
    }


_UPSTREAM_CACHE: Dict[str, Any] = {}


def _upstream_for(row: Dict[str, Any], days: List[str], tz_offset_hours: int, public_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Coalesced adapter fetch: one physical request per unique primary URL."""
    primary = row.get("primary") or {}
    family = str(primary.get("family") or "")
    adapter_key = str(primary.get("adapter") or "")
    url = str(primary.get("url") or "")
    if family.lower() in {"access_blocked"} or "ACCESS" in str(primary.get("status") or "").upper():
        return {
            "upstream_fixtures": None,
            "root_cause": "ACCESS_BLOCKED_SKIPPED",
        }
    cache_key = f"{adapter_key}|{url}|{days[0]}|{days[-1]}"
    if cache_key not in _UPSTREAM_CACHE:
        _UPSTREAM_CACHE[cache_key] = _fetch_adapter_events(adapter_key, family, row["competition"], row.get("sport"), url, days, tz_offset_hours)
    fetched = _UPSTREAM_CACHE[cache_key]
    events = [
        event
        for event in (fetched.get("events") or [])
        if str(event.get("competition_key") or event.get("competition") or row["competition"])
        in {row["competition"], str(event.get("competition") or "")}
    ]
    if not events:
        events = fetched.get("events") or []
    source_finished = [e for e in events if canonical_status(e.get("status")) == "finished"]
    source_live = [e for e in events if canonical_status(e.get("status")) in {"live", "break"}]
    source_finished_scored = [e for e in source_finished if has_valid_result(e)]
    public_finished = [e for e in public_events if canonical_status(e.get("status")) == "finished"]
    public_finished_scored = [e for e in public_finished if has_valid_result(e)]
    loss = None
    if fetched.get("error"):
        loss = f"upstream_fetch:{fetched.get('error')}"
    elif events and len(public_events) < len(events):
        loss = "public_short_of_upstream"
    elif source_finished_scored and len(public_finished_scored) < len(source_finished_scored):
        loss = "finished_result_lost_in_pipeline"
    return {
        "upstream_fixtures": len(events),
        "fixture_recall": ratio(len(public_events), len(events)) if events else None,
        "upstream_finished": len(source_finished),
        "finished_result_completeness": ratio(len(public_finished_scored), len(source_finished_scored))
        if source_finished_scored
        else ratio(len(public_finished_scored), len(public_finished)),
        "upstream_live": len(source_live),
        "upstream_error": fetched.get("error"),
        "upstream_http": fetched.get("http_status"),
        "root_cause": loss,
        "parsed_fixture_count": fetched.get("parsed_count"),
    }


def _fetch_adapter_events(
    adapter_key: str,
    family: str,
    competition_id: str,
    sport: str,
    url: str,
    days: List[str],
    tz_offset_hours: int,
) -> Dict[str, Any]:
    try:
        from collector.production import register_production_adapters
        from collector.adapters import FetchRequest, make_adapter

        register_production_adapters()
        adapter = make_adapter(adapter_key, f"audit:{family}:{competition_id}")
        date_from, _ = local_day_bounds(days[0], tz_offset_hours)
        _, date_to = local_day_bounds(days[-1], tz_offset_hours)
        result = adapter.fetch(
            FetchRequest(
                capability="snapshot",
                sport_id=sport,
                competition_id=competition_id,
                date_from=date_from,
                date_to=date_to,
                upstream_family=family,
                source_config={"url": url} if url else {},
            )
        )
        events = list(result.events or [])
        return {
            "ok": result.ok,
            "http_status": result.http_status,
            "events": events,
            "parsed_count": len(events),
            "restricted": result.restricted,
            "error": result.error,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "events": [], "parsed_count": 0, "error": str(exc)}


def write_artifact(payload: Dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_path = path.with_suffix(".csv")
    headers = [
        "sport",
        "competition",
        "primary_provider",
        "dates_checked",
        "upstream_fixtures",
        "public_fixtures",
        "fixture_recall",
        "upstream_finished",
        "public_finished",
        "finished_with_result",
        "finished_result_completeness",
        "upstream_live",
        "public_live",
        "live_with_score",
        "duplicates",
        "mapping_failures",
        "status",
        "root_cause",
    ]
    lines = [",".join(headers)]
    for row in payload.get("competitions") or []:
        values = []
        for key in headers:
            value = row.get(key)
            if isinstance(value, list):
                value = "|".join(str(item) for item in value if item)
            text = "" if value is None else str(value)
            values.append('"' + text.replace('"', "'") + '"')
        lines.append(",".join(values))
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    return path
