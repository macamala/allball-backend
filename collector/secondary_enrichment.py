"""Budgeted secondary enrichment. Background only. Disabled by default.

Match Centre and Score Centre reads must never scrape upstream.
OpenDota match detail and ESPN play-by-play stay off until a worker budget
is explicitly enabled after measuring calls/hour.
"""

from __future__ import annotations

import os
from typing import Any, Dict

# Never enable from a page view. Worker-only if NINKO_SECONDARY_ENRICH=1.
SECONDARY_ENABLED = os.getenv("NINKO_SECONDARY_ENRICH", "").strip() == "1"

CATALOG: Dict[str, Dict[str, Any]] = {
    "opendota_match_detail": {
        "status": "SECONDARY SOURCE VERIFIED — NOT ENABLED",
        "endpoint": "https://api.opendota.com/api/matches/{match_id}",
        "same_fetch": False,
        "cost": "1 request per match; payload often 100KB–1MB; OpenDota free 60 req/min",
        "expected_calls_if_enabled": "Dota list is ~100 pro matches/window. Polling live+recent only ≈ 20–80/hour if TTL 30m. Global every-match poll would exceed free budget.",
        "railway_impact": "Do not store full replay dumps. Cache map winners + duration only.",
        "when": "live | post-match (one final pass)",
    },
    "espn_play_by_play": {
        "status": "SECONDARY SOURCE VERIFIED — NOT ENABLED",
        "endpoint": "site.api.espn.com ... playbyplay (same family as scoreboard)",
        "same_fetch": False,
        "cost": "Extra request per live event; ESPN HTML already rate-sensitive",
        "note": "Same-fetch linescores/clock must be proven in production first.",
    },
    "sportscore_match_html": {
        "status": "UNKNOWN — NEEDS INVESTIGATION",
        "endpoint": "sportscore match page HTML (not widget JSON)",
        "same_fetch": False,
        "cost": "One HTML page per match; high if applied to all tennis lives",
        "note": "Widget JSON verified without set scores. HTML not enabled.",
    },
    "openliga_getbltable": {
        "status": "IMPLEMENTED — already collected as standings",
        "endpoint": "https://api.openligadb.de/getbltable/{shortcut}/{year}",
        "same_fetch": False,
        "cost": "Already on standings schedule; no extra live poll",
    },
}


def budget_summary() -> Dict[str, Any]:
    return {
        "enabled": SECONDARY_ENABLED,
        "match_centre_triggers_upstream": False,
        "catalog": CATALOG,
    }


def run_secondary_pass(_db) -> Dict[str, Any]:
    if not SECONDARY_ENABLED:
        return {"enabled": False, "fetched": 0}
    return {"enabled": True, "fetched": 0, "note": "No secondary fetchers registered."}
