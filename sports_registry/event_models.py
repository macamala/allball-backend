"""Normalized domain contracts for event families.

These are shapes only. No fixtures, scores, fighters, runners, or esports
matches are created here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class TeamMatchEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    competition_id: Optional[str]
    event_family: str
    home: Dict[str, Any]
    away: Dict[str, Any]
    score: Dict[str, Any]
    status: str
    start_time: Optional[str]


class IndividualMatchEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    competition_id: Optional[str]
    event_family: str
    participant_a: Dict[str, Any]
    participant_b: Dict[str, Any]
    sets: Optional[List[Dict[str, Any]]]
    games: Optional[List[Dict[str, Any]]]
    score: Dict[str, Any]
    status: str
    start_time: Optional[str]


class CombatEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    competition_id: Optional[str]
    event_family: str
    fighter_a: Dict[str, Any]
    fighter_b: Dict[str, Any]
    bout: Optional[str]
    card_event: Optional[str]
    round: Optional[int]
    result: Optional[str]
    status: str
    start_time: Optional[str]


class MotorsportEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    series_id: Optional[str]
    season: Optional[str]
    event_family: str
    weekend: Optional[str]
    session: Optional[str]
    session_type: Optional[str]
    drivers: List[Dict[str, Any]]
    teams: List[Dict[str, Any]]
    classification: List[Dict[str, Any]]
    status: str
    start_time: Optional[str]


class RacingEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    event_family: str
    meeting_id: Optional[str]
    race_number: Optional[int]
    race_name: Optional[str]
    venue: Optional[str]
    country_id: Optional[str]
    distance: Optional[str]
    runners: List[Dict[str, Any]]
    result: Optional[List[Dict[str, Any]]]
    status: str
    start_time: Optional[str]


class TournamentEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    competition_id: Optional[str]
    event_family: str
    tournament: Optional[str]
    round: Optional[str]
    competitors: List[Dict[str, Any]]
    leaderboard: List[Dict[str, Any]]
    status: str
    start_time: Optional[str]


class EsportsMatchEvent(TypedDict, total=False):
    event_id: str
    sport_id: str
    game_id: Optional[str]
    competition_id: Optional[str]
    event_family: str
    home: Optional[Dict[str, Any]]
    away: Optional[Dict[str, Any]]
    teams: List[Dict[str, Any]]
    players: List[Dict[str, Any]]
    best_of: Optional[int]
    maps: List[Dict[str, Any]]
    score: Dict[str, Any]
    status: str
    start_time: Optional[str]
    esports_kind: Optional[str]


FAMILY_BY_EVENT_MODEL = {
    "team_match": "team_match",
    "individual_match": "individual_match",
    "combat": "combat",
    "motorsport_race": "motorsport_race",
    "racing": "racing",
    "tournament": "tournament",
    "esports_match": "esports_match",
}


def event_family_for_sport(sport_id: Optional[str]) -> Optional[str]:
    from .sports import get_sport

    row = get_sport(sport_id)
    if not row:
        return None
    return FAMILY_BY_EVENT_MODEL.get(row.get("event_model") or "")
