"""Audit public canonical events for geography and identity integrity."""

from __future__ import annotations

import json
import os
import urllib.request
from collections import Counter

from collector.competition_presentation import SPORT_GEOGRAPHY_BLOCKLIST, metadata_for
from collector.matrix_guard import frozen_competition_ids
from collector.duplicate_audit import audit_duplicates
from collector.participant_text import clean_participant_name

SPORT_PREFIX_RE = __import__("re").compile(r"^(US|GB|FR|DE|IT|ES|BR|AR|NL|PT|BE)\s+")


def inspect_events(events):
    frozen = frozen_competition_ids()
    counts = Counter()
    counts["events_inspected"] = len(events)
    remaining = []
    for event in events:
        counts["events_inspected"]  # noqa: B018
        key = str(event.get("competition_key") or event.get("competition") or "")
        sport = str(event.get("sport") or "")
        geo = str(event.get("geography_label") or "").strip()
        meta = metadata_for(key, sport)
        if not geo:
            counts["missing_geography"] += 1
            remaining.append(("missing_geography", key, event.get("id")))
        folded = geo.lower().replace("-", " ")
        if folded in SPORT_GEOGRAPHY_BLOCKLIST or folded == sport.replace("-", " "):
            counts["sport_as_geography"] += 1
            remaining.append(("sport_as_geography", key, geo, event.get("id")))
        if key and key not in frozen:
            counts["outside_registry"] += 1
            remaining.append(("outside_registry", key, event.get("id")))
        if not key or key == "unknown":
            counts["unknown_competition"] += 1
        if meta.get("geography_label") and geo and meta["geography_label"] != geo:
            counts["competition_geography_conflict"] += 1
        for side in (event.get("home"), event.get("away")):
            name = ""
            if isinstance(side, dict):
                name = side.get("display_name") or side.get("name") or ""
            else:
                name = str(side or "")
            if not name:
                counts["missing_participant_names"] += 1
            cleaned = clean_participant_name(
                name,
                sport=sport,
                competition_country=event.get("country_id") or meta.get("country_code"),
            )
            if SPORT_PREFIX_RE.match(str(name or "").strip()):
                if cleaned != name:
                    counts["provider_prefix_leakage"] += 1
                    remaining.append(("prefix", name, event.get("id")))
                elif name.startswith("US ") and sport in {
                    "baseball",
                    "basketball",
                    "american-football",
                    "ice-hockey",
                }:
                    counts["provider_prefix_leakage"] += 1
        seen = event.get("id")
        if not seen:
            counts["missing_ids"] += 1
    return dict(counts), remaining[:40]


def fetch_production(url: str):
    with urllib.request.urlopen(url, timeout=40) as res:
        return json.loads(res.read().decode("utf-8"))


if __name__ == "__main__":
    base = os.environ.get("NINKO_AUDIT_API", "https://allball-backend-production.up.railway.app")
    payload = fetch_production(f"{base}/sports-data/events")
    events = payload.get("events") or payload.get("matches") or []
    counts, samples = inspect_events(events)
    duplicates = audit_duplicates(events)
    print(
        json.dumps(
            {"counts": counts, "samples": samples, "duplicates": duplicates, "connected": payload.get("connected")},
            indent=2,
        )
    )
