"""Provider-independent sports-data contracts.

No paid sports-data API is connected. Empty payloads are intentional: the
frontend must never receive fake fixtures, scores, or standings.

To plug in a real provider later:
1. Implement SportsDataProvider (see Protocol below).
2. Set env SPORTS_DATA_PROVIDER to that class path, or extend get_active_provider().
3. Map provider IDs onto internal event/participant IDs in NormalizedEvent.
4. Keep returning the same dict shapes — frontend never consumes raw vendor JSON.

Live Scores and Predictions both read NormalizedEvent objects from this layer.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Protocol, TypedDict


PROVIDER_NOT_CONNECTED = (
    "Live sports data will appear when a sports-data provider is connected."
)

PREDICTION_SPORTS = ("football", "basketball", "tennis")


class TeamStandingRow(TypedDict, total=False):
    position: int
    team: str
    team_slug: str
    played: Optional[int]
    wins: Optional[int]
    draws: Optional[int]
    losses: Optional[int]
    goal_difference: Optional[int]
    points: Optional[int]
    pct: Optional[float]
    conference: Optional[str]
    division: Optional[str]


class ScoreMatch(TypedDict, total=False):
    """Legacy live-scores row. Prefer NormalizedEvent for new code."""

    id: str
    competition: str
    home: str
    away: str
    home_score: Optional[int]
    away_score: Optional[int]
    status: str
    kickoff: Optional[str]


class Participant(TypedDict, total=False):
    id: str
    slug: str
    name: str
    side: str


class EventScore(TypedDict, total=False):
    home: Optional[int]
    away: Optional[int]
    period: Optional[str]
    minute: Optional[str]


class NormalizedEvent(TypedDict, total=False):
    """Shared match/event object for Live Scores and Predictions.

    Team-match events use home/away. Other families add their own fields and
    set event_family. Missing participants must stay empty — never invented.
    """

    id: str
    sport: str
    competition: str
    competition_key: str
    season: Optional[str]
    event_family: str
    home: Participant
    away: Participant
    participant_a: Participant
    participant_b: Participant
    start_time: Optional[str]
    status: str
    score: EventScore
    venue: Optional[str]
    provider: Optional[str]
    provider_id: Optional[str]
    updated_at: Optional[str]


class SportsDataProvider(Protocol):
    """Adapter boundary. A future vendor implements this; UI stays unchanged."""

    def status(self) -> Dict[str, Any]:
        ...

    def get_sports(self) -> List[Dict[str, Any]]:
        ...

    def get_competitions(self, sport: Optional[str] = None) -> List[Dict[str, Any]]:
        ...

    def get_events(
        self,
        sport: Optional[str] = None,
        competition: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[NormalizedEvent]:
        ...

    def get_live_events(self) -> List[NormalizedEvent]:
        ...

    def get_event(self, event_id: str) -> Optional[NormalizedEvent]:
        ...

    def get_standings(self, competition_key: Optional[str] = None) -> List[TeamStandingRow]:
        ...

    def get_team_form(self, team_id: str) -> Optional[Dict[str, Any]]:
        ...

    def get_statistics(self, event_id: str) -> Optional[Dict[str, Any]]:
        ...

    def get_availability(self, event_id: str) -> List[Dict[str, Any]]:
        ...


def provider_status() -> Dict[str, Any]:
    return {
        "connected": False,
        "provider": None,
        "message": PROVIDER_NOT_CONNECTED,
    }


def empty_scores_payload() -> Dict[str, Any]:
    return {
        **provider_status(),
        "live": [],
        "today": [],
        "tomorrow": [],
        "finished": [],
        "matches": [],
        "events": [],
    }


def empty_standings_payload(league: Optional[str] = None) -> Dict[str, Any]:
    return {
        **provider_status(),
        "league": league,
        "sport": None,
        "rows": [],
    }


def empty_match_payload(match_id: str) -> Dict[str, Any]:
    return {
        **provider_status(),
        "id": match_id,
        "header": None,
        "event": None,
        "events": [],
        "lineups": None,
        "statistics": None,
        "h2h": [],
        "form": None,
        "availability": [],
        "standings": None,
    }


def empty_team_payload(slug: str) -> Dict[str, Any]:
    return {
        "available": False,
        "slug": slug,
        "reason": (
            "Team pages need a team entity table (name, slug, sport, league, "
            "logo) plus provider fixtures/results/standings. Not in the "
            "database yet — public team routes are not advertised."
        ),
        "team": None,
        "recent_news": [],
        "fixtures": [],
        "results": [],
        "standings_position": None,
    }


def empty_events_payload(
    sport: Optional[str] = None,
    competition: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        **provider_status(),
        "sport": sport,
        "competition": competition,
        "status": status,
        "events": [],
        "matches": [],
    }


def empty_competitions_payload(sport: Optional[str] = None) -> Dict[str, Any]:
    return {
        **provider_status(),
        "sport": sport,
        "competitions": [],
        "source": "provider",
    }


class DisconnectedSportsDataProvider:
    """Default production provider: honest empty responses, no sample fixtures."""

    def status(self) -> Dict[str, Any]:
        return provider_status()

    def get_sports(self) -> List[Dict[str, Any]]:
        return []

    def get_competitions(self, sport: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    def get_events(
        self,
        sport: Optional[str] = None,
        competition: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[NormalizedEvent]:
        return []

    def get_live_events(self) -> List[NormalizedEvent]:
        return []

    def get_event(self, event_id: str) -> Optional[NormalizedEvent]:
        return None

    def get_standings(self, competition_key: Optional[str] = None) -> List[TeamStandingRow]:
        return []

    def get_team_form(self, team_id: str) -> Optional[Dict[str, Any]]:
        return None

    def get_statistics(self, event_id: str) -> Optional[Dict[str, Any]]:
        return None

    def get_availability(self, event_id: str) -> List[Dict[str, Any]]:
        return []


def get_active_provider() -> SportsDataProvider:
    """Factory for the live sports-data adapter.

    Plug-in point for a paid provider:
    1. Implement SportsDataProvider (map vendor IDs onto NormalizedEvent).
    2. Register that class here (SPORTS_DATA_PROVIDER env is reserved).
    3. Keep returning NormalizedEvent / empty helpers — never raw vendor JSON.

    Until an adapter is registered, production always returns honest empties.
    Providers that require public branding are never selected.
    """
    from sports_registry.router import get_sports_data_provider

    _configured = (os.getenv("SPORTS_DATA_PROVIDER") or "").strip()
    return get_sports_data_provider()


def normalize_legacy_match(row: Dict[str, Any]) -> NormalizedEvent:
    """Map the older ScoreMatch shape onto NormalizedEvent."""
    home_name = row.get("home") or row.get("home_team") or ""
    away_name = row.get("away") or row.get("away_team") or ""
    status = str(row.get("status") or "scheduled")
    return {
        "id": str(row.get("id") or ""),
        "sport": row.get("sport") or "",
        "competition": row.get("competition") or row.get("league") or "",
        "competition_key": row.get("competition_key") or row.get("league") or "",
        "season": row.get("season"),
        "home": {"name": home_name, "slug": row.get("home_slug") or "", "side": "home"},
        "away": {"name": away_name, "slug": row.get("away_slug") or "", "side": "away"},
        "start_time": row.get("start_time") or row.get("kickoff"),
        "status": status,
        "score": {
            "home": row.get("home_score"),
            "away": row.get("away_score"),
            "period": row.get("period"),
            "minute": row.get("minute"),
        },
        "venue": row.get("venue"),
        "provider": row.get("provider"),
        "provider_id": row.get("provider_id"),
        "updated_at": row.get("updated_at"),
        "event_family": row.get("event_family") or "",
        "participant_a": row.get("participant_a") or {},
        "participant_b": row.get("participant_b") or {},
    }


def partition_score_events(events: Iterable[NormalizedEvent]) -> Dict[str, List[Dict[str, Any]]]:
    """Split normalized events into Live Scores buckets without inventing rows."""
    from datetime import datetime, timezone, timedelta

    live: List[NormalizedEvent] = []
    today_rows: List[NormalizedEvent] = []
    tomorrow_rows: List[NormalizedEvent] = []
    finished: List[NormalizedEvent] = []
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    finished_status = {"finished", "ft", "final", "ended"}
    live_status = {"live", "inplay", "1h", "2h", "ht"}
    for event in events:
        status = str(event.get("status") or "").lower()
        if status in live_status:
            live.append(event)
        if status in finished_status:
            finished.append(event)
        start = event.get("start_time") or ""
        day = None
        if start:
            try:
                day = datetime.fromisoformat(str(start).replace("Z", "+00:00")).date()
            except ValueError:
                day = None
        if day == today:
            today_rows.append(event)
        elif day == tomorrow:
            tomorrow_rows.append(event)
    return {
        "live": events_to_legacy_matches(live),
        "today": events_to_legacy_matches(today_rows),
        "tomorrow": events_to_legacy_matches(tomorrow_rows),
        "finished": events_to_legacy_matches(finished),
    }


def events_to_legacy_matches(events: Iterable[NormalizedEvent]) -> List[Dict[str, Any]]:
    """Keep Live Scores consumers that still read home/away strings working."""
    rows = []
    for event in events:
        home = (event.get("home") or {}).get("name") or ""
        away = (event.get("away") or {}).get("name") or ""
        score = event.get("score") or {}
        status = event.get("status") or ""
        rows.append(
            {
                "id": event.get("id"),
                "sport": event.get("sport"),
                "competition": event.get("competition"),
                "league": event.get("competition_key") or event.get("competition"),
                "home": home,
                "away": away,
                "home_score": score.get("home"),
                "away_score": score.get("away"),
                "status": status,
                "kickoff": event.get("start_time"),
                "live": status == "live",
                "provider": event.get("provider"),
                "provider_id": event.get("provider_id"),
            }
        )
    return rows
