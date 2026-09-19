"""Observed live-capability inventory. Parser existence is not support."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from collector.family_caps import family_caps
from collector.models import (
    SportsCompetition,
    SportsCompetitionHealth,
    SportsEvent,
    SportsEventObservation,
    SportsSchedulerSlot,
    SportsSource,
    SportsSourceCompetition,
)
from collector.util import load_json
from sports_registry.sports import SPORTS

ROOT = Path(__file__).resolve().parent.parent


def _obs_flags(extra: Dict[str, Any], score: Dict[str, Any]) -> Dict[str, bool]:
    return {
        "live_score_available": score.get("home") is not None or score.get("away") is not None,
        "explicit_live_status": bool(extra.get("source_status")) and not extra.get("status_inferred"),
        "live_minute_or_clock": score.get("minute") is not None or score.get("clock") is not None,
        "periods_sets_innings": bool(extra.get("periods") or extra.get("maps") or extra.get("innings") or extra.get("current_set")),
        "incidents": bool(extra.get("incidents")),
        "lineups": bool(extra.get("lineups")),
        "stats": bool(extra.get("statistics")),
        "classification": bool(extra.get("classification") or extra.get("runners")),
        "standings": False,
        "source_event_id": bool(extra.get("source_event_ids")),
        "source_competition_id": bool(extra.get("source_competition_id")),
    }


def _class_for(flags: Dict[str, bool], access: str, family: str) -> str:
    if family_caps(family).get("production_status") == "ACCESS_BLOCKED" or access in {"ACCESS_BLOCKED", "blocked"}:
        return "E"
    score = bool(flags.get("live_score_available"))
    explicit = bool(flags.get("explicit_live_status"))
    clockish = bool(flags.get("live_minute_or_clock") or flags.get("periods_sets_innings"))
    if score and explicit and clockish:
        return "A"
    if score and explicit:
        return "B"
    if score:
        return "C"
    if family:
        return "D"
    return "UNKNOWN"


def build_inventory(db: Session) -> Dict[str, Any]:
    comps = {row.competition_id: row for row in db.query(SportsCompetition).all()}
    maps = db.query(SportsSourceCompetition).filter_by(enabled=True).all()
    sources = {row.source_id: row for row in db.query(SportsSource).all()}
    health = {row.competition_id: row for row in db.query(SportsCompetitionHealth).all()}
    slots = db.query(SportsSchedulerSlot).all()
    slot_by = defaultdict(list)
    for slot in slots:
        slot_by[(slot.competition_id, slot.family)].append(slot)
    events = db.query(SportsEvent).filter(SportsEvent.canonical_event_id.is_(None)).all()
    family_obs = defaultdict(lambda: defaultdict(list))
    for row in events:
        extra = load_json(row.extra_json, {}) or {}
        family = extra.get("source_family") or ""
        family_obs[row.competition_id][family].append((row, extra, load_json(row.score_json, {}) or {}))
    by_comp: Dict[str, List[SportsSourceCompetition]] = defaultdict(list)
    for mapping in maps:
        by_comp[mapping.competition_id].append(mapping)
    rows = []
    classes = Counter()
    for cid, mapping_rows in by_comp.items():
        mapping_rows = sorted(mapping_rows, key=lambda item: item.priority)
        comp = comps.get(cid)
        families = []
        for mapping in mapping_rows:
            source = sources.get(mapping.source_id)
            family = mapping.upstream_family or (source.upstream_family if source else None) or mapping.source_id
            observed = family_obs.get(cid, {}).get(family) or []
            flags = {
                "fixtures_available": False,
                "live_score_available": False,
                "explicit_live_status": False,
                "live_minute_or_clock": False,
                "periods_sets_innings": False,
                "incidents": False,
                "lineups": False,
                "stats": False,
                "classification": False,
                "standings": False,
                "source_event_id": bool(mapping.source_competition_id),
                "source_competition_id": bool(mapping.source_competition_id),
            }
            for _row, extra, score in observed:
                got = _obs_flags(extra, score)
                for key, value in got.items():
                    flags[key] = flags[key] or value
                flags["fixtures_available"] = True
            last_slot = None
            for slot in slot_by.get((cid, family), []):
                if last_slot is None or (slot.last_run_at and (last_slot.last_run_at is None or slot.last_run_at > last_slot.last_run_at)):
                    last_slot = slot
            access = "UNKNOWN"
            if family_caps(family).get("production_status") == "ACCESS_BLOCKED":
                access = "ACCESS_BLOCKED"
            elif last_slot and last_slot.last_status:
                access = last_slot.last_status
            live_class = _class_for(flags, access, family)
            families.append(
                {
                    "family": family,
                    "priority": mapping.priority,
                    "polling_class": mapping.polling_class,
                    "min_interval": family_caps(family).get("minimum_safe_interval"),
                    "last_run_at": last_slot.last_run_at.isoformat() + "Z" if last_slot and last_slot.last_run_at else None,
                    "last_status": last_slot.last_status if last_slot else None,
                    "access_state": access,
                    **flags,
                    "live_coverage_class": live_class,
                }
            )
        overall = "UNKNOWN"
        order = ["A", "B", "C", "D", "E", "UNKNOWN"]
        for grade in order:
            if any(item["live_coverage_class"] == grade for item in families):
                overall = grade
                break
        if not families:
            overall = "UNKNOWN"
        classes[overall] += 1
        rows.append(
            {
                "sport": comp.sport_id if comp else None,
                "competition_id": cid,
                "competition_name": comp.name if comp else cid,
                "primary_family": families[0]["family"] if families else None,
                "fallback_b": families[1]["family"] if len(families) > 1 else None,
                "fallback_c": families[2]["family"] if len(families) > 2 else None,
                "families": families,
                "live_coverage_class": overall,
                "last_success_at": health[cid].last_success_at.isoformat() + "Z" if cid in health and health[cid].last_success_at else None,
            }
        )
    sports_enabled = sorted({row["sport"] for row in rows if row["sport"]})
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_sports_registry": len(SPORTS),
        "sports_with_mapped_competitions": len(sports_enabled),
        "total_enabled_competitions": len(rows),
        "total_provider_families": len({item["family"] for row in rows for item in row["families"]}),
        "class_counts": dict(classes),
        "competitions": rows,
    }
    out = ROOT / "audit" / "live_capability_matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
