"""Jeff Sackmann tennis CSV family (sackmann-tennis)."""

from __future__ import annotations

import csv
import io
from typing import Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_text, fetch_url

ATP_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
WTA_URL = "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_{year}.csv"
ATP_MEDIA = "https://media.githubusercontent.com/media/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
WTA_MEDIA = "https://media.githubusercontent.com/media/JeffSackmann/tennis_wta/master/wta_matches_{year}.csv"
ATP_LIST = "https://api.github.com/repos/JeffSackmann/tennis_atp/contents/?ref=master"
WTA_LIST = "https://api.github.com/repos/JeffSackmann/tennis_wta/contents/?ref=master"


def parse_sackmann_csv(text: str, competition_id: str = "") -> List[Dict]:
    events = []
    handle = io.StringIO(text or "")
    reader = csv.DictReader(handle)
    for index, row in enumerate(reader):
        winner = (row.get("winner_name") or "").strip()
        loser = (row.get("loser_name") or "").strip()
        if not winner or not loser:
            continue
        date = str(row.get("tourney_date") or "")
        start = None
        if len(date) == 8 and date.isdigit():
            start = f"{date[0:4]}-{date[4:6]}-{date[6:8]}T00:00:00Z"
        events.append(
            {
                "id": row.get("match_num") or f"{winner}-{loser}-{index}",
                "home": {"name": winner},
                "away": {"name": loser},
                "status": "finished",
                "start_time": start,
                "competition": row.get("tourney_name") or competition_id,
                "round": row.get("round"),
                "score": {"home": None, "away": None},
            }
        )
        if len(events) >= 80:
            break
    return events


class SackmannTennisAdapter:
    adapter_key = "sackmann-csv"

    def __init__(self, source_id: str = "sackmann-tennis", text_getter=None, getter=None):
        self.source_id = source_id
        self._get_text = text_getter or fetch_text
        self._get = getter or fetch_url

    def health_check(self, request: FetchRequest) -> FetchResult:
        return self.fetch(request)

    def fetch(self, request: FetchRequest) -> FetchResult:
        config = request.source_config or {}
        configured = (config.get("url") or "").strip()
        years = [2026, 2025, 2024, 2023, 2022]
        urls = []
        if configured:
            urls.append(configured)
        template = WTA_URL if "wta" in (request.competition_id or "") else ATP_URL
        media = WTA_MEDIA if "wta" in (request.competition_id or "") else ATP_MEDIA
        urls.extend(template.format(year=year) for year in years)
        urls.extend(media.format(year=year) for year in years)
        last = FetchResult(ok=False, http_status=0, error="no sackmann csv", classification="CONFIG_MISSING")
        tried = list(dict.fromkeys(urls))
        for url in tried:
            result = self._get_text(url)
            last = result
            if not result.ok:
                continue
            text = result.payload if isinstance(result.payload, str) else ""
            header = text.splitlines()[0] if text else ""
            if "winner_name" not in header:
                continue
            events = parse_sackmann_csv(text, request.competition_id or "")
            return FetchResult(
                ok=True,
                http_status=result.http_status or 200,
                events=events,
                empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
            )
        listing = ATP_LIST if "wta" not in (request.competition_id or "") else WTA_LIST
        listed = self._get(listing)
        if listed.ok and isinstance(listed.payload, list):
            names = [
                row.get("download_url")
                for row in listed.payload
                if isinstance(row, dict)
                and str(row.get("name") or "").endswith(".csv")
                and "matches" in str(row.get("name") or "")
            ]
            for url in names:
                if not url or url in tried:
                    continue
                result = self._get_text(url)
                last = result
                if not result.ok:
                    continue
                text = result.payload if isinstance(result.payload, str) else ""
                header = text.splitlines()[0] if text else ""
                if "winner_name" not in header:
                    continue
                events = parse_sackmann_csv(text, request.competition_id or "")
                return FetchResult(
                    ok=True,
                    http_status=result.http_status or 200,
                    events=events,
                    empty_reason=None if events else "SOURCE_HEALTHY_NO_EVENTS",
                )
        if last.http_status in {404, 410}:
            last.classification = "SOURCE_CHANGED"
        return last
