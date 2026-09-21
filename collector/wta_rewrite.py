"""Apply official WTA result_type (W/O, retired) onto existing canonical rows."""

from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from collector.adapters import FetchRequest
from collector.adapters_wta import WtaJsonAdapter
from collector.cache import note_list_invalidation
from collector.list_extra import store_list_extra
from collector.match import match_event
from collector.models import SportsEvent
from collector.tennis_score import apply_tennis_match_score
from collector.util import dump_json, load_json

logger = logging.getLogger(__name__)

TARGET_TYPES = {"walkover", "retired", "retirement", "abandoned"}


def rewrite_wta_result_types(db: Session) -> Dict[str, Any]:
    adapter = WtaJsonAdapter()
    result = adapter.fetch(
        FetchRequest(
            competition_id="wta-tour",
            capability="results",
            source_config={"max_match_fetches": 80},
        )
    )
    events = result.events if result.ok else []
    applied = scanned = 0
    for incoming in events:
        if str(incoming.get("result_type") or "").lower() not in TARGET_TYPES:
            continue
        scanned += 1
        payload = dict(incoming)
        payload["sport"] = "tennis"
        payload["competition"] = "wta-tour"
        payload["competition_key"] = "wta-tour"
        row = match_event(db, payload, source_id="wta-json")
        if row is None:
            continue
        extra = load_json(row.extra_json, {}) or {}
        extra["result_type"] = incoming.get("result_type")
        extra["walkover"] = bool(incoming.get("walkover") or incoming.get("result_type") == "walkover")
        scored = apply_tennis_match_score({**payload, **extra, "score": incoming.get("score") or {}})
        if scored.get("score") is not None:
            row.score_json = dump_json(scored.get("score") or {})
        extra["result_type"] = scored.get("result_type") or extra["result_type"]
        row.status = incoming.get("status") or row.status or "finished"
        row.live = False
        row.extra_json = dump_json(extra)
        store_list_extra(row, extra)
        note_list_invalidation(
            db,
            sport="tennis",
            competition="wta-tour",
            start_time=row.start_time,
            scoreboard_visible=True,
        )
        applied += 1
    db.flush()
    logger.info("wta_result_rewrite scanned=%s applied=%s", scanned, applied)
    return {"scanned": scanned, "applied": applied, "fetched": len(events)}
