"""Read-only audit and safe historical integrity backfill.

Does not delete rows. Quarantines public-ineligible events and repairs
high-confidence participant encoding/flag-glue.
"""

from __future__ import annotations

import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from collector.cache import cache_clear
from collector.maintenance_policy import automatic_promotion_blocked, sync_public_visibility
from collector.competition_identity import (
    COMPETITION_LABELS,
    MAPPING_OWNED_FAMILIES,
    OFFICIAL_PUBLIC_COMPETITIONS,
    label_matches_competition,
    resolve_competition,
)
from collector.enrichment import is_display_eligible, quality_flags_for_event
from collector.identity_events import identity_confidence
from collector.models import SportsCompetition, SportsEvent, SportsEventObservation, SportsSourceCompetition
from collector.matrix_guard import frozen_competition_ids
from collector.normalize import fingerprint
from collector.participant_text import clean_participant_name, fold_for_identity, repair_mojibake
from collector.source_ids import as_family_map
from collector.util import dump_json, load_json

HUB_FAMILIES = {"bbc-sport", "sportscore", "espn-html"}
PROTECTED_SOURCE_NATIVE_FOOTBALL_FAMILIES = {"fotmob", "fifa", "fifa-digital", "fifa-json"}


def _protected_source_native_football(item: Any, extra: Optional[Dict[str, Any]] = None) -> bool:
    """True only for football rows already positively revalidated from source-native identity.

    These rows may still be merged/corrected, but a later generic integrity pass must not
    hide the last public copy merely because canonical competition attribution is ambiguous.
    """
    if isinstance(item, SportsEvent):
        sport = str(item.sport_id or "").strip().lower()
        extra = extra if isinstance(extra, dict) else (load_json(item.extra_json, {}) or {})
    else:
        event = item if isinstance(item, dict) else {}
        sport = str(event.get("sport") or "").strip().lower()
        extra = extra if isinstance(extra, dict) else (event.get("extra") or {})
    family = str((extra or {}).get("source_family") or "").strip().lower()
    method = str((extra or {}).get("resolution_method") or "").strip().lower()
    return bool(
        sport == "football"
        and family in PROTECTED_SOURCE_NATIVE_FOOTBALL_FAMILIES
        and (
            (extra or {}).get("source_native_revalidated_at")
            or method == "source_native_revalidated"
        )
        and str((extra or {}).get("source_competition_name") or "").strip()
    )


def _sides(row: SportsEvent) -> Dict[str, Any]:
    parts = load_json(row.participants_json, {}) or {}
    return {
        "home": parts.get("home") or {},
        "away": parts.get("away") or {},
        "sport": row.sport_id,
        "score": load_json(row.score_json, {}) or {},
        "competition_key": row.competition_id,
        "start_time": row.start_time.isoformat() + "Z" if row.start_time else None,
        "event_id": row.event_id,
        "primary_source_id": row.primary_source_id,
    }


def _cluster_key(event: Dict[str, Any]) -> Optional[Tuple[str, str, str, str]]:
    home = fold_for_identity((event.get("home") or {}).get("name") or "")
    away = fold_for_identity((event.get("away") or {}).get("name") or "")
    start = str(event.get("start_time") or "")[:10]
    sport = event.get("sport") or ""
    if not home or not away or not start:
        return None
    pair = tuple(sorted((home, away)))
    return (sport, start, pair[0], pair[1])


