"""Reconcile public identity for current FIFA global football rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from collector.adapters import FetchRequest
from collector.adapters_feeds import FifaFootballAdapter
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra
from collector.models import SportsEvent
from collector.util import dump_json, isoformat, load_json


def _source_id(extra: Dict[str, Any]) -> str:
    ids = extra.get("source_event_ids") if isinstance(extra.get("source_event_ids"), dict) else {}
    return str(
        extra.get("source_event_id")
        or ids.get("fifa-digital")
        or ids.get("fifa")
        or ""
    ).strip()


def reconcile_current_fifa_identity(db, *, days_back: int = 2, days_forward: int = 7) -> Dict[str, int]:
    result = FifaFootballAdapter().fetch(
        FetchRequest(
            capability="snapshot",
            sport_id="football",
            competition_id="fifa-connected-competitions",
        )
    )
    if not result.ok:
        return {"fetched": 0, "matched": 0, "changed": 0}

    by_id = {
        str(event.get("source_event_id") or ""): event
        for event in (result.events or [])
        if isinstance(event, dict) and event.get("source_event_id")
    }
    if not by_id:
        return {"fetched": 0, "matched": 0, "changed": 0}

    now = datetime.utcnow()
    rows = (
        db.query(SportsEvent)
        .filter(SportsEvent.primary_source_id == "fifa")
        .filter(SportsEvent.start_time >= now - timedelta(days=days_back))
        .filter(SportsEvent.start_time <= now + timedelta(days=days_forward))
        .all()
    )

    matched = 0
    changed = 0
    participant_logos_filled = 0
    for row in rows:
        extra = load_json(row.extra_json, {}) or {}
        source = by_id.get(_source_id(extra))
        if source is None:
            continue
        matched += 1
        participants = load_json(row.participants_json, {}) or {}
        participant_changed = False

        # FIFA match rows expose club/national-team artwork as Team.PictureUrl.
        # Fill blanks only, preserving any better artwork already supplied by
        # another trusted source.
        for source_key, target_keys in (
            ("home", ("home", "participant_a")),
            ("away", ("away", "participant_b")),
        ):
            source_side = source.get(source_key) if isinstance(source.get(source_key), dict) else {}
            source_logo = str(source_side.get("logo") or "").strip()
            source_id = str(source_side.get("id") or "").strip()
            source_country = str(source_side.get("country_id") or "").strip()
            for target_key in target_keys:
                side = participants.get(target_key)
                if not isinstance(side, dict):
                    continue
                merged = dict(side)
                if source_logo and not any(
                    merged.get(key)
                    for key in ("logo", "image", "crest", "badge", "team_logo", "teamLogo", "logo_url", "logoUrl")
                ):
                    merged["logo"] = source_logo
                    participant_logos_filled += 1
                    participant_changed = True
                if source_id and not merged.get("id"):
                    merged["id"] = source_id
                    participant_changed = True
                if source_country and not (
                    merged.get("country_id") or merged.get("country") or merged.get("nationality")
                ):
                    merged["country_id"] = source_country
                    participant_changed = True
                participants[target_key] = merged

        before = (
            extra.get("public_competition_key"),
            extra.get("source_competition_id"),
            extra.get("source_competition_name"),
            row.country_id,
        )
        public_key = str(source.get("competition_key") or "").strip()
        if public_key.startswith("football-"):
            extra["public_competition_key"] = public_key
        if source.get("source_competition_id"):
            extra["source_competition_id"] = str(source.get("source_competition_id"))
        if source.get("source_competition_name") or source.get("competition"):
            extra["source_competition_name"] = source.get("source_competition_name") or source.get("competition")
        if source.get("country_id"):
            row.country_id = str(source.get("country_id"))
        flags = list(extra.get("quality_flags") or [])
        flags = [flag for flag in flags if flag != "competition_attribution_mismatch"]
        extra["quality_flags"] = flags
        extra["fifa_identity_reconciled_at"] = isoformat(datetime.utcnow())
        after = (
            extra.get("public_competition_key"),
            extra.get("source_competition_id"),
            extra.get("source_competition_name"),
            row.country_id,
        )
        if participant_changed:
            row.participants_json = dump_json(participants)
            note_list_invalidation(
                db,
                sport=row.sport_id,
                competition=row.competition_id,
                start_time=row.start_time,
            )
        if after != before or participant_changed:
            changed += 1
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)

    return {
        "fetched": len(by_id),
        "matched": matched,
        "changed": changed,
        "participant_logos_filled": participant_logos_filled,
    }
