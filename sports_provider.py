"""Prepared contracts for a future live sports-data provider.

Phase 3 does not connect API-Sports or any paid provider. These shapes exist
so frontend Live Scores, Match, Standings, and Team pages can plug in later
without fake scores, fixtures, or standings.

Required later (not implemented now):
- Team entity table: slug, name, sport, league, logo_url, provider_id
- Match entity: provider_id, home/away teams, kickoff, status, score, league
- Standings snapshot: league, season, table rows
- Fixture/result events and lineups
"""

from typing import Any, Dict, List, Optional, TypedDict


PROVIDER_NOT_CONNECTED = (
    "Live sports data will appear when a sports-data provider is connected."
)


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
    id: str
    competition: str
    home: str
    away: str
    home_score: Optional[int]
    away_score: Optional[int]
    status: str
    kickoff: Optional[str]


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
        "matches": [],
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
        "events": [],
        "lineups": None,
        "statistics": None,
        "h2h": [],
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
