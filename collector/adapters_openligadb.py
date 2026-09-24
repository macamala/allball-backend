"""OpenLigaDB adapter. ODbL community results for verified current German leagues."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from collector.adapters import FetchRequest, FetchResult
from collector.http import fetch_url
from collector.verified_coverage import OPENLIGADB_LEAGUES
from collector.enrichment import incidents_from_openliga_goals, periods_from_openliga_results

API = "https://api.openligadb.de"


def _final_score(match: Dict[str, Any]) -> Dict[str, Any]:
    results = match.get("matchResults") or []
    end = None
    for row in results:
        name = str(row.get("resultName") or "").lower()
        if "end" in name or row.get("resultTypeId") == 2:
            end = row
    if end is None and results:
        end = results[-1]
    if not end:
        goals = match.get("goals") or []
        if goals:
            last = goals[-1]
            return {
                "home": last.get("scoreTeam1"),
                "away": last.get("scoreTeam2"),
            }
        return {"home": None, "away": None}
    return {"home": end.get("pointsTeam1"), "away": end.get("pointsTeam2")}


def _status(match: Dict[str, Any]) -> str:
    if match.get("matchIsFinished"):
        return "finished"
    goals = match.get("goals") or []
    results = match.get("matchResults") or []
    if goals:
        return "live"
    for row in results:
        if not isinstance(row, dict):
            continue
        name = str(row.get("resultName") or "").lower()
        kind = str(row.get("resultTypeKind") or "").lower()
        type_id = row.get("resultTypeId")
        if "end" in name or "endergebnis" in name or "after90" in kind or type_id == 2:
            return "finished"
        if "half" in name or "halbzeit" in name or kind == "halftime":
            return "break"
    return "scheduled"


def _team(node: Any) -> Dict[str, str]:
    if not isinstance(node, dict):
        return {"name": ""}
    return {
        "id": str(node.get("teamId") or ""),
        "name": node.get("teamName") or node.get("shortName") or "",
        "logo": node.get("teamIconUrl") or node.get("teamIconURL") or node.get("logo"),
    }


def _to_event(match: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    start = match.get("matchDateTimeUTC") or match.get("matchDateTime")
    if start and not str(start).endswith("Z") and "T" in str(start):
        start = f"{start}Z" if "+" not in str(start) else start
    shortcut = str(match.get("leagueShortcut") or spec.get("shortcut") or "")
    league_name = match.get("leagueName") or spec.get("name") or spec.get("competition_id")
    return {
        "id": f"openligadb:{match.get('matchID')}",
        "home": _team(match.get("team1")),
        "away": _team(match.get("team2")),
        "status": _status(match),
        "score": _final_score(match),
        "start_time": start,
        "venue": (match.get("location") or {}).get("locationStadium")
        if isinstance(match.get("location"), dict)
        else None,
        "competition": league_name,
        "source_competition_name": league_name,
        "source_competition_id": shortcut,
        "season": match.get("leagueSeason"),
        "round": (match.get("group") or {}).get("groupName")
        if isinstance(match.get("group"), dict)
        else None,
        "attendance": match.get("numberOfViewers"),
        "periods": periods_from_openliga_results(match),
        "incidents": incidents_from_openliga_goals(match),
        "source_event_id": str(match.get("matchID") or ""),
        "source_event_ids": {"openligadb": str(match.get("matchID") or "")},
        "source_family": "openligadb",
        "sport": spec.get("sport_id") or "football",
    }


def _standings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for index, row in enumerate(rows, start=1):
        out.append(
            {
                "position": index,
                "team": row.get("teamName"),
                "played": row.get("matches"),
                "wins": row.get("won"),
                "draws": row.get("draw"),
                "losses": row.get("lost"),
                "goal_difference": row.get("goalDiff"),
                "points": row.get("points"),
            }
        )
    return out


class OpenLigaDbAdapter:
    adapter_key = "openligadb"
    source_id = "openligadb"

    def __init__(self, source_id: str = "openligadb", getter=fetch_url):
        self.source_id = source_id
        self._get = getter

    def fetch(self, request: FetchRequest) -> FetchResult:
        shortcut = request.source_competition_id or ""
        spec = next((row for row in OPENLIGADB_LEAGUES if row["shortcut"] == shortcut), None)
        if spec is None:
            return FetchResult(ok=True, http_status=200, events=[])
        if request.capability == "standings":
            year = datetime.utcnow().year
            result = self._get(f"{API}/getbltable/{shortcut}/{year}")
            if not result.ok:
                return result
            rows = result.payload if isinstance(result.payload, list) else []
            return FetchResult(ok=True, http_status=result.http_status, payload=result.payload, standings=_standings(rows))
        result = self._get(f"{API}/getmatchdata/{shortcut}")
        if not result.ok:
            return result
        matches = result.payload if isinstance(result.payload, list) else []
        events = [_to_event(match, spec) for match in matches]
        if request.capability == "live_scores":
            events = [row for row in events if row["status"] == "live"]
        elif request.capability == "results":
            events = [row for row in events if row["status"] == "finished"]
        # fixtures/snapshot keep the full current-matchday payload (one HTTP).
        # Finished HT/FT/goals would otherwise never persist when the due job is fixtures.
        return FetchResult(ok=True, http_status=result.http_status, payload=result.payload, events=events)