def audit_population(db: Session) -> Dict[str, Any]:
    rows = db.query(SportsEvent).all()
    by_sport: Counter = Counter()
    by_comp: Counter = Counter()
    by_source: Counter = Counter()
    ineligible = 0
    suspicious_names = 0
    mojibake = 0
    missing_start = 0
    midnight = 0
    country_glue = 0
    clusters: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_sport[row.sport_id] += 1
        by_comp[row.competition_id] += 1
        extra = load_json(row.extra_json, {}) or {}
        by_source[extra.get("source_family") or row.primary_source_id or "unknown"] += 1
        event = _sides(row)
        flags = extra.get("quality_flags") or quality_flags_for_event(event)
        if extra.get("display_eligible") is False or not is_display_eligible({**event, "quality_flags": flags}):
            ineligible += 1
        names = [(event.get("home") or {}).get("name"), (event.get("away") or {}).get("name")]
        if any(quality_flags_for_event({"home": {"name": names[0]}, "away": {"name": names[1]}}) for _ in [0]):
            if quality_flags_for_event(event):
                suspicious_names += 1
        joined = " ".join(str(item or "") for item in names)
        if "Ã" in joined or "Â" in joined:
            mojibake += 1
        if any(item and (str(item).startswith(("GB ", "CZ ", "BR ")) or str(item).endswith(("GB", "CZ", "BR"))) for item in names):
            country_glue += 1
        if not row.start_time:
            missing_start += 1
        elif row.start_time.hour == 0 and row.start_time.minute == 0:
            midnight += 1
        key = _cluster_key(event)
        if key:
            clusters[key].append(event)
    duplicate_clusters = {str(key): value for key, value in clusters.items() if len(value) > 1}
    leak_clusters = [
        items
        for items in duplicate_clusters.values()
        if len({item.get("competition_key") for item in items}) > 1
    ]
    return {
        "total": len(rows),
        "by_sport": dict(by_sport),
        "by_competition_top": by_comp.most_common(25),
        "by_source_family": dict(by_source),
        "display_ineligible": ineligible,
        "suspicious_participant_names": suspicious_names,
        "mojibake": mojibake,
        "missing_start_time": missing_start,
        "midnight_00_00": midnight,
        "country_code_glue": country_glue,
        "duplicate_clusters": len(duplicate_clusters),
        "cross_competition_duplicate_clusters": len(leak_clusters),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def plan_backfill(db: Session) -> Dict[str, Any]:
    events = []
    query = db.query(SportsEvent).execution_options(stream_results=True).yield_per(300)
    for row in query:
        if automatic_promotion_blocked(row):
            continue
        event = _sides(row)
        extra = load_json(row.extra_json, {}) or {}
        event["extra"] = extra
        event["updated_at"] = row.updated_at
        events.append(event)
    db.expire_all()
    clusters: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        key = _cluster_key(event)
        if key:
            clusters[key].append(event)
    leak_score: Counter = Counter()
    for items in clusters.values():
        comps = {item.get("competition_key") for item in items}
        if len(items) > 1 and len(comps) > 1:
            for cid in comps:
                leak_score[cid] += 1
    quarantine: List[str] = []
    repair_names: List[str] = []
    conflicts: List[Dict[str, Any]] = []
    auto_merge: List[List[str]] = []
    for items in clusters.values():
        comps = {item.get("competition_key") for item in items}
        if len(items) > 1 and len(comps) > 1:
            def _label_supported(item: Dict[str, Any]) -> bool:
                extra = item.get("extra") or {}
                name = extra.get("source_competition_name") or extra.get("competition") or ""
                cid = str(item.get("competition_key") or "")
                return bool(name) and label_matches_competition(str(name), cid)

            supported = [item for item in items if _label_supported(item)]
            protected = [item for item in items if _protected_source_native_football(item)]
            keep_id = None
            if len(supported) == 1:
                keep_id = supported[0]["event_id"]
            elif protected:
                # Never let a generic cross-competition duplicate heuristic hide every
                # already revalidated source-native football copy. Keep one deterministic
                # public row; later canonical collapse can still merge a proven duplicate.
                chosen = sorted(
                    protected,
                    key=lambda item: (
                        item.get("updated_at") or datetime.min,
                        str(item.get("event_id") or ""),
                    ),
                    reverse=True,
                )[0]
                keep_id = chosen["event_id"]
            elif len(items) == 2:
                unique_leaks = {leak_score[cid] for cid in comps}
                if len(unique_leaks) != 1:
                    keep_comp = min(comps, key=lambda cid: (leak_score[cid], str(cid)))
                    keep_id = next(
                        item["event_id"] for item in items if item.get("competition_key") == keep_comp
                    )

            if keep_id is None:
                # Never quarantine every representation of a fixture. The old
                # equal-leak fallback could make a real match disappear until a
                # later repair pass happened to restore it. Prefer source-native
                # football evidence, otherwise keep the newest deterministic row.
                source_native = [
                    item
                    for item in items
                    if str((item.get("extra") or {}).get("source_family") or "").strip().lower()
                    in PROTECTED_SOURCE_NATIVE_FOOTBALL_FAMILIES
                ]
                pool = source_native or items
                chosen = sorted(
                    pool,
                    key=lambda item: (
                        1 if (item.get("extra") or {}).get("source_event_id") else 0,
                        1 if (item.get("extra") or {}).get("source_competition_id") else 0,
                        item.get("updated_at") or datetime.min,
                        str(item.get("event_id") or ""),
                    ),
                    reverse=True,
                )[0]
                keep_id = chosen["event_id"]

            for item in items:
                if item["event_id"] != keep_id:
                    quarantine.append(item["event_id"])
            scores = []
            for left in items:
                for right in items:
                    if left["event_id"] >= right["event_id"]:
                        continue
                    scores.append(identity_confidence(left, right))
            if scores and min(scores) >= 65:
                left, right = items[0], items[1]
                if (left.get("score") or {}).get("home") != (right.get("score") or {}).get("home"):
                    conflicts.append(
                        {
                            "ids": [left["event_id"], right["event_id"]],
                            "scores": [left.get("score"), right.get("score")],
                            "competitions": [left.get("competition_key"), right.get("competition_key")],
                            "category": "CONFLICTING_PROVIDER_DATA",
                        }
                    )
                elif min(scores) >= 90 and keep_id:
                    auto_merge.append([keep_id, left["event_id"] if left["event_id"] != keep_id else right["event_id"]])
        elif len(items) > 1:
            ordered = sorted(items, key=lambda item: item.get("updated_at") or datetime.min, reverse=True)
            for item in ordered[1:]:
                quarantine.append(item["event_id"])
            if len(ordered) >= 2:
                conf = identity_confidence(ordered[0], ordered[1])
                if conf >= 90:
                    auto_merge.append([ordered[0]["event_id"], ordered[1]["event_id"]])
    for event in events:
        home = (event.get("home") or {}).get("name") or ""
        away = (event.get("away") or {}).get("name") or ""
        if home != clean_participant_name(home) or away != clean_participant_name(away):
            repair_names.append(event["event_id"])
        extra = event.get("extra") or {}
        family = str(extra.get("source_family") or "")
        sources = extra.get("field_sources") or {}
        source_blob = str(sources)
        hub = family in HUB_FAMILIES or any(token in source_blob for token in HUB_FAMILIES)
        src_name = extra.get("source_competition_name") or extra.get("competition") or ""
        cid = str(event.get("competition_key") or "")
        if hub and cid in COMPETITION_LABELS:
            if src_name:
                if not label_matches_competition(str(src_name), cid):
                    quarantine.append(event["event_id"])
            else:
                quarantine.append(event["event_id"])
        if not is_display_eligible(event) and event["event_id"] not in quarantine:
            quarantine.append(event["event_id"])
    return {
        "quarantine": sorted(set(quarantine)),
        "repair_names": sorted(set(repair_names)),
        "conflicts": conflicts[:50],
        "auto_merge": auto_merge[:200],
        "quarantine_count": len(set(quarantine)),
        "repair_count": len(set(repair_names)),
        "conflict_count": len(conflicts),
        "auto_merge_count": len(auto_merge),
    }


def _mutate_row(row: SportsEvent, quarantine: set, repair: set) -> bool:
    extra = load_json(row.extra_json, {}) or {}
    parts = load_json(row.participants_json, {}) or {}
    dirty = False
    if row.event_id in repair:
        for key in ("home", "away", "participant_a", "participant_b"):
            side = parts.get(key)
            if isinstance(side, dict) and side.get("name"):
                cleaned = clean_participant_name(side["name"])
                if cleaned != side["name"]:
                    side["name"] = cleaned
                    dirty = True
        if dirty:
            row.participants_json = dump_json(parts)
    event = _sides(row)
    flags = quality_flags_for_event(event)
    eligible = (is_display_eligible(event) and row.event_id not in quarantine
                and not automatic_promotion_blocked(row, extra))
    if extra.get("quality_flags") != flags:
        extra["quality_flags"] = flags
        dirty = True
    if extra.get("display_eligible") is not eligible:
        extra["display_eligible"] = eligible
        dirty = True
    if row.event_id in quarantine:
        extra["quality_flags"] = list(dict.fromkeys((extra.get("quality_flags") or []) + ["duplicate_or_contaminated"]))
        extra["display_eligible"] = False
        dirty = True
    if getattr(row, "display_eligible", None) is not extra.get("display_eligible"):
        row.display_eligible = extra.get("display_eligible")
        dirty = True
    synced = sync_public_visibility(row, extra, extra.get("display_eligible", False))
    return dirty or synced


def _public_football_competition_ids(db: Session) -> set[str]:
    ids = set(frozen_competition_ids()) | set(OFFICIAL_PUBLIC_COMPETITIONS)
    native = (
        db.query(SportsSourceCompetition.competition_id)
        .join(
            SportsCompetition,
            SportsCompetition.competition_id == SportsSourceCompetition.competition_id,
        )
        .filter(
            SportsCompetition.sport_id == "football",
            SportsSourceCompetition.enabled.is_(True),
            SportsSourceCompetition.independence_status == "single-source-breadth",
        )
        .all()
    )
    ids.update(str(row[0]) for row in native if row and row[0])
    return ids


def restore_orphaned_duplicate_football(
    db: Session,
    *,
    days_back: int = 3,
    days_forward: int = 14,
) -> Dict[str, Any]:
    """Restore one trusted recent football row when duplicate quarantine hid the whole fixture.

    A duplicate is only safely hidden when another public canonical row represents
    the same participant pair/date cluster. This guard never creates an extra public
    copy when a keeper is already visible.
    """
    now = datetime.utcnow()
    rows = (
        db.query(SportsEvent)
        .filter(
            SportsEvent.sport_id == "football",
            SportsEvent.start_time >= now - timedelta(days=days_back),
            SportsEvent.start_time <= now + timedelta(days=days_forward),
        )
        .all()
    )
    clusters: Dict[Any, List[SportsEvent]] = defaultdict(list)
    for row in rows:
        key = _cluster_key(_sides(row))
        if key:
            clusters[key].append(row)

    public_competitions = _public_football_competition_ids(db)
    restored: List[str] = []
    for cluster_rows in clusters.values():
        def _extra(row: SportsEvent) -> Dict[str, Any]:
            return load_json(row.extra_json, {}) or {}

        public = [
            row
            for row in cluster_rows
            if not automatic_promotion_blocked(row)
            and row.display_eligible is not False
            and _extra(row).get("display_eligible") is not False
            and not row.canonical_event_id
            and not _extra(row).get("canonical_event_id")
            and (
                str(row.competition_id or "") in public_competitions
                or str(row.competition_id or "").startswith("football-")
            )
        ]
        if public:
            continue

        candidates = []
        for row in cluster_rows:
            extra = _extra(row)
            if automatic_promotion_blocked(row, extra):
                continue
            flags = {str(flag) for flag in (extra.get("quality_flags") or [])}
            family = str(extra.get("source_family") or "").strip().lower()
            method = str(extra.get("resolution_method") or "").strip().lower()
            if "duplicate_or_contaminated" not in flags:
                continue
            if family not in PROTECTED_SOURCE_NATIVE_FOOTBALL_FAMILIES:
                continue
            if method not in {
                "mapping_request_trusted",
                "source_native_revalidated",
                "source_native_preserved",
                "recovered_mapping_owned",
            } and not extra.get("source_native_revalidated_at"):
                continue
            event = _sides(row)
            if not is_display_eligible(event):
                continue
            candidates.append((row, extra))

        if not candidates:
            continue

        candidates.sort(
            key=lambda item: (
                1 if item[1].get("source_event_id") else 0,
                1 if item[1].get("source_competition_id") else 0,
                item[0].updated_at or datetime.min,
                str(item[0].event_id or ""),
            ),
            reverse=True,
        )
        row, extra = candidates[0]
        flags = [flag for flag in (extra.get("quality_flags") or []) if flag != "duplicate_or_contaminated"]
        extra["quality_flags"] = flags
        extra["display_eligible"] = True
        extra["quarantine_disposition"] = "RESTORED_ORPHAN_DUPLICATE"
        extra["orphan_duplicate_restored_at"] = datetime.utcnow().isoformat() + "Z"
        sync_public_visibility(row, extra, True)
        restored.append(row.event_id)

    if restored:
        db.flush()
        cache_clear(db, prefix="events:")
    return {
        "scanned_clusters": len(clusters),
        "restored": len(restored),
        "restored_ids": restored[:50],
    }


def apply_backfill(db: Session, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    plan = plan or plan_backfill(db)
    quarantine = set(plan.get("quarantine") or [])
    repair = set(plan.get("repair_names") or [])
    ids = list(dict.fromkeys([*quarantine, *repair]))
    changed = 0
    batch_size = 25
    for index in range(0, len(ids), batch_size):
        chunk = ids[index : index + batch_size]
        for attempt in range(6):
            try:
                rows = db.query(SportsEvent).filter(SportsEvent.event_id.in_(chunk)).all()
                for row in rows:
                    if _mutate_row(row, quarantine, repair):
                        changed += 1
                db.commit()
                break
            except OperationalError:
                db.rollback()
                time.sleep(0.35 * (attempt + 1))
    try:
        cache_clear(db)
        db.commit()
    except OperationalError:
        db.rollback()

    # Repair any pre-existing orphaned duplicate immediately after the batch.
    # Phase2 repeats the invariant later, but the public score board should not
    # wait through the long attribution/quarantine pass to regain a real fixture.
    orphan_guard = restore_orphaned_duplicate_football(db)
    if orphan_guard.get("restored"):
        db.commit()

    return {
        "updated": changed,
        "orphan_duplicate_guard": orphan_guard,
        **{k: plan[k] for k in ("quarantine_count", "repair_count", "conflict_count", "auto_merge_count") if k in plan},
    }


def _openliga_live_index() -> Tuple[Dict[str, Dict[str, str]], int]:
    from collector.http import fetch_url
    from collector.verified_coverage import OPENLIGADB_LEAGUES

    by_shortcut = {row["shortcut"]: row for row in OPENLIGADB_LEAGUES}
    index: Dict[str, Dict[str, str]] = {}
    requests = 0
    for spec in OPENLIGADB_LEAGUES:
        requests += 1
        result = fetch_url(f"https://api.openligadb.de/getmatchdata/{spec['shortcut']}")
        matches = result.payload if result.ok and isinstance(result.payload, list) else []
        for match in matches:
            if not isinstance(match, dict):
                continue
            match_id = str(match.get("matchID") or "")
            if not match_id:
                continue
            shortcut = str(match.get("leagueShortcut") or spec["shortcut"])
            canon = by_shortcut.get(shortcut) or spec
            index[match_id] = {
                "source_competition_id": shortcut,
                "source_competition_name": str(match.get("leagueName") or canon.get("name") or ""),
                "competition_id": canon["competition_id"],
            }
    return index, requests


def _fingerprint_for(row: SportsEvent, competition_id: str) -> str:
    parts = load_json(row.participants_json, {}) or {}
    start = row.start_time.isoformat() + "Z" if row.start_time else ""
    return fingerprint(
        {
            "event_family": row.event_family,
            "sport": row.sport_id,
            "competition_key": competition_id,
            "start_time": start,
            "home": parts.get("home") or {},
            "away": parts.get("away") or {},
            "participant_a": parts.get("participant_a") or {},
            "participant_b": parts.get("participant_b") or {},
            "series_id": row.series_id,
            "session_type": row.session_type,
            "country_id": row.country_id,
            "meeting_id": row.meeting_id,
            "venue": row.venue,
            "game_id": row.game_id,
        }
    )


def apply_competition_attribution(
    db: Session,
    *,
    live_index: Optional[Dict[str, Dict[str, str]]] = None,
    fetch_live: Optional[bool] = None,
) -> Dict[str, Any]:
    """Correct or quarantine public events whose stored source competition contradicts canonical."""
    if fetch_live is None:
        fetch_live = os.getenv("NINKO_SKIP_OPENLIGA_ATTRIBUTION") != "1"
    requests = 0
    if live_index is None and fetch_live:
        live_index, requests = _openliga_live_index()
    live_index = live_index or {}
    obs_by_event: Dict[str, List[str]] = defaultdict(list)
    if live_index:
        for observation in db.query(SportsEventObservation).all():
            if observation.event_id and observation.source_event_id:
                obs_by_event[observation.event_id].append(str(observation.source_event_id))
    public = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).all()
    kept = []
    for row in public:
        extra = load_json(row.extra_json, {}) or {}
        if automatic_promotion_blocked(row, extra):
            sync_public_visibility(row, extra, False)
            continue
        eligible = row.display_eligible is not False and extra.get("display_eligible") is not False
        recover = extra.get("competition_attribution") == "quarantined_unproven"
        family = str(extra.get("source_family") or "")
        id_families = set(as_family_map(extra.get("source_event_ids")).keys())
        owned = family in MAPPING_OWNED_FAMILIES or bool(id_families & MAPPING_OWNED_FAMILIES)
        owned_hidden = owned and (
            row.display_eligible is False or extra.get("display_eligible") is False
        )
        if eligible or recover or owned_hidden:
            kept.append(row)
    public = kept
    scanned = len(public)
    affected = 0
    corrected = 0
    quarantined = 0
    recovered = 0
    for row in public:
        extra = load_json(row.extra_json, {}) or {}
        source_id = extra.get("source_competition_id")
        source_name = extra.get("source_competition_name") or extra.get("competition") or ""
        family = str(extra.get("source_family") or "")
        id_families = set(as_family_map(extra.get("source_event_ids")).keys())
        for candidate in id_families:
            if candidate in MAPPING_OWNED_FAMILIES:
                family = candidate
                break
        for match_id in obs_by_event.get(row.event_id) or []:
            live = live_index.get(str(match_id))
            if live:
                source_id = live.get("source_competition_id") or source_id
                source_name = live.get("source_competition_name") or source_name
                extra["source_competition_id"] = source_id
                extra["source_competition_name"] = source_name
                break
        resolved = resolve_competition(
            mapping_competition_id=str(row.competition_id or ""),
            source_competition_id=str(source_id or "") or None,
            source_competition_name=str(source_name or ""),
            source_family=family,
            sport_id=str(row.sport_id or ""),
        )
        if resolved.get("accepted"):
            if row.display_eligible is False or extra.get("competition_attribution") == "quarantined_unproven":
                flags = [flag for flag in (extra.get("quality_flags") or []) if flag != "competition_attribution_mismatch"]
                extra["quality_flags"] = flags
                extra["display_eligible"] = True
                extra["competition_attribution"] = "recovered_mapping_owned"
                extra["resolution_method"] = resolved.get("resolution_method")
                extra["resolution_confidence"] = resolved.get("resolution_confidence")
                row.display_eligible = True
                sync_public_visibility(row, extra, extra.get("display_eligible", row.display_eligible is not False))
                recovered += 1
            continue
        affected += 1
        suggested = resolved.get("suggested_competition_id")
        extra["resolution_method"] = resolved.get("resolution_method")
        extra["resolution_confidence"] = resolved.get("resolution_confidence")
        extra["source_competition_id"] = resolved.get("source_competition_id") or extra.get("source_competition_id")
        extra["source_competition_name"] = resolved.get("source_competition_name") or extra.get("source_competition_name")
        if suggested:
            extra["canonical_competition_id"] = suggested
            extra["competition_attribution"] = "corrected_from_source"
            new_fp = _fingerprint_for(row, suggested)
            existing = db.query(SportsEvent).filter_by(fingerprint=new_fp).first()
            if existing and existing.event_id != row.event_id:
                from collector.canonical_collapse import _collapse_pair

                extra["display_eligible"] = False
                sync_public_visibility(row, extra, extra.get("display_eligible", row.display_eligible is not False))
                db.flush()
                if _collapse_pair(db, existing.event_id, row.event_id):
                    corrected += 1
                else:
                    row.display_eligible = False
                    quarantined += 1
                continue
            row.competition_id = suggested
            row.fingerprint = new_fp
            extra["display_eligible"] = True
            row.display_eligible = True
            sync_public_visibility(row, extra, extra.get("display_eligible", row.display_eligible is not False))
            corrected += 1
            continue
        if _protected_source_native_football(row, extra):
            # Source-native football was already positively revalidated from the
            # provider's own competition identity. Preserve public visibility if
            # generic canonical attribution cannot prove a safer remap.
            flags = [
                flag
                for flag in (extra.get("quality_flags") or [])
                if flag not in {"competition_attribution_mismatch", "duplicate_or_contaminated"}
            ]
            extra["quality_flags"] = flags
            extra["display_eligible"] = True
            extra["competition_attribution"] = "source_native_preserved"
            sync_public_visibility(row, extra, extra.get("display_eligible", row.display_eligible is not False))
            row.display_eligible = True
            recovered += 1
            continue
        extra["display_eligible"] = False
        extra["competition_attribution"] = "quarantined_unproven"
        flags = list(extra.get("quality_flags") or [])
        if "competition_attribution_mismatch" not in flags:
            flags.append("competition_attribution_mismatch")
        extra["quality_flags"] = flags
        sync_public_visibility(row, extra, extra.get("display_eligible", row.display_eligible is not False))
        row.display_eligible = False
        quarantined += 1
    try:
        db.commit()
    except OperationalError:
        db.rollback()
        time.sleep(0.4)
        db.commit()
    cache_clear(db)
    try:
        db.commit()
    except OperationalError:
        db.rollback()
    return {
        "scanned": scanned,
        "affected": affected,
        "corrected": corrected,
        "quarantined": quarantined,
        "recovered": recovered,
        "openliga_requests": requests,
        "recrawl_request_impact": (
            f"{requests} OpenLigaDB getmatchdata requests (one per mapped shortcut). "
            "No other extra upstream requests."
        ),
    }


def _side_name(side: Any) -> str:
    if isinstance(side, dict):
        return str(side.get("name") or "").strip()
    return str(side or "").strip()


def audit_event_detail_consistency(event: Dict[str, Any], *, route_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Flag contradictions. Does not repair."""
    from collector.wta_orientation import tennis_sets_agree_with_match_score

    flags: List[Dict[str, Any]] = []
    event_id = str(event.get("id") or event.get("event_id") or "")
    if route_id and event_id and route_id != event_id:
        flags.append({"class": "route_id_mismatch", "route_id": route_id, "event_id": event_id})
    home = _side_name(event.get("home"))
    away = _side_name(event.get("away"))
    pa = _side_name(event.get("participant_a"))
    pb = _side_name(event.get("participant_b"))
    if pa and home and pa != home:
        flags.append({"class": "participant_a_home_mismatch", "home": home, "participant_a": pa, "event_id": event_id})
    if pb and away and pb != away:
        flags.append({"class": "participant_b_away_mismatch", "away": away, "participant_b": pb, "event_id": event_id})
    score = event.get("score") if isinstance(event.get("score"), dict) else {}
    periods = event.get("periods")
    sport = str(event.get("sport") or event.get("sport_id") or "")
    if sport == "tennis" and periods and not tennis_sets_agree_with_match_score(score, periods):
        flags.append(
            {
                "class": "tennis_score_period_orientation",
                "event_id": event_id,
                "home": home,
                "away": away,
                "score": score,
                "periods": periods,
            }
        )
    incidents = event.get("incidents") or []
    if isinstance(incidents, list) and incidents and score.get("home") not in (None, "") and score.get("away") not in (None, ""):
        last = None
        for item in incidents:
            if isinstance(item, dict) and isinstance(item.get("score_after"), dict):
                last = item.get("score_after")
        if last and (last.get("home"), last.get("away")) != (score.get("home"), score.get("away")):
            flags.append(
                {
                    "class": "incident_score_after_mismatch",
                    "event_id": event_id,
                    "score": score,
                    "score_after": last,
                }
            )
    competition = event.get("competition_key") or event.get("competition") or ""
    if event.get("canonical_competition_id") and event.get("canonical_competition_id") != competition:
        flags.append(
            {
                "class": "competition_mismatch",
                "event_id": event_id,
                "competition": competition,
                "canonical_competition_id": event.get("canonical_competition_id"),
            }
        )
    for key in ("classification", "runners", "leaderboard"):
        rows = event.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("event_id") and row.get("event_id") != event_id:
                    flags.append({"class": f"{key}_wrong_event", "event_id": event_id, "row_event_id": row.get("event_id")})
                    break
    return flags
