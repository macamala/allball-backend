"""Attach provider event IDs onto existing canonical keepers.

Reusable across PulseLive, Squiggle, CFL, Euroleague, OpenDota, PGA, and
other already-wired rich families. Does not create a second fixture for the
same match. Unmatched historical events may be ingested only when no keeper
exists and persist_missing is enabled for that family.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from collector.identity_events import IDENTITY_MERGE_THRESHOLD, identity_confidence
from collector.list_extra import store_list_extra
from collector.lock import lock_status
from collector.models import SportsCollectorJob, SportsEvent, SportsSource, SportsSourceCompetition
from collector.source_ids import families_with_ids, merge_family_ids
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

ATTACH_JOB = "provider-id-attach-v5"
MAX_INGEST_PER_FAMILY = 40
FAMILY_SPORT = {
    "pulselive": "rugby",
    "squiggle-afl": "australian-rules",
    "cfl-scoreboard-json": "canadian-football",
    "euroleague-live": "basketball",
    "opendota": "dota-2",
    "pga-graphql": "golf",
    "championdata-netball": "netball",
    "click-tt-remix": "table-tennis",
    "dataproject-web": "volleyball",
    "cricsheet": "cricket",
    "lolesports-json": "esports-lol",
    "ibu-web": "winter-sports",
    "fis-web": "winter-sports",
}
_YOUTH = ("u17", "u18", "u19", "u20", "u21", "u23", "youth", "junior")
_WOMEN = ("women", "womens", "woms")
_RESERVE = ("reserve", " ii", "2nd", "b team")


def _tokens(name: str) -> set:
    folded = " ".join(str(name or "").lower().replace("-", " ").split())
    marks = set()
    for item in _YOUTH:
        if item in folded:
            marks.add("youth")
    for item in _WOMEN:
        if item in folded:
            marks.add("women")
    for item in _RESERVE:
        if item in folded:
            marks.add("reserve")
    return marks


def _protected_conflict(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    l_home = ((left.get("home") or {}).get("name") or "") + " " + ((left.get("away") or {}).get("name") or "")
    r_home = ((right.get("home") or {}).get("name") or "") + " " + ((right.get("away") or {}).get("name") or "")
    return bool(_tokens(l_home) ^ _tokens(r_home))


def _date_only(value: Any) -> bool:
    text = str(value or "")
    if not text:
        return True
    if "T" not in text:
        return True
    clock = text.split("T", 1)[-1]
    return clock.startswith("00:00")


def event_view(row: SportsEvent) -> Dict[str, Any]:
    parts = load_json(row.participants_json, {}) or {}
    extra = load_json(row.extra_json, {}) or {}
    return {
        "sport": row.sport_id,
        "competition": row.competition_id,
        "competition_key": row.competition_id,
        "home": parts.get("home") or {},
        "away": parts.get("away") or {},
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "round": row.stage or extra.get("round"),
        "source_event_ids": families_with_ids(extra),
    }


def attach_family_id(row: SportsEvent, family: str, source_event_id: str, incoming: Optional[Dict[str, Any]] = None) -> bool:
    extra = load_json(row.extra_json, {}) or {}
    before = dict(families_with_ids(extra))
    extra["source_event_ids"] = merge_family_ids(
        extra.get("source_event_ids"),
        family=family,
        source_event_id=source_event_id,
    )
    extra["source_family"] = extra.get("source_family") or family
    changed = families_with_ids(extra) != before
    if incoming:
        if incoming.get("periods") and not extra.get("periods"):
            extra["periods"] = incoming.get("periods")
            changed = True
        detail = incoming.get("sport_detail") or ((incoming.get("extra") or {}).get("sport_detail") if isinstance(incoming.get("extra"), dict) else None)
        if isinstance(detail, dict) and detail:
            extra["sport_detail"] = {**(extra.get("sport_detail") or {}), **detail}
            changed = True
        if incoming.get("venue") and not row.venue:
            row.venue = incoming.get("venue")
            changed = True
    if not changed:
        return False
    row.extra_json = dump_json(extra)
    store_list_extra(row, extra)
    return True


def match_keepers(
    incoming: Dict[str, Any],
    rows: List[SportsEvent],
) -> Tuple[Optional[SportsEvent], int, int]:
    scored: List[Tuple[int, SportsEvent]] = []
    protected = 0
    date_candidates: List[SportsEvent] = []
    incoming_date = str(incoming.get("start_time") or "")[:10]
    for row in rows:
        view = event_view(row)
        if incoming.get("sport") and not view.get("sport"):
            view["sport"] = incoming.get("sport")
        if view.get("sport") and not incoming.get("sport"):
            incoming = {**incoming, "sport": view.get("sport")}
        if _protected_conflict(view, incoming):
            protected += 1
            continue
        score = identity_confidence(view, incoming)
        if score >= IDENTITY_MERGE_THRESHOLD:
            scored.append((score, row))
            continue
        if (
            incoming_date
            and str(view.get("start_time") or "")[:10] == incoming_date
        ):
            loose = dict(incoming)
            loose["start_time"] = view.get("start_time")
            if identity_confidence(view, loose) >= IDENTITY_MERGE_THRESHOLD:
                date_candidates.append(row)
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) > 1 and scored[1][0] >= IDENTITY_MERGE_THRESHOLD:
            return None, 2, protected
        return scored[0][1], 1, protected
    if len(date_candidates) == 1:
        return date_candidates[0], 1, protected
    if len(date_candidates) > 1:
        return None, 2, protected
    timed = []
    for row in rows:
        view = event_view(row)
        if incoming.get("sport") and not view.get("sport"):
            view["sport"] = incoming.get("sport")
        if view.get("sport") and not incoming.get("sport"):
            incoming = {**incoming, "sport": view.get("sport")}
        if _protected_conflict(view, incoming):
            continue
        if not view.get("start_time"):
            continue
        loose = dict(incoming)
        loose["start_time"] = view.get("start_time")
        if identity_confidence(view, loose) >= IDENTITY_MERGE_THRESHOLD:
            timed.append(row)
    if len(timed) == 1:
        return timed[0], 1, protected
    if len(timed) > 1:
        return None, 2, protected
    return None, 0, protected


def _family_key(incoming: Dict[str, Any]) -> Tuple[str, str]:
    ids = incoming.get("source_event_ids") or {}
    if isinstance(ids, dict) and ids:
        family, sid = next(iter(ids.items()))
        return str(family), str(sid)
    return str(incoming.get("source_family") or ""), str(incoming.get("source_event_id") or "")


def _ingest(db: Session, incoming: Dict[str, Any], source_id: str) -> bool:
    from collector.collect import _upsert_event
    from collector.match import match_event
    from collector.normalize import normalize_event

    source = db.query(SportsSource).filter_by(source_id=source_id).first()
    if source is None:
        return False
    competition_id = incoming.get("competition_key") or ""
    mapping = (
        db.query(SportsSourceCompetition)
        .filter_by(source_id=source.source_id, competition_id=competition_id)
        .first()
    )
    if mapping is None:
        return False
    sport_id = incoming.get("sport") or ""
    event = normalize_event(incoming, sport_id=sport_id, competition_id=competition_id)
    event["competition_key"] = competition_id
    existing = match_event(db, event, source_id=source.source_id)
    _upsert_event(db, incoming=event, source=source, mapping=mapping, existing=existing)
    return True


def crosswalk_family(
    db: Session,
    *,
    family: str,
    source_id: str,
    events: List[Dict[str, Any]],
    persist_missing: bool = False,
    hours: int = 24 * 900,
) -> Dict[str, int]:
    from sqlalchemy import or_

    bound = datetime.utcnow() - timedelta(hours=hours)
    comps = {str(row.get("competition_key") or "") for row in events if row.get("competition_key")}
    keepers = (
        db.query(SportsEvent)
        .filter(SportsEvent.canonical_event_id.is_(None))
        .filter(or_(SportsEvent.start_time >= bound, SportsEvent.start_time.is_(None)))
        .filter(SportsEvent.competition_id.in_(comps or ["__none__"]))
        .all()
    )
    by_comp: Dict[str, List[SportsEvent]] = {}
    for row in keepers:
        by_comp.setdefault(row.competition_id, []).append(row)
    stats = {
        "upstream_total": len(events),
        "upstream_eligible": 0,
        "attached": 0,
        "canonical_matched": 0,
        "already_had_id": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "ingested": 0,
        "protected_conflicts": 0,
    }
    ingested = 0
    for incoming in events:
        family_key, sid = _family_key(incoming)
        family_key = family_key or family
        incoming.setdefault("sport", FAMILY_SPORT.get(family) or incoming.get("sport"))
        if not sid:
            continue
        stats["upstream_eligible"] += 1
        competition_id = str(incoming.get("competition_key") or "")
        best, n_ok, protected = match_keepers(incoming, by_comp.get(competition_id) or [])
        stats["protected_conflicts"] += protected
        if n_ok >= 2:
            stats["ambiguous"] += 1
            continue
        if best is not None:
            stats["canonical_matched"] += 1
            if attach_family_id(best, family_key, sid, incoming=incoming):
                stats["attached"] += 1
            else:
                stats["already_had_id"] += 1
            continue
        stats["unmatched"] += 1
        if persist_missing and ingested < MAX_INGEST_PER_FAMILY:
            if _ingest(db, incoming, source_id):
                ingested += 1
                stats["ingested"] += 1
    db.flush()
    logger.info("provider_crosswalk family=%s %s", family, stats)
    return stats


def _load_family_events(family: str, getter=None) -> List[Dict[str, Any]]:
    from collector.adapters import FetchRequest

    events: List[Dict[str, Any]] = []
    if family == "pulselive":
        from collector.adapters_feeds import PULSELIVE_COMP_TOKENS, WorldRugbyAdapter
        from collector.http import fetch_url

        adapter = WorldRugbyAdapter(getter=getter) if getter else WorldRugbyAdapter()
        get = getter or fetch_url
        today = datetime.utcnow().date()
        start = (today - timedelta(days=120)).isoformat()
        end = (today + timedelta(days=14)).isoformat()
        events = []
        for page in range(0, 6):
            url = (
                "https://api.wr-rims-prod.pulselive.com/rugby/v3/match"
                f"?pageSize=100&page={page}&sport=mru&startDate={start}&endDate={end}"
            )
            result = get(url)
            payload = result.payload if result and result.ok else {}
            rows = (payload or {}).get("content") if isinstance(payload, dict) else []
            if not rows:
                break
            for row in rows:
                event = adapter._event(row, None)
                if not event:
                    continue
                name = str(event.get("competition") or "").lower()
                matched = None
                for cid, tokens in PULSELIVE_COMP_TOKENS.items():
                    if any(tok in name for tok in tokens):
                        matched = cid
                        break
                if not matched:
                    continue
                event["competition_key"] = matched
                events.append(event)
            if len(rows) < 100:
                break
        return events
    if family == "squiggle-afl":
        from collector.adapters_squiggle import SquiggleAflAdapter

        adapter = SquiggleAflAdapter(getter=getter) if getter else SquiggleAflAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="australia-afl"))
        logger.info(
            "squiggle_fetch status=%s ok=%s events=%s reason=%s empty=%s",
            result.http_status,
            result.ok,
            len(result.events or []),
            (result.parse_reason or "")[:400],
            (result.empty_reason or result.error or "")[:400],
        )
        return result.events or []
    if family == "cfl-scoreboard-json":
        from collector.adapters_ro56 import CflScoreboardAdapter

        adapter = CflScoreboardAdapter(getter=getter) if getter else CflScoreboardAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="cfl"))
        return result.events or []
    if family == "euroleague-live":
        from collector.adapters_feeds import EuroleagueLiveAdapter

        adapter = EuroleagueLiveAdapter(getter=getter) if getter else EuroleagueLiveAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="euroleague"))
        return result.events or []
    if family == "opendota":
        from collector.adapters_opendota import OpenDotaAdapter

        adapter = OpenDotaAdapter(getter=getter) if getter else OpenDotaAdapter()
        result = adapter.fetch(FetchRequest(capability="results", competition_id="professional"))
        return (result.events or [])[:80]
    if family == "pga-graphql":
        from collector.adapters_final18 import PgaGraphqlAdapter

        adapter = PgaGraphqlAdapter()
        result = adapter.fetch(FetchRequest(capability="results", competition_id="pga-tour"))
        tournaments = []
        seen = set()
        for row in result.events or []:
            ids = row.get("source_event_ids") or {}
            tid = str(ids.get("pga-graphql") or "")
            if not tid or tid in seen:
                continue
            away = ((row.get("away") or {}).get("name") or "").lower()
            if away != "field":
                continue
            seen.add(tid)
            tournaments.append(row)
        return tournaments[:20]
    if family == "championdata-netball":
        from collector.adapters_final18 import ChampionDataNetballAdapter

        adapter = ChampionDataNetballAdapter(getter=getter) if getter else ChampionDataNetballAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="ssn-australia"))
        return result.events or []
    if family == "click-tt-remix":
        from collector.adapters_final18 import ClickTtRemixAdapter

        adapter = ClickTtRemixAdapter(getter=getter) if getter else ClickTtRemixAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="germany-click-tt"))
        return result.events or []
    if family == "dataproject-web":
        from collector.adapters_dataproject import DataProjectWebAdapter

        adapter = DataProjectWebAdapter()
        for cid in ("italy-superlega", "plusliga"):
            result = adapter.fetch(FetchRequest(capability="results", competition_id=cid, sport_id="volleyball"))
            events.extend(result.events or [])
        return events
    if family == "cricsheet":
        from collector.adapters_cricsheet import CricsheetAdapter

        adapter = CricsheetAdapter()
        result = adapter.fetch(FetchRequest(capability="results", competition_id="t20-internationals", sport_id="cricket"))
        return (result.events or [])[:20]
    if family == "lolesports-json":
        from collector.adapters_ro56 import LolEsportsAdapter

        adapter = LolEsportsAdapter(getter=getter) if getter else LolEsportsAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="lol-world-championship"))
        return result.events or []
    if family == "ibu-web":
        from collector.adapters_final import IbuResultsAdapter

        adapter = IbuResultsAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="biathlon", sport_id="winter-sports"))
        return result.events or []
    if family == "fis-web":
        from collector.adapters_official import FisResultsAdapter

        adapter = FisResultsAdapter()
        result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="fis-disciplines", sport_id="winter-sports"))
        return result.events or []
    return []


FAMILY_JOBS = (
    ("pulselive", "world-rugby", False),
    ("squiggle-afl", "squiggle", False),
    ("cfl-scoreboard-json", "cfl-scoreboard", False),
    ("euroleague-live", "euroleague-live", False),
    ("opendota", "opendota", True),
    ("pga-graphql", "pga-graphql", True),
    ("championdata-netball", "championdata-netball", True),
    ("click-tt-remix", "click-tt-remix", True),
    ("dataproject-web", "dataproject-web", True),
    ("cricsheet", "cricsheet", True),
    ("lolesports-json", "lolesports", True),
    ("ibu-web", "ibu-web", True),
    ("fis-web", "fis-web", True),
)


def run_provider_id_attach(
    db: Session,
    *,
    getter=None,
    families: Optional[List[str]] = None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    totals: Dict[str, Any] = {"families": {}}
    wanted = set(families or [item[0] for item in FAMILY_JOBS])
    for family, source_id, persist_missing in FAMILY_JOBS:
        if family not in wanted:
            continue
        if heartbeat:
            heartbeat()
        try:
            events = _load_family_events(family, getter=getter)
        except Exception:
            logger.exception("provider_crosswalk load failed family=%s", family)
            totals["families"][family] = {"error": "load_failed"}
            continue
        if heartbeat:
            heartbeat()
        totals["families"][family] = crosswalk_family(
            db,
            family=family,
            source_id=source_id,
            events=events,
            persist_missing=persist_missing,
        )
        logger.info(
            "provider_id_attach family=%s upstream=%s with_id=%s matched=%s attached=%s unmatched=%s ambiguous=%s ingested=%s",
            family,
            totals["families"][family].get("upstream_total"),
            totals["families"][family].get("upstream_eligible"),
            totals["families"][family].get("canonical_matched"),
            totals["families"][family].get("attached"),
            totals["families"][family].get("unmatched"),
            totals["families"][family].get("ambiguous"),
            totals["families"][family].get("ingested"),
        )
    return totals


def run_provider_id_attach_if_due(
    db: Session,
    *,
    owner: Optional[str] = None,
    min_interval_hours: int = 4,
    getter=None,
    heartbeat: Optional[Callable[[], None]] = None,
) -> Optional[Dict[str, Any]]:
    status = lock_status(db)
    if not status.get("held"):
        logger.info("provider_id_attach skipped: no writer lease")
        return None
    if owner and status.get("owner_id") != owner:
        logger.info("provider_id_attach skipped: standby worker")
        return None
    job = db.get(SportsCollectorJob, ATTACH_JOB)
    if job is None:
        job = SportsCollectorJob(job_key=ATTACH_JOB)
        db.add(job)
        db.flush()
    if job.last_run_at and datetime.utcnow() - job.last_run_at < timedelta(hours=min_interval_hours):
        if (job.last_status or "") == "ok":
            return None
    if heartbeat:
        heartbeat()
    totals = run_provider_id_attach(db, getter=getter, heartbeat=heartbeat)
    job.last_run_at = datetime.utcnow()
    job.last_status = "ok"
    attached = sum(int((row or {}).get("attached") or 0) for row in totals.get("families", {}).values() if isinstance(row, dict))
    ingested = sum(int((row or {}).get("ingested") or 0) for row in totals.get("families", {}).values() if isinstance(row, dict))
    job.items_written = attached + ingested
    job.last_error = dump_json(totals)[:4000]
    db.commit()
    logger.info("provider_id_attach %s", totals)
    return totals
